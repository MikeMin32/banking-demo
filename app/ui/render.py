"""Screen presentation: Rich Message primary, Widget optional, banners preserved.

Widgets currently fail for this bot with INPUT_MEDIA_WIDGET_NOT_ALLOWED.
Approved /ui_preview prototype A (Rich Message) is the production path.
"""

from __future__ import annotations

import logging
import zlib
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, InputRichMessage, Message

from app.utils.telegram import safe_edit, try_delete

logger = logging.getLogger(__name__)

WIDGET_MAX_HTML = 32_768
WIDGET_MAX_COMPRESSED = 4_096

BANNER_DIR = Path(__file__).resolve().parents[2] / "assets" / "banners"
_BANNER_FILE_IDS: dict[str, str] = {}
# chat_id -> (banner_message_id, content_message_id)
_LAST_PAIR: dict[int, tuple[int | None, int]] = {}


def widget_size_ok(html: str) -> tuple[bool, int, int]:
    raw = len(html.encode("utf-8"))
    compressed = len(zlib.compress(html.encode("utf-8"), 9))
    return raw <= WIDGET_MAX_HTML and compressed <= WIDGET_MAX_COMPRESSED, raw, compressed


def banner_path(screen: str) -> Path:
    return BANNER_DIR / f"{screen}.png"


def banner_exists(screen: str) -> bool:
    return banner_path(screen).is_file()


def _message(target: Message | CallbackQuery) -> Message | None:
    return target.message if isinstance(target, CallbackQuery) else target


def _banner_media(screen: str) -> BufferedInputFile | str | None:
    if not banner_exists(screen):
        return None
    cached = _BANNER_FILE_IDS.get(screen)
    if cached:
        return cached
    return BufferedInputFile(banner_path(screen).read_bytes(), filename=f"{screen}.png")


def _remember_banner(screen: str, message: Message | None) -> None:
    if message and message.photo:
        _BANNER_FILE_IDS[screen] = message.photo[-1].file_id


def _error_description(exc: BaseException) -> str:
    """Safe Telegram error text for logs (no tokens/secrets)."""
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()[:500]
    text = str(exc).strip()
    return text[:500] if text else type(exc).__name__


async def _cleanup_previous(chat_id: int, bot, current: Message | None) -> None:
    old = _LAST_PAIR.pop(chat_id, None)
    if old:
        banner_id, content_id = old
        for mid in (content_id, banner_id):
            if mid is None:
                continue
            try:
                await bot.delete_message(chat_id, mid)
            except TelegramBadRequest:
                pass
        return
    if current is not None:
        await try_delete(current)


async def _send_banner(bot, chat_id: int, screen: str | None) -> Message | None:
    if not screen:
        return None
    media = _banner_media(screen)
    if media is None:
        return None
    try:
        banner_msg = await bot.send_photo(chat_id=chat_id, photo=media)
        _remember_banner(screen, banner_msg)
        return banner_msg
    except (TelegramBadRequest, TelegramAPIError) as exc:
        logger.warning(
            "banner send failed screen=%s err_type=%s description=%s",
            screen,
            type(exc).__name__,
            _error_description(exc),
        )
        return None


async def present_rich(
    target: Message | CallbackQuery,
    rich: InputRichMessage,
    keyboard,
    *,
    text_fallback: str,
    screen: str | None = None,
) -> Message | None:
    """Primary presentation: OG banner photo + approved Rich Message."""
    message = _message(target)
    if message is None:
        return None
    bot = message.bot
    chat_id = message.chat.id

    if isinstance(target, CallbackQuery):
        await _cleanup_previous(chat_id, bot, message)
    else:
        await _cleanup_previous(chat_id, bot, None)

    banner_msg = await _send_banner(bot, chat_id, screen)
    try:
        sent = await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=rich,
            reply_markup=keyboard,
        )
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "rich_message send failed err_type=%s description=%s",
            type(exc).__name__,
            _error_description(exc),
        )
        if banner_msg is not None:
            await try_delete(banner_msg)
        return await _last_resort_text(target, text_fallback, keyboard, screen=screen, reason=type(exc).__name__)

    _LAST_PAIR[chat_id] = (
        banner_msg.message_id if banner_msg is not None else None,
        sent.message_id,
    )
    logger.info("rich_message sent chat_id=%s screen=%s", chat_id, screen)
    return sent


async def present_widget(
    target: Message | CallbackQuery,
    html: str,
    keyboard,
    *,
    text_fallback: str,
    height: int | None = None,
    caption: str | None = None,
    screen: str | None = None,
    rich_fallback: InputRichMessage | None = None,
) -> Message | None:
    """Optional Widget path. On failure, prefer Rich Message — never pretend Widget worked."""
    message = _message(target)
    if message is None:
        return None

    ok, raw, compressed = widget_size_ok(html)
    if not ok:
        logger.warning("widget oversized raw=%s compressed=%s", raw, compressed)
        if rich_fallback is not None:
            return await present_rich(
                target, rich_fallback, keyboard, text_fallback=text_fallback, screen=screen
            )
        return await _last_resort_text(target, text_fallback, keyboard, screen=screen, reason="size_limit")

    bot = message.bot
    chat_id = message.chat.id
    if isinstance(target, CallbackQuery):
        await _cleanup_previous(chat_id, bot, message)
    else:
        await _cleanup_previous(chat_id, bot, None)

    banner_msg = await _send_banner(bot, chat_id, screen)
    try:
        kwargs: dict = {
            "chat_id": chat_id,
            "html": html,
            "allow_queries": False,
            "reply_markup": keyboard,
        }
        if height is not None:
            kwargs["height"] = height
        if caption:
            kwargs["caption"] = caption
        sent = await bot.send_widget(**kwargs)
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        desc = _error_description(exc)
        logger.warning(
            "widget send failed err_type=%s description=%s — falling back to rich/text",
            type(exc).__name__,
            desc,
        )
        if banner_msg is not None:
            await try_delete(banner_msg)
        if rich_fallback is not None:
            return await present_rich(
                target, rich_fallback, keyboard, text_fallback=text_fallback, screen=screen
            )
        return await _last_resort_text(target, text_fallback, keyboard, screen=screen, reason=desc)

    _LAST_PAIR[chat_id] = (
        banner_msg.message_id if banner_msg is not None else None,
        sent.message_id,
    )
    return sent


async def _last_resort_text(
    target: Message | CallbackQuery,
    text: str,
    keyboard,
    *,
    screen: str | None,
    reason: str,
) -> Message | None:
    notice = f"{text}\n\n<i>Native rich UI unavailable ({reason}).</i>"
    if "Native rich UI unavailable" in text:
        notice = text
    message = _message(target)
    if message is not None and screen and banner_exists(screen):
        media = _banner_media(screen)
        if media is not None:
            try:
                sent = await message.answer_photo(media, caption=notice[:1024], reply_markup=keyboard)
                _remember_banner(screen, sent)
                if isinstance(target, CallbackQuery):
                    await try_delete(message)
                return sent
            except Exception:
                pass
    return await safe_edit(target, notice, keyboard)


async def render_app_screen(
    target: Message | CallbackQuery,
    screen: str,
    keyboard,
    *,
    rich: InputRichMessage | None = None,
    html: str | None = None,
    text_fallback: str,
    height: int | None = None,
    caption: str | None = None,
    wrap_caption_as_prompt: bool = False,
    prefer_widget: bool = False,
) -> Message | None:
    """Render a screen. Rich Message is primary unless prefer_widget is set."""
    del wrap_caption_as_prompt  # prompts now supply rich explicitly when possible

    if prefer_widget and html is not None:
        return await present_widget(
            target,
            html,
            keyboard,
            text_fallback=text_fallback,
            height=height,
            caption=caption,
            screen=screen,
            rich_fallback=rich,
        )

    if rich is not None:
        return await present_rich(
            target,
            rich,
            keyboard,
            text_fallback=text_fallback,
            screen=screen,
        )

    if html is not None:
        # No rich available: try widget, then last-resort text.
        return await present_widget(
            target,
            html,
            keyboard,
            text_fallback=text_fallback,
            height=height,
            caption=caption,
            screen=screen,
            rich_fallback=None,
        )

    return await safe_edit(target, text_fallback, keyboard)
