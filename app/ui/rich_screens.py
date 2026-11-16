"""Rich Message screen builders — approved /ui_preview prototype A style."""

from __future__ import annotations

from collections.abc import Iterable
from zoneinfo import ZoneInfo

from aiogram.types import InputRichBlockDivider, InputRichMessage

from app.database.repositories.accounts import Account
from app.services.dashboard import DashboardSnapshot
from app.services.ledger import LedgerEvent, LedgerPage
from app.services.money import format_amount
from app.services.totals import AccountTotals
from app.ui.rich_blocks import (
    brand_header,
    details,
    divider,
    heading,
    kv_table,
    paragraph,
    rich_message,
)
from app.ui.theme import BRAND
from app.utils.time import to_local
from app.utils.ui_preview import AccountDetailsSnapshot, snapshot_from_totals


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


def account_details_rich(snap: AccountDetailsSnapshot) -> InputRichMessage:
    """Exact approved Account Details Rich Message layout from /ui_preview A."""
    blocks = brand_header(snap.line_name, snap.subtitle, archived=snap.is_archived)
    blocks.extend(
        [
            heading("Current Balance", 5),
            heading(snap.money(snap.current_minor), 1),
            divider(),
            heading("Secondary", 5),
            kv_table(
                [
                    ("Projected", snap.money(snap.projected_minor)),
                    ("Expected", snap.money(snap.expected_minor)),
                ]
            ),
            divider(),
            heading("Activity", 5),
            kv_table(
                [
                    ("In", snap.money(snap.in_minor)),
                    ("Out", snap.money(snap.out_minor)),
                ]
            ),
            details(
                "Account Information",
                [
                    ("VM", snap.vm),
                    ("Stored", snap.stored),
                    ("IBAN", snap.iban),
                    ("BIN", snap.bin),
                    ("Updated", snap.updated_label),
                ],
                open_=False,
            ),
        ]
    )
    return rich_message(blocks)


def account_details_rich_from_totals(totals: AccountTotals, tz: ZoneInfo) -> InputRichMessage:
    return account_details_rich(snapshot_from_totals(totals, tz))


def dashboard_rich(snap: DashboardSnapshot) -> InputRichMessage:
    balances = _currency_lines(snap, "available_minor") or [("—", "—")]
    charges = _currency_lines(snap, "pending_minor") or [("—", "—")]
    blocks = brand_header("Banking", "Private account workspace")
    if len(balances) == 1 and balances[0][0] != "—":
        blocks.extend(
            [
                heading(f"Active · {balances[0][0]}", 5),
                heading(balances[0][1], 1),
                divider(),
            ]
        )
    else:
        blocks.extend(
            [
                heading("Active Balances", 5),
                kv_table(balances),
                divider(),
            ]
        )
    blocks.extend(
        [
            heading("Active Charges", 5),
            kv_table(charges),
            details(
                "Workspace",
                [("Active accounts", str(len(snap.accounts)))],
                open_=False,
            ),
        ]
    )
    return rich_message(blocks)


def accounts_overview_rich(
    accounts: list[Account],
    totals_map: dict[int, AccountTotals],
    *,
    archived: bool,
) -> InputRichMessage:
    title = "Archived accounts" if archived else "Bank accounts"
    blocks = brand_header(title, "Tap an account below")
    if not accounts:
        msg = "No archived accounts." if archived else "No active accounts yet."
        blocks.append(paragraph(msg))
        return rich_message(blocks)
    for account in accounts:
        totals = totals_map[account.id]
        blocks.append(heading(account.line_label, 4))
        blocks.append(paragraph(f"{account.banking_provider} · {account.currency}"))
        blocks.append(
            kv_table(
                [
                    ("Expected", _money(totals.expected_minor, account.currency)),
                    ("Current", _money(totals.current_minor, account.currency)),
                    ("Projected", _money(totals.projected_minor, account.currency)),
                ]
            )
        )
        blocks.append(divider())
    while blocks and isinstance(blocks[-1], InputRichBlockDivider):
        blocks.pop()
    return rich_message(blocks)


def balance_summary_rich(snap: DashboardSnapshot) -> InputRichMessage:
    blocks = brand_header("Balance Summary", "By account")
    if not snap.accounts:
        blocks.append(paragraph("No active accounts yet."))
        return rich_message(blocks)
    for account in snap.accounts:
        pending = snap.pending_by_account.get(account.id, 0)
        current = account.balance_minor
        projected = current - pending
        blocks.append(heading(account.line_label, 4))
        blocks.append(paragraph(f"{account.banking_provider} · {account.currency}"))
        blocks.append(
            kv_table(
                [
                    ("Expected", _money(pending, account.currency)),
                    ("Current", _money(current, account.currency)),
                    ("Projected", _money(projected, account.currency)),
                ]
            )
        )
        blocks.append(divider())
    blocks.append(heading("Totals · available", 5))
    blocks.append(kv_table(_currency_lines(snap, "available_minor") or [("—", "—")]))
    blocks.append(heading("Totals · charges", 5))
    blocks.append(kv_table(_currency_lines(snap, "pending_minor") or [("—", "—")]))
    return rich_message(blocks)


def _event_line(event: LedgerEvent, currency: str, hhmm: str) -> str:
    if event.kind == "deposit":
        amount = _money(event.amount_minor or 0, currency)
        body = f"🟢 +{amount}"
        if event.struck:
            body = f"🟢 +{amount} (reversed)"
        return f"{hhmm}  {body}"
    if event.kind == "charge":
        amount = _money(event.amount_minor or 0, currency)
        return f"{hhmm}  🔴 -{amount}"
    if event.kind == "expected":
        amount = _money(event.amount_minor or 0, currency)
        if event.struck:
            return f"{hhmm}  ⏳ -{amount} (resolved)"
        return f"{hhmm}  ⏳ -{amount}"
    if event.kind == "manual":
        old = _money(event.old_minor or 0, currency)
        new = _money(event.new_minor or 0, currency)
        return f"{hhmm}  💰 {old} → {new}"
    return f"{hhmm}  •"


def transactions_rich(page: LedgerPage, tz: ZoneInfo) -> InputRichMessage:
    account = page.account
    totals = page.totals
    currency = account.currency
    blocks = brand_header(account.line_label, f"{account.banking_provider} · {currency}")
    blocks.extend(
        [
            heading("Current", 5),
            heading(_money(totals.current_minor, currency), 1),
            divider(),
            heading("Summary", 5),
            kv_table(
                [
                    ("Projected", _money(totals.projected_minor, currency)),
                    ("In", _money(totals.in_minor, currency)),
                    ("Out", _money(totals.out_minor, currency)),
                    ("Expected", _money(totals.expected_minor, currency)),
                ]
            ),
            divider(),
            heading("Ledger", 5),
        ]
    )
    if not page.events:
        blocks.append(paragraph("No transactions yet."))
    else:
        current_date: str | None = None
        for event in page.events:
            local = to_local(event.at, tz)
            if local is None:
                continue
            date_label = local.strftime("%d %b %Y")
            if date_label != current_date:
                current_date = date_label
                blocks.append(heading(date_label, 6))
            blocks.append(paragraph(_event_line(event, currency, local.strftime("%H:%M"))))
    blocks.append(paragraph(f"Page {page.page + 1} / {page.total_pages}"))
    return rich_message(blocks)


def settings_rich(*, reminders_enabled: bool, reminder_time: str) -> InputRichMessage:
    status = "Enabled" if reminders_enabled else "Disabled"
    blocks = brand_header("Settings", "Workspace preferences")
    blocks.extend(
        [
            heading("Reminders", 5),
            kv_table([("Status", status), ("Time", reminder_time)]),
            details(
                "Advanced",
                [("Note", "Only settings supported by this bot are shown.")],
                open_=False,
            ),
        ]
    )
    return rich_message(blocks)


def login_rich(account: Account, *, can_reveal: bool) -> InputRichMessage:
    password = "••••••••" if account.has_password else "—"
    blocks = brand_header(account.line_label, f"{account.banking_provider} · Login")
    blocks.extend(
        [
            heading("Credentials", 5),
            kv_table(
                [
                    ("Mobile", account.login_mobile or "—"),
                    ("Email", account.login_email or "—"),
                    ("Password", password),
                    ("2FA", account.two_fa_method or "—"),
                ]
            ),
            details(
                "Security notes",
                [
                    (
                        "Reveal",
                        "Owner can reveal" if can_reveal and account.has_password else "Masked",
                    ),
                    ("Storage", "Encrypted at rest"),
                ],
                open_=False,
            ),
        ]
    )
    return rich_message(blocks)


def list_items_rich(
    *,
    title: str,
    subtitle: str,
    items: Iterable[tuple[str, str, str | None]],
    empty_message: str,
) -> InputRichMessage:
    rows = list(items)
    blocks = brand_header(title, subtitle)
    if not rows:
        blocks.append(paragraph(empty_message))
        return rich_message(blocks)
    for name, value, status in rows:
        blocks.append(heading(name, 5))
        blocks.append(paragraph(value if not status else f"{value} · {status}"))
    return rich_message(blocks)


def detail_rich(
    *,
    title: str,
    subtitle: str,
    pairs: list[tuple[str, str]],
    notice: str | None = None,
) -> InputRichMessage:
    blocks = brand_header(title, subtitle)
    blocks.append(heading("Details", 5))
    blocks.append(kv_table(pairs))
    if notice:
        blocks.append(details("Notes", [("Info", notice)], open_=False))
    return rich_message(blocks)


def prompt_rich(
    *,
    screen: str,
    title: str,
    body_lines: list[str],
) -> InputRichMessage:
    del screen
    blocks = brand_header(title, BRAND)
    for line in body_lines:
        text = line.strip()
        if not text:
            blocks.append(divider())
        else:
            # Strip simple Telegram HTML tags for rich plain text when present.
            plain = (
                text.replace("<b>", "")
                .replace("</b>", "")
                .replace("<i>", "")
                .replace("</i>", "")
                .replace("<code>", "")
                .replace("</code>", "")
                .replace("&amp;", "&")
            )
            blocks.append(paragraph(plain))
    blocks.append(
        details(
            "Tip",
            [("Input", "Reply with text when prompted. Actions use the buttons below.")],
            open_=False,
        )
    )
    return rich_message(blocks)


# Keep build_rich_account_details as the canonical export used by /ui_preview.
def build_rich_account_details(snap: AccountDetailsSnapshot) -> InputRichMessage:
    return account_details_rich(snap)
