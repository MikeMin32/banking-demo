"""Expected charges. Pending amounts reserve available balance; completion deducts recorded balance once."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.repositories.withdrawals import Withdrawal, WithdrawalRepository
from app.services.accounts import AccountError
from app.services.money import MoneyError, parse_to_minor
from app.utils.time import utc_now_iso

WITHDRAWAL_EDITABLE = frozenset({"amount_minor", "expected_date", "description"})
MAX_DESCRIPTION = 300


class WithdrawalError(ValueError):
    pass


@dataclass(slots=True)
class Projection:
    account: Account
    pending_minor: int
    recorded_minor: int
    available_minor: int

    @property
    def projected_minor(self) -> int:
        return self.available_minor

    @property
    def current_minor(self) -> int:
        return self.recorded_minor


@dataclass(slots=True)
class ActualChargeResult:
    withdrawal: Withdrawal
    account: Account
    old_balance_minor: int
    new_balance_minor: int
    deducted: bool


class WithdrawalService:
    def __init__(
        self,
        accounts: AccountRepository,
        withdrawals: WithdrawalRepository,
        history: BalanceRepository | None = None,
    ) -> None:
        self.accounts = accounts
        self.withdrawals = withdrawals
        self.history = history

    async def _account(self, account_id: int) -> Account:
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        return account

    async def create(
        self,
        account_id: int,
        raw_amount: str,
        *,
        expected_date: date | str | None = None,
        description: str | None = None,
    ) -> Withdrawal:
        account = await self._account(account_id)
        try:
            amount_minor = parse_to_minor(raw_amount, account.currency)
        except MoneyError as exc:
            raise WithdrawalError(str(exc)) from exc
        if amount_minor <= 0:
            raise WithdrawalError("Charge amount must be greater than zero.")
        date_value = expected_date.isoformat() if isinstance(expected_date, date) else expected_date
        desc = _clean_description(description)
        return await self.withdrawals.create(
            account_id=account.id,
            amount_minor=amount_minor,
            created_at=utc_now_iso(),
            expected_date=date_value,
            description=desc,
            origin="expected",
        )

    async def get(self, withdrawal_id: int) -> Withdrawal:
        withdrawal = await self.withdrawals.get(withdrawal_id)
        if withdrawal is None:
            raise WithdrawalError("That charge no longer exists.")
        return withdrawal

    async def page(
        self,
        *,
        status: str | None,
        account_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Withdrawal], int]:
        page = max(page, 0)
        total = await self.withdrawals.count(status=status, account_id=account_id)
        items = await self.withdrawals.list_withdrawals(
            status=status, account_id=account_id, offset=page * page_size, limit=page_size
        )
        return items, total

    async def projection(self, account_id: int) -> Projection:
        account = await self._account(account_id)
        pending = await self.withdrawals.pending_total_for_account(account.id)
        return Projection(
            account=account,
            pending_minor=pending,
            recorded_minor=account.balance_minor,
            available_minor=account.balance_minor - pending,
        )

    async def projections_by_account(self) -> dict[int, int]:
        return await self.withdrawals.pending_totals_by_account()

    async def complete(self, withdrawal_id: int) -> Withdrawal:
        """Complete a pending charge at its expected amount and deduct once."""
        result = await self.confirm_actual(withdrawal_id, deduct=True)
        return result.withdrawal

    async def confirm_actual(
        self,
        withdrawal_id: int,
        *,
        raw_actual: str | None = None,
        actual_minor: int | None = None,
        deduct: bool = True,
    ) -> ActualChargeResult:
        """Confirm an expected charge with an actual amount.

        When deduct=True, subtract the actual amount from recorded balance once.
        When deduct=False, mark applied without changing balance (already reflected
        in a manual bank-balance snapshot). Expected amount stays in amount_minor.
        """
        withdrawal = await self.get(withdrawal_id)
        account = await self._account(withdrawal.account_id)
        old_balance = account.balance_minor

        if withdrawal.status == "completed" and withdrawal.applied_to_balance:
            return ActualChargeResult(
                withdrawal=withdrawal,
                account=account,
                old_balance_minor=old_balance,
                new_balance_minor=old_balance,
                deducted=False,
            )
        if withdrawal.status == "cancelled":
            raise WithdrawalError("Cancelled charges cannot be confirmed.")
        if withdrawal.status == "completed" and not withdrawal.applied_to_balance:
            # Legacy completed rows stay untouched (no retroactive deduction).
            return ActualChargeResult(
                withdrawal=withdrawal,
                account=account,
                old_balance_minor=old_balance,
                new_balance_minor=old_balance,
                deducted=False,
            )

        resolved_actual = await self._resolve_actual_minor(
            account, withdrawal, raw_actual=raw_actual, actual_minor=actual_minor
        )
        now = utc_now_iso()
        claimed = await self.withdrawals.mark_completed_if_pending(withdrawal.id, now)
        if claimed == 0:
            refreshed = await self.get(withdrawal.id)
            account = await self._account(refreshed.account_id)
            return ActualChargeResult(
                withdrawal=refreshed,
                account=account,
                old_balance_minor=account.balance_minor,
                new_balance_minor=account.balance_minor,
                deducted=False,
            )

        await self.withdrawals.update_fields(
            withdrawal.id,
            {"actual_amount_minor": resolved_actual},
            now,
        )
        applied = await self.withdrawals.mark_applied_if_needed(withdrawal.id, now)
        new_balance = old_balance
        did_deduct = False
        if applied and deduct and resolved_actual > 0:
            new_balance = old_balance - resolved_actual
            if self.history is not None:
                await self.history.add(
                    account_id=account.id,
                    old_balance_minor=old_balance,
                    new_balance_minor=new_balance,
                    recorded_at=now,
                    source="charge",
                )
            updated_account = await self.accounts.set_balance(
                account.id,
                new_balance,
                last_updated_at=now,
                last_checked_at=account.last_checked_at or now,
                updated_at=now,
            )
            if updated_account is not None:
                account = updated_account
            did_deduct = True
        elif applied and not deduct:
            # Already reflected in bank balance — still mark applied so Out totals
            # include the actual amount without changing recorded balance again.
            pass

        refreshed = await self.get(withdrawal.id)
        account = await self._account(refreshed.account_id)
        return ActualChargeResult(
            withdrawal=refreshed,
            account=account,
            old_balance_minor=old_balance,
            new_balance_minor=account.balance_minor,
            deducted=did_deduct,
        )

    async def create_actual(
        self,
        account_id: int,
        raw_amount: str,
        *,
        deduct: bool = True,
    ) -> ActualChargeResult:
        """Standalone actual charge with no prior expected reservation."""
        account = await self._account(account_id)
        try:
            amount_minor = parse_to_minor(raw_amount, account.currency)
        except MoneyError as exc:
            raise WithdrawalError(str(exc)) from exc
        if amount_minor <= 0:
            raise WithdrawalError("Charge amount must be greater than zero.")

        now = utc_now_iso()
        old_balance = account.balance_minor
        withdrawal = await self.withdrawals.create(
            account_id=account.id,
            amount_minor=amount_minor,
            created_at=now,
            status="completed",
            completed_at=now,
            applied_to_balance=0,
            actual_amount_minor=amount_minor,
            origin="actual",
        )
        applied = await self.withdrawals.mark_applied_if_needed(withdrawal.id, now)
        new_balance = old_balance
        did_deduct = False
        if applied and deduct:
            new_balance = old_balance - amount_minor
            if self.history is not None:
                await self.history.add(
                    account_id=account.id,
                    old_balance_minor=old_balance,
                    new_balance_minor=new_balance,
                    recorded_at=now,
                    source="charge",
                )
            updated = await self.accounts.set_balance(
                account.id,
                new_balance,
                last_updated_at=now,
                last_checked_at=account.last_checked_at or now,
                updated_at=now,
            )
            if updated is not None:
                account = updated
            did_deduct = True
        refreshed = await self.get(withdrawal.id)
        account = await self._account(refreshed.account_id)
        return ActualChargeResult(
            withdrawal=refreshed,
            account=account,
            old_balance_minor=old_balance,
            new_balance_minor=account.balance_minor,
            deducted=did_deduct,
        )

    async def _resolve_actual_minor(
        self,
        account: Account,
        withdrawal: Withdrawal,
        *,
        raw_actual: str | None,
        actual_minor: int | None,
    ) -> int:
        if actual_minor is not None:
            if actual_minor < 0:
                raise WithdrawalError("Actual charge amount cannot be negative.")
            return actual_minor
        if raw_actual is None or not str(raw_actual).strip():
            return withdrawal.amount_minor
        try:
            value = parse_to_minor(raw_actual, account.currency)
        except MoneyError as exc:
            raise WithdrawalError(str(exc)) from exc
        if value < 0:
            raise WithdrawalError("Actual charge amount cannot be negative.")
        if value == 0:
            raise WithdrawalError("Actual charge amount must be greater than zero.")
        return value

    async def cancel(self, withdrawal_id: int) -> Withdrawal:
        withdrawal = await self.get(withdrawal_id)
        if withdrawal.status == "cancelled":
            return withdrawal
        if withdrawal.status != "pending":
            raise WithdrawalError("Only pending charges can be cancelled.")
        now = utc_now_iso()
        updated = await self.withdrawals.update_fields(
            withdrawal.id, {"status": "cancelled", "completed_at": now}, now
        )
        assert updated is not None
        return updated

    async def update(
        self,
        withdrawal_id: int,
        *,
        raw_amount: str | None = None,
        expected_date: date | str | None = ...,
        description: str | None = ...,
    ) -> Withdrawal:
        withdrawal = await self.get(withdrawal_id)
        if withdrawal.status != "pending" and raw_amount is not None:
            raise WithdrawalError("Only pending charges can be edited.")
        account = await self._account(withdrawal.account_id)
        fields: dict[str, object] = {}
        if raw_amount is not None:
            try:
                amount_minor = parse_to_minor(raw_amount, account.currency)
            except MoneyError as exc:
                raise WithdrawalError(str(exc)) from exc
            if amount_minor <= 0:
                raise WithdrawalError("Charge amount must be greater than zero.")
            fields["amount_minor"] = amount_minor
        if expected_date is not ...:
            if expected_date is None or expected_date == "":
                fields["expected_date"] = None
            elif isinstance(expected_date, date):
                fields["expected_date"] = expected_date.isoformat()
            else:
                fields["expected_date"] = str(expected_date)
        if description is not ...:
            fields["description"] = _clean_description(description)
        updated = await self.withdrawals.update_fields(withdrawal.id, fields, utc_now_iso())
        assert updated is not None
        return updated

    async def delete(self, withdrawal_id: int) -> None:
        withdrawal = await self.get(withdrawal_id)
        await self.withdrawals.delete(withdrawal.id)


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_DESCRIPTION:
        raise WithdrawalError(f"Description is too long (max {MAX_DESCRIPTION} characters).")
    return text
