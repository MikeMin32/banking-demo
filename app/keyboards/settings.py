"""Settings, reminders, and login keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.database.repositories.settings import ReminderSettings
from app.keyboards.callbacks import AccCB, MenuCB, SetCB
from app.keyboards.common import _nav_row, confirm_action_kb


def settings_kb(settings: ReminderSettings) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if settings.enabled:
        builder.button(text="🔕 Disable Reminders", callback_data=SetCB(o="tog").pack())
    else:
        builder.button(text="🔔 Enable Reminders", callback_data=SetCB(o="tog").pack())
    builder.adjust(1)
    _nav_row(builder, back="menu")
    return builder.as_markup()


def reminders_kb(accounts: list[Account]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts[:20]:
        builder.button(text=f"🏦 {account.line_label}"[:64], callback_data=AccCB(o="view", i=account.id).pack())
        builder.button(text="✅ Check", callback_data=AccCB(o="chk", i=account.id).pack())
    builder.adjust(2)
    if accounts:
        builder.row(InlineKeyboardButton(text="✅ Mark all checked", callback_data=SetCB(o="macq").pack()))
    builder.row(InlineKeyboardButton(text="⚙️ Settings", callback_data=MenuCB(a="settings").pack()))
    _nav_row(builder, back="menu")
    return builder.as_markup()


def reminder_inline_kb(accounts: list[Account]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts[:15]:
        builder.button(text=f"🏦 {account.line_label}"[:32], callback_data=AccCB(o="view", i=account.id).pack())
        builder.button(text="✅", callback_data=AccCB(o="chk", i=account.id).pack())
    builder.adjust(2)
    if accounts:
        builder.row(InlineKeyboardButton(text="✅ Mark all checked", callback_data=SetCB(o="macq").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Open menu", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def mark_all_confirm_kb() -> InlineKeyboardMarkup:
    return confirm_action_kb(
        yes_data=SetCB(o="mac").pack(),
        no_data=MenuCB(a="menu").pack(),
        yes_text="✅ Yes, mark all checked",
        no_text="✖️ Cancel",
    )


DEPOSIT_FIELDS = [
    ("account_holder", "Account holder"),
    ("bank_name", "Bank name"),
    ("iban", "IBAN"),
    ("account_number", "Account number"),
    ("routing_number", "Routing number"),
    ("sort_code", "Sort code"),
    ("swift_bic", "SWIFT / BIC"),
    ("payment_reference", "Reference / instructions"),
    ("notes", "Notes"),
]


def deposit_kb(account_id: int) -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import DepCB

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit fields", callback_data=DepCB(o="edit", i=account_id).pack())
    builder.adjust(1)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


def deposit_fields_kb(account_id: int) -> InlineKeyboardMarkup:
    from app.keyboards.callbacks import DepCB

    builder = InlineKeyboardBuilder()
    for code, label in DEPOSIT_FIELDS:
        builder.button(text=label, callback_data=DepCB(o="fld", i=account_id, f=code).pack())
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="✅ Done", callback_data=DepCB(o="view", i=account_id).pack()))
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


def login_kb(account_id: int, *, can_reveal: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_reveal:
        builder.button(text="👁 Show Password", callback_data=AccCB(o="pw", i=account_id).pack())
    builder.button(text="✏️ Edit Login Details", callback_data=AccCB(o="led", i=account_id).pack())
    builder.adjust(1)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()
