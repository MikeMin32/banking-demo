"""Balance update, confirm-checked, and history."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.keyboards.accounts import history_kb
from app.keyboards.callbacks import AccCB
from app.keyboards.common import HISTORY_PAGE_SIZE, form_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.services.money import difference_label, format_amount
from app.states.forms import BalanceForm
from app.utils.formatting import e, history_text
from app.utils.telegram import answer_callback, clear_state, safe_edit

router = Router(name="balances")


@router.callback_query(AccCB.filter(F.o == "bal"))
async def cb_update_balance(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    account = await services.accounts.get(callback_data.i)
    await state.set_state(BalanceForm.amount)
    await state.update_data(account_id=account.id)
    await safe_edit(
        query,
        f"<b>💵 Update balance — {e(account.display_name)}</b>\n"
        f"Current: <b>{format_amount(account.balance_minor, account.currency)}</b>\n\n"
        f"Enter the new amount ({account.currency}). Zero and negative values are allowed.",
        form_kb(back=f"acc:{account.id}"),
    )


@router.message(BalanceForm.amount)
async def form_balance_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    try:
        result = await services.balances.update_balance(account_id, message.text or "")
    except AccountError as exc:
        await message.answer(str(exc), reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await clear_state(state)
    delta = difference_label(result.old_balance_minor, result.new_balance_minor, result.account.currency)
    await message.answer(
        "<b>Balance updated</b>\n"
        f"{format_amount(result.old_balance_minor, result.account.currency)}"
        f"  →  <b>{format_amount(result.new_balance_minor, result.account.currency)}</b>\n"
        f"Difference: {delta}"
    )
    await render_account(message, services, result.account.id)


@router.callback_query(AccCB.filter(F.o == "chk"))
async def cb_confirm_checked(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    try:
        account = await services.balances.confirm_checked(callback_data.i)
    except AccountError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, "Marked as checked")
    await render_account(query, services, account.id)


@router.callback_query(AccCB.filter(F.o == "his"))
async def cb_history(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account, entries, total = await services.balances.history_page(
        callback_data.i, page=callback_data.p, page_size=HISTORY_PAGE_SIZE
    )
    await safe_edit(
        query,
        history_text(account, entries, services.tz, callback_data.p, total),
        history_kb(account.id, page=callback_data.p, total=total, page_size=HISTORY_PAGE_SIZE),
    )
