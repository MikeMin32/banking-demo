"""Shared handler helpers."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.common import main_menu_kb
from app.services.container import Services
from app.utils.formatting import dashboard_text
from app.utils.telegram import clear_state, safe_edit


async def show_dashboard(
    target: Message | CallbackQuery,
    services: Services,
    state: FSMContext | None = None,
) -> None:
    await clear_state(state)
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    await safe_edit(target, dashboard_text(snap, services.tz), main_menu_kb())


async def current_account_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    value = data.get("account_id")
    return int(value) if value is not None else None
