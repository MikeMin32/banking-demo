"""Account list, grouped-template creation, edit, archive, and delete."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.accounts import (
    account_edit_kb,
    account_view_kb,
    accounts_list_kb,
    create_confirm_kb,
    create_fields_kb,
    currency_kb,
    provider_kb,
)
from app.keyboards.callbacks import AccCB, AccFieldCB, FormCB, MenuCB, PickCB
from app.keyboards.common import PAGE_SIZE, confirm_action_kb, form_kb
from app.services.accounts import AccountDraft, AccountError, CurrencyChangeNeedsConfirm
from app.services.container import Services
from app.services.money import UI_CURRENCIES
from app.services.templates import BANK_TEMPLATE, LOGIN_TEMPLATE, parse_bank_block, parse_login_block
from app.states.forms import AccountForm
from app.utils.account_context import account_body
from app.utils.formatting import account_card, e, mask_password
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state, try_delete

router = Router(name="accounts")

_FIELD_LABELS = {
    "bank_name": "bank provider",
    "iban": "IBAN",
    "bin": "BIN",
    "currency": "currency",
    "line_name": "line",
    "linked_vm": "VM",
    "stored_where": "stored where",
    "login_mobile": "mobile number",
    "login_email": "email",
    "login_password": "password",
    "two_fa_method": "2FA method",
    "vm_number": "VM number",
    "company_name": "company name",
    "login_url": "login URL",
    "login_username": "login username",
    "password_manager_ref": "password manager item",
    "notes": "notes",
}


def _draft_from_state(data: dict) -> AccountDraft:
    return AccountDraft(
        bank_name=str(data.get("bank_name") or ""),
        currency=str(data.get("currency") or ""),
        balance_raw=str(data.get("balance_raw") or "0"),
        line_name=data.get("line_name"),
        linked_vm=data.get("linked_vm"),
        stored_where=data.get("stored_where"),
        iban=data.get("iban"),
        bin=data.get("bin"),
        login_mobile=data.get("login_mobile"),
        login_email=data.get("login_email"),
        login_password=data.get("login_password"),
        two_fa_method=data.get("two_fa_method"),
    )


def _review_text(data: dict) -> str:
    return (
        "<b>REVIEW ACCOUNT</b>\n\n"
        f"Bank: {e(data.get('bank_name'))}\n"
        f"IBAN: <code>{e(data.get('iban'))}</code>\n"
        f"BIN: <code>{e(data.get('bin'))}</code>\n"
        f"Currency: {e(data.get('currency'))}\n"
        f"Line: {e(data.get('line_name'))}\n"
        f"VM: {e(data.get('linked_vm'))}\n"
        f"Stored: {e(data.get('stored_where'))}\n"
        f"Balance: {e(data.get('balance_raw') or '0')}\n\n"
        f"Mobile: <code>{e(data.get('login_mobile'))}</code>\n"
        f"Email: <code>{e(data.get('login_email'))}</code>\n"
        f"Password: {mask_password(data.get('login_password'))}\n"
        f"2FA: {e(data.get('two_fa_method'))}"
    )


async def _list_accounts(query: CallbackQuery, services: Services, *, archived: bool, page: int) -> None:
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    items, total = await services.accounts.page(archived=archived, page=page, page_size=PAGE_SIZE)
    available = {
        account.id: account.balance_minor - snap.pending_by_account.get(account.id, 0)
        for account in items
    }
    if not items and page == 0:
        text = "No accounts in this list yet." if not archived else "No archived accounts."
    elif archived:
        text = "Archived accounts:"
    else:
        totals_map = await services.totals.for_accounts(items)
        from app.utils.account_context import account_identity_line, totals_block
        from app.utils.formatting import accounts_page_summary

        blocks = [
            f"{account_identity_line(account)}\n{totals_block(totals_map[account.id], compact=True)}"
            for account in items
        ]
        text = accounts_page_summary(blocks)
    await render_screen(
        query,
        "accounts",
        text,
        accounts_list_kb(items, page=page, total=total, archived=archived, available_by_account=available),
    )


async def render_account(target: Message | CallbackQuery, services: Services, account_id: int, *, page: int = 0) -> None:
    account = await services.accounts.get(account_id)
    totals = await services.totals.for_account(account.id)
    await render_screen(
        target,
        "account-details",
        account_card(
            account,
            services.tz,
            pending_minor=totals.expected_minor,
            totals=totals,
        ),
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
    await state.set_state(AccountForm.bank_block)
    await render_screen(
        query,
        "add-account",
        "<b>➕ ADD ACCOUNT</b>\n\n"
        "Copy the template, fill it in, and send it as one message.\n"
        "Required: Bank Provider, Currency, Line.\n\n"
        f"<code>{escape(BANK_TEMPLATE)}</code>",
        form_kb(),
    )


@router.message(AccountForm.bank_block)
async def form_bank_block(message: Message, state: FSMContext) -> None:
    try:
        parsed = parse_bank_block(message.text or "")
    except AccountError as exc:
        await message.answer(str(exc), reply_markup=form_kb())
        return
    await state.update_data(**parsed)
    await state.set_state(AccountForm.login_block)
    await message.answer(
        "<b>LOGIN &amp; SECURITY</b>\n\n"
        "Copy the template, fill any fields you have, and send it as one message.\n"
        "Empty fields are allowed.\n\n"
        f"<code>{escape(LOGIN_TEMPLATE)}</code>",
        reply_markup=form_kb(),
    )


@router.message(AccountForm.login_block)
async def form_login_block(message: Message, state: FSMContext) -> None:
    try:
        parsed = parse_login_block(message.text or "")
    except AccountError as exc:
        await message.answer(str(exc), reply_markup=form_kb())
        return
    if parsed.get("login_password"):
        await try_delete(message)
    await state.update_data(**parsed)
    await _show_review(message, state)


async def _show_review(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AccountForm.confirm)
    if isinstance(target, CallbackQuery):
        await render_screen(target, "add-account", _review_text(data), create_confirm_kb())
    else:
        await target.answer(_review_text(data), reply_markup=create_confirm_kb())


@router.callback_query(FormCB.filter(F.o == "review"), AccountForm.confirm)
@router.callback_query(FormCB.filter(F.o == "review"), AccountForm.edit_value)
async def cb_review(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await _show_review(query, state)


@router.callback_query(FormCB.filter(F.o == "edit"), AccountForm.confirm)
async def cb_edit_draft(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.set_state(AccountForm.edit_value)
    await render_screen(
        query,
        "add-account",
        "<b>✏️ EDIT INFORMATION</b>\nChoose a field to change.",
        create_fields_kb(),
    )


@router.callback_query(FormCB.filter(F.o == "ok"), AccountForm.confirm)
async def form_create(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Saving…")
    data = await state.get_data()
    await state.clear()
    try:
        account = await services.accounts.create(_draft_from_state(data))
    except AccountError as exc:
        await render_screen(query, "add-account", f"{exc}\n\nPlease start again from Add Account.", form_kb())
        return
    await render_account(query, services, account.id)


@router.callback_query(AccCB.filter(F.o == "edt"))
async def cb_edit_menu(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account = await services.accounts.get(callback_data.i)
    _, text = await account_body(
        services,
        account.id,
        "Change a field, or use the actions below.",
    )
    await render_screen(query, "account-details", text, account_edit_kb(account.id))


@router.callback_query(AccFieldCB.filter())
async def cb_edit_field(query: CallbackQuery, callback_data: AccFieldCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    field = callback_data.f
    if callback_data.i == 0:
        data = await state.get_data()
        current = data.get("login_password") if field == "login_password" else data.get(field)
        await state.set_state(AccountForm.edit_value)
        await state.update_data(account_id=0, field=field, return_to="draft")
        await _prompt_field(query, field, current, account_id=None, services=None)
        return

    account = await services.accounts.get(callback_data.i)
    current = "••••••••" if field == "login_password" and account.has_password else getattr(account, field, None)
    previous = await state.get_data()
    return_to = previous.get("return_to") or "account"
    await state.set_state(AccountForm.edit_value)
    await state.update_data(account_id=account.id, field=field, return_to=return_to)
    await _prompt_field(query, field, current, account_id=account.id, services=services)


async def _prompt_field(
    target: CallbackQuery,
    field: str,
    current: object,
    *,
    account_id: int | None,
    services: Services | None = None,
) -> None:
    if field == "bank_name":
        body = f"<b>✏️ EDIT FIELD</b>\nSelect a banking provider.\nCurrent: <code>{e(current)}</code>"
    elif field == "currency":
        body = (
            f"<b>✏️ EDIT FIELD</b>\nSelect currency.\nCurrent: <code>{e(current)}</code>\n"
            "USD and EUR stay separate. This does not convert the balance."
        )
    else:
        extra = ""
        if field == "login_password":
            extra = "\nThe incoming message will be deleted when possible."
        body = (
            f"<b>✏️ EDIT FIELD</b>\n"
            f"Send a new {_FIELD_LABELS.get(field, field)}.\n"
            f"Current: <code>{e(current)}</code>{extra}"
        )
    if account_id is not None and services is not None:
        _, text = await account_body(services, account_id, body)
    else:
        text = body
    if field == "bank_name":
        await render_screen(
            target,
            "add-account" if account_id is None else "account-details",
            text,
            provider_kb(account_id=account_id),
        )
        return
    if field == "currency":
        await render_screen(
            target,
            "add-account" if account_id is None else "account-details",
            text,
            currency_kb(account_id=account_id),
        )
        return
    skip = field not in {"bank_name", "currency", "line_name"}
    back = "menu" if account_id is None else f"acc:{account_id}"
    await render_screen(
        target,
        "add-account" if account_id is None else "account-details",
        text,
        form_kb(skip=skip, keep=True, back=back),
    )


async def _currency_activity(services: Services, account_id: int) -> tuple[int, int]:
    _, _, history_count = await services.balances.history_page(account_id, page=0, page_size=1)
    withdrawal_count = (await services.withdrawals.page(status=None, account_id=account_id, page=0, page_size=1))[1]
    return history_count, withdrawal_count


async def _after_account_edit(target: Message | CallbackQuery, services: Services, state: FSMContext, account_id: int) -> None:
    data = await state.get_data()
    return_to = data.get("return_to")
    await clear_state(state)
    if return_to == "login":
        from app.handlers.login import render_login

        await render_login(target, services, account_id)
        return
    await render_account(target, services, account_id)


@router.callback_query(PickCB.filter(F.k == "cur"), AccountForm.edit_value)
async def edit_currency_pick(query: CallbackQuery, callback_data: PickCB, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if callback_data.v not in UI_CURRENCIES:
        await query.answer("Please choose USD or EUR.", show_alert=True)
        return
    if int(data.get("account_id") or 0) == 0:
        await answer_callback(query)
        await state.update_data(currency=callback_data.v)
        await _show_review(query, state)
        return
    account_id = int(data["account_id"])
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
        _, text = await account_body(
            services,
            account_id,
            f"<b>✏️ CHANGE CURRENCY</b>\n\n"
            f"Change the currency label to <b>{callback_data.v}</b>?\n\n"
            "This does <b>not</b> convert the stored balance or history.",
        )
        await render_screen(
            query,
            "account-details",
            text,
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
    await _after_account_edit(query, services, state, account.id)


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
    await _after_account_edit(query, services, state, account.id)


@router.callback_query(PickCB.filter(F.k == "prv"), AccountForm.edit_value)
async def edit_provider_pick(query: CallbackQuery, callback_data: PickCB, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if callback_data.v == "OTHER":
        await answer_callback(query)
        await render_screen(query, "add-account", "Send the banking provider name.", form_kb(keep=True))
        return
    await answer_callback(query)
    if int(data.get("account_id") or 0) == 0:
        await state.update_data(bank_name=callback_data.v)
        await _show_review(query, state)
        return
    account = await services.accounts.update(int(data["account_id"]), bank_name=callback_data.v)
    await _after_account_edit(query, services, state, account.id)


@router.callback_query(FormCB.filter(F.o == "keep"), AccountForm.edit_value)
async def edit_keep(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Unchanged")
    data = await state.get_data()
    if int(data.get("account_id") or 0) == 0:
        await _show_review(query, state)
        return
    await _after_account_edit(query, services, state, int(data["account_id"]))


@router.callback_query(FormCB.filter(F.o == "skip"), AccountForm.edit_value)
async def edit_clear(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    data = await state.get_data()
    field = str(data["field"])
    if int(data.get("account_id") or 0) == 0:
        if field in {"bank_name", "currency", "line_name"}:
            await query.answer("That field is required.", show_alert=True)
            return
        await state.update_data(**{field: None})
        await _show_review(query, state)
        return
    if field in {"bank_name", "currency", "line_name"}:
        await query.answer("That field is required.", show_alert=True)
        return
    account = await services.accounts.update(int(data["account_id"]), **{field: None})
    await _after_account_edit(query, services, state, account.id)


@router.message(AccountForm.edit_value)
async def edit_value(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    field = str(data.get("field") or "")
    if field == "currency":
        await message.answer("Please tap 🇺🇸 USD or 🇪🇺 EUR.", reply_markup=currency_kb(account_id=int(data.get("account_id") or 0) or None))
        return
    value = (message.text or "").strip()
    if field == "login_password":
        await try_delete(message)
    if int(data.get("account_id") or 0) == 0:
        await state.update_data(**{field: value})
        await _show_review(message, state)
        return
    try:
        account = await services.accounts.update(int(data["account_id"]), **{field: value})
    except AccountError as exc:
        await message.answer(str(exc), reply_markup=form_kb(keep=True, back=f"acc:{data['account_id']}"))
        return
    await _after_account_edit(message, services, state, account.id)


@router.callback_query(AccCB.filter(F.o == "arq"))
async def cb_archive_ask(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    await answer_callback(query)
    account = await services.accounts.get(callback_data.i)
    if account.is_archived:
        body = "<b>📦 RESTORE ACCOUNT</b>\n\nRestore this account to the active list?"
        yes = AccCB(o="uar", i=callback_data.i).pack()
        yes_text = "✅ Restore"
    else:
        body = (
            "<b>📦 ARCHIVE ACCOUNT</b>\n\n"
            "Archive this account? It will drop out of active totals but stay in Archived Accounts."
        )
        yes = AccCB(o="arc", i=callback_data.i).pack()
        yes_text = "📦 Archive"
    _, text = await account_body(services, account.id, body)
    await render_screen(
        query,
        "account-details",
        text,
        confirm_action_kb(
            yes_data=yes,
            no_data=AccCB(o="edt", i=callback_data.i).pack(),
            yes_text=yes_text,
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
    _, text = await account_body(
        services,
        account.id,
        f"<b>🗑️ DELETE ACCOUNT</b>\n\n"
        f"Delete <b>{e(account.line_label)}</b> permanently?\n"
        "Balance history, charges, and top-ups for this account will also be removed.\n"
        "This cannot be undone.",
    )
    await render_screen(
        query,
        "account-details",
        text,
        confirm_action_kb(
            yes_data=AccCB(o="dly", i=callback_data.i).pack(),
            no_data=AccCB(o="edt", i=callback_data.i).pack(),
            yes_text="🗑️ Delete forever",
        ),
    )


@router.callback_query(AccCB.filter(F.o == "dly"))
async def cb_delete(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Deleted")
    await services.accounts.delete(callback_data.i)
    await _list_accounts(query, services, archived=False, page=0)
