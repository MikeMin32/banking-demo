"""Shared keyboard rows."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import AccCB, FormCB, MenuCB, WdCB

PAGE_SIZE = 6
HISTORY_PAGE_SIZE = 8


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏦 Accounts", callback_data=MenuCB(a="accounts").pack())
    builder.button(text="📋 All Balances", callback_data=MenuCB(a="overview").pack())
    builder.button(text="📤 Withdrawals", callback_data=MenuCB(a="withdrawals").pack())
    builder.button(text="➕ Add Account", callback_data=MenuCB(a="add").pack())
    builder.button(text="⏰ Reminders", callback_data=MenuCB(a="reminders").pack())
    builder.button(text="⚙️ Settings", callback_data=MenuCB(a="settings").pack())
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def back_main_kb(*, back: str = "menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _nav_row(builder, back=back)
    return builder.as_markup()


def _nav_row(builder: InlineKeyboardBuilder, *, back: str = "menu") -> None:
    if back == "menu":
        builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()))
        return
    if back.startswith("acc:"):
        account_id = int(back.split(":")[1])
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="view", i=account_id).pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
        return
    if back == "accounts":
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=MenuCB(a="accounts").pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
        return
    if back == "withdrawals":
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=MenuCB(a="withdrawals").pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
        return
    if back == "settings":
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=MenuCB(a="settings").pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
        return
    if back == "reminders":
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=MenuCB(a="reminders").pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
        return
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=back),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
    )


def form_kb(*, skip: bool = False, zero: bool = False, keep: bool = False, back: str = "menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    if skip:
        row.append(InlineKeyboardButton(text="⏭️ Skip", callback_data=FormCB(o="skip").pack()))
    if keep:
        row.append(InlineKeyboardButton(text="✅ Keep current", callback_data=FormCB(o="keep").pack()))
    if zero:
        row.append(InlineKeyboardButton(text="0️⃣ Use 0", callback_data=FormCB(o="zero").pack()))
    row.append(InlineKeyboardButton(text="✖️ Cancel", callback_data=FormCB(o="cancel").pack()))
    builder.row(*row)
    _nav_row(builder, back=back)
    return builder.as_markup()


def confirm_kb(yes: str, *, back: str = "menu", yes_text: str = "✅ Confirm", no_text: str = "✖️ Cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=yes_text, callback_data=yes),
        InlineKeyboardButton(text=no_text, callback_data=FormCB(o="cancel").pack() if back == "cancel" else MenuCB(a="menu").pack() if back == "menu" else yes.replace("dly", "view").replace("dlq", "view")),
    )
    # The no button is better as an explicit back target; callers pass packed callback data.
    return builder.as_markup()


def confirm_action_kb(*, yes_data: str, no_data: str, yes_text: str = "✅ Confirm", no_text: str = "✖️ Cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=yes_text, callback_data=yes_data),
        InlineKeyboardButton(text=no_text, callback_data=no_data),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def pagination_row(builder: InlineKeyboardBuilder, *, page: int, total: int, page_size: int, factory) -> None:
    last_page = max((total - 1) // page_size, 0)
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=factory(page - 1)))
    if total > page_size:
        buttons.append(InlineKeyboardButton(text=f"{page + 1}/{last_page + 1}", callback_data=factory(page)))
    if page < last_page:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=factory(page + 1)))
    if buttons:
        builder.row(*buttons)


def account_choice_kb(
    accounts: list,
    *,
    page: int,
    total: int,
    op: str,
    back: str = "menu",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts:
        label = f"{account.display_name}"[:64]
        builder.button(text=label, callback_data=AccCB(o=op, i=account.id, p=page).pack())
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: AccCB(o="pick" if op != "view" else "list", i=0, p=p).pack()
        if op == "view"
        else AccCB(o="wpick" if op == "wsel" else op, i=0, p=p).pack(),
    )
    if op == "wsel":
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=WdCB(o="list", s="pending").pack()),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
        )
    else:
        _nav_row(builder, back=back)
    return builder.as_markup()
