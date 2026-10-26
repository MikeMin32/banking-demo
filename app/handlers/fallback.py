"""Last-resort handlers for stale buttons and unknown input."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

router = Router(name="fallback")


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer("Unknown command. Try /menu or /help.")


@router.callback_query()
async def unknown_callback(query: CallbackQuery) -> None:
    await query.answer("This button is out of date. Open /menu to continue.", show_alert=True)
