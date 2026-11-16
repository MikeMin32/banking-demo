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
    """Prototype A — native Rich Message blocks (headings, tables, details)."""
    brand = BRAND
    if snap.is_archived:
        brand = f"{BRAND} · Archived"

    blocks = [
        InputRichBlockSectionHeading(text=brand, size=3),
        InputRichBlockParagraph(text=RichTextBold(text=snap.line_name)),
        InputRichBlockParagraph(text=snap.subtitle),
        InputRichBlockDivider(),
        InputRichBlockSectionHeading(text="Current Balance", size=5),
        InputRichBlockSectionHeading(text=snap.money(snap.current_minor), size=1),
        InputRichBlockDivider(),
        InputRichBlockSectionHeading(text="Secondary", size=5),
        _kv_table(
            [
                ("Projected", snap.money(snap.projected_minor)),
                ("Expected", snap.money(snap.expected_minor)),
            ]
        ),
        InputRichBlockDivider(),
        InputRichBlockSectionHeading(text="Activity", size=5),
        _kv_table(
            [
                ("In", snap.money(snap.in_minor)),
                ("Out", snap.money(snap.out_minor)),
            ]
        ),
        InputRichBlockDetails(
            summary="Account Information",
            is_open=True,
            blocks=[
                _kv_table(
                    [
                        ("VM", snap.vm),
                        ("Stored", snap.stored),
                        ("IBAN", snap.iban),
                        ("BIN", snap.bin),
                        ("Updated", snap.updated_label),
                    ],
                    compact=True,
                )
            ],
        ),
    ]
    return InputRichMessage(blocks=blocks)


def build_widget_account_details(snap: AccountDetailsSnapshot) -> str:
    """Prototype B — sandboxed HTML widget with theme CSS variables."""
    brand = escape(BRAND)
    line = escape(snap.line_name)
    subtitle = escape(snap.subtitle)
    current = escape(snap.money(snap.current_minor))
    projected = escape(snap.money(snap.projected_minor))
    expected = escape(snap.money(snap.expected_minor))
    inn = escape(snap.money(snap.in_minor))
    out = escape(snap.money(snap.out_minor))
    vm = escape(snap.vm)
    stored = escape(snap.stored)
    iban = escape(snap.iban)
    bin_v = escape(snap.bin)
    updated = escape(snap.updated_label)
    archived = (
        '<div class="meta">Archived</div>' if snap.is_archived else ""
    )

    # Compact inline CSS; no external assets; theme vars for light/dark.
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;font:14px/1.35 system-ui,sans-serif;
color:var(--tg-theme-text-color,#e7e7e7);
background:var(--tg-theme-bg-color,#1c1c1e)}}
.wrap{{padding:12px 12px max(12px,var(--tg-content-safe-area-inset-bottom,0));
max-width:430px;min-width:280px}}
.brand{{font-size:11px;letter-spacing:.08em;font-weight:700;
color:var(--tg-theme-accent-text-color,#3dd68c);text-transform:uppercase}}
.title{{margin:4px 0 0;font-size:17px;font-weight:700}}
.sub{{margin:2px 0 0;font-size:12px;color:var(--tg-theme-hint-color,#8e8e93)}}
.meta{{margin-top:4px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}}
.card{{margin-top:10px;padding:10px 12px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}}
.lbl{{font-size:11px;color:var(--tg-theme-hint-color,#8e8e93);text-transform:uppercase;
letter-spacing:.04em}}
.bal{{margin-top:2px;font-size:28px;font-weight:750;letter-spacing:-.02em;
color:var(--tg-theme-text-color,#fff)}}
.sec{{margin-top:8px}}
.row{{display:flex;justify-content:space-between;gap:10px;padding:7px 10px;
border-radius:6px}}
.row:nth-child(odd){{background:color-mix(in srgb,var(--tg-theme-section-separator-color,#3a3a3c) 28%,transparent)}}
.k{{color:var(--tg-theme-hint-color,#8e8e93);font-size:12px}}
.v{{font-weight:650;font-size:13px;text-align:right;word-break:break-word}}
.h{{margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;color:var(--tg-theme-subtitle-text-color,#aeaeb2)}}
.accent{{width:28px;height:2px;margin:8px 0 0;border-radius:2px;
background:var(--tg-theme-accent-text-color,#3dd68c)}}
</style></head><body><div class="wrap">
<div class="brand">{brand}</div>
<div class="title">{line}</div>
<div class="sub">{subtitle}</div>
{archived}
<div class="accent"></div>
<div class="card">
<div class="lbl">Current Balance</div>
<div class="bal">{current}</div>
</div>
<div class="card sec">
<div class="h">Secondary</div>
<div class="row"><span class="k">Projected</span><span class="v">{projected}</span></div>
<div class="row"><span class="k">Expected</span><span class="v">{expected}</span></div>
</div>
<div class="card sec">
<div class="h">Activity</div>
<div class="row"><span class="k">In</span><span class="v">{inn}</span></div>
<div class="row"><span class="k">Out</span><span class="v">{out}</span></div>
</div>
<div class="card sec">
<div class="h">Account Information</div>
<div class="row"><span class="k">VM</span><span class="v">{vm}</span></div>
<div class="row"><span class="k">Stored</span><span class="v">{stored}</span></div>
<div class="row"><span class="k">IBAN</span><span class="v">{iban}</span></div>
<div class="row"><span class="k">BIN</span><span class="v">{bin_v}</span></div>
<div class="row"><span class="k">Updated</span><span class="v">{updated}</span></div>
</div>
</div></body></html>"""
    return html


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

