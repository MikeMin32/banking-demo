"""Safe Telegram message helpers."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def safe_edit(
    target: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> Message | None:
    message = target.message if isinstance(target, CallbackQuery) else target
    if message is None:
        return None
    try:
        return await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return message
        logger.info("edit_text failed, sending a new message")
        return await message.answer(text, reply_markup=keyboard)


async def answer_callback(query: CallbackQuery, text: str | None = None, *, alert: bool = False) -> None:
    try:
        await query.answer(text, show_alert=alert)
    except TelegramBadRequest:
        pass


async def send_document(message: Message, filename: str, payload: bytes, caption: str) -> None:
    await message.answer_document(
        BufferedInputFile(payload, filename=filename),
        caption=caption,
    )


async def clear_state(state: FSMContext | None) -> None:
    if state is not None:
        await state.clear()
