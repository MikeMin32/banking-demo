"""Quick Update keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.repositories.accounts import Account
from app.database.repositories.withdrawals import Withdrawal
from app.keyboards.callbacks import MenuCB, QuCB
from app.keyboards.common import PAGE_SIZE, _nav_row, pagination_row
from app.services.money import format_amount


def quick_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Expected Charge", callback_data=QuCB(o="exp").pack())
    builder.button(text="✅ Actual Charge", callback_data=QuCB(o="act").pack())
    builder.button(text="💰 Deposit", callback_data=QuCB(o="dep").pack())
    builder.adjust(1)
    _nav_row(builder, back="menu")
    return builder.as_markup()


def quick_pick_account_kb(
    accounts: list[Account],
    *,
    op: str,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account in accounts:
        label = f"{account.line_label} · {account.currency}"[:64]
        builder.button(text=label, callback_data=QuCB(o="pick", a=account.id, i=_op_code(op)).pack())
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: QuCB(o=op, p=p).pack(),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data=QuCB(o="menu").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def quick_link_pending_kb(
    pending: list[tuple[Withdrawal, Account]],
    *,
    account_id: int,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for withdrawal, account in pending:
        amount = format_amount(withdrawal.amount_minor, account.currency, with_symbol=True)
        builder.button(
            text=f"⏳ {amount}"[:64],
            callback_data=QuCB(o="link", a=account_id, i=withdrawal.id).pack(),
        )
    builder.adjust(1)
    pagination_row(
        builder,
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        factory=lambda p: QuCB(o="act", a=account_id, p=p).pack(),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ New Actual (no expected)",
            callback_data=QuCB(o="solo", a=account_id).pack(),
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data=QuCB(o="act").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(a="menu").pack()))
    return builder.as_markup()


def actual_confirm_kb(*, account_id: int, withdrawal_id: int = 0, standalone: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if standalone:
        builder.row(
            InlineKeyboardButton(
                text="✅ Deduct from balance",
                callback_data=QuCB(o="ded", a=account_id, i=0).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="✅ Deduct from balance",
                callback_data=QuCB(o="ded", a=account_id, i=withdrawal_id).pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📌 Already in bank balance",
                callback_data=QuCB(o="alr", a=account_id, i=withdrawal_id).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=MenuCB(a="quick").pack()))
    return builder.as_markup()


def use_expected_kb(*, account_id: int, withdrawal_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Use expected amount",
            callback_data=QuCB(o="use", a=account_id, i=withdrawal_id).pack(),
        )
    )
    builder.row(InlineKeyboardButton(text="✖️ Cancel", callback_data=MenuCB(a="quick").pack()))
    return builder.as_markup()


def _op_code(op: str) -> int:
    return {"exp": 1, "act": 2, "dep": 3}.get(op, 0)


def op_from_code(code: int) -> str:
    return {1: "exp", 2: "act", 3: "dep"}.get(code, "exp")
