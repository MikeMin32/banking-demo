"""Expected withdrawal tracking. Never mutates stored balances."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.keyboards.callbacks import FormCB, MenuCB, WdCB
from app.keyboards.common import PAGE_SIZE, confirm_action_kb, form_kb
from app.keyboards.withdrawals import pick_account_for_wd_kb, withdrawal_view_kb, withdrawals_list_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.services.money import format_amount
from app.services.withdrawals import WithdrawalError
from app.states.forms import WithdrawalForm
from app.utils.formatting import e, withdrawal_card
from app.utils.telegram import answer_callback, clear_state, safe_edit
from app.utils.time import parse_user_date

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
    title = filter_status.capitalize()
    scope = ""
    if account_id:
        try:
            account = await services.accounts.get(account_id)
            scope = f" — {e(account.display_name)}"
        except AccountError:
            scope = ""
    if not paired and page == 0:
        text = f"<b>📤 {title} withdrawals{scope}</b>\n\nNothing in this list."
    else:
        text = f"<b>📤 {title} withdrawals{scope}</b>"
    await safe_edit(
        target,
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
    await safe_edit(
        query,
        withdrawal_card(withdrawal, account, services.tz),
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
        await safe_edit(query, "Add an account before creating a withdrawal.", form_kb())
        return
    await safe_edit(
        query,
        "<b>➕ Expected withdrawal</b>\nChoose the account this plan belongs to.",
        pick_account_for_wd_kb(items, page=callback_data.p, total=total),
    )


@router.callback_query(WdCB.filter(F.o == "asel"))
async def cb_account_selected(query: CallbackQuery, callback_data: WdCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await _start_amount(query, state, callback_data.a, services)


async def _start_amount(target: Message | CallbackQuery, state: FSMContext, account_id: int, services: Services) -> None:
    account = await services.accounts.get(account_id)
    projection = await services.withdrawals.projection(account.id)
    await state.set_state(WithdrawalForm.amount)
    await state.update_data(account_id=account.id)
    text = (
        f"<b>➕ Withdrawal — {e(account.display_name)}</b>\n"
        f"Current balance: {format_amount(account.balance_minor, account.currency)}\n"
        f"Already pending: {format_amount(projection.pending_minor, account.currency)}\n"
        f"Projected remaining: {format_amount(projection.projected_minor, account.currency)}\n\n"
        f"Enter the expected withdrawal amount ({account.currency}):"
    )
    markup = form_kb(back=f"acc:{account.id}")
    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(WithdrawalForm.amount)
async def form_amount(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    account = await services.accounts.get(account_id)
    try:
        from app.services.money import parse_to_minor

        amount = parse_to_minor(message.text or "", account.currency)
        if amount <= 0:
            raise WithdrawalError("Withdrawal amount must be greater than zero.")
    except Exception as exc:
        await message.answer(str(exc), reply_markup=form_kb(back=f"acc:{account_id}"))
        return
    await state.update_data(amount_raw=(message.text or "").strip())
    await state.set_state(WithdrawalForm.date)
    await message.answer(
        "Optional expected date.\nUse <code>YYYY-MM-DD</code>, <code>today</code>, or <code>tomorrow</code>.",
        reply_markup=form_kb(skip=True, back=f"acc:{account_id}"),
    )


@router.callback_query(FormCB.filter(F.o == "skip"), WithdrawalForm.date)
async def skip_date(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(expected_date=None)
    await state.set_state(WithdrawalForm.description)
    data = await state.get_data()
    await safe_edit(query, "Optional description.", form_kb(skip=True, back=f"acc:{data['account_id']}"))


@router.message(WithdrawalForm.date)
async def form_date(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        parsed = parse_user_date(message.text or "", services.tz)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=form_kb(skip=True, back=f"acc:{data['account_id']}"))
        return
    await state.update_data(expected_date=parsed.isoformat())
    await state.set_state(WithdrawalForm.description)
    await message.answer("Optional description.", reply_markup=form_kb(skip=True, back=f"acc:{data['account_id']}"))


@router.callback_query(FormCB.filter(F.o == "skip"), WithdrawalForm.description)
async def skip_desc(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(description=None)
    await _create_withdrawal(query, services, state)


@router.message(WithdrawalForm.description)
async def form_desc(message: Message, services: Services, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await _create_withdrawal(message, services, state)


async def _create_withdrawal(target: Message | CallbackQuery, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        withdrawal = await services.withdrawals.create(
            int(data["account_id"]),
            str(data["amount_raw"]),
            expected_date=data.get("expected_date"),
            description=data.get("description"),
        )
        account = await services.accounts.get(withdrawal.account_id)
        projection = await services.withdrawals.projection(account.id)
    except (WithdrawalError, AccountError) as exc:
        text = str(exc)
        if isinstance(target, CallbackQuery):
            await safe_edit(target, text, form_kb())
        else:
            await target.answer(text)
        return
    summary = (
        "<b>Withdrawal added successfully.</b>\n"
        f"{format_amount(withdrawal.amount_minor, account.currency)} · {e(account.display_name)}\n\n"
        f"Current balance: {format_amount(account.balance_minor, account.currency)}\n"
        f"Pending total: {format_amount(projection.pending_minor, account.currency)}\n"
        f"Projected remaining: <b>{format_amount(projection.projected_minor, account.currency)}</b>"
    )
    if isinstance(target, CallbackQuery):
        await safe_edit(
            target,
            summary,
            withdrawal_view_kb(withdrawal, status="pending", account_id=account.id, page=0),
        )
    else:
        await target.answer(summary)
        await render_account(target, services, account.id)


@router.callback_query(WdCB.filter(F.o == "done"))
async def cb_complete(query: CallbackQuery, callback_data: WdCB, services: Services) -> None:
    try:
        withdrawal = await services.withdrawals.complete(callback_data.i)
        account = await services.accounts.get(withdrawal.account_id)
    except (WithdrawalError, AccountError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, "Marked completed")
    await safe_edit(
        query,
        withdrawal_card(withdrawal, account, services.tz),
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
    await safe_edit(
        query,
        withdrawal_card(withdrawal, account, services.tz),
        withdrawal_view_kb(withdrawal, status=callback_data.s, account_id=callback_data.a, page=0),
    )


@router.callback_query(WdCB.filter(F.o.in_({"eamt", "edat", "edsc"})))
async def cb_edit_field(query: CallbackQuery, callback_data: WdCB, state: FSMContext) -> None:
    await answer_callback(query)
    field = {"eamt": "amount", "edat": "date", "edsc": "description"}[callback_data.o]
    await state.set_state(WithdrawalForm.edit_value)
    await state.update_data(withdrawal_id=callback_data.i, field=field, account_id=callback_data.a, status=callback_data.s)
    prompts = {
        "amount": "Send the new amount.",
        "date": "Send the new date (YYYY-MM-DD, today, tomorrow) or Skip to clear it.",
        "description": "Send the new description, or Skip to clear it.",
    }
    await safe_edit(
        query,
        prompts[field],
        form_kb(skip=field != "amount", back="withdrawals"),
    )


@router.callback_query(FormCB.filter(F.o == "skip"), WithdrawalForm.edit_value)
async def edit_skip(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    if field == "amount":
        await query.answer("Amount is required.", show_alert=True)
        return
    await answer_callback(query)
    if field == "date":
        withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), expected_date=None)
    else:
        withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), description=None)
    await clear_state(state)
    account = await services.accounts.get(withdrawal.account_id)
    await safe_edit(
        query,
        withdrawal_card(withdrawal, account, services.tz),
        withdrawal_view_kb(withdrawal, status=str(data.get("status") or "pending"), account_id=int(data.get("account_id") or 0), page=0),
    )


@router.message(WithdrawalForm.edit_value)
async def edit_value(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    try:
        if field == "amount":
            withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), raw_amount=message.text or "")
        elif field == "date":
            parsed = parse_user_date(message.text or "", services.tz)
            withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), expected_date=parsed)
        else:
            withdrawal = await services.withdrawals.update(int(data["withdrawal_id"]), description=message.text)
    except (WithdrawalError, ValueError) as exc:
        await message.answer(str(exc), reply_markup=form_kb(skip=field != "amount"))
        return
    await clear_state(state)
    account = await services.accounts.get(withdrawal.account_id)
    await message.answer(withdrawal_card(withdrawal, account, services.tz))


@router.callback_query(WdCB.filter(F.o == "dlq"))
async def cb_delete_ask(query: CallbackQuery, callback_data: WdCB) -> None:
    await answer_callback(query)
    await safe_edit(
        query,
        "Delete this withdrawal? This cannot be undone.",
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
