"""Start, menu, help, and cancel commands plus main navigation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message

from app.handlers.common import show_dashboard
from app.keyboards.callbacks import AccCB, FormCB, MenuCB
from app.keyboards.common import back_main_kb
from app.services.container import Services
from app.utils.formatting import HELP_TEXT, overview_pages
from app.utils.telegram import answer_callback, clear_state, safe_edit

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, services: Services, state: FSMContext) -> None:
    await show_dashboard(message, services, state)


@router.message(Command("menu"))
async def cmd_menu(message: Message, services: Services, state: FSMContext) -> None:
    await show_dashboard(message, services, state)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await clear_state(state)
    await message.answer(HELP_TEXT, reply_markup=back_main_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, services: Services, state: FSMContext) -> None:
    current = await state.get_state()
    await show_dashboard(message, services, state)
    if current is None:
        await message.answer("Nothing to cancel — you are on the main menu.")


@router.callback_query(MenuCB.filter(F.a == "menu"))
async def cb_menu(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await show_dashboard(query, services, state)


@router.callback_query(MenuCB.filter(F.a == "help"))
async def cb_help(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await safe_edit(query, HELP_TEXT, back_main_kb())


@router.callback_query(FormCB.filter(F.o == "cancel"))
async def cb_form_cancel(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Cancelled")
    await show_dashboard(query, services, state)


@router.callback_query(MenuCB.filter(F.a == "overview"))
async def cb_overview(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    pages = overview_pages(snap, services.tz, compact=reminder.compact_overview)
    from app.keyboards.callbacks import AccCB
    from app.keyboards.common import _nav_row
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    if len(pages) > 1:
        from aiogram.types import InlineKeyboardButton

        builder.row(
            InlineKeyboardButton(text="➡️ Next", callback_data=AccCB(o="ovw", p=1).pack()),
        )
    _nav_row(builder, back="menu")
    await safe_edit(query, pages[0], builder.as_markup())


@router.callback_query(AccCB.filter(F.o == "ovw"))
async def cb_overview_page(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    from app.keyboards.common import _nav_row
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    await answer_callback(query)
    callback = callback_data
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    pages = overview_pages(snap, services.tz, compact=reminder.compact_overview)
    page = min(max(callback.p, 0), len(pages) - 1)
    builder = InlineKeyboardBuilder()
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=AccCB(o="ovw", p=page - 1).pack()))
    if page < len(pages) - 1:
        buttons.append(InlineKeyboardButton(text="➡️ Next", callback_data=AccCB(o="ovw", p=page + 1).pack()))
    if buttons:
        builder.row(*buttons)
    _nav_row(builder, back="menu")
    await safe_edit(query, pages[page], builder.as_markup())


@router.message(StateFilter(default_state), F.text & ~F.text.startswith("/"))
async def unhandled_text(message: Message) -> None:
    await message.answer("Please use the buttons below, or send /menu.")
