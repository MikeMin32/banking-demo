"""Expected-charge list and detail keyboards."""

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
        amount = format_amount(withdrawal.amount_minor, account.currency, with_symbol=True)
        builder.button(
            text=f"{icon} {amount}"[:64],
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
        InlineKeyboardButton(text="⏳ Pending", callback_data=WdCB(o="alist" if account_id else "list", a=account_id, s="pending").pack()),
        InlineKeyboardButton(text="✅ Done", callback_data=WdCB(o="alist" if account_id else "list", a=account_id, s="completed").pack()),
        InlineKeyboardButton(text="🚫 Cancelled", callback_data=WdCB(o="alist" if account_id else "list", a=account_id, s="cancelled").pack()),
    )
    builder.row(InlineKeyboardButton(text="➕ Add Expected Charge", callback_data=WdCB(o="add", a=account_id).pack()))
    if account_id:
        builder.row(
            InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="txn", i=account_id).pack()),
            InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
        )
    else:
        _nav_row(builder, back="accounts")
    return builder.as_markup()


def withdrawal_view_kb(withdrawal: Withdrawal, *, status: str, account_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if withdrawal.status == "pending":
        builder.button(
            text="✅ Actual Charge",
            callback_data=WdCB(o="act", i=withdrawal.id, a=account_id, s=status).pack(),
        )
        builder.button(text="🚫 Cancel charge", callback_data=WdCB(o="cncl", i=withdrawal.id, a=account_id, s=status).pack())
        builder.button(text="✏️ Amount", callback_data=WdCB(o="eamt", i=withdrawal.id, a=account_id, s=status).pack())
        builder.adjust(2, 1)
    builder.button(text="🗑️ Delete", callback_data=WdCB(o="dlq", i=withdrawal.id, a=account_id, s=status).pack())
    list_op = "alist" if account_id else "list"
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=WdCB(o=list_op, a=account_id, s=status, p=page).pack()),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()),
    )
    return builder.as_markup()


def pick_account_for_wd_kb(accounts: list[Account], *, page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts:
        label = f"{account.line_label} · {account.currency}"[:64]
        builder.button(text=label, callback_data=WdCB(o="asel", a=account.id).pack())
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: WdCB(o="add", p=p).pack(),
    )
    _nav_row(builder, back="accounts")
    return builder.as_markup()
