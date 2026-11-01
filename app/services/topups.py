"""Top-ups: incoming funds applied immediately to recorded bank balance."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.repositories.topups import TopUp, TopUpRepository
from app.services.accounts import AccountError
from app.services.money import MoneyError, parse_to_minor
from app.utils.time import utc_now_iso


class TopUpError(ValueError):
    pass


@dataclass(slots=True)
class TopUpResult:
    top_up: TopUp
    account: Account
    old_balance_minor: int
    new_balance_minor: int


class TopUpService:
    def __init__(
        self,
        accounts: AccountRepository,
        topups: TopUpRepository,
        history: BalanceRepository,
    ) -> None:
        self.accounts = accounts
        self.topups = topups
        self.history = history

    async def _account(self, account_id: int) -> Account:
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        return account

    async def create(self, account_id: int, raw_amount: str) -> TopUpResult:
        account = await self._account(account_id)
        try:
            amount_minor = parse_to_minor(raw_amount, account.currency)
        except MoneyError as exc:
            raise TopUpError(str(exc)) from exc
        if amount_minor <= 0:
            raise TopUpError("Top-up amount must be greater than zero.")

        now = utc_now_iso()
        top_up = await self.topups.create(
            account_id=account.id,
            amount_minor=amount_minor,
            currency=account.currency,
            created_at=now,
        )
        return await self._apply(top_up)

    async def _apply(self, top_up: TopUp) -> TopUpResult:
        claimed = await self.topups.mark_applied_if_needed(top_up.id, top_up.created_at)
        account = await self._account(top_up.account_id)
        if claimed == 0:
            # Already applied — return current state without double-credit.
            refreshed = await self.topups.get(top_up.id)
            assert refreshed is not None
            return TopUpResult(
                top_up=refreshed,
                account=account,
                old_balance_minor=account.balance_minor,
                new_balance_minor=account.balance_minor,
            )

        old_minor = account.balance_minor
        new_minor = old_minor + top_up.amount_minor
        now = top_up.created_at
        await self.history.add(
            account_id=account.id,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
            recorded_at=now,
        )
        updated = await self.accounts.set_balance(
            account.id,
            new_minor,
            last_updated_at=now,
            last_checked_at=account.last_checked_at or now,
            updated_at=now,
        )
        if updated is None:
            raise AccountError("That account no longer exists.")
        refreshed = await self.topups.get(top_up.id)
        assert refreshed is not None
        return TopUpResult(
            top_up=refreshed,
            account=updated,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
        )

    async def get(self, top_up_id: int) -> TopUp:
        top_up = await self.topups.get(top_up_id)
        if top_up is None:
            raise TopUpError("That top-up no longer exists.")
        return top_up

    async def page(
        self, account_id: int, *, page: int, page_size: int
    ) -> tuple[Account, list[TopUp], int]:
        account = await self._account(account_id)
        page = max(page, 0)
        total = await self.topups.count_for_account(account.id)
        items = await self.topups.list_for_account(
            account.id, offset=page * page_size, limit=page_size
        )
        return account, items, total

    async def reverse(self, top_up_id: int) -> TopUpResult:
        """Explicit auditable reversal. Deducts exactly once if previously applied."""
        top_up = await self.get(top_up_id)
        if top_up.is_reversed:
            account = await self._account(top_up.account_id)
            return TopUpResult(
                top_up=top_up,
                account=account,
                old_balance_minor=account.balance_minor,
                new_balance_minor=account.balance_minor,
            )
        if not top_up.applied_to_balance:
            raise TopUpError("This top-up was never applied to the balance.")

        now = utc_now_iso()
        claimed = await self.topups.mark_reversed_if_applied(top_up.id, now)
        account = await self._account(top_up.account_id)
        if claimed == 0:
            refreshed = await self.get(top_up.id)
            return TopUpResult(
                top_up=refreshed,
                account=account,
                old_balance_minor=account.balance_minor,
                new_balance_minor=account.balance_minor,
            )

        old_minor = account.balance_minor
        new_minor = old_minor - top_up.amount_minor
        await self.history.add(
            account_id=account.id,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
            recorded_at=now,
        )
        updated = await self.accounts.set_balance(
            account.id,
            new_minor,
            last_updated_at=now,
            last_checked_at=account.last_checked_at or now,
            updated_at=now,
        )
        if updated is None:
            raise AccountError("That account no longer exists.")
        refreshed = await self.get(top_up.id)
        return TopUpResult(
            top_up=refreshed,
            account=updated,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
        )
