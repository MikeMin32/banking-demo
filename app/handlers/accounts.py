"""Account list, wizard, edit, archive, and delete."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.accounts import (
    account_edit_kb,
    account_view_kb,
    accounts_list_kb,
    currency_kb,
    provider_kb,
)
from app.keyboards.callbacks import AccCB, AccFieldCB, FormCB, MenuCB, PickCB
from app.keyboards.common import PAGE_SIZE, confirm_action_kb, form_kb
from app.services.accounts import AccountDraft, AccountError, CurrencyChangeNeedsConfirm
from app.services.container import Services
from app.services.dashboard import is_stale
from app.services.money import UI_CURRENCIES
from app.services.naming import NamingError, clean_company_name, parse_vm_number, resolve_display_name
from app.states.forms import AccountForm
from app.utils.formatting import account_card, e
from app.utils.telegram import answer_callback, clear_state, safe_edit
from app.utils.time import utc_now

router = Router(name="accounts")


async def _list_accounts(query: CallbackQuery, services: Services, *, archived: bool, page: int) -> None:
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    items, total = await services.accounts.page(archived=archived, page=page, page_size=PAGE_SIZE)
    title = "📦 Archived accounts" if archived else "🏦 Accounts"
    if not items and page == 0:
        text = f"<b>{title}</b>\n\nNo accounts in this list yet."
    else:
        text = f"<b>{title}</b>\nSelect an account to open it."
    await safe_edit(
        query,
        text,
        accounts_list_kb(items, page=page, total=total, archived=archived, stale_ids=snap.stale_ids),
    )


async def render_account(target: Message | CallbackQuery, services: Services, account_id: int, *, page: int = 0) -> None:
    account = await services.accounts.get(account_id)
    reminder = await services.reminders.get_settings()
    projection = await services.withdrawals.projection(account.id)
    stale = is_stale(account, now=utc_now(), stale_hours=reminder.stale_hours)
    await safe_edit(
        target,
        account_card(account, services.tz, pending_minor=projection.pending_minor, stale=stale),
        account_view_kb(account, from_page=page),
    )


@router.callback_query(MenuCB.filter(F.a == "accounts"))
@router.callback_query(AccCB.filter(F.o == "list"))
async def cb_list(query: CallbackQuery, callback_data: AccCB | MenuCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    page = callback_data.p if isinstance(callback_data, AccCB) else 0
    await _list_accounts(query, services, archived=False, page=page)


@router.callback_query(AccCB.filter(F.o == "alst"))
async def cb_archived(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await _list_accounts(query, services, archived=True, page=callback_data.p)


@router.callback_query(AccCB.filter(F.o == "view"))
async def cb_view(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    try:
        await render_account(query, services, callback_data.i, page=callback_data.p)
    except AccountError as exc:
        await query.answer(str(exc), show_alert=True)
        await _list_accounts(query, services, archived=False, page=0)


@router.callback_query(MenuCB.filter(F.a == "add"))
async def cb_add(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.clear()
    await state.set_state(AccountForm.vm_number)
    await safe_edit(
        query,
        "<b>➕ New account</b>\n\nEnter the VM number.\nExample: <code>9</code>",
        form_kb(),
    )


@router.message(AccountForm.vm_number)
async def form_vm_number(message: Message, state: FSMContext) -> None:
    try:
        number = parse_vm_number(message.text or "")
    except NamingError as exc:
        await message.answer(str(exc), reply_markup=form_kb())
        return
    await state.update_data(vm_number=number)
    await state.set_state(AccountForm.company)
    await message.answer("Enter the company name.\nExample: <i>LeBon Shoppe</i>", reply_markup=form_kb())


@router.message(AccountForm.company)
async def form_company(message: Message, state: FSMContext) -> None:
    try:
        company = clean_company_name(message.text or "")
    except NamingError as exc:
        await message.answer(str(exc), reply_markup=form_kb())
        return
    await state.update_data(company_name=company)
    await state.set_state(AccountForm.provider)
    await message.answer("<b>🏦 Select Banking Provider</b>", reply_markup=provider_kb())


@router.callback_query(PickCB.filter(F.k == "prv"), AccountForm.provider)
async def form_provider_pick(query: CallbackQuery, callback_data: PickCB, state: FSMContext) -> None:
    await answer_callback(query)
    if callback_data.v == "OTHER":
        await state.set_state(AccountForm.provider_other)
        await safe_edit(query, "Send the banking provider name.", form_kb())
        return
    await state.update_data(bank_name=callback_data.v)
    await _ask_currency(query, state)


@router.message(AccountForm.provider_other)
async def form_provider_other(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if not name:
        await message.answer("Banking provider cannot be empty.", reply_markup=form_kb())
        return
    await state.update_data(bank_name=name)
    await state.set_state(AccountForm.currency)
    await message.answer("<b>Select Account Currency:</b>", reply_markup=currency_kb())


async def _ask_currency(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AccountForm.currency)
    text = "<b>Select Account Currency:</b>"
    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, currency_kb())
    else:
        await target.answer(text, reply_markup=currency_kb())


@router.callback_query(PickCB.filter(F.k == "cur"), AccountForm.currency)
async def form_currency_pick(query: CallbackQuery, callback_data: PickCB, state: FSMContext) -> None:
    await answer_callback(query)
    if callback_data.v not in UI_CURRENCIES:
        await query.answer("Please choose USD or EUR.", show_alert=True)
        return
    await state.update_data(currency=callback_data.v)
    await state.set_state(AccountForm.balance)
    await safe_edit(
        query,
        f"Currency set to <b>{callback_data.v}</b>.\nSend the current balance. Zero and negative amounts are allowed.",
        form_kb(zero=True),
    )


@router.message(AccountForm.currency)
async def form_currency_text(message: Message) -> None:
    await message.answer("Please tap 🇺🇸 USD or 🇪🇺 EUR.", reply_markup=currency_kb())


@router.callback_query(FormCB.filter(F.o == "zero"), AccountForm.balance)
async def form_balance_zero(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(balance_raw="0")
    await _ask_login_url(query, state)


@router.message(AccountForm.balance)
async def form_balance(message: Message, state: FSMContext) -> None:
    await state.update_data(balance_raw=(message.text or "").strip())
    await _ask_login_url(message, state)


async def _ask_login_url(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AccountForm.login_url)
    text = (
        "Optional: login URL for the bank or platform.\n"
        "<i>Do not send a password. A link is enough.</i>"
    )
    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, form_kb(skip=True))
    else:
        await target.answer(text, reply_markup=form_kb(skip=True))


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.login_url)
async def skip_url(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(login_url=None)
    await state.set_state(AccountForm.login_username)
    await safe_edit(query, "Optional: login username or email.", form_kb(skip=True))


@router.message(AccountForm.login_url)
async def form_url(message: Message, state: FSMContext) -> None:
    await state.update_data(login_url=(message.text or "").strip())
    await state.set_state(AccountForm.login_username)
    await message.answer("Optional: login username or email.", reply_markup=form_kb(skip=True))


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.login_username)
async def skip_username(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(login_username=None)
    await _ask_vault(query, state)


@router.message(AccountForm.login_username)
async def form_username(message: Message, state: FSMContext) -> None:
    await state.update_data(login_username=(message.text or "").strip())
    await _ask_vault(message, state)


async def _ask_vault(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AccountForm.vault)
    text = (
        "Optional: password-manager item name or vault URL.\n"
        "⚠️ <b>Never send a bank password, OTP, or 2FA backup code.</b>"
    )
    markup = form_kb(skip=True)
    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.vault)
async def skip_vault(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(password_manager_ref=None)
    await state.set_state(AccountForm.notes)
    await safe_edit(query, "Optional: notes (authentication hints are fine — not secrets).", form_kb(skip=True))


@router.message(AccountForm.vault)
async def form_vault(message: Message, state: FSMContext) -> None:
    await state.update_data(password_manager_ref=(message.text or "").strip())
    await state.set_state(AccountForm.notes)
    await message.answer("Optional: notes (authentication hints are fine — not secrets).", reply_markup=form_kb(skip=True))


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.notes)
async def skip_notes(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.update_data(notes=None)
    await _show_confirm(query, state)


@router.message(AccountForm.notes)
async def form_notes(message: Message, state: FSMContext) -> None:
    await state.update_data(notes=(message.text or "").strip())
    await _show_confirm(message, state)


async def _show_confirm(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AccountForm.confirm)
    name = resolve_display_name(data.get("vm_number"), data.get("company_name"))
    text = (
        "<b>Create this account?</b>\n\n"
        f"🏦 {e(name)}\n"
        f"Banking: {e(data.get('bank_name'))}\n"
        f"Currency: {e(data.get('currency'))}\n"
        f"Balance: {e(data.get('balance_raw'))}"
    )
    markup = confirm_action_kb(
        yes_data=FormCB(o="ok").pack(),
        no_data=FormCB(o="cancel").pack(),
        yes_text="✅ Create account",
        no_text="✖️ Cancel",
    )
    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(FormCB.filter(F.o == "ok"), AccountForm.confirm)
async def form_create(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Saving…")
    data = await state.get_data()
    await state.clear()
    try:
        account = await services.accounts.create(
            AccountDraft(
                vm_number=data.get("vm_number") or 0,
                company_name=str(data.get("company_name") or ""),
                bank_name=str(data.get("bank_name") or ""),
                currency=str(data.get("currency") or ""),
                balance_raw=str(data.get("balance_raw") or "0"),
                login_url=data.get("login_url"),
                login_username=data.get("login_username"),
                password_manager_ref=data.get("password_manager_ref"),
                notes=data.get("notes"),
            )
        )
    except AccountError as exc:
        await safe_edit(query, f"{exc}\n\nPlease start again from Add Account.", form_kb())
        return
    await render_account(query, services, account.id)


@router.callback_query(AccCB.filter(F.o == "edt"))
async def cb_edit_menu(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account = await services.accounts.get(callback_data.i)
    await safe_edit(
        query,
        f"<b>✏️ Edit {e(account.display_name)}</b>\nChoose a field to change.",
        account_edit_kb(account.id),
    )


@router.callback_query(AccFieldCB.filter())
async def cb_edit_field(query: CallbackQuery, callback_data: AccFieldCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    account = await services.accounts.get(callback_data.i)
    labels = {
        "vm_number": "VM number",
        "company_name": "company name",
        "bank_name": "banking provider",
        "currency": "currency",
        "login_url": "login URL",
        "login_username": "login username / email",
        "password_manager_ref": "password manager item / URL",
        "notes": "notes",
    }
    required = {"vm_number", "company_name", "bank_name", "currency"}
    current = getattr(account, callback_data.f)
    await state.set_state(AccountForm.edit_value)
    await state.update_data(account_id=account.id, field=callback_data.f)
    extra = ""
    if callback_data.f in {"login_url", "login_username", "password_manager_ref"}:
        extra = "\n⚠️ Do not send a bank password."
    if callback_data.f == "bank_name":
        await safe_edit(
            query,
            f"Select a banking provider.\nCurrent: <code>{e(current)}</code>",
            provider_kb(),
        )
        return
    if callback_data.f == "currency":
        await safe_edit(
            query,
            f"<b>Select New Currency:</b>\nCurrent: <code>{e(current)}</code>\n"
            "USD and EUR totals stay separate. Changing currency does not convert the balance.",
            currency_kb(account_id=account.id),
        )
        return
    await safe_edit(
        query,
        f"Send a new {labels[callback_data.f]}.\nCurrent: <code>{e(current)}</code>{extra}",
        form_kb(skip=callback_data.f not in required, keep=True, back=f"acc:{account.id}"),
    )


async def _currency_activity(services: Services, account_id: int) -> tuple[int, int]:
    _, _, history_count = await services.balances.history_page(account_id, page=0, page_size=1)
    withdrawal_count = (await services.withdrawals.page(status=None, account_id=account_id, page=0, page_size=1))[1]
    return history_count, withdrawal_count


@router.callback_query(PickCB.filter(F.k == "cur"), AccountForm.edit_value)
async def edit_currency_pick(query: CallbackQuery, callback_data: PickCB, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    if callback_data.v not in UI_CURRENCIES:
        await query.answer("Please choose USD or EUR.", show_alert=True)
        return
    history_count, withdrawal_count = await _currency_activity(services, account_id)
    try:
        account = await services.accounts.change_currency(
            account_id,
            callback_data.v,
            history_count=history_count,
            withdrawal_count=withdrawal_count,
        )
    except CurrencyChangeNeedsConfirm:
        await answer_callback(query)
        await state.update_data(pending_currency=callback_data.v)
        await safe_edit(
            query,
            f"Change the currency label to <b>{callback_data.v}</b>?\n\n"
            "This does <b>not</b> convert the stored balance or history. "
            "The same numbers will be shown with the new currency code.",
            confirm_action_kb(
                yes_data=FormCB(o="cury").pack(),
                no_data=AccCB(o="edt", i=account_id).pack(),
                yes_text=f"✅ Use {callback_data.v}",
            ),
        )
        return
    except AccountError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, f"Currency: {account.currency}")
    await clear_state(state)
    await render_account(query, services, account.id)


@router.callback_query(FormCB.filter(F.o == "cury"), AccountForm.edit_value)
async def edit_currency_confirm(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    currency = str(data.get("pending_currency") or "")
    account_id = int(data["account_id"])
    history_count, withdrawal_count = await _currency_activity(services, account_id)
    try:
        account = await services.accounts.change_currency(
            account_id,
            currency,
            confirmed=True,
            history_count=history_count,
            withdrawal_count=withdrawal_count,
        )
    except AccountError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await answer_callback(query, f"Currency: {account.currency}")
    await clear_state(state)
    await render_account(query, services, account.id)


@router.callback_query(PickCB.filter(F.k == "prv"), AccountForm.edit_value)
async def edit_provider_pick(query: CallbackQuery, callback_data: PickCB, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if callback_data.v == "OTHER":
        await answer_callback(query)
        await safe_edit(query, "Send the banking provider name.", form_kb(keep=True, back=f"acc:{data['account_id']}"))
        return
    await answer_callback(query)
    account = await services.accounts.update(int(data["account_id"]), bank_name=callback_data.v)
    await clear_state(state)
    await render_account(query, services, account.id)


@router.callback_query(FormCB.filter(F.o == "keep"), AccountForm.edit_value)
async def edit_keep(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Unchanged")
    data = await state.get_data()
    await clear_state(state)
    await render_account(query, services, int(data["account_id"]))


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.edit_value)
async def edit_clear(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    data = await state.get_data()
    field = data["field"]
    if field in {"vm_number", "company_name", "bank_name", "currency"}:
        await query.answer("That field is required.", show_alert=True)
        return
    account = await services.accounts.update(int(data["account_id"]), **{field: None})
    await clear_state(state)
    await render_account(query, services, account.id)


@router.message(AccountForm.edit_value)
async def edit_value(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("field") == "currency":
        await message.answer("Please tap 🇺🇸 USD or 🇪🇺 EUR.", reply_markup=currency_kb(account_id=int(data["account_id"])))
        return
    try:
        account = await services.accounts.update(int(data["account_id"]), **{data["field"]: message.text})
    except AccountError as exc:
        await message.answer(str(exc), reply_markup=form_kb(keep=True, back=f"acc:{data['account_id']}"))
        return
    await clear_state(state)
    await render_account(message, services, account.id)


@router.callback_query(AccCB.filter(F.o == "arq"))
async def cb_archive_ask(query: CallbackQuery, callback_data: AccCB) -> None:
    await answer_callback(query)
    await safe_edit(
        query,
        "Archive this account? It will drop out of active totals but stay in Archived Accounts.",
        confirm_action_kb(
            yes_data=AccCB(o="arc", i=callback_data.i).pack(),
            no_data=AccCB(o="view", i=callback_data.i).pack(),
            yes_text="📦 Archive",
        ),
    )


@router.callback_query(AccCB.filter(F.o == "arc"))
async def cb_archive(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    await answer_callback(query, "Archived")
    account = await services.accounts.archive(callback_data.i)
    await render_account(query, services, account.id)


@router.callback_query(AccCB.filter(F.o == "uar"))
async def cb_unarchive(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    await answer_callback(query, "Restored")
    account = await services.accounts.unarchive(callback_data.i)
    await render_account(query, services, account.id)


@router.callback_query(AccCB.filter(F.o == "dlq"))
async def cb_delete_ask(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    await answer_callback(query)
    account = await services.accounts.get(callback_data.i)
    await safe_edit(
        query,
        f"Delete <b>{e(account.display_name)}</b> permanently?\n"
        "Balance history, deposit details, and withdrawals for this account will also be removed.\n"
        "This cannot be undone.",
        confirm_action_kb(
            yes_data=AccCB(o="dly", i=callback_data.i).pack(),
            no_data=AccCB(o="view", i=callback_data.i).pack(),
            yes_text="🗑️ Delete forever",
        ),
    )


@router.callback_query(AccCB.filter(F.o == "dly"))
async def cb_delete(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Deleted")
    await services.accounts.delete(callback_data.i)
    await _list_accounts(query, services, archived=False, page=0)
