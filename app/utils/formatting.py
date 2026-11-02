"""Telegram HTML message builders. User-supplied text is always escaped."""

from __future__ import annotations

from html import escape
from zoneinfo import ZoneInfo

from app.database.repositories.accounts import Account
from app.database.repositories.balances import BalanceHistoryEntry
from app.database.repositories.deposits import DepositDetails
from app.database.repositories.withdrawals import Withdrawal
from app.services.dashboard import DashboardSnapshot, format_currency_lines
from app.services.money import difference_label, format_amount
from app.utils.time import format_dt

TELEGRAM_LIMIT = 4000


def e(value: object | None, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return escape(text)


def _money(minor: int, currency: str) -> str:
    return format_amount(minor, currency, with_symbol=True)


def _currency_block(snap: DashboardSnapshot, field: str) -> str:
    if not snap.by_currency:
        return "—"
    lines = []
    for currency in ("USD", "EUR"):
        bucket = snap.by_currency.get(currency)
        if bucket is None:
            continue
        lines.append(f"{currency}: {_money(getattr(bucket, field), currency)}")
    for currency, bucket in snap.by_currency.items():
        if currency in {"USD", "EUR"}:
            continue
        lines.append(f"{currency}: {_money(getattr(bucket, field), currency)}")
    return "\n".join(lines) if lines else "—"


def dashboard_text(snap: DashboardSnapshot, tz: ZoneInfo) -> str:
    del tz
    return (
        "<b>💰 Active Balances</b>\n"
        f"{_currency_block(snap, 'available_minor')}\n\n"
        "<b>⏳ Active Charges</b>\n"
        f"{_currency_block(snap, 'pending_minor')}"
    )


def account_card(
    account: Account,
    tz: ZoneInfo,
    *,
    pending_minor: int,
    stale: bool = False,
    totals=None,
) -> str:
    del stale
    from app.utils.account_context import account_identity_line, totals_block

    if totals is not None:
        money = totals_block(totals)
    else:
        current = account.balance_minor
        projected = current - pending_minor
        money = (
            f"⏳ Expected: {_money(pending_minor, account.currency)}\n\n"
            f"💰 Current Balance: <b>{_money(current, account.currency)}</b>\n"
            f"📊 Projected Balance: <b>{_money(projected, account.currency)}</b>"
        )
    archived_line = "📦 Archived\n" if account.is_archived else ""
    body = (
        f"{archived_line}"
        f"{money}\n\n"
        f"VM: {e(account.vm_label)}\n"
        f"Stored: {e(account.stored_label)}\n"
        f"IBAN: <code>{e(account.iban)}</code>\n"
        f"BIN: <code>{e(account.bin)}</code>\n"
        f"Updated: {format_dt(account.last_updated_at, tz)}"
    )
    return f"{account_identity_line(account)}\n\n{body}"


def accounts_page_summary(blocks: list[str]) -> str:
    if not blocks:
        return "Select an account:"
    return "\n\n".join(blocks) + "\n\nSelect an account:"


def overview_pages(snap: DashboardSnapshot, tz: ZoneInfo, *, compact: bool = False) -> list[str]:
    del compact, tz
    if not snap.accounts:
        return ["No active accounts yet. Tap <b>Add Account</b> to create one."]

    chunks: list[str] = []
    current = ""
    for account in snap.accounts:
        pending = snap.pending_by_account.get(account.id, 0)
        available = account.balance_minor - pending
        block = (
            f"<b>{e(account.line_label)}</b> · {e(account.banking_provider)}\n"
            f"💰 {_money(available, account.currency)}"
            f"  ·  ⏳ {_money(pending, account.currency)}\n\n"
        )
        if len(current) + len(block) > TELEGRAM_LIMIT:
            chunks.append(current.rstrip())
            current = block
        else:
            current += block

    totals = (
        "<b>Totals</b>\n"
        f"💰 {_currency_block(snap, 'available_minor')}\n"
        f"⏳ {_currency_block(snap, 'pending_minor')}"
    )
    if len(current) + len(totals) + 1 > TELEGRAM_LIMIT:
        chunks.append(current.rstrip())
        chunks.append(totals)
    else:
        chunks.append((current + totals).rstrip())
    return chunks


def history_text(account: Account, entries: list[BalanceHistoryEntry], tz: ZoneInfo, page: int, total: int) -> str:
    if not entries:
        return "No balance updates yet."
    lines: list[str] = []
    for entry in entries:
        delta = difference_label(entry.old_balance_minor, entry.new_balance_minor, account.currency)
        lines.append(
            f"{format_dt(entry.recorded_at, tz, with_seconds=True)}\n"
            f"{_money(entry.old_balance_minor, account.currency)}"
            f" → {_money(entry.new_balance_minor, account.currency)}"
            f" ({delta})"
        )
    page_size = 8
    lines.append(f"{page + 1}/{max((total + page_size - 1) // page_size, 1)}")
    return "\n\n".join(lines)


def withdrawal_section(withdrawal: Withdrawal, account: Account, tz: ZoneInfo) -> str:
    status_icon = {"pending": "⏳", "completed": "✅", "cancelled": "🚫"}.get(withdrawal.status, "•")
    completed = ""
    if withdrawal.completed_at:
        completed = f"\nClosed: {format_dt(withdrawal.completed_at, tz)}"
    applied = ""
    if withdrawal.status == "completed" and not withdrawal.applied_to_balance:
        applied = "\n<i>Legacy — bank balance unchanged.</i>"
    actual = ""
    if (
        withdrawal.status == "completed"
        and withdrawal.actual_amount_minor is not None
        and withdrawal.actual_amount_minor != withdrawal.amount_minor
    ):
        actual = (
            f"\nExpected: {_money(withdrawal.amount_minor, account.currency)}"
            f"\nActual: {_money(withdrawal.actual_amount_minor, account.currency)}"
        )
        amount_line = f"{status_icon} {_money(withdrawal.actual_amount_minor, account.currency)} · {withdrawal.status}"
    else:
        amount_line = f"{status_icon} {_money(withdrawal.amount_minor, account.currency)} · {withdrawal.status}"
    return (
        f"{amount_line}"
        f"{actual}\n"
        f"Added: {format_dt(withdrawal.created_at, tz)}"
        f"{completed}{applied}"
    )


def withdrawal_card(withdrawal: Withdrawal, account: Account, tz: ZoneInfo) -> str:
    return withdrawal_section(withdrawal, account, tz)


def deposit_text(account: Account, details: DepositDetails | None) -> str:
    header = f"<b>🏦 Deposit details — {e(account.line_label)}</b>\n"
    if details is None or details.is_empty():
        return header + "\nNo deposit details saved yet."

    def row(label: str, value: str | None) -> str:
        if not value:
            return ""
        return f"\n<b>{label}</b>\n<code>{escape(value)}</code>\n"

    body = "".join(
        [
            row("Account holder", details.account_holder),
            row("Bank name", details.bank_name),
            row("IBAN", details.iban),
            row("Account number", details.account_number),
            row("Routing number", details.routing_number),
            row("Sort code", details.sort_code),
            row("SWIFT / BIC", details.swift_bic),
            row("Reference / instructions", details.payment_reference),
            row("Notes", details.notes),
        ]
    )
    return header + body


def login_section(account: Account) -> str:
    password = "••••••••" if account.has_password else "—"
    return (
        f"Mobile: <code>{e(account.login_mobile)}</code>\n"
        f"Email: <code>{e(account.login_email)}</code>\n"
        f"Password: {password}\n"
        f"2FA: {e(account.two_fa_method)}"
    )


def login_text(account: Account) -> str:
    return login_section(account)


def topup_section(top_up, account: Account, tz: ZoneInfo) -> str:
    status = "Reversed" if getattr(top_up, "is_reversed", False) else "Applied"
    return (
        f"+{_money(top_up.amount_minor, account.currency)} · {status}\n"
        f"Added: {format_dt(top_up.created_at, tz)}"
    )


def topups_list_section(*, empty: bool, page: int, total: int, page_size: int = 6) -> str:
    if empty and page == 0:
        return "No top-ups yet."
    pages = max((total + page_size - 1) // page_size, 1)
    return f"Select a top-up · {page + 1}/{pages}"


def reminder_text(accounts: list[Account], tz: ZoneInfo, stale_hours: int) -> str:
    if not accounts:
        return (
            f"<b>⏰ Daily balance check</b>\n\n"
            f"All active accounts were checked within the last {stale_hours} hour(s)."
        )
    lines = [
        "<b>⏰ Daily balance check</b>",
        f"{len(accounts)} account(s) have not been confirmed in the last {stale_hours} hour(s).",
        "",
    ]
    for account in accounts:
        lines.append(
            f"⚠️ <b>{e(account.line_label)}</b> · {e(account.banking_provider)}\n"
            f"{_money(account.balance_minor, account.currency)}"
            f"  ·  last check {format_dt(account.last_checked_at, tz)}"
        )
    return "\n".join(lines)


def mask_password(value: str | None) -> str:
    if not value:
        return "—"
    return "••••••••"


HELP_TEXT = (
    "<b>🏦 Bank Manager</b>\n\n"
    "Track bank balances, top-ups, and expected charges by line.\n"
    "Available balance = bank balance − pending charges.\n"
    "Top-ups increase the recorded bank balance immediately.\n\n"
    "Commands: /start /menu /help /cancel"
)
