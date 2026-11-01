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
        withdrawal = await self.get(withdrawal_id)
        if withdrawal.status == "completed":
            return withdrawal
        if withdrawal.status != "pending":
            raise WithdrawalError("Only pending charges can be marked completed.")
        now = utc_now_iso()
        claimed = await self.withdrawals.mark_completed_if_pending(withdrawal.id, now)
        if claimed == 0:
            return await self.get(withdrawal_id)
        if not withdrawal.applied_to_balance:
            applied = await self.withdrawals.mark_applied_if_needed(withdrawal.id, now)
            if applied:
                account = await self._account(withdrawal.account_id)
                new_minor = account.balance_minor - withdrawal.amount_minor
                if self.history is not None:
                    await self.history.add(
                        account_id=account.id,
                        old_balance_minor=account.balance_minor,
                        new_balance_minor=new_minor,
                        recorded_at=now,
                    )
                await self.accounts.set_balance(
                    account.id,
                    new_minor,
                    last_updated_at=now,
                    last_checked_at=account.last_checked_at or now,
                    updated_at=now,
                )
        updated = await self.get(withdrawal_id)
        assert updated is not None
        return updated

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
