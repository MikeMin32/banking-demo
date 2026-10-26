"""Balance updates, confirmation checks, and history."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.balances import BalanceHistoryEntry, BalanceRepository
from app.services.accounts import AccountError
from app.services.money import MoneyError, parse_to_minor
from app.utils.time import utc_now_iso


@dataclass(slots=True)
class BalanceUpdateResult:
    account: Account
    old_balance_minor: int
    new_balance_minor: int
    history: BalanceHistoryEntry


class BalanceService:
    def __init__(self, accounts: AccountRepository, history: BalanceRepository) -> None:
        self.accounts = accounts
        self.history = history

    async def _get(self, account_id: int) -> Account:
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        return account

    async def update_balance(self, account_id: int, raw_amount: str) -> BalanceUpdateResult:
        account = await self._get(account_id)
        try:
            new_minor = parse_to_minor(raw_amount, account.currency)
        except MoneyError as exc:
            raise AccountError(str(exc)) from exc
        old_minor = account.balance_minor
        now = utc_now_iso()
        entry = await self.history.add(
            account_id=account.id,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
            recorded_at=now,
        )
        updated = await self.accounts.set_balance(
            account.id,
            new_minor,
            last_updated_at=now,
            last_checked_at=now,
            updated_at=now,
        )
        if updated is None:
            raise AccountError("That account no longer exists.")
        return BalanceUpdateResult(
            account=updated,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
            history=entry,
        )

    async def confirm_checked(self, account_id: int) -> Account:
        account = await self._get(account_id)
        now = utc_now_iso()
        updated = await self.accounts.mark_checked(account.id, now)
        if updated is None:
            raise AccountError("That account no longer exists.")
        return updated

    async def confirm_all_checked(self) -> int:
        return await self.accounts.mark_all_checked(utc_now_iso(), archived=False)

    async def history_page(
        self, account_id: int, *, page: int, page_size: int
    ) -> tuple[Account, list[BalanceHistoryEntry], int]:
        account = await self._get(account_id)
        page = max(page, 0)
        total = await self.history.count_for_account(account.id)
        items = await self.history.list_for_account(
            account.id, offset=page * page_size, limit=page_size
        )
        return account, items, total
