"""Minimal settings: reminder toggle. Backup is owner-only."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.callbacks import MenuCB, SetCB
from app.keyboards.settings import settings_kb
from app.services.backup import backup_database
from app.services.container import Services
from app.utils.screens import render_screen
from app.utils.telegram import answer_callback, clear_state, send_document

logger = logging.getLogger(__name__)
router = Router(name="settings")


def _settings_text(enabled: bool) -> str:
    if enabled:
        return "<b>⚙️ SETTINGS</b>\n\n🔔 Reminders: Enabled"
    return "<b>⚙️ SETTINGS</b>\n\n🔕 Reminders: Disabled"


async def _render_settings(target: Message | CallbackQuery, services: Services) -> None:
    settings = await services.reminders.get_settings()
    await render_screen(target, "settings", _settings_text(settings.enabled), settings_kb(settings))


@router.callback_query(MenuCB.filter(F.a == "settings"))
@router.callback_query(SetCB.filter(F.o == "home"))
async def cb_settings(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await _render_settings(query, services)


@router.callback_query(SetCB.filter(F.o == "tog"))
async def cb_toggle(query: CallbackQuery, services: Services) -> None:
    current = await services.reminders.get_settings()
    updated = await services.reminders.set_enabled(not current.enabled)
    await answer_callback(query, "Reminders on" if updated.enabled else "Reminders off")
    if services.on_reminder_settings_changed is not None:
        await services.on_reminder_settings_changed()
    await _render_settings(query, services)


@router.message(Command("backup"))
async def do_backup(message: Message, services: Services, is_owner: bool = False) -> None:
    if not is_owner:
        await message.answer("Database backup is limited to the owner.")
        return
    dest_dir = Path(services.settings.database_path).resolve().parent / "backups"
    try:
        path = await backup_database(services.db, dest_dir)
    except Exception:
        logger.exception("backup failed")
        await message.answer("Backup failed. Check the server logs.")
        return
    await send_document(
        message,
        path.name,
        path.read_bytes(),
        "SQLite snapshot created with the online backup API. Keep this file private.",
    )
