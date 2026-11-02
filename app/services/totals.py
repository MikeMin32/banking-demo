"""Per-account running totals: In / Out / Expected / Current / Projected."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.topups import TopUpRepository
from app.database.repositories.withdrawals import WithdrawalRepository
from app.services.accounts import AccountError


@dataclass(slots=True)
class AccountTotals:
    account: Account
    in_minor: int
    out_minor: int
    expected_minor: int
    current_minor: int
    projected_minor: int


class TotalsService:
    def __init__(
        self,
        accounts: AccountRepository,
        withdrawals: WithdrawalRepository,
        topups: TopUpRepository,
    ) -> None:
        self.accounts = accounts
        self.withdrawals = withdrawals
        self.topups = topups

    async def for_account(self, account_id: int) -> AccountTotals:
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        in_minor = await self.topups.in_total_for_account(account.id)
        out_minor = await self.withdrawals.out_total_for_account(account.id)
        expected_minor = await self.withdrawals.pending_total_for_account(account.id)
        current = account.balance_minor
        return AccountTotals(
            account=account,
            in_minor=in_minor,
            out_minor=out_minor,
            expected_minor=expected_minor,
            current_minor=current,
            projected_minor=current - expected_minor,
        )

    async def for_accounts(self, accounts: list[Account]) -> dict[int, AccountTotals]:
        in_by = await self.topups.in_totals_by_account()
        out_by = await self.withdrawals.out_totals_by_account()
        expected_by = await self.withdrawals.pending_totals_by_account()
        result: dict[int, AccountTotals] = {}
        for account in accounts:
            expected = expected_by.get(account.id, 0)
            current = account.balance_minor
            result[account.id] = AccountTotals(
                account=account,
                in_minor=in_by.get(account.id, 0),
                out_minor=out_by.get(account.id, 0),
                expected_minor=expected,
                current_minor=current,
                projected_minor=current - expected,
            )
        return result
