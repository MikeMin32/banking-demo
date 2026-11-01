"""Balance update and history."""

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
from app.utils.account_context import account_body
from app.utils.formatting import history_text
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

router = Router(name="balances")


@router.callback_query(AccCB.filter(F.o == "bal"))
async def cb_update_balance(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    account = await services.accounts.get(callback_data.i)
    projection = await services.withdrawals.projection(account.id)
    await state.set_state(BalanceForm.amount)
    await state.update_data(account_id=account.id)
    body = (
        f"Recorded bank: <b>{format_amount(account.balance_minor, account.currency, with_symbol=True)}</b>\n"
        f"Enter new bank balance ({account.currency}):"
    )
    _, text = await account_body(services, account.id, body)
    await render_screen(query, "account-details", text, form_kb(back=f"acc:{account.id}"))


@router.message(BalanceForm.amount)
async def form_balance_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    try:
        result = await services.balances.update_balance(account_id, message.text or "")
        projection = await services.withdrawals.projection(result.account.id)
    except AccountError as exc:
        _, text = await account_body(services, account_id, f"<b>💵 UPDATE BALANCE</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await clear_state(state)
    delta = difference_label(result.old_balance_minor, result.new_balance_minor, result.account.currency)
    summary = (
        f"<b>Bank balance updated</b>\n"
        f"{format_amount(result.old_balance_minor, result.account.currency, with_symbol=True)}"
        f"  →  <b>{format_amount(result.new_balance_minor, result.account.currency, with_symbol=True)}</b>\n"
        f"Difference: {delta}\n"
        f"Pending charges: {format_amount(projection.pending_minor, result.account.currency, with_symbol=True)}\n"
        f"Available: <b>{format_amount(projection.available_minor, result.account.currency, with_symbol=True)}</b>"
    )
    _, text = await account_body(services, result.account.id, summary)
    await message.answer(text)
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
    _, text = await account_body(
        services,
        account.id,
        history_text(account, entries, services.tz, callback_data.p, total),
    )
    await render_screen(
        query,
        "account-details",
        text,
        history_kb(account.id, page=callback_data.p, total=total, page_size=HISTORY_PAGE_SIZE),
    )
