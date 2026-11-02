"""Top-up create, history, and explicit reverse."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.keyboards.callbacks import AccCB, TuCB
from app.keyboards.common import PAGE_SIZE, confirm_action_kb, form_kb
from app.keyboards.topups import topup_view_kb, topups_list_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.services.money import format_amount
from app.services.topups import TopUpError
from app.states.forms import TopUpForm
from app.utils.account_context import account_body
from app.utils.formatting import topup_section, topups_list_section
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

router = Router(name="topups")


@router.callback_query(TuCB.filter(F.o == "add"))
async def cb_add(query: CallbackQuery, callback_data: TuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account_id = callback_data.a
    currency = (await services.accounts.get(account_id)).currency
    account, text = await account_body(
        services,
        account_id,
        f"Enter deposit amount ({currency}):",
    )
    await state.set_state(TopUpForm.amount)
    await state.update_data(account_id=account.id)
    await render_screen(query, "account-details", text, form_kb(back=f"acc:{account.id}"))


@router.message(TopUpForm.amount)
async def form_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    try:
        result = await services.topups.create(account_id, message.text or "")
        projection = await services.withdrawals.projection(result.account.id)
    except (TopUpError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>💰 DEPOSIT</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await clear_state(state)
    summary = (
        f"<b>Deposit saved</b>\n"
        f"+{format_amount(result.top_up.amount_minor, result.account.currency, with_symbol=True)}\n"
        f"Current: {format_amount(result.old_balance_minor, result.account.currency, with_symbol=True)}"
        f"  →  <b>{format_amount(result.new_balance_minor, result.account.currency, with_symbol=True)}</b>\n"
        f"Expected: {format_amount(projection.pending_minor, result.account.currency, with_symbol=True)}\n"
        f"Projected: <b>{format_amount(projection.available_minor, result.account.currency, with_symbol=True)}</b>"
    )
    _, text = await account_body(services, result.account.id, summary)
    await message.answer(text)
    await render_account(message, services, result.account.id)


@router.callback_query(TuCB.filter(F.o == "list"))
async def cb_list(query: CallbackQuery, callback_data: TuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account, items, total = await services.topups.page(
        callback_data.a, page=callback_data.p, page_size=PAGE_SIZE
    )
    section = topups_list_section(empty=not items, page=callback_data.p, total=total, page_size=PAGE_SIZE)
    _, text = await account_body(services, account.id, section)
    await render_screen(
        query,
        "account-details",
        text,
        topups_list_kb(items, account, page=callback_data.p, total=total),
    )


@router.callback_query(TuCB.filter(F.o == "view"))
async def cb_view(query: CallbackQuery, callback_data: TuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    try:
        top_up = await services.topups.get(callback_data.i)
        account = await services.accounts.get(top_up.account_id)
    except (TopUpError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    _, text = await account_body(services, account.id, topup_section(top_up, account, services.tz))
    await render_screen(
        query,
        "account-details",
        text,
        topup_view_kb(top_up, account_id=account.id, page=callback_data.p),
    )


@router.callback_query(TuCB.filter(F.o == "rvq"))
async def cb_reverse_ask(query: CallbackQuery, callback_data: TuCB, services: Services) -> None:
    await answer_callback(query)
    _, text = await account_body(
        services,
        callback_data.a,
        "<b>↩️ REVERSE TOP UP</b>\n\n"
        "This deducts the top-up amount from the recorded bank balance exactly once.\n"
        "Continue?",
    )
    await render_screen(
        query,
        "account-details",
        text,
        confirm_action_kb(
            yes_data=TuCB(o="rvy", i=callback_data.i, a=callback_data.a, p=callback_data.p).pack(),
            no_data=TuCB(o="view", i=callback_data.i, a=callback_data.a, p=callback_data.p).pack(),
            yes_text="↩️ Reverse",
        ),
    )


@router.callback_query(TuCB.filter(F.o == "rvy"))
async def cb_reverse(query: CallbackQuery, callback_data: TuCB, services: Services) -> None:
    try:
        result = await services.topups.reverse(callback_data.i)
    except (TopUpError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, "Reversed")
    _, text = await account_body(
        services,
        result.account.id,
        topup_section(result.top_up, result.account, services.tz),
    )
    await render_screen(
        query,
        "account-details",
        text,
        topup_view_kb(result.top_up, account_id=result.account.id, page=callback_data.p),
    )


@router.callback_query(AccCB.filter(F.o == "txn"))
async def cb_transactions(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    from app.keyboards.accounts import transactions_hub_kb

    await answer_callback(query)
    await clear_state(state)
    _, text = await account_body(services, callback_data.i, "Choose a list:")
    await render_screen(query, "transactions", text, transactions_hub_kb(callback_data.i))
