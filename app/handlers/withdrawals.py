"""Expected charges. Pending amounts reserve available balance."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.keyboards.callbacks import MenuCB, WdCB
from app.keyboards.common import PAGE_SIZE, confirm_action_kb, form_kb
from app.keyboards.withdrawals import pick_account_for_wd_kb, withdrawal_view_kb, withdrawals_list_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.services.money import format_amount
from app.services.withdrawals import WithdrawalError
from app.states.forms import ChargeForm
from app.utils.account_context import account_body
from app.utils.formatting import withdrawal_section
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

router = Router(name="withdrawals")


async def _show_list(
    target: Message | CallbackQuery,
    services: Services,
    *,
    status: str,
    page: int,
    account_id: int = 0,
) -> None:
    filter_status = status if status in {"pending", "completed", "cancelled"} else "pending"
    acc_filter = account_id or None
    items, total = await services.withdrawals.page(
        status=filter_status, account_id=acc_filter, page=page, page_size=PAGE_SIZE
    )
    paired = []
    for item in items:
        try:
            account = await services.accounts.get(item.account_id)
        except AccountError:
            continue
        paired.append((item, account))
    title = {"pending": "Pending", "completed": "Completed", "cancelled": "Cancelled"}[filter_status]
    if account_id:
        if not paired and page == 0:
            section = f"{title} charges: none yet."
        else:
            section = f"{title} charges:"
        _, text = await account_body(services, account_id, section)
    else:
        if not paired and page == 0:
            text = f"{title} charges: none yet."
        else:
            text = f"{title} charges:"
    await render_screen(
        target,
        "expected-charges",
        text,
        withdrawals_list_kb(paired, status=filter_status, page=page, total=total, account_id=account_id),
    )


@router.callback_query(MenuCB.filter(F.a == "withdrawals"))
@router.callback_query(WdCB.filter(F.o == "list"))
async def cb_list(query: CallbackQuery, callback_data: MenuCB | WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    status = callback_data.s if isinstance(callback_data, WdCB) else "pending"
    page = callback_data.p if isinstance(callback_data, WdCB) else 0
    await _show_list(query, services, status=status, page=page, account_id=0)


@router.callback_query(WdCB.filter(F.o == "alist"))
async def cb_account_list(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await _show_list(query, services, status=callback_data.s, page=callback_data.p, account_id=callback_data.a)


@router.callback_query(WdCB.filter(F.o == "view"))
async def cb_view(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    try:
        withdrawal = await services.withdrawals.get(callback_data.i)
        account = await services.accounts.get(withdrawal.account_id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        await _show_list(query, services, status=callback_data.s, page=0, account_id=callback_data.a)
        return
    _, text = await account_body(
        services,
        account.id,
        withdrawal_section(withdrawal, account, services.tz),
    )
    await render_screen(
        query,
        "expected-charges",
        text,
        withdrawal_view_kb(withdrawal, status=callback_data.s, account_id=callback_data.a, page=callback_data.p),
    )


@router.callback_query(WdCB.filter(F.o == "add"))
async def cb_add(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    if callback_data.a:
        await _start_amount(query, state, callback_data.a, services)
        return
    items, total = await services.accounts.page(archived=False, page=callback_data.p, page_size=PAGE_SIZE)
    if not items and callback_data.p == 0:
        await render_screen(query, "expected-charges", "Add an account before creating a charge.", form_kb())
        return
    await render_screen(
        query,
        "expected-charges",
        "<b>➕ ADD EXPECTED CHARGE</b>\nChoose the account.",
        pick_account_for_wd_kb(items, page=callback_data.p, total=total),
    )


@router.callback_query(WdCB.filter(F.o == "asel"))
async def cb_account_selected(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await _start_amount(query, state, callback_data.a, services)


async def _start_amount(target: Message | CallbackQuery, state: FSMContext, account_id: int, services: Services) -> None:
    account = await services.accounts.get(account_id)
    await state.set_state(ChargeForm.amount)
    await state.update_data(account_id=account.id)
    body = f"Enter charge amount ({account.currency}):"
    _, text = await account_body(services, account.id, body)
    markup = form_kb(back=f"acc:{account.id}")
    if isinstance(target, CallbackQuery):
        await render_screen(target, "expected-charges", text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(ChargeForm.amount)
async def form_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    try:
        withdrawal = await services.withdrawals.create(account_id, message.text or "")
        account = await services.accounts.get(withdrawal.account_id)
        projection = await services.withdrawals.projection(account.id)
    except (WithdrawalError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>➕ ADD EXPECTED CHARGE</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await clear_state(state)
    summary = (
        f"<b>Charge added</b>\n"
        f"{format_amount(withdrawal.amount_minor, account.currency, with_symbol=True)} reserved.\n"
        f"Bank balance: {format_amount(account.balance_minor, account.currency, with_symbol=True)}\n"
        f"Pending: {format_amount(projection.pending_minor, account.currency, with_symbol=True)}\n"
        f"Available: <b>{format_amount(projection.available_minor, account.currency, with_symbol=True)}</b>"
    )
    _, text = await account_body(services, account.id, summary)
    await message.answer(text)
    await render_account(message, services, account.id)


@router.callback_query(WdCB.filter(F.o == "act"))
async def cb_actual_start(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    """Ask for the actual charged amount (may differ from expected)."""
    await answer_callback(query)
    try:
        withdrawal = await services.withdrawals.get(callback_data.i)
        account = await services.accounts.get(withdrawal.account_id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    expected = format_amount(withdrawal.amount_minor, account.currency, with_symbol=True)
    await state.set_state(ChargeForm.actual_amount)
    await state.update_data(
        withdrawal_id=withdrawal.id,
        account_id=account.id,
        status=callback_data.s,
        expected_minor=withdrawal.amount_minor,
    )
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Use expected amount",
            callback_data=WdCB(o="ause", i=withdrawal.id, a=account.id, s=callback_data.s).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✖️ Cancel",
            callback_data=WdCB(o="view", i=withdrawal.id, a=callback_data.a, s=callback_data.s).pack(),
        )
    )
    _, text = await account_body(
        services,
        account.id,
        f"<b>✅ Actual Charge</b>\nExpected: {expected}\nEnter the actual amount charged:",
    )
    await render_screen(query, "expected-charges", text, builder.as_markup())


@router.callback_query(WdCB.filter(F.o == "ause"))
async def cb_actual_use_expected(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    data = await state.get_data()
    expected_minor = int(data.get("expected_minor") or 0)
    await state.update_data(actual_raw="", actual_minor=expected_minor)
    await _prompt_actual_apply(
        query, services, account_id=callback_data.a, withdrawal_id=callback_data.i, status=callback_data.s
    )


@router.message(ChargeForm.actual_amount)
async def form_charge_actual(message: Message, services: Services, state: FSMContext) -> None:
    from app.services.money import MoneyError, parse_to_minor

    data = await state.get_data()
    account_id = int(data["account_id"])
    withdrawal_id = int(data["withdrawal_id"])
    status = str(data.get("status") or "pending")
    raw = message.text or ""
    try:
        account = await services.accounts.get(account_id)
        amount_minor = parse_to_minor(raw, account.currency)
        if amount_minor <= 0:
            raise WithdrawalError("Actual charge amount must be greater than zero.")
    except (MoneyError, WithdrawalError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>✅ Actual Charge</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await state.update_data(actual_raw=raw, actual_minor=amount_minor)
    await _prompt_actual_apply(
        message, services, account_id=account_id, withdrawal_id=withdrawal_id, status=status
    )


async def _prompt_actual_apply(
    target: Message | CallbackQuery,
    services: Services,
    *,
    account_id: int,
    withdrawal_id: int,
    status: str,
) -> None:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Deduct from balance",
            callback_data=WdCB(o="aded", i=withdrawal_id, a=account_id, s=status).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📌 Already in bank balance",
            callback_data=WdCB(o="aalr", i=withdrawal_id, a=account_id, s=status).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✖️ Cancel",
            callback_data=WdCB(o="view", i=withdrawal_id, a=account_id, s=status).pack(),
        )
    )
    _, text = await account_body(
        services,
        account_id,
        "<b>✅ Confirm actual charge</b>\n"
        "Deduct from recorded balance, or mark as already reflected after a manual update.",
    )
    if isinstance(target, CallbackQuery):
        await render_screen(target, "expected-charges", text, builder.as_markup())
    else:
        await target.answer(text, reply_markup=builder.as_markup())


@router.callback_query(WdCB.filter(F.o.in_({"aded", "aalr", "done"})))
async def cb_complete(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    deduct = callback_data.o != "aalr"
    data = await state.get_data()
    raw = data.get("actual_raw") or None
    actual_minor = data.get("actual_minor")
    try:
        if callback_data.o == "done":
            result_wd = await services.withdrawals.complete(callback_data.i)
            account = await services.accounts.get(result_wd.account_id)
            withdrawal = result_wd
        else:
            result = await services.withdrawals.confirm_actual(
                callback_data.i,
                raw_actual=str(raw) if raw else None,
                actual_minor=int(actual_minor) if actual_minor is not None else None,
                deduct=deduct,
            )
            withdrawal = result.withdrawal
            account = result.account
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await clear_state(state)
    await answer_callback(query, "Saved")
    _, text = await account_body(
        services,
        account.id,
        withdrawal_section(withdrawal, account, services.tz),
    )
    await render_screen(
        query,
        "expected-charges",
        text,
        withdrawal_view_kb(withdrawal, status=callback_data.s, account_id=callback_data.a, page=0),
    )


@router.callback_query(WdCB.filter(F.o == "cncl"))
async def cb_cancel_wd(query: CallbackQuery, callback_data: WdCB, services: Services) -> None:
    try:
        withdrawal = await services.withdrawals.cancel(callback_data.i)
        account = await services.accounts.get(withdrawal.account_id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, "Cancelled")
    _, text = await account_body(
        services,
        account.id,
        withdrawal_section(withdrawal, account, services.tz),
    )
    await render_screen(
        query,
        "expected-charges",
        text,
        withdrawal_view_kb(withdrawal, status=callback_data.s, account_id=callback_data.a, page=0),
    )


@router.callback_query(WdCB.filter(F.o == "eamt"))
async def cb_edit_amount(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await state.set_state(ChargeForm.edit_value)
    await state.update_data(
        withdrawal_id=callback_data.i,
        account_id=callback_data.a,
        status=callback_data.s,
    )
    _, text = await account_body(
        services,
        callback_data.a,
        "<b>✏️ EDIT CHARGE AMOUNT</b>\n\nSend the new charge amount.",
    )
    await render_screen(
        query,
        "expected-charges",
        text,
        form_kb(back=f"acc:{callback_data.a}" if callback_data.a else "accounts"),
    )


@router.message(ChargeForm.edit_value)
async def edit_value(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data.get("account_id") or 0)
    try:
        withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), raw_amount=message.text or "")
        account = await services.accounts.get(withdrawal.account_id)
        projection = await services.withdrawals.projection(account.id)
    except (WithdrawalError, AccountError) as exc:
        _, text = await account_body(services, account_id, f"<b>✏️ EDIT CHARGE AMOUNT</b>\n\n{exc}")
        await message.answer(text, reply_markup=form_kb())
        return
    await clear_state(state)
    summary = (
        f"<b>Charge updated</b>\n"
        f"Available is now {format_amount(projection.available_minor, account.currency, with_symbol=True)}."
    )
    _, text = await account_body(services, account.id, summary + "\n\n" + withdrawal_section(withdrawal, account, services.tz))
    await render_screen(
        message,
        "expected-charges",
        text,
        withdrawal_view_kb(
            withdrawal,
            status=str(data.get("status") or "pending"),
            account_id=int(data.get("account_id") or account.id),
            page=0,
        ),
    )


@router.callback_query(WdCB.filter(F.o == "dlq"))
async def cb_delete_ask(query: CallbackQuery, callback_data: WdCB, services: Services) -> None:
    await answer_callback(query)
    body = "<b>🗑️ DELETE CHARGE</b>\n\nDelete this charge record? Completed deductions are not reversed."
    if callback_data.a:
        _, text = await account_body(services, callback_data.a, body)
    else:
        text = body
    await render_screen(
        query,
        "expected-charges",
        text,
        confirm_action_kb(
            yes_data=WdCB(o="dly", i=callback_data.i, a=callback_data.a, s=callback_data.s).pack(),
            no_data=WdCB(o="view", i=callback_data.i, a=callback_data.a, s=callback_data.s).pack(),
            yes_text="🗑️ Delete",
        ),
    )


@router.callback_query(WdCB.filter(F.o == "dly"))
async def cb_delete(query: CallbackQuery, callback_data: WdCB, services: Services) -> None:
    await answer_callback(query, "Deleted")
    await services.withdrawals.delete(callback_data.i)
    await _show_list(query, services, status=callback_data.s, page=0, account_id=callback_data.a)
