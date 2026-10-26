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
from app.utils.time import format_date, format_dt

TELEGRAM_LIMIT = 4000


def e(value: object | None, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return escape(text)


def status_dot(stale: bool, archived: bool = False) -> str:
    if archived:
        return "📦"
    return "⚠️" if stale else "🟢"


def dashboard_text(snap: DashboardSnapshot, tz: ZoneInfo) -> str:
    latest = "No updates yet"
    if snap.latest_update_name and snap.latest_update_at:
        latest = f"{e(snap.latest_update_name)} · {format_dt(snap.latest_update_at, tz)}"

    totals = format_currency_lines(snap.by_currency, "balance_minor")
    pending = format_currency_lines(snap.by_currency, "pending_minor")
    projected = format_currency_lines(snap.by_currency, "projected_minor")
    if not snap.by_currency:
        totals = pending = projected = "No active accounts yet"

    return (
        "<b>🏦 Bank Manager</b>\n\n"
        f"📊 <b>Active accounts:</b> {snap.active_count}\n"
        f"⚠️ <b>Need a check:</b> {snap.stale_count}\n"
        f"📤 <b>Pending withdrawals:</b> {snap.pending_withdrawal_count}\n"
        f"🕒 <b>Latest update:</b> {latest}\n\n"
        f"<b>💰 Totals by currency</b>\n{totals}\n\n"
        f"<b>📤 Pending withdrawals</b>\n{pending}\n\n"
        f"<b>📈 Projected remaining</b>\n{projected}"
    )


def account_card(account: Account, tz: ZoneInfo, *, pending_minor: int, stale: bool) -> str:
    projected = account.balance_minor - pending_minor
    archived = "  ·  archived" if account.is_archived else ""
    incomplete = ""
    if account.vm_number is None or not account.company_name:
        incomplete = "\n⚠️ Add VM number and company name in Edit."
    notes = f"\n📝 {e(account.notes)}" if account.notes else ""
    return (
        f"{status_dot(stale, account.is_archived)} <b>🏦 {e(account.display_name)}</b>{archived}\n"
        f"Banking: {e(account.banking_provider)}\n"
        f"Currency: {e(account.currency)}{incomplete}\n\n"
        f"💰 Balance: <b>{format_amount(account.balance_minor, account.currency)}</b>\n"
        f"📤 Pending withdrawals: {format_amount(pending_minor, account.currency)}\n"
        f"📈 Projected remaining: <b>{format_amount(projected, account.currency)}</b>\n\n"
        f"🕒 Updated: {format_dt(account.last_updated_at, tz)}\n"
        f"✅ Checked: {format_dt(account.last_checked_at, tz)}"
        f"{notes}"
    )


def overview_pages(snap: DashboardSnapshot, tz: ZoneInfo, *, compact: bool = False) -> list[str]:
    if not snap.accounts:
        return ["No active accounts yet. Tap <b>Add Account</b> to create one."]

    header = (
        "<b>📋 All balances</b>\n"
        "<i>Currencies are listed separately. Projected remaining = "
        "balance − pending withdrawals.</i>\n"
    )
    chunks: list[str] = []
    current = header
    for account in snap.accounts:
        pending = snap.pending_by_account.get(account.id, 0)
        stale = account.id in snap.stale_ids
        projected = account.balance_minor - pending
        if compact:
            block = (
                f"\n{status_dot(stale)} <b>{e(account.display_name)}</b> · {e(account.banking_provider)}\n"
                f"{format_amount(account.balance_minor, account.currency)}"
                f"  →  {format_amount(projected, account.currency)}\n"
            )
        else:
            block = (
                f"\n{status_dot(stale)} <b>{e(account.display_name)}</b>\n"
                f"Banking: {e(account.banking_provider)}\n"
                f"💰 {format_amount(account.balance_minor, account.currency)}\n"
                f"📤 Pending: {format_amount(pending, account.currency)}\n"
                f"📈 Projected: {format_amount(projected, account.currency)}\n"
                f"✅ Checked: {format_dt(account.last_checked_at, tz)}\n"
            )
        if len(current) + len(block) > TELEGRAM_LIMIT:
            chunks.append(current)
            current = "<b>📋 All balances</b> (continued)\n" + block
        else:
            current += block

    totals = "\n<b>Totals by currency</b>\n"
    totals += format_currency_lines(snap.by_currency, "balance_minor")
    totals += "\n<b>Projected remaining</b>\n"
    totals += format_currency_lines(snap.by_currency, "projected_minor")
    if len(current) + len(totals) > TELEGRAM_LIMIT:
        chunks.append(current)
        chunks.append("<b>📋 Totals</b>\n" + totals)
    else:
        chunks.append(current + "\n" + totals)
    return chunks


def history_text(account: Account, entries: list[BalanceHistoryEntry], tz: ZoneInfo, page: int, total: int) -> str:
    if not entries:
        return f"<b>📜 Balance history — {e(account.display_name)}</b>\n\nNo updates recorded yet."
    lines = [f"<b>📜 Balance history — {e(account.display_name)}</b>\n"]
    for entry in entries:
        delta = difference_label(entry.old_balance_minor, entry.new_balance_minor, account.currency)
        lines.append(
            f"{format_dt(entry.recorded_at, tz, with_seconds=True)}\n"
            f"{format_amount(entry.old_balance_minor, account.currency)}"
            f"  →  {format_amount(entry.new_balance_minor, account.currency)}"
            f"  ({delta})\n"
        )
    page_size = 8
    lines.append(f"Page {page + 1} of {max((total + page_size - 1) // page_size, 1)}")
    return "\n".join(lines)


def withdrawal_card(withdrawal: Withdrawal, account: Account, tz: ZoneInfo) -> str:
    status_icon = {"pending": "⏳", "completed": "✅", "cancelled": "🚫"}.get(withdrawal.status, "•")
    desc = f"\n📝 {e(withdrawal.description)}" if withdrawal.description else ""
    completed = ""
    if withdrawal.completed_at:
        completed = f"\n✔️ Closed: {format_dt(withdrawal.completed_at, tz)}"
    return (
        f"{status_icon} <b>Expected withdrawal</b>\n"
        f"🏦 {e(account.display_name)} · {e(account.banking_provider)}\n"
        f"💸 {format_amount(withdrawal.amount_minor, account.currency)}\n"
        f"📅 Expected: {format_date(withdrawal.expected_date)}\n"
        f"📌 Status: {withdrawal.status}"
        f"{desc}\n"
        f"🕒 Created: {format_dt(withdrawal.created_at, tz)}"
        f"{completed}"
    )


def deposit_text(account: Account, details: DepositDetails | None) -> str:
    header = (
        f"<b>🏦 Deposit details — {e(account.display_name)}</b>\n"
        "<i>Copy from the code blocks below.</i>\n"
    )
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


def login_text(account: Account) -> str:
    url = f"<code>{escape(account.login_url)}</code>" if account.login_url else "—"
    user = f"<code>{escape(account.login_username)}</code>" if account.login_username else "—"
    vault = (
        f"<code>{escape(account.password_manager_ref)}</code>"
        if account.password_manager_ref
        else "—"
    )
    notes = e(account.notes)
    return (
        f"<b>🔐 Login references — {e(account.display_name)}</b>\n"
        "<i>This bot never stores bank passwords, OTP codes, or 2FA backups. "
        "Open your password manager to sign in.</i>\n\n"
        f"🔗 URL: {url}\n"
        f"👤 Username / email: {user}\n"
        f"🗝️ Password manager item: {vault}\n"
        f"📝 Notes: {notes}"
    )


def reminder_text(accounts: list[Account], tz: ZoneInfo, stale_hours: int) -> str:
    if not accounts:
        return (
            f"<b>⏰ Daily balance check</b>\n\n"
            f"All active accounts were checked within the last {stale_hours} hour(s). Nice work."
        )
    lines = [
        f"<b>⏰ Daily balance check</b>",
        f"{len(accounts)} account(s) have not been confirmed in the last {stale_hours} hour(s).",
        "",
    ]
    for account in accounts:
        lines.append(
            f"⚠️ <b>{e(account.display_name)}</b> · {e(account.banking_provider)}\n"
            f"{format_amount(account.balance_minor, account.currency)}"
            f"  ·  last check {format_dt(account.last_checked_at, tz)}"
        )
    return "\n".join(lines)


HELP_TEXT = (
    "<b>🏦 Bank Manager — Help</b>\n\n"
    "Accounts are named <code>VM {number} - {company}</code>, for example "
    "<code>VM 9 - LeBon Shoppe</code>.\n\n"
    "<b>Accounts</b> — add, edit, archive, or delete VM-linked accounts.\n"
    "<b>Balances</b> — update an amount, confirm a check, and browse history.\n"
    "<b>Expected withdrawals</b> — plan upcoming payouts. "
    "Projected remaining = balance − pending withdrawals.\n"
    "<b>Deposit details</b> — optional IBAN / account numbers for copy-paste. "
    "Not included in CSV exports.\n"
    "<b>Login references</b> — URL, username, and a password-manager link. "
    "Never send a bank password here.\n"
    "<b>Daily reminders</b> — stale-balance list at the configured time.\n"
    "<b>Exports</b> — CSV overviews without secrets or banking identifiers.\n\n"
    "Commands: /start /menu /help /cancel /backup"
)
