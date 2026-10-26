"""Settings, reminders, deposit, and export keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.database.repositories.settings import ReminderSettings
from app.keyboards.callbacks import AccCB, DepCB, MenuCB, SetCB
from app.keyboards.common import _nav_row, confirm_action_kb


def settings_kb(settings: ReminderSettings) -> InlineKeyboardMarkup:
    toggle = "🔕 Disable reminders" if settings.enabled else "🔔 Enable reminders"
    compact = "📋 Detailed overview" if settings.compact_overview else "📋 Compact overview"
    builder = InlineKeyboardBuilder()
    builder.button(text=toggle, callback_data=SetCB(o="tog").pack())
    builder.button(text=f"🕘 Time: {settings.reminder_time}", callback_data=SetCB(o="time").pack())
    builder.button(text=f"⚠️ Stale after: {settings.stale_hours}h", callback_data=SetCB(o="stale").pack())
    builder.button(text=compact, callback_data=SetCB(o="comp").pack())
    builder.button(text="📤 Export CSV", callback_data=SetCB(o="exp").pack())
    builder.button(text="💾 Backup database", callback_data=SetCB(o="bak").pack())
    builder.button(text="❓ Help", callback_data=MenuCB(a="help").pack())
    builder.adjust(1)
    _nav_row(builder, back="menu")
    return builder.as_markup()


def stale_hours_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for hours in (12, 24, 48, 72, 168):
        label = f"{hours}h" if hours < 168 else "7 days"
        builder.button(text=label, callback_data=SetCB(o="sh", v=str(hours)).pack())
    builder.button(text="✏️ Custom", callback_data=SetCB(o="shc").pack())
    builder.adjust(3, 2, 1)
    _nav_row(builder, back="settings")
    return builder.as_markup()


def export_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏦 Accounts CSV", callback_data=SetCB(o="expa").pack())
    builder.button(text="📜 Balance history CSV", callback_data=SetCB(o="expb").pack())
    builder.button(text="📤 Withdrawals CSV", callback_data=SetCB(o="expw").pack())
    builder.adjust(1)
    _nav_row(builder, back="settings")
    return builder.as_markup()


def reminders_kb(accounts: list[Account]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts[:20]:
        label = f"🏦 {account.display_name}"[:64]
        builder.button(text=label, callback_data=AccCB(o="view", i=account.id).pack())
        builder.button(text="✅ Check", callback_data=AccCB(o="chk", i=account.id).pack())
    builder.adjust(2)
    if accounts:
        builder.row(
            InlineKeyboardButton(
                text="✅ Mark all checked",
                callback_data=SetCB(o="macq").pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="⚙️ Reminder settings", callback_data=MenuCB(a="settings").pack()))
    _nav_row(builder, back="menu")
    return builder.as_markup()


def reminder_inline_kb(accounts: list[Account]) -> InlineKeyboardMarkup:
    """Compact keyboard attached to the scheduled reminder message."""
    builder = InlineKeyboardBuilder()
    for account in accounts[:15]:
        builder.button(text=f"🏦 {account.display_name}"[:32], callback_data=AccCB(o="view", i=account.id).pack())
        builder.button(text="✅", callback_data=AccCB(o="chk", i=account.id).pack())
    builder.adjust(2)
    if accounts:
        builder.row(InlineKeyboardButton(text="✅ Mark all checked", callback_data=SetCB(o="macq").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Open menu", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def deposit_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit fields", callback_data=DepCB(o="edit", i=account_id).pack())
    builder.button(text="🧹 Clear all", callback_data=DepCB(o="clq", i=account_id).pack())
    builder.adjust(2)
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


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


def deposit_fields_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in DEPOSIT_FIELDS:
        builder.button(text=label, callback_data=DepCB(o="fld", i=account_id, f=code).pack())
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="✅ Done", callback_data=DepCB(o="view", i=account_id).pack()))
    _nav_row(builder, back=f"acc:{account_id}")
    return builder.as_markup()


def mark_all_confirm_kb() -> InlineKeyboardMarkup:
    return confirm_action_kb(
        yes_data=SetCB(o="mac").pack(),
        no_data=MenuCB(a="reminders").pack(),
        yes_text="✅ Yes, mark all checked",
        no_text="✖️ Cancel",
    )
