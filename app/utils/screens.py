"""Render major screens as photo+caption when banners exist."""

from __future__ import annotations

from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from app.utils.telegram import safe_edit

BANNER_DIR = Path(__file__).resolve().parents[2] / "assets" / "banners"
CAPTION_LIMIT = 1024
_FILE_IDS: dict[str, str] = {}


def banner_path(screen: str) -> Path:
    return BANNER_DIR / f"{screen}.png"


def banner_exists(screen: str) -> bool:
    return banner_path(screen).is_file()


def _message(target: Message | CallbackQuery) -> Message | None:
    return target.message if isinstance(target, CallbackQuery) else target


def _photo_file(screen: str) -> BufferedInputFile | str:
    cached = _FILE_IDS.get(screen)
    if cached:
        return cached
    return BufferedInputFile(banner_path(screen).read_bytes(), filename=f"{screen}.png")


def _remember(screen: str, message: Message | None) -> None:
    if message and message.photo:
        _FILE_IDS[screen] = message.photo[-1].file_id


async def render_screen(
    target: Message | CallbackQuery,
    screen: str,
    caption: str,
    keyboard,
) -> Message | None:
    text = caption if len(caption) <= CAPTION_LIMIT else caption[: CAPTION_LIMIT - 1] + "…"
    message = _message(target)
    if not banner_exists(screen):
        return await safe_edit(target, text, keyboard)

    media = InputMediaPhoto(media=_photo_file(screen), caption=text)
    if isinstance(target, CallbackQuery) and message is not None and message.photo:
        try:
            edited = await message.edit_media(media, reply_markup=keyboard)
            _remember(screen, edited if isinstance(edited, Message) else message)
            return edited if isinstance(edited, Message) else message
        except TelegramBadRequest:
            pass
    if message is None:
        return None
    try:
        sent = await message.answer_photo(_photo_file(screen), caption=text, reply_markup=keyboard)
        _remember(screen, sent)
        if isinstance(target, CallbackQuery):
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
        return sent
    except TelegramBadRequest:
        return await safe_edit(target, text, keyboard)
