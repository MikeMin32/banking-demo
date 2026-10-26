"""Reminder screen and mark-all-checked flow."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.keyboards.callbacks import MenuCB, SetCB
from app.keyboards.settings import mark_all_confirm_kb, reminders_kb
from app.services.container import Services
from app.utils.formatting import reminder_text
from app.utils.telegram import answer_callback, clear_state, safe_edit

router = Router(name="reminders")


@router.callback_query(MenuCB.filter(F.a == "reminders"))
async def cb_reminders(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    settings, stale = await services.reminders.stale_accounts()
    extra = (
        f"\n\nReminders are <b>{'on' if settings.enabled else 'off'}</b>"
        f" at {settings.reminder_time} ({services.settings.timezone})."
    )
    await safe_edit(
        query,
        reminder_text(stale, services.tz, settings.stale_hours) + extra,
        reminders_kb(stale),
    )


@router.callback_query(SetCB.filter(F.o == "macq"))
async def cb_mark_all_ask(query: CallbackQuery) -> None:
    await answer_callback(query)
    await safe_edit(
        query,
        "Mark <b>all active accounts</b> as checked now?\n"
        "Balances will not change — only the last-checked timestamp is updated.",
        mark_all_confirm_kb(),
    )


@router.callback_query(SetCB.filter(F.o == "mac"))
async def cb_mark_all(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    count = await services.balances.confirm_all_checked()
    await answer_callback(query, f"Checked {count} account(s)")
    await cb_reminders(query, services, state)
