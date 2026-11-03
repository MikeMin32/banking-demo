"""Chronological financial ledger for an account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database.repositories.accounts import Account, AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.repositories.topups import TopUpRepository
from app.database.repositories.withdrawals import WithdrawalRepository
from app.services.accounts import AccountError
from app.services.money import format_amount
from app.services.totals import AccountTotals, TotalsService
from app.utils.time import parse_iso, to_local

LEDGER_PAGE_SIZE = 7


@dataclass(slots=True)
class LedgerEvent:
    kind: str  # deposit | charge | expected | manual
    at: datetime
    sort_id: int
    amount_minor: int | None = None
    old_minor: int | None = None
    new_minor: int | None = None
    struck: bool = False
    reversed: bool = False


@dataclass(slots=True)
class LedgerPage:
    account: Account
    totals: AccountTotals
    events: list[LedgerEvent]
    page: int
    total_pages: int
    total_events: int


class LedgerService:
    def __init__(
        self,
        accounts: AccountRepository,
        withdrawals: WithdrawalRepository,
        topups: TopUpRepository,
        history: BalanceRepository,
        totals: TotalsService,
    ) -> None:
        self.accounts = accounts
        self.withdrawals = withdrawals
        self.topups = topups
        self.history = history
        self.totals = totals

    async def page(
        self,
        account_id: int,
        *,
        page: int = 0,
        page_size: int = LEDGER_PAGE_SIZE,
        tz: ZoneInfo,
    ) -> LedgerPage:
        del tz  # Ordering uses UTC timestamps; display converts later.
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        events = await self._collect_events(account.id)
        events.sort(key=lambda e: (e.at, e.sort_id), reverse=True)
        total = len(events)
        page_size = max(page_size, 1)
        total_pages = max((total + page_size - 1) // page_size, 1)
        page = min(max(page, 0), total_pages - 1)
        start = page * page_size
        slice_ = events[start : start + page_size]
        totals = await self.totals.for_account(account.id)
        return LedgerPage(
            account=account,
            totals=totals,
            events=slice_,
            page=page,
            total_pages=total_pages,
            total_events=total,
        )

    async def _collect_events(self, account_id: int) -> list[LedgerEvent]:
        events: list[LedgerEvent] = []

        for top_up in await self.topups.list_all_for_account(account_id):
            at = parse_iso(top_up.created_at)
            if at is None:
                continue
            events.append(
                LedgerEvent(
                    kind="deposit",
                    at=at,
                    sort_id=top_up.id,
                    amount_minor=top_up.amount_minor,
                    struck=bool(top_up.is_reversed),
                    reversed=bool(top_up.is_reversed),
                )
            )

        for wd in await self.withdrawals.list_all_for_account(account_id):
            created = parse_iso(wd.created_at)
            if created is None:
                continue
            if wd.is_standalone_actual:
                # Standalone actual: show only the outgoing charge row.
                events.append(
                    LedgerEvent(
                        kind="charge",
                        at=parse_iso(wd.completed_at) or created,
                        sort_id=wd.id * 10 + 1,
                        amount_minor=wd.posted_minor,
                    )
                )
                continue

            # Expected creation always appears.
            events.append(
                LedgerEvent(
                    kind="expected",
                    at=created,
                    sort_id=wd.id * 10,
                    amount_minor=wd.amount_minor,
                    struck=wd.status != "pending",
                )
            )
            # Settled/applied actual appears separately (no double Out counting in totals).
            if wd.applied_to_balance and wd.status == "completed":
                completed = parse_iso(wd.completed_at) or created
                events.append(
                    LedgerEvent(
                        kind="charge",
                        at=completed,
                        sort_id=wd.id * 10 + 1,
                        amount_minor=wd.posted_minor,
                    )
                )

        for entry in await self.history.list_manual_for_account(account_id):
            at = parse_iso(entry.recorded_at)
            if at is None:
                continue
            events.append(
                LedgerEvent(
                    kind="manual",
                    at=at,
                    sort_id=entry.id,
                    old_minor=entry.old_balance_minor,
                    new_minor=entry.new_balance_minor,
                )
            )
        return events


def format_ledger_message(page: LedgerPage, tz: ZoneInfo) -> str:
    """Assemble the Transactions caption with explicit blank-line spacing.

    Spacing contract (blank lines = empty lines between content):
    1 blank after account identity
    0 between Current/Projected
    1 between balances and In/Out/Expected
    0 inside In/Out/Expected
    2 between Expected and first date heading
    1 between date groups
    0 between rows of the same date
    1 before Page X / Y
    """
    account = page.account
    totals = page.totals
    currency = account.currency
    header = (
        f"🏦 <b>{_esc(account.line_label.upper())} · {_esc(account.banking_provider.upper())}</b>\n"
        f"\n"
        f"💰 Current: {format_amount(totals.current_minor, currency, with_symbol=True)}\n"
        f"📊 Projected: {format_amount(totals.projected_minor, currency, with_symbol=True)}\n"
        f"\n"
        f"🟢 In: {format_amount(totals.in_minor, currency, with_symbol=True)}\n"
        f"🔴 Out: {format_amount(totals.out_minor, currency, with_symbol=True)}\n"
        f"⏳ Expected: {format_amount(totals.expected_minor, currency, with_symbol=True)}"
    )
    page_line = f"Page {page.page + 1} / {page.total_pages}"
    if not page.events:
        # Two blank lines after Expected, then empty-state, then one blank before page.
        return f"{header}\n\n\nNo transactions yet.\n\n{page_line}"

    date_groups: list[str] = []
    current_date: str | None = None
    rows: list[str] = []
    for event in page.events:
        local = to_local(event.at, tz)
        if local is None:
            continue
        date_label = local.strftime("%d %b %Y")
        if date_label != current_date:
            if current_date is not None and rows:
                date_groups.append("\n".join(rows))
            current_date = date_label
            rows = [f"<b>{date_label}</b>"]
        rows.append(_format_event_row(event, currency, local.strftime("%H:%M")))
    if rows:
        date_groups.append("\n".join(rows))

    # Two blank lines after Expected (\n\n\n), one blank between date groups (\n\n),
    # one blank before pagination (\n\n).
    body = "\n\n".join(date_groups)
    return f"{header}\n\n\n{body}\n\n{page_line}"


def _format_event_row(event: LedgerEvent, currency: str, hhmm: str) -> str:
    if event.kind == "deposit":
        amount = format_amount(event.amount_minor or 0, currency, with_symbol=True)
        body = f"🟢 +{amount}"
        if event.struck:
            body = f"🟢 <s>+{amount}</s>"
        return f"{hhmm}  {body}"
    if event.kind == "charge":
        amount = format_amount(event.amount_minor or 0, currency, with_symbol=True)
        return f"{hhmm}  🔴 -{amount}"
    if event.kind == "expected":
        amount = format_amount(event.amount_minor or 0, currency, with_symbol=True)
        signed = f"-{amount}"
        if event.struck:
            return f"{hhmm}  ⏳ <s>{signed}</s>"
        return f"{hhmm}  ⏳ {signed}"
    if event.kind == "manual":
        old = format_amount(event.old_minor or 0, currency, with_symbol=True)
        new = format_amount(event.new_minor or 0, currency, with_symbol=True)
        return f"{hhmm}  💰 {old} → {new}"
    return f"{hhmm}  •"


def _esc(value: str) -> str:
    from html import escape

    return escape(value)
