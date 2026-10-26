"""Account list, detail, and edit keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.keyboards.callbacks import AccCB, AccFieldCB, DepCB, MenuCB, WdCB
from app.keyboards.common import PAGE_SIZE, _nav_row, pagination_row


def accounts_list_kb(
    accounts: list[Account],
    *,
    page: int,
    total: int,
    archived: bool,
    stale_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    stale_ids = stale_ids or set()
    builder = InlineKeyboardBuilder()
    for account in accounts:
        icon = "📦" if archived else ("⚠️" if account.id in stale_ids else "🟢")
        label = f"{icon} {account.display_name} · {account.currency}"[:64]
        builder.button(text=label, callback_data=AccCB(o="view", i=account.id, p=page).pack())
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
            InlineKeyboardButton(text="➕ Add account", callback_data=MenuCB(a="add").pack()),
            InlineKeyboardButton(text="📦 Archived", callback_data=AccCB(o="alst").pack()),
        )
    _nav_row(builder, back="menu")
    return builder.as_markup()


def account_view_kb(account: Account, *, from_page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Update Balance", callback_data=AccCB(o="bal", i=account.id).pack())
    builder.button(text="✅ Confirm Checked", callback_data=AccCB(o="chk", i=account.id).pack())
    builder.button(text="📜 History", callback_data=AccCB(o="his", i=account.id).pack())
    builder.button(text="📤 Withdrawals", callback_data=WdCB(o="alist", a=account.id, s="pending").pack())
    builder.button(text="🏦 Deposit Details", callback_data=DepCB(o="view", i=account.id).pack())
    builder.button(text="🔐 Login Info", callback_data=AccCB(o="log", i=account.id).pack())
    builder.button(text="✏️ Edit", callback_data=AccCB(o="edt", i=account.id).pack())
    if account.is_archived:
        builder.button(text="♻️ Unarchive", callback_data=AccCB(o="uar", i=account.id).pack())
    else:
        builder.button(text="📦 Archive", callback_data=AccCB(o="arq", i=account.id).pack())
    builder.button(text="🗑️ Delete", callback_data=AccCB(o="dlq", i=account.id).pack())
    builder.adjust(2, 2, 2, 2, 1)
    back_op = "alst" if account.is_archived else "list"
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o=back_op, p=from_page).pack()),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


EDIT_FIELDS = [
    ("vm_number", "VM number"),
    ("company_name", "Company name"),
    ("bank_name", "Banking provider"),
    ("currency", "Change Currency"),
    ("login_url", "Login URL"),
    ("login_username", "Login username"),
    ("password_manager_ref", "Password manager item"),
    ("notes", "Notes"),
]


def account_edit_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in EDIT_FIELDS:
        builder.button(text=label, callback_data=AccFieldCB(i=account_id, f=code).pack())
    builder.adjust(2)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


def currency_kb(*, account_id: int | None = None) -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import PickCB

    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇸 USD", callback_data=PickCB(k="cur", v="USD").pack())
    builder.button(text="🇪🇺 EUR", callback_data=PickCB(k="cur", v="EUR").pack())
    builder.adjust(2)
    if account_id is not None:
        builder.row(
            InlineKeyboardButton(text="✖️ Cancel", callback_data=AccCB(o="edt", i=account_id).pack()),
        )
    else:
        builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def provider_kb() -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import PickCB

    builder = InlineKeyboardBuilder()
    builder.button(text="Airwallex", callback_data=PickCB(k="prv", v="Airwallex").pack())
    builder.button(text="N26", callback_data=PickCB(k="prv", v="N26").pack())
    builder.button(text="Other", callback_data=PickCB(k="prv", v="OTHER").pack())
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=MenuCB(a="menu").pack()))
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
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()
