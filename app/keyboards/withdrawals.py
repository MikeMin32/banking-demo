"""Withdrawal list and detail keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.database.repositories.withdrawals import Withdrawal
from app.keyboards.callbacks import AccCB, MenuCB, WdCB
from app.keyboards.common import PAGE_SIZE, _nav_row, pagination_row
from app.services.money import format_amount


def withdrawals_list_kb(
    items: list[tuple[Withdrawal, Account]],
    *,
    status: str,
    page: int,
    total: int,
    account_id: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for withdrawal, account in items:
        icon = {"pending": "⏳", "completed": "✅", "cancelled": "🚫"}.get(withdrawal.status, "•")
        amount = format_amount(withdrawal.amount_minor, account.currency)
        label = f"{icon} {account.display_name} · {amount}"[:64]
        builder.button(
            text=label,
            callback_data=WdCB(o="view", i=withdrawal.id, a=account_id, s=status, p=page).pack(),
        )
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: WdCB(o="list" if not account_id else "alist", a=account_id, s=status, p=p).pack(),
    )
    builder.row(
        InlineKeyboardButton(text="⏳ Pending", callback_data=WdCB(o="list" if not account_id else "alist", a=account_id, s="pending").pack()),
        InlineKeyboardButton(text="✅ Done", callback_data=WdCB(o="list" if not account_id else "alist", a=account_id, s="completed").pack()),
        InlineKeyboardButton(text="🚫 Cancelled", callback_data=WdCB(o="list" if not account_id else "alist", a=account_id, s="cancelled").pack()),
    )
    builder.row(InlineKeyboardButton(text="➕ Add withdrawal", callback_data=WdCB(o="add", a=account_id).pack()))
    if account_id:
        _nav_row(builder, back=f"acc:{account_id}")
    else:
        _nav_row(builder, back="menu")
    return builder.as_markup()


def withdrawal_view_kb(withdrawal: Withdrawal, *, status: str, account_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if withdrawal.status == "pending":
        builder.button(text="✅ Mark completed", callback_data=WdCB(o="done", i=withdrawal.id, a=account_id, s=status).pack())
        builder.button(text="🚫 Cancel plan", callback_data=WdCB(o="cncl", i=withdrawal.id, a=account_id, s=status).pack())
        builder.button(text="✏️ Amount", callback_data=WdCB(o="eamt", i=withdrawal.id, a=account_id, s=status).pack())
        builder.button(text="📅 Date", callback_data=WdCB(o="edat", i=withdrawal.id, a=account_id, s=status).pack())
        builder.button(text="📝 Description", callback_data=WdCB(o="edsc", i=withdrawal.id, a=account_id, s=status).pack())
        builder.adjust(2, 1, 2)
    builder.button(text="🗑️ Delete", callback_data=WdCB(o="dlq", i=withdrawal.id, a=account_id, s=status).pack())
    builder.adjust(2, 1, 2, 1)
    list_op = "alist" if account_id else "list"
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Back",
            callback_data=WdCB(o=list_op, a=account_id, s=status, p=page).pack(),
        ),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def pick_account_for_wd_kb(accounts: list[Account], *, page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts:
        label = f"{account.display_name} · {account.currency}"[:64]
        builder.button(text=label, callback_data=WdCB(o="asel", a=account.id).pack())
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: WdCB(o="add", p=p).pack(),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=WdCB(o="list", s="pending").pack()),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()
