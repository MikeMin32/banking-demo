"""Account list, detail, and edit keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.keyboards.callbacks import AccCB, AccFieldCB, MenuCB, TuCB, WdCB
from app.keyboards.common import PAGE_SIZE, _nav_row, pagination_row
from app.services.money import format_amount


def _short(text: str, max_len: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[: max(max_len - 1, 1)].rstrip() + "…"


def account_button_label(account: Account, available_minor: int) -> str:
    amount = format_amount(available_minor, account.currency, with_symbol=True)
    # Keep line · provider · stored readable within Telegram's 64-char button limit.
    budget = 64 - len(amount) - 3
    line = _short(account.line_label, max(8, budget // 3))
    provider = _short(account.banking_provider, max(6, budget // 3))
    stored = _short(account.stored_label, max(4, budget - len(line) - len(provider) - 6))
    prefix = f"{line} · {provider} · {stored}"
    label = f"{prefix} | {amount}"
    if len(label) <= 64:
        return label
    return f"{prefix[: max(budget, 8)].rstrip()} | {amount}"[:64]


def accounts_list_kb(
    accounts: list[Account],
    *,
    page: int,
    total: int,
    archived: bool,
    available_by_account: dict[int, int] | None = None,
) -> InlineKeyboardMarkup:
    available_by_account = available_by_account or {}
    builder = InlineKeyboardBuilder()
    for account in accounts:
        pending_available = available_by_account.get(account.id, account.balance_minor)
        icon = "📦 " if archived else ""
        builder.button(
            text=f"{icon}{account_button_label(account, pending_available)}"[:64],
            callback_data=AccCB(o="view", i=account.id, p=page).pack(),
        )
    builder.adjust(1)
    list_op = "alst" if archived else "list"
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: AccCB(o=list_op, p=p).pack(),
    )
    if archived:
        builder.row(InlineKeyboardButton(text="🏦 Active accounts", callback_data=AccCB(o="list").pack()))
    else:
        builder.row(
            InlineKeyboardButton(text="➕ Add Account", callback_data=MenuCB(a="add").pack()),
            InlineKeyboardButton(text="📦 Archived", callback_data=AccCB(o="alst").pack()),
        )
    _nav_row(builder, back="menu")
    return builder.as_markup()


def account_view_kb(account: Account, *, from_page: int = 0) -> InlineKeyboardMarkup:
    # Exact 4×2 layout for mobile. Short "Balance" label avoids iOS truncation.
    back_op = "alst" if account.is_archived else "list"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💵 Balance", callback_data=AccCB(o="bal", i=account.id).pack()),
        InlineKeyboardButton(text="📋 Transactions", callback_data=AccCB(o="txn", i=account.id).pack()),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Add Charge", callback_data=WdCB(o="add", a=account.id).pack()),
        InlineKeyboardButton(text="💰 Deposit", callback_data=TuCB(o="add", a=account.id).pack()),
    )
    builder.row(
        InlineKeyboardButton(text="🔐 Login Details", callback_data=AccCB(o="log", i=account.id).pack()),
        InlineKeyboardButton(text="✏️ Edit Account", callback_data=AccCB(o="edt", i=account.id).pack()),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o=back_op, p=from_page).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def transactions_hub_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Expected Charges", callback_data=WdCB(o="alist", a=account_id, s="pending").pack())
    builder.button(text="💰 Top Ups", callback_data=TuCB(o="list", a=account_id).pack())
    builder.adjust(2)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


EDIT_FIELDS = [
    ("bank_name", "Bank provider"),
    ("iban", "IBAN"),
    ("bin", "BIN"),
    ("currency", "Currency"),
    ("line_name", "Line"),
    ("linked_vm", "VM"),
    ("stored_where", "Stored where"),
    ("login_mobile", "Mobile"),
    ("login_email", "Email"),
    ("login_password", "Password"),
    ("two_fa_method", "2FA method"),
]


def account_edit_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in EDIT_FIELDS:
        builder.button(text=label, callback_data=AccFieldCB(i=account_id, f=code).pack())
    builder.adjust(2)
    builder.button(text="📜 Balance history", callback_data=AccCB(o="his", i=account_id).pack())
    builder.button(text="📦 Archive / restore", callback_data=AccCB(o="arq", i=account_id).pack())
    builder.button(text="🗑️ Delete account", callback_data=AccCB(o="dlq", i=account_id).pack())
    builder.adjust(2, 2, 1, 1, 1)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


def currency_kb(*, account_id: int | None = None) -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import PickCB

    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇸 USD", callback_data=PickCB(k="cur", v="USD").pack())
    builder.button(text="🇪🇺 EUR", callback_data=PickCB(k="cur", v="EUR").pack())
    builder.adjust(2)
    if account_id is not None:
        builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=AccCB(o="edt", i=account_id).pack()))
    else:
        builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def provider_kb(*, account_id: int | None = None) -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import PickCB

    builder = InlineKeyboardBuilder()
    builder.button(text="Airwallex", callback_data=PickCB(k="prv", v="Airwallex").pack())
    builder.button(text="N26", callback_data=PickCB(k="prv", v="N26").pack())
    builder.button(text="Other", callback_data=PickCB(k="prv", v="OTHER").pack())
    builder.adjust(1)
    cancel = AccCB(o="edt", i=account_id).pack() if account_id is not None else MenuCB(a="menu").pack()
    builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=cancel))
    return builder.as_markup()


def history_kb(account_id: int, *, page: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=page_size,
        factory=lambda p: AccCB(o="his", i=account_id, p=p).pack(),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="edt", i=account_id).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def create_confirm_kb() -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import FormCB

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Save Account", callback_data=FormCB(o="ok").pack())
    builder.button(text="✏️ Edit Information", callback_data=FormCB(o="edit").pack())
    builder.button(text="❌ Cancel", callback_data=FormCB(o="cancel").pack())
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def create_fields_kb() -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import FormCB

    builder = InlineKeyboardBuilder()
    for code, label in EDIT_FIELDS:
        builder.button(text=label, callback_data=AccFieldCB(i=0, f=code).pack())
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data=FormCB(o="review").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def login_edit_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in (
        ("login_mobile", "Mobile"),
        ("login_email", "Email"),
        ("login_password", "Password"),
        ("two_fa_method", "2FA method"),
    ):
        builder.button(text=label, callback_data=AccFieldCB(i=account_id, f=code).pack())
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="log", i=account_id).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def overview_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=AccCB(o="ovw", p=page - 1).pack()))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="➡️ Next", callback_data=AccCB(o="ovw", p=page + 1).pack()))
    if buttons:
        builder.row(*buttons)
    _nav_row(builder, back="menu")
    return builder.as_markup()
