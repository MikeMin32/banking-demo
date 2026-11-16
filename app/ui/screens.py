"""Screen-level Widget HTML builders with real tabs/accordions/cards."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from zoneinfo import ZoneInfo

from app.database.repositories.accounts import Account
from app.services.dashboard import DashboardSnapshot
from app.services.ledger import LedgerEvent, LedgerPage
from app.services.money import format_amount
from app.services.totals import AccountTotals
from app.ui.components import (
    accordion,
    account_card_block,
    app_header,
    balance_card,
    date_header,
    document,
    e,
    empty_state,
    footer,
    kv_rows,
    notice_card,
    section_card,
    status_pill,
    tab_bar,
    tab_panel,
    tx_row,
)
from app.ui.theme import BRAND
from app.utils.time import format_dt, to_local
from app.utils.ui_preview import AccountDetailsSnapshot, snapshot_from_totals

SCREEN_TITLES = {
    "dashboard": "Home",
    "accounts": "Accounts",
    "account-details": "Account",
    "balance-summary": "Balance Summary",
    "add-account": "Add Account",
    "expected-charges": "Charges",
    "login-details": "Login Details",
    "settings": "Settings",
    "quick-add": "Quick Update",
    "transactions": "Transactions",
}


def _money(minor: int, currency: str) -> str:
    return format_amount(minor, currency, with_symbol=True)


def _currency_lines(snap: DashboardSnapshot, field: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for currency in ("USD", "EUR"):
        bucket = snap.by_currency.get(currency)
        if bucket is None:
            continue
        lines.append((currency, _money(getattr(bucket, field), currency)))
    for currency, bucket in snap.by_currency.items():
        if currency in {"USD", "EUR"}:
            continue
        lines.append((currency, _money(getattr(bucket, field), currency)))
    return lines


def dashboard_html(snap: DashboardSnapshot) -> str:
    balances = _currency_lines(snap, "available_minor") or [("—", "—")]
    charges = _currency_lines(snap, "pending_minor") or [("—", "—")]
    header = app_header(title="Banking", subtitle="Private account workspace")
    if len(balances) == 1 and balances[0][0] != "—":
        primary = balance_card(f"Active · {balances[0][0]}", balances[0][1])
        balance_section = ""
    else:
        primary = balance_card(
            "Active balances",
            "Multi-currency" if balances[0][0] != "—" else "—",
        )
        balance_section = section_card("Balances by currency", kv_rows(balances))
    overview = primary + balance_section + section_card("Active charges", kv_rows(charges))
    more = accordion(
        "Workspace notes",
        notice_card(
            f"{len(snap.accounts)} active account(s). Use Bank Accounts to open a line."
        ),
        open_=False,
    )
    body = (
        header
        + tab_bar([("home", "Overview"), ("more", "Notes")], active="home")
        + tab_panel("home", overview, active="home")
        + tab_panel("more", more, active="home")
        + footer(f"{len(snap.accounts)} active account(s)")
    )
    return document(body, with_tabs=True)


def accounts_overview_html(
    accounts: list[Account],
    totals_map: dict[int, AccountTotals],
    *,
    archived: bool,
) -> str:
    title = "📦 Archived accounts" if archived else "🏦 Bank accounts"
    header = app_header(title=title, subtitle="Tap an account below")
    if not accounts:
        msg = "No archived accounts." if archived else "No active accounts yet."
        return document(header + empty_state(msg))
    # Compact 2-line cards: name/provider, then Expected/Current/Projected inline.
    blocks = [header]
    for account in accounts:
        totals = totals_map[account.id]
        metrics = (
            f"⏳ {_money(totals.expected_minor, account.currency)}"
            f"&nbsp;&nbsp;💰 {_money(totals.current_minor, account.currency)}"
            f"&nbsp;&nbsp;📊 {_money(totals.projected_minor, account.currency)}"
        )
        arch = status_pill("Archived") if account.is_archived else ""
        blocks.append(
            f'<div class="acc"><div class="name">{e(account.line_label)} · '
            f"{e(account.banking_provider)}</div>{arch}"
            f'<div class="prov">{metrics}</div></div>'
        )
    return document("".join(blocks))


def account_details_html(snap: AccountDetailsSnapshot) -> str:
    """Approved Account Details experience: balance + internal tabs + accordion."""
    meta = "Archived" if snap.is_archived else None
    header = app_header(
        title=snap.line_name,
        subtitle=snap.subtitle,
        brand=BRAND,
        meta=meta,
    )
    primary = balance_card("💰 Current Balance", snap.money(snap.current_minor))
    overview = section_card(
        "📊 Overview",
        kv_rows(
            [
                ("📊 Projected", snap.money(snap.projected_minor)),
                ("⏳ Expected", snap.money(snap.expected_minor)),
            ]
        ),
    )
    activity = section_card(
        "Activity",
        kv_rows(
            [
                ("🟢 In", snap.money(snap.in_minor)),
                ("🔴 Out", snap.money(snap.out_minor)),
            ]
        ),
    )
    details_rows = kv_rows(
        [
            ("VM", snap.vm),
            ("Stored", snap.stored),
            ("IBAN", snap.iban),
            ("BIN", snap.bin),
            ("Updated", snap.updated_label),
        ]
    )
    details = accordion("ℹ️ Account Information", details_rows, open_=False)
    body = (
        header
        + primary
        + tab_bar(
            [("overview", "Overview"), ("activity", "Activity"), ("details", "Details")],
            active="overview",
        )
        + tab_panel("overview", overview, active="overview")
        + tab_panel("activity", activity, active="overview")
        + tab_panel("details", details, active="overview")
    )
    return document(body, with_tabs=True)


def account_details_from_totals(totals: AccountTotals, tz: ZoneInfo) -> str:
    return account_details_html(snapshot_from_totals(totals, tz))


def _event_body(event: LedgerEvent, currency: str) -> str:
    if event.kind == "deposit":
        amount = _money(event.amount_minor or 0, currency)
        text = f"🟢 +{escape(amount)}"
        return f'<span class="struck">{text}</span>' if event.struck else text
    if event.kind == "charge":
        amount = _money(event.amount_minor or 0, currency)
        return f'<span class="neg">🔴 -{escape(amount)}</span>'
    if event.kind == "expected":
        amount = _money(event.amount_minor or 0, currency)
        text = f"⏳ -{escape(amount)}"
        return (
            f'<span class="struck wait">{text}</span>'
            if event.struck
            else f'<span class="wait">{text}</span>'
        )
    if event.kind == "manual":
        old = _money(event.old_minor or 0, currency)
        new = _money(event.new_minor or 0, currency)
        return f"💰 {escape(old)} → {escape(new)}"
    return "•"


def transactions_html(page: LedgerPage, tz: ZoneInfo) -> str:
    account = page.account
    totals = page.totals
    currency = account.currency
    header = app_header(
        title=account.line_label,
        subtitle=f"{account.banking_provider} · {currency}",
        brand=BRAND,
    )
    summary = (
        balance_card("Current", _money(totals.current_minor, currency))
        + section_card(
            "Summary",
            kv_rows(
                [
                    ("Projected", _money(totals.projected_minor, currency)),
                    ("In", _money(totals.in_minor, currency)),
                    ("Out", _money(totals.out_minor, currency)),
                    ("Expected", _money(totals.expected_minor, currency)),
                ]
            ),
        )
    )
    if not page.events:
        ledger = empty_state("No transactions yet.")
    else:
        parts: list[str] = ['<div class="card"><div class="h">Ledger</div>']
        current_date: str | None = None
        for event in page.events:
            local = to_local(event.at, tz)
            if local is None:
                continue
            date_label = local.strftime("%d %b %Y")
            if date_label != current_date:
                current_date = date_label
                parts.append(date_header(date_label))
            parts.append(tx_row(time=local.strftime("%H:%M"), body_html=_event_body(event, currency)))
        parts.append("</div>")
        ledger = "".join(parts)

    body = (
        header
        + tab_bar([("summary", "Summary"), ("ledger", "Ledger")], active="ledger")
        + tab_panel("summary", summary, active="ledger")
        + tab_panel("ledger", ledger + footer(f"Page {page.page + 1} / {page.total_pages}"), active="ledger")
    )
    return document(body, with_tabs=True)


def balance_summary_html(snap: DashboardSnapshot, *, page_text: str | None = None) -> str:
    del page_text
    header = app_header(title="Balance Summary", subtitle="By account")
    if not snap.accounts:
        return document(header + empty_state("No active accounts yet."))
    cards: list[str] = []
    for account in snap.accounts:
        pending = snap.pending_by_account.get(account.id, 0)
        current = account.balance_minor
        projected = current - pending
        cards.append(
            account_card_block(
                name=account.line_label,
                provider=f"{account.banking_provider} · {account.currency}",
                expected=_money(pending, account.currency),
                current=_money(current, account.currency),
                projected=_money(projected, account.currency),
            )
        )
    accounts_panel = "".join(cards)
    totals_panel = (
        section_card("Totals · available", kv_rows(_currency_lines(snap, "available_minor") or [("—", "—")]))
        + section_card("Totals · charges", kv_rows(_currency_lines(snap, "pending_minor") or [("—", "—")]))
    )
    body = (
        header
        + tab_bar([("accounts", "Accounts"), ("totals", "Totals")], active="accounts")
        + tab_panel("accounts", accounts_panel, active="accounts")
        + tab_panel("totals", totals_panel, active="accounts")
    )
    return document(body, with_tabs=True)


def settings_html(*, reminders_enabled: bool, reminder_time: str) -> str:
    status = "Enabled" if reminders_enabled else "Disabled"
    general = section_card(
        "General",
        kv_rows([("Workspace", "Operation Greenline"), ("Theme", "Telegram native")]),
    )
    reminders = section_card(
        "Reminders",
        kv_rows([("Status", status), ("Time", reminder_time)]),
    )
    optional = accordion(
        "Advanced",
        notice_card("Only settings supported by this bot are shown. Owner backup uses /backup."),
        open_=False,
    )
    body = (
        app_header(title="Settings", subtitle="Workspace preferences")
        + tab_bar([("general", "General"), ("reminders", "Reminders")], active="reminders")
        + tab_panel("general", general + optional, active="reminders")
        + tab_panel("reminders", reminders, active="reminders")
    )
    return document(body, with_tabs=True)


def login_html(account: Account, *, can_reveal: bool) -> str:
    password = "••••••••" if account.has_password else "—"
    reveal = status_pill("Owner can reveal") if can_reveal and account.has_password else ""
    creds = section_card(
        "Credentials",
        kv_rows(
            [
                ("Mobile", account.login_mobile or "—"),
                ("Email", account.login_email or "—"),
                ("Password", password),
                ("2FA", account.two_fa_method or "—"),
            ]
        ),
    )
    more = accordion(
        "Security notes",
        notice_card("Credentials stay encrypted. Reveal only through the secure owner flow."),
        open_=False,
    )
    body = (
        app_header(
            title=account.line_label,
            subtitle=f"{account.banking_provider} · Login",
            brand=BRAND,
        )
        + creds
        + (f'<div class="meta">{reveal}</div>' if reveal else "")
        + more
    )
    return document(body)


def list_items_html(
    *,
    title: str,
    subtitle: str,
    items: Iterable[tuple[str, str, str | None]],
    empty_message: str,
) -> str:
    rows = list(items)
    header = app_header(title=title, subtitle=subtitle, brand=BRAND)
    if not rows:
        return document(header + empty_state(empty_message))
    cards: list[str] = [header]
    for name, value, status in rows:
        status_html = f'<div class="meta">{e(status)}</div>' if status else ""
        cards.append(
            f'<div class="acc"><div class="name">{e(name)}</div>'
            f'<div class="prov">{e(value)}</div>{status_html}</div>'
        )
    return document("".join(cards))


def detail_html(
    *,
    title: str,
    subtitle: str,
    pairs: list[tuple[str, str]],
    notice: str | None = None,
) -> str:
    body = (
        app_header(title=title, subtitle=subtitle, brand=BRAND)
        + section_card("Details", kv_rows(pairs))
        + (accordion("Notes", notice_card(escape(notice)), open_=False) if notice else "")
    )
    return document(body)


def prompt_html(
    *,
    screen: str,
    caption_html: str,
    title: str | None = None,
    subtitle: str | None = None,
) -> str:
    heading = title or SCREEN_TITLES.get(screen, "Operation Greenline")
    body = (
        app_header(title=heading, subtitle=subtitle or BRAND)
        + notice_card(caption_html)
        + accordion("Tip", notice_card("Reply with text below when prompted. Actions use the buttons under this card."), open_=False)
    )
    return document(body)


def short_updated(value: str | None, tz: ZoneInfo) -> str:
    if not value:
        return "—"
    local = to_local(value, tz)
    if local is None:
        return format_dt(value, tz)
    return local.strftime("%d %b %Y")
