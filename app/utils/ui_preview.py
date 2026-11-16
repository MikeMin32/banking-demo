"""Account Details UI prototypes: Rich Message + HTML Widget (presentation only)."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from html import escape
from zoneinfo import ZoneInfo

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichTextBold,
)

from app.database.repositories.accounts import Account
from app.keyboards.callbacks import AccCB, MenuCB, TuCB, WdCB
from app.services.money import format_amount
from app.services.totals import AccountTotals
from app.utils.time import format_dt

BRAND = "OPERATION GREENLINE"
WIDGET_MAX_HTML = 32_768
WIDGET_MAX_COMPRESSED = 4_096


@dataclass(slots=True, frozen=True)
class AccountDetailsSnapshot:
    """Shared presentation model for both prototypes. No secrets."""

    account_id: int | None
    line_name: str
    provider: str
    currency: str
    current_minor: int
    projected_minor: int
    expected_minor: int
    in_minor: int
    out_minor: int
    vm: str
    stored: str
    iban: str
    bin: str
    updated_label: str
    is_archived: bool = False

    @property
    def subtitle(self) -> str:
        return f"{self.provider} · {self.currency}"

    def money(self, minor: int) -> str:
        return format_amount(minor, self.currency, with_symbol=True)


def sample_account_details(*, tz: ZoneInfo | None = None) -> AccountDetailsSnapshot:
    """Deterministic sample used when no test account exists."""
    del tz
    return AccountDetailsSnapshot(
        account_id=None,
        line_name="Automation Direct",
        provider="Airwallex",
        currency="USD",
        current_minor=500_000,
        projected_minor=300_000,
        expected_minor=200_000,
        in_minor=0,
        out_minor=0,
        vm="VM 4",
        stored="—",
        iban="—",
        bin="—",
        updated_label="16 Nov 2026",
    )


def snapshot_from_totals(totals: AccountTotals, tz: ZoneInfo) -> AccountDetailsSnapshot:
    account = totals.account
    return AccountDetailsSnapshot(
        account_id=account.id,
        line_name=account.line_label,
        provider=account.banking_provider,
        currency=account.currency,
        current_minor=totals.current_minor,
        projected_minor=totals.projected_minor,
        expected_minor=totals.expected_minor,
        in_minor=totals.in_minor,
        out_minor=totals.out_minor,
        vm=account.vm_label,
        stored=account.stored_label,
        iban=(account.iban or "").strip() or "—",
        bin=(account.bin or "").strip() or "—",
        updated_label=_short_updated(account.last_updated_at, tz),
        is_archived=account.is_archived,
    )


def _short_updated(value: str | None, tz: ZoneInfo) -> str:
    if not value:
        return "—"
    # Prefer day-month-year without clock for the compact prototype header.
    from app.utils.time import to_local

    local = to_local(value, tz)
    if local is None:
        return format_dt(value, tz)
    return local.strftime("%d %b %Y")


def _cell(text: str, *, align: str = "left", header: bool = False, bold: bool = False) -> RichBlockTableCell:
    content: str | RichTextBold = RichTextBold(text=text) if bold else text
    return RichBlockTableCell(
        align=align,
        valign="middle",
        text=content,
        is_header=header or None,
    )


def _kv_table(rows: list[tuple[str, str]], *, striped: bool = True, compact: bool = True) -> InputRichBlockTable:
    cells = [
        [_cell(label), _cell(value, align="right", bold=True)]
        for label, value in rows
    ]
    return InputRichBlockTable(cells=cells, is_striped=striped, is_compact=compact)


def build_rich_account_details(snap: AccountDetailsSnapshot) -> InputRichMessage:
    """Prototype A — approved Rich Message layout (shared with production screens)."""
    from app.ui.rich_screens import account_details_rich

    return account_details_rich(snap)


def build_widget_account_details(snap: AccountDetailsSnapshot) -> str:
    """Prototype B — shared Widget design-system Account Details layout."""
    from app.ui.screens import account_details_html

    return account_details_html(snap)


def widget_size_ok(html: str) -> tuple[bool, int, int]:
    raw = len(html.encode("utf-8"))
    compressed = len(zlib.compress(html.encode("utf-8"), 9))
    ok = raw <= WIDGET_MAX_HTML and compressed <= WIDGET_MAX_COMPRESSED
    return ok, raw, compressed


def preview_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="A · Rich Message",
                    callback_data="uip:a",
                    style="primary",
                )
            ],
            [
                InlineKeyboardButton(
                    text="B · HTML Widget",
                    callback_data="uip:b",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Both side-by-side",
                    callback_data="uip:both",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=MenuCB(a="menu").pack(),
                )
            ],
        ]
    )


def preview_actions_kb(account: Account | None) -> InlineKeyboardMarkup:
    """Reuse real account callbacks when possible; otherwise isolated preview stubs."""
    if account is not None:
        # Styled variant of the production 4×2 actions without changing account_view_kb.
        back_op = "alst" if account.is_archived else "list"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Update Balance",
                        callback_data=AccCB(o="bal", i=account.id).pack(),
                        style="primary",
                    ),
                    InlineKeyboardButton(
                        text="Transactions",
                        callback_data=AccCB(o="txn", i=account.id).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Add Charge",
                        callback_data=WdCB(o="add", a=account.id).pack(),
                        style="danger",
                    ),
                    InlineKeyboardButton(
                        text="Deposit",
                        callback_data=TuCB(o="add", a=account.id).pack(),
                        style="success",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Login Details",
                        callback_data=AccCB(o="log", i=account.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="Edit Account",
                        callback_data=AccCB(o="edt", i=account.id).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Back",
                        callback_data=AccCB(o=back_op, p=0).pack(),
                    ),
                    InlineKeyboardButton(
                        text="Home",
                        callback_data=MenuCB(a="menu").pack(),
                    ),
                ],
            ]
        )
    # Isolated preview controls — no financial mutations.
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Update Balance", callback_data="uip:noop", style="primary"),
                InlineKeyboardButton(text="Transactions", callback_data="uip:noop"),
            ],
            [
                InlineKeyboardButton(text="Add Charge", callback_data="uip:noop", style="danger"),
                InlineKeyboardButton(text="Deposit", callback_data="uip:noop", style="success"),
            ],
            [
                InlineKeyboardButton(text="Login Details", callback_data="uip:noop"),
                InlineKeyboardButton(text="Edit Account", callback_data="uip:noop"),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data="uip:menu"),
                InlineKeyboardButton(text="Home", callback_data=MenuCB(a="menu").pack()),
            ],
        ]
    )


def assert_no_secrets(payload: str) -> None:
    """Guardrail for tests: preview payloads must not leak credential material."""
    lowered = payload.lower()
    for needle in (
        "password",
        "login_password",
        "credentials",
        "2fa secret",
        "otp",
    ):
        if needle in lowered:
            raise AssertionError(f"preview payload must not contain {needle!r}")


def build_fallback_notice(kind: str, reason: str) -> str:
    """Honest HTML notice when a prototype API is unavailable — never pretend success."""
    safe_reason = escape(reason)[:200]
    return (
        f"<b>UI preview · {escape(kind)}</b>\n\n"
        f"Could not render the native prototype.\n"
        f"<i>{safe_reason}</i>\n\n"
        "Existing HTML Account Details screens are unchanged."
    )

