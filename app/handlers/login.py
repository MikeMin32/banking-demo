"""Login references. Never displays or stores bank passwords."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.keyboards.callbacks import AccCB
from app.services.container import Services
from app.utils.formatting import login_text
from app.utils.telegram import answer_callback, clear_state, safe_edit

router = Router(name="login")


@router.callback_query(AccCB.filter(F.o == "log"))
async def cb_login(query: CallbackQuery, callback_data: AccCB, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    account = await services.accounts.get(callback_data.i)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from app.keyboards.callbacks import MenuCB

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data=AccCB(o="view", i=account.id).pack()),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=MenuCB(a="menu").pack()),
    )
    await safe_edit(query, login_text(account), builder.as_markup())
