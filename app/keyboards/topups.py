"""Top-up list and detail keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.database.repositories.topups import TopUp
from app.keyboards.callbacks import AccCB, MenuCB, TuCB
from app.keyboards.common import PAGE_SIZE, _nav_row, pagination_row
from app.services.money import format_amount


def topups_list_kb(
    items: list[TopUp],
    account: Account,
    *,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        amount = format_amount(item.amount_minor, account.currency, with_symbol=True)
        icon = "↩️" if item.is_reversed else "💰"
        builder.button(
            text=f"{icon} +{amount}"[:64],
            callback_data=TuCB(o="view", i=item.id, a=account.id, p=page).pack(),
        )
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: TuCB(o="list", a=account.id, p=p).pack(),
    )
    builder.row(InlineKeyboardButton(text="💰 Add Top Up", callback_data=TuCB(o="add", a=account.id).pack()))
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="txn", i=account.id).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def topup_view_kb(top_up: TopUp, *, account_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if top_up.applied_to_balance and not top_up.is_reversed:
        builder.button(
            text="↩️ Reverse Top Up",
            callback_data=TuCB(o="rvq", i=top_up.id, a=account_id, p=page).pack(),
        )
        builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=TuCB(o="list", a=account_id, p=page).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()
