"""Dashboard aggregates. Currencies are never mixed without exchange rates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.withdrawals import WithdrawalRepository
from app.services.money import format_amount
from app.utils.time import parse_iso


@dataclass(slots=True)
class CurrencyBucket:
    currency: str
    balance_minor: int = 0
    pending_minor: int = 0

    @property
    def projected_minor(self) -> int:
        return self.balance_minor - self.pending_minor


@dataclass(slots=True)
class DashboardSnapshot:
    active_count: int
    archived_count: int
    stale_count: int
    pending_withdrawal_count: int
    latest_update_name: str | None
    latest_update_at: str | None
    by_currency: dict[str, CurrencyBucket] = field(default_factory=dict)
    accounts: list[Account] = field(default_factory=list)
    pending_by_account: dict[int, int] = field(default_factory=dict)
    stale_ids: set[int] = field(default_factory=set)
    stale_hours: int = 24


def is_stale(account: Account, *, now: datetime, stale_hours: int) -> bool:
    checked = parse_iso(account.last_checked_at)
    if checked is None:
        return True
    return now - checked >= timedelta(hours=stale_hours)


class DashboardService:
    def __init__(self, accounts: AccountRepository, withdrawals: WithdrawalRepository) -> None:
        self.accounts = accounts
        self.withdrawals = withdrawals

    async def snapshot(self, *, stale_hours: int, now: datetime | None = None) -> DashboardSnapshot:
        moment = now or datetime.now(timezone.utc)
        active = await self.accounts.list_all(archived=False)
        archived_count = await self.accounts.count(archived=True)
        pending_by_account = await self.withdrawals.pending_totals_by_account()
        pending_count = await self.withdrawals.count(status="pending")
        latest = await self.accounts.latest_update()

        buckets: dict[str, CurrencyBucket] = {}
        stale_ids: set[int] = set()
        for account in active:
            bucket = buckets.setdefault(account.currency, CurrencyBucket(currency=account.currency))
            bucket.balance_minor += account.balance_minor
            pending = pending_by_account.get(account.id, 0)
            bucket.pending_minor += pending
            if is_stale(account, now=moment, stale_hours=stale_hours):
                stale_ids.add(account.id)

        return DashboardSnapshot(
            active_count=len(active),
            archived_count=archived_count,
            stale_count=len(stale_ids),
            pending_withdrawal_count=pending_count,
            latest_update_name=latest[0] if latest else None,
            latest_update_at=latest[1] if latest else None,
            by_currency=dict(sorted(buckets.items())),
            accounts=active,
            pending_by_account=pending_by_account,
            stale_ids=stale_ids,
            stale_hours=stale_hours,
        )


def format_currency_lines(buckets: dict[str, CurrencyBucket], field_name: str) -> str:
    if not buckets:
        return "—"
    lines = []
    for currency, bucket in buckets.items():
        minor = getattr(bucket, field_name)
        lines.append(f"• {format_amount(minor, currency)}")
    return "\n".join(lines)
