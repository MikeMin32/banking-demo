"""Deposit instructions. Sensitive; shown only after auth + private-chat middleware."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.repositories.deposits import DEPOSIT_FIELDS
from app.handlers.accounts import render_account
from app.keyboards.callbacks import DepCB, FormCB
from app.keyboards.common import confirm_action_kb, form_kb
from app.keyboards.settings import DEPOSIT_FIELDS as FIELD_LABELS
from app.keyboards.settings import deposit_fields_kb, deposit_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.states.forms import DepositForm
from app.utils.formatting import deposit_text, e
from app.utils.telegram import answer_callback, clear_state, safe_edit
from app.utils.time import utc_now_iso

router = Router(name="deposits")

_LABELS = dict(FIELD_LABELS)
MAX_LEN = 128
MAX_NOTES = 500


@router.callback_query(DepCB.filter(F.o == "view"))
async def cb_view(query: CallbackQuery, callback_data: DepCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account = await services.accounts.get(callback_data.i)
    details = await services.deposits.get(account.id)
    await safe_edit(query, deposit_text(account, details), deposit_kb(account.id))


@router.callback_query(DepCB.filter(F.o == "edit"))
async def cb_edit(query: CallbackQuery, callback_data: DepCB, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await safe_edit(
        query,
        "<b>✏️ Deposit details</b>\n"
        "Pick a field to change. Identifiers are stored as text so leading zeros are kept.\n"
        "<i>These details are not included in CSV exports.</i>",
        deposit_fields_kb(callback_data.i),
    )


@router.callback_query(DepCB.filter(F.o == "fld"))
async def cb_field(query: CallbackQuery, callback_data: DepCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    if callback_data.f not in DEPOSIT_FIELDS:
        await query.answer("Unknown field.", show_alert=True)
        return
    details = await services.deposits.get(callback_data.i)
    current = getattr(details, callback_data.f) if details else None
    await state.set_state(DepositForm.value)
    await state.update_data(account_id=callback_data.i, field=callback_data.f)
    shown = e(current)
    await safe_edit(
        query,
        f"Send a new value for <b>{_LABELS.get(callback_data.f, callback_data.f)}</b>.\n"
        f"Current: <code>{shown}</code>\n"
        "Skip clears the field. Keep leaves it unchanged.",
        form_kb(skip=True, keep=True, back=f"acc:{callback_data.i}"),
    )


@router.callback_query(FormCB.filter(F.o == "keep"), DepositForm.value)
async def keep_field(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    await answer_callback(query, "Unchanged")
    await clear_state(state)
    account = await services.accounts.get(int(data["account_id"]))
    details = await services.deposits.get(account.id)
    await safe_edit(query, deposit_text(account, details), deposit_fields_kb(account.id))


@router.callback_query(FormCB.filter(F.o == "skip"), DepositForm.value)
async def clear_field(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    await answer_callback(query)
    account_id = int(data["account_id"])
    field = str(data["field"])
    await services.deposits.upsert(account_id, {field: None}, utc_now_iso())
    await clear_state(state)
    account = await services.accounts.get(account_id)
    details = await services.deposits.get(account.id)
    await safe_edit(query, deposit_text(account, details), deposit_fields_kb(account.id))


@router.message(DepositForm.value)
async def set_field(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    field = str(data["field"])
    account_id = int(data["account_id"])
    value = (message.text or "").strip()
    limit = MAX_NOTES if field == "notes" else MAX_LEN
    if len(value) > limit:
        await message.answer(f"That value is too long (max {limit} characters).")
        return
    await services.deposits.upsert(account_id, {field: value}, utc_now_iso())
    await clear_state(state)
    account = await services.accounts.get(account_id)
    details = await services.deposits.get(account.id)
    await message.answer(deposit_text(account, details), reply_markup=deposit_fields_kb(account.id))


@router.callback_query(DepCB.filter(F.o == "clq"))
async def cb_clear_ask(query: CallbackQuery, callback_data: DepCB) -> None:
    await answer_callback(query)
    await safe_edit(
        query,
        "Clear all deposit details for this account? This cannot be undone.",
        confirm_action_kb(
            yes_data=DepCB(o="clr", i=callback_data.i).pack(),
            no_data=DepCB(o="view", i=callback_data.i).pack(),
            yes_text="🧹 Clear details",
        ),
    )


@router.callback_query(DepCB.filter(F.o == "clr"))
async def cb_clear(query: CallbackQuery, callback_data: DepCB, services: Services) -> None:
    await answer_callback(query, "Cleared")
    await services.deposits.delete(callback_data.i)
    try:
        account = await services.accounts.get(callback_data.i)
    except AccountError:
        await render_account(query, services, callback_data.i)
        return
    await safe_edit(query, deposit_text(account, None), deposit_kb(account.id))
