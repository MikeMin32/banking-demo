"""Login details. Passwords are masked unless the owner explicitly reveals them."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.accounts import login_edit_kb
from app.keyboards.callbacks import AccCB
from app.keyboards.settings import login_kb
from app.services.accounts import AccountError
from app.services.container import Services
from app.utils.account_context import account_body
from app.utils.formatting import login_section
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

router = Router(name="login")

PASSWORD_WARNING = (
    "Telegram chat history can retain this message. "
    "Treat the revealed password as exposed to this chat."
)


async def render_login(
    target: Message | CallbackQuery,
    services: Services,
    account_id: int,
    *,
    can_reveal: bool | None = None,
) -> None:
    account = await services.accounts.get(account_id)
    if can_reveal is None:
        can_reveal = False
    _, text = await account_body(services, account.id, login_section(account))
    await render_screen(
        target,
        "login-details",
        text,
        login_kb(account.id, can_reveal=can_reveal),
    )


@router.callback_query(AccCB.filter(F.o == "log"))
async def cb_login(
    query: CallbackQuery,
    callback_data: AccCB,
    services: Services,
    state: FSMContext,
    can_view_credentials: bool = False,
) -> None:
    await answer_callback(query)
    await clear_state(state)
    await render_login(query, services, callback_data.i, can_reveal=can_view_credentials)


@router.callback_query(AccCB.filter(F.o == "led"))
async def cb_login_edit(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await state.clear()
    await state.update_data(account_id=callback_data.i, return_to="login")
    _, text = await account_body(services, callback_data.i, "Choose a field to change:")
    await render_screen(query, "login-details", text, login_edit_kb(callback_data.i))


@router.callback_query(AccCB.filter(F.o == "pw"))
async def cb_show_password(
    query: CallbackQuery,
    callback_data: AccCB,
    services: Services,
    can_view_credentials: bool = False,
) -> None:
    if not can_view_credentials:
        await query.answer("Only the owner can view stored passwords.", show_alert=True)
        return
    try:
        account = await services.accounts.get(callback_data.i)
        password = services.accounts.reveal_password(account)
    except AccountError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    if not password:
        await query.answer("No password is stored for this account.", show_alert=True)
        return
    await answer_callback(query)
    if query.message:
        _, text = await account_body(
            services,
            account.id,
            "<b>👁 Password revealed</b>\n"
            f"<code>{escape(password)}</code>\n\n"
            f"<i>{PASSWORD_WARNING}</i>",
        )
        await query.message.answer(text)
