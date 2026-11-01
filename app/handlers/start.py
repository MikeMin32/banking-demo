"""Start, menu, help, and cancel commands plus main navigation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message

from app.handlers.accounts import render_account
from app.handlers.common import show_dashboard
from app.keyboards.accounts import overview_kb
from app.keyboards.callbacks import AccCB, FormCB, MenuCB
from app.keyboards.common import back_main_kb
from app.services.container import Services
from app.utils.formatting import HELP_TEXT, overview_pages
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state

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
    data = await state.get_data()
    account_id = data.get("account_id")
    await clear_state(state)
    if account_id:
        await render_account(message, services, int(account_id))
        return
    await show_dashboard(message, services, state)


@router.callback_query(MenuCB.filter(F.a == "menu"))
async def cb_menu(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await show_dashboard(query, services, state)


@router.callback_query(MenuCB.filter(F.a == "help"))
async def cb_help(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await query.message.answer(HELP_TEXT, reply_markup=back_main_kb()) if query.message else None


@router.callback_query(FormCB.filter(F.o == "cancel"))
async def cb_form_cancel(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query, "Cancelled")
    data = await state.get_data()
    account_id = data.get("account_id")
    await clear_state(state)
    if account_id:
        await render_account(query, services, int(account_id))
        return
    await show_dashboard(query, services, state)


@router.callback_query(MenuCB.filter(F.a == "overview"))
async def cb_overview(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    pages = overview_pages(snap, services.tz)
    await render_screen(query, "balance-summary", pages[0], overview_kb(page=0, total_pages=len(pages)))


@router.callback_query(AccCB.filter(F.o == "ovw"))
async def cb_overview_page(query: CallbackQuery, callback_data: AccCB, services: Services) -> None:
    await answer_callback(query)
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    pages = overview_pages(snap, services.tz)
    page = min(max(callback_data.p, 0), len(pages) - 1)
    await render_screen(query, "balance-summary", pages[page], overview_kb(page=page, total_pages=len(pages)))


@router.message(StateFilter(default_state), F.text & ~F.text.startswith("/"))
async def unhandled_text(message: Message) -> None:
    await message.answer("Please use the buttons below, or send /menu.")
