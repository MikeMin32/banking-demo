"""Home Quick Update: Expected Charge / Actual Charge / Deposit."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.keyboards.callbacks import MenuCB, QuCB
from app.keyboards.common import PAGE_SIZE, form_kb
from app.keyboards.quick import (
    actual_confirm_kb,
    op_from_code,
    quick_link_pending_kb,
    quick_menu_kb,
    quick_pick_account_kb,
    use_expected_kb,
)
from app.services.accounts import AccountError
from app.services.container import Services
from app.services.money import format_amount
from app.services.topups import TopUpError
from app.services.withdrawals import WithdrawalError
from app.states.forms import QuickUpdateForm
from app.utils.account_context import account_body
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

router = Router(name="quick")


async def _show_menu(target: Message | CallbackQuery) -> None:
    text = (
        "<b>⚡ Quick Update</b>\n"
        "Expected Charge · Actual Charge · Deposit"
    )
    await render_screen(target, "quick-add", text, quick_menu_kb())


@router.callback_query(MenuCB.filter(F.a == "quick"))
@router.callback_query(QuCB.filter(F.o == "menu"))
async def cb_quick_menu(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    del services
    await answer_callback(query)
    await clear_state(state)
    await _show_menu(query)


@router.callback_query(QuCB.filter(F.o.in_({"exp", "act", "dep"})))
async def cb_pick_op(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    op = callback_data.o
    if op == "act" and callback_data.a:
        await _show_pending_links(query, services, account_id=callback_data.a, page=callback_data.p)
        return
    items, total = await services.accounts.page(archived=False, page=callback_data.p, page_size=PAGE_SIZE)
    titles = {
        "exp": "<b>⏳ Expected Charge</b>\nChoose the account.",
        "act": "<b>✅ Actual Charge</b>\nChoose the account.",
        "dep": "<b>💰 Deposit</b>\nChoose the account.",
    }
    if not items and callback_data.p == 0:
        await render_screen(query, "quick-add", "Add an account first.", quick_menu_kb())
        return
    await render_screen(
        query,
        "quick-add",
        titles[op],
        quick_pick_account_kb(items, op=op, page=callback_data.p, total=total),
    )


@router.callback_query(QuCB.filter(F.o == "pick"))
async def cb_account_picked(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    op = op_from_code(callback_data.i)
    account_id = callback_data.a
    if op == "act":
        await _show_pending_links(query, services, account_id=account_id, page=0)
        return
    await _start_simple_amount(query, state, services, account_id=account_id, op=op)


async def _show_pending_links(
    target: CallbackQuery, services: Services, *, account_id: int, page: int
) -> None:
    items, total = await services.withdrawals.page(
        status="pending", account_id=account_id, page=page, page_size=PAGE_SIZE
    )
    paired = []
    for item in items:
        account = await services.accounts.get(item.account_id)
        paired.append((item, account))
    _, text = await account_body(
        services,
        account_id,
        "<b>✅ Actual Charge</b>\nLink a pending expected charge, or add a new actual.",
    )
    await render_screen(
        target,
        "quick-add",
        text,
        quick_link_pending_kb(paired, account_id=account_id, page=page, total=total),
    )


async def _start_simple_amount(
    target: Message | CallbackQuery,
    state: FSMContext,
    services: Services,
    *,
    account_id: int,
    op: str,
) -> None:
    account = await services.accounts.get(account_id)
    labels = {
        "exp": f"Enter expected charge amount ({account.currency}):",
        "dep": f"Enter deposit amount ({account.currency}):",
        "solo": f"Enter actual charge amount ({account.currency}):",
    }
    await state.set_state(QuickUpdateForm.amount)
    await state.update_data(account_id=account.id, quick_op=op)
    _, text = await account_body(services, account.id, labels[op])
    markup = form_kb(back="menu")
    if isinstance(target, CallbackQuery):
        await render_screen(target, "quick-add", text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(QuCB.filter(F.o == "solo"))
async def cb_solo(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await _start_simple_amount(query, state, services, account_id=callback_data.a, op="solo")


@router.callback_query(QuCB.filter(F.o == "link"))
async def cb_link(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    try:
        withdrawal = await services.withdrawals.get(callback_data.i)
        account = await services.accounts.get(withdrawal.account_id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    expected = format_amount(withdrawal.amount_minor, account.currency, with_symbol=True)
    await state.set_state(QuickUpdateForm.actual_amount)
    await state.update_data(
        account_id=account.id,
        withdrawal_id=withdrawal.id,
        quick_op="link",
        expected_minor=withdrawal.amount_minor,
    )
    _, text = await account_body(
        services,
        account.id,
        f"<b>✅ Actual Charge</b>\nExpected: {expected}\nEnter the actual amount charged:",
    )
    await render_screen(query, "quick-add", text, use_expected_kb(account_id=account.id, withdrawal_id=withdrawal.id))


@router.callback_query(QuCB.filter(F.o == "use"))
async def cb_use_expected(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    data = await state.get_data()
    expected_minor = int(data.get("expected_minor") or 0)
    account = await services.accounts.get(callback_data.a)
    await state.update_data(actual_raw="", actual_minor=expected_minor)
    _, text = await account_body(
        services,
        account.id,
        f"<b>✅ Confirm actual {format_amount(expected_minor, account.currency, with_symbol=True)}</b>\n"
        "Deduct from recorded balance, or mark as already reflected after a manual update.",
    )
    await render_screen(
        query,
        "quick-add",
        text,
        actual_confirm_kb(account_id=account.id, withdrawal_id=callback_data.i),
    )


@router.message(QuickUpdateForm.amount)
async def form_simple_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    op = str(data.get("quick_op") or "")
    raw = message.text or ""
    try:
        if op == "exp":
            withdrawal = await services.withdrawals.create(account_id, raw)
            totals = await services.totals.for_account(account_id)
            summary = (
                f"<b>Expected charge saved</b>\n"
                f"{format_amount(withdrawal.amount_minor, totals.account.currency, with_symbol=True)}\n"
                f"Current: {format_amount(totals.current_minor, totals.account.currency, with_symbol=True)}\n"
                f"Projected: <b>{format_amount(totals.projected_minor, totals.account.currency, with_symbol=True)}</b>"
            )
        elif op == "dep":
            result = await services.topups.create(account_id, raw)
            totals = await services.totals.for_account(account_id)
            summary = (
                f"<b>Deposit saved</b>\n"
                f"+{format_amount(result.top_up.amount_minor, result.account.currency, with_symbol=True)}\n"
                f"Current: <b>{format_amount(totals.current_minor, totals.account.currency, with_symbol=True)}</b>\n"
                f"Projected: {format_amount(totals.projected_minor, totals.account.currency, with_symbol=True)}"
            )
        elif op == "solo":
            result = await services.withdrawals.create_actual(account_id, raw, deduct=True)
            totals = await services.totals.for_account(account_id)
            summary = (
                f"<b>Actual charge saved</b>\n"
                f"−{format_amount(result.withdrawal.posted_minor, result.account.currency, with_symbol=True)}\n"
                f"Current: <b>{format_amount(totals.current_minor, totals.account.currency, with_symbol=True)}</b>\n"
                f"Projected: {format_amount(totals.projected_minor, totals.account.currency, with_symbol=True)}"
            )
        else:
            raise WithdrawalError("Unknown Quick Update operation.")
    except (WithdrawalError, TopUpError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>⚡ Quick Update</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back="menu"))
        return
    await clear_state(state)
    _, text = await account_body(services, account_id, summary)
    await message.answer(text)
    await render_account(message, services, account_id)


@router.message(QuickUpdateForm.actual_amount)
async def form_actual_amount(message: Message, services: Services, state: FSMContext) -> None:
    from app.services.money import MoneyError, parse_to_minor

    data = await state.get_data()
    account_id = int(data["account_id"])
    withdrawal_id = int(data["withdrawal_id"])
    raw = message.text or ""
    try:
        account = await services.accounts.get(account_id)
        amount_minor = parse_to_minor(raw, account.currency)
        if amount_minor <= 0:
            raise WithdrawalError("Actual charge amount must be greater than zero.")
    except (MoneyError, WithdrawalError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>✅ Actual Charge</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back="menu"))
        return
    await state.update_data(actual_raw=raw, actual_minor=amount_minor)
    amount_label = format_amount(amount_minor, account.currency, with_symbol=True)
    _, text = await account_body(
        services,
        account_id,
        f"<b>✅ Confirm actual {amount_label}</b>\n"
        "Deduct from recorded balance, or mark as already reflected after a manual update.",
    )
    await message.answer(
        text,
        reply_markup=actual_confirm_kb(account_id=account_id, withdrawal_id=withdrawal_id),
    )


@router.callback_query(QuCB.filter(F.o.in_({"ded", "alr"})))
async def cb_confirm_actual(query: CallbackQuery, callback_data: QuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    data = await state.get_data()
    withdrawal_id = callback_data.i
    raw = str(data.get("actual_raw") or "") or None
    actual_minor = data.get("actual_minor")
    deduct = callback_data.o == "ded"
    try:
        if withdrawal_id:
            result = await services.withdrawals.confirm_actual(
                withdrawal_id,
                raw_actual=raw,
                actual_minor=int(actual_minor) if actual_minor is not None else None,
                deduct=deduct,
            )
        else:
            raise WithdrawalError("Missing charge to confirm.")
        totals = await services.totals.for_account(result.account.id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await clear_state(state)
    mode = "deducted" if result.deducted else "marked as already in bank balance"
    summary = (
        f"<b>Actual charge {mode}</b>\n"
        f"Expected: {format_amount(result.withdrawal.amount_minor, result.account.currency, with_symbol=True)}\n"
        f"Actual: {format_amount(result.withdrawal.posted_minor, result.account.currency, with_symbol=True)}\n"
        f"Current: <b>{format_amount(totals.current_minor, totals.account.currency, with_symbol=True)}</b>\n"
        f"Projected: {format_amount(totals.projected_minor, totals.account.currency, with_symbol=True)}"
    )
    if query.message:
        await query.message.answer(summary)
    await render_account(query, services, result.account.id)
