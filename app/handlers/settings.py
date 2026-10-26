"""Settings, exports, and database backup."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.callbacks import SetCB
from app.keyboards.common import back_main_kb, form_kb
from app.keyboards.settings import export_kb, settings_kb, stale_hours_kb
from app.services.backup import backup_database
from app.services.container import Services
from app.states.forms import SettingsForm
from app.utils.telegram import answer_callback, clear_state, safe_edit, send_document

logger = logging.getLogger(__name__)
router = Router(name="settings")

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


async def _render_settings(target: Message | CallbackQuery, services: Services) -> None:
    settings = await services.reminders.get_settings()
    text = (
        "<b>⚙️ Settings</b>\n\n"
        f"🔔 Reminders: <b>{'enabled' if settings.enabled else 'disabled'}</b>\n"
        f"🕘 Time: <b>{settings.reminder_time}</b> ({services.settings.timezone})\n"
        f"⚠️ Stale after: <b>{settings.stale_hours} hour(s)</b>\n"
        f"📋 Overview: <b>{'compact' if settings.compact_overview else 'detailed'}</b>\n\n"
        "CSV exports omit login URLs, vault references, and banking identifiers."
    )
    await safe_edit(target, text, settings_kb(settings))


@router.callback_query(F.data == "m:settings")
@router.callback_query(SetCB.filter(F.o == "home"))
async def cb_settings(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await _render_settings(query, services)


# MenuCB packed form varies; also bind the typed filter.
from app.keyboards.callbacks import MenuCB


@router.callback_query(MenuCB.filter(F.a == "settings"))
async def cb_settings_typed(query: CallbackQuery, services: Services, state: FSMContext) -> None:
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


@router.callback_query(SetCB.filter(F.o == "time"))
async def cb_time(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.set_state(SettingsForm.reminder_time)
    await safe_edit(
        query,
        "Send the reminder time as <code>HH:MM</code> in 24-hour format, for example <code>09:00</code>.",
        form_kb(back="settings"),
    )


@router.message(SettingsForm.reminder_time)
async def form_time(message: Message, services: Services, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not _TIME_RE.match(raw):
        await message.answer("Use HH:MM, for example 09:00 or 18:30.", reply_markup=form_kb(back="settings"))
        return
    await services.reminders.set_time(raw)
    if services.on_reminder_settings_changed is not None:
        await services.on_reminder_settings_changed()
    await clear_state(state)
    await message.answer(f"Reminder time set to {raw}.")
    await _render_settings(message, services)


@router.callback_query(SetCB.filter(F.o == "stale"))
async def cb_stale(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await safe_edit(query, "How long before an unchecked balance is considered stale?", stale_hours_kb())


@router.callback_query(SetCB.filter(F.o == "sh"))
async def cb_stale_set(query: CallbackQuery, callback_data: SetCB, services: Services) -> None:
    hours = int(callback_data.v)
    await services.reminders.set_stale_hours(hours)
    await answer_callback(query, f"Stale after {hours}h")
    await _render_settings(query, services)


@router.callback_query(SetCB.filter(F.o == "shc"))
async def cb_stale_custom(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await state.set_state(SettingsForm.stale_hours)
    await safe_edit(query, "Send the number of hours (1–720).", form_kb(back="settings"))


@router.message(SettingsForm.stale_hours)
async def form_stale(message: Message, services: Services, state: FSMContext) -> None:
    try:
        hours = int((message.text or "").strip())
        await services.reminders.set_stale_hours(hours)
    except ValueError as exc:
        await message.answer(str(exc) or "Enter a whole number of hours.", reply_markup=form_kb(back="settings"))
        return
    await clear_state(state)
    await _render_settings(message, services)


@router.callback_query(SetCB.filter(F.o == "comp"))
async def cb_compact(query: CallbackQuery, services: Services) -> None:
    current = await services.reminders.get_settings()
    updated = await services.reminders.set_compact_overview(not current.compact_overview)
    await answer_callback(query, "Compact" if updated.compact_overview else "Detailed")
    await _render_settings(query, services)


@router.callback_query(SetCB.filter(F.o == "exp"))
async def cb_export_menu(query: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(query)
    await clear_state(state)
    await safe_edit(
        query,
        "<b>📤 CSV exports</b>\n"
        "Files exclude login URLs, password-manager references, notes, and banking identifiers (IBAN, account numbers, SWIFT).",
        export_kb(),
    )


@router.callback_query(SetCB.filter(F.o.in_({"expa", "expb", "expw"})))
async def cb_export(query: CallbackQuery, callback_data: SetCB, services: Services) -> None:
    await answer_callback(query, "Preparing file…")
    if callback_data.o == "expa":
        payload = await services.exports.accounts_csv()
        filename = "accounts.csv"
        caption = "Account overview (no secrets)."
    elif callback_data.o == "expb":
        payload = await services.exports.balance_history_csv()
        filename = "balance_history.csv"
        caption = "Balance history."
    else:
        payload = await services.exports.withdrawals_csv()
        filename = "withdrawals.csv"
        caption = "Expected withdrawals."
    if query.message:
        await send_document(query.message, filename, payload, caption)


@router.callback_query(SetCB.filter(F.o == "bak"))
@router.message(Command("backup"))
async def do_backup(event: CallbackQuery | Message, services: Services) -> None:
    if isinstance(event, CallbackQuery):
        await answer_callback(event, "Creating backup…")
        message = event.message
    else:
        message = event
    if message is None:
        return
    dest_dir = Path(services.settings.database_path).resolve().parent / "backups"
    try:
        path = await backup_database(services.db, dest_dir)
    except Exception:
        logger.exception("backup failed")
        await message.answer("Backup failed. Check the server logs.")
        return
    data = path.read_bytes()
    await send_document(
        message,
        path.name,
        data,
        "SQLite snapshot created with the online backup API. Keep this file private.",
    )
