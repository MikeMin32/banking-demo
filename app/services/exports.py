"""CSV exports. Secrets, login URLs, vault refs, and banking identifiers are excluded."""

from __future__ import annotations

import csv
import io

from app.database.repositories.accounts import AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.repositories.withdrawals import WithdrawalRepository
from app.services.money import format_amount, from_minor


def _writer() -> tuple[io.StringIO, csv.writer]:
    buffer = io.StringIO()
    return buffer, csv.writer(buffer)


class ExportService:
    def __init__(
        self,
        accounts: AccountRepository,
        balances: BalanceRepository,
        withdrawals: WithdrawalRepository,
    ) -> None:
        self.accounts = accounts
        self.balances = balances
        self.withdrawals = withdrawals

    async def accounts_csv(self) -> bytes:
        items = await self.accounts.list_all(archived=None)
        pending = await self.withdrawals.pending_totals_by_account()
        buffer, writer = _writer()
        writer.writerow(
            [
                "id",
                "display_name",
                "vm_number",
                "company_name",
                "banking_provider",
                "currency",
                "balance",
                "pending_withdrawals",
                "projected_remaining",
                "last_updated_at_utc",
                "last_checked_at_utc",
                "archived",
                "created_at_utc",
            ]
        )
        for account in items:
            pending_minor = pending.get(account.id, 0)
            writer.writerow(
                [
                    account.id,
                    account.display_name,
                    account.vm_number if account.vm_number is not None else "",
                    account.company_name or "",
                    account.banking_provider,
                    account.currency,
                    format_amount(account.balance_minor, account.currency, with_code=False),
                    format_amount(pending_minor, account.currency, with_code=False),
                    format_amount(account.balance_minor - pending_minor, account.currency, with_code=False),
                    account.last_updated_at or "",
                    account.last_checked_at or "",
                    "yes" if account.is_archived else "no",
                    account.created_at,
                ]
            )
        return buffer.getvalue().encode("utf-8")

    async def balance_history_csv(self) -> bytes:
        accounts = {account.id: account for account in await self.accounts.list_all(archived=None)}
        entries = await self.balances.list_all()
        buffer, writer = _writer()
        writer.writerow(
            [
                "id",
                "account_id",
                "account_name",
                "currency",
                "old_balance",
                "new_balance",
                "difference",
                "recorded_at_utc",
            ]
        )
        for entry in entries:
            account = accounts.get(entry.account_id)
            currency = account.currency if account else "XXX"
            name = account.display_name if account else f"#{entry.account_id}"
            delta = from_minor(entry.new_balance_minor - entry.old_balance_minor, currency)
            writer.writerow(
                [
                    entry.id,
                    entry.account_id,
                    name,
                    currency,
                    format_amount(entry.old_balance_minor, currency, with_code=False),
                    format_amount(entry.new_balance_minor, currency, with_code=False),
                    f"{delta:f}",
                    entry.recorded_at,
                ]
            )
        return buffer.getvalue().encode("utf-8")

    async def withdrawals_csv(self) -> bytes:
        accounts = {account.id: account for account in await self.accounts.list_all(archived=None)}
        items = await self.withdrawals.list_all()
        buffer, writer = _writer()
        writer.writerow(
            [
                "id",
                "account_id",
                "account_name",
                "currency",
                "amount",
                "expected_date",
                "description",
                "status",
                "created_at_utc",
                "completed_at_utc",
            ]
        )
        for item in items:
            account = accounts.get(item.account_id)
            currency = account.currency if account else "XXX"
            name = account.display_name if account else f"#{item.account_id}"
            writer.writerow(
                [
                    item.id,
                    item.account_id,
                    name,
                    currency,
                    format_amount(item.amount_minor, currency, with_code=False),
                    item.expected_date or "",
                    item.description or "",
                    item.status,
                    item.created_at,
                    item.completed_at or "",
                ]
            )
        return buffer.getvalue().encode("utf-8")
