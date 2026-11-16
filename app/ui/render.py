"""Widget presentation with OG banner photos + honest text fallback."""

from __future__ import annotations

import logging
import zlib
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.ui.screens import prompt_html
from app.utils.telegram import safe_edit, try_delete

logger = logging.getLogger(__name__)

WIDGET_MAX_HTML = 32_768
WIDGET_MAX_COMPRESSED = 4_096

BANNER_DIR = Path(__file__).resolve().parents[2] / "assets" / "banners"
_BANNER_FILE_IDS: dict[str, str] = {}
# chat_id -> (banner_message_id, widget_message_id) for cleanup without flooding chat
_LAST_PAIR: dict[int, tuple[int | None, int]] = {}

# Prefer auto height so tabs/accordions can resize (Telegram clamps 50–600).
SCREEN_HEIGHTS: dict[str, int | None] = {
    "dashboard": None,
    "accounts": None,
    "account-details": None,
    "balance-summary": None,
    "transactions": None,
    "settings": None,
    "login-details": None,
    "expected-charges": None,
    "quick-add": None,
    "add-account": None,
}


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


async def _cleanup_previous(chat_id: int, bot, current: Message | None) -> None:
    old = _LAST_PAIR.pop(chat_id, None)
    if old:
        banner_id, widget_id = old
        for mid in (widget_id, banner_id):
            if mid is None:
                continue
            try:
                await bot.delete_message(chat_id, mid)
            except TelegramBadRequest:
                pass
        return
    # First navigation from an older single message (callback target).
    if current is not None:
        await try_delete(current)


async def present_widget(
    target: Message | CallbackQuery,
    html: str,
    keyboard,
    *,
    text_fallback: str,
    height: int | None = None,
    caption: str | None = None,
    screen: str | None = None,
) -> Message | None:
    """Send optional OG banner photo + Widget; delete prior pair to avoid flood."""
    message = _message(target)
    if message is None:
        return None

    ok, raw, compressed = widget_size_ok(html)
    if not ok:
        logger.warning("widget oversized raw=%s compressed=%s — using text fallback", raw, compressed)
        return await _fallback(target, text_fallback, keyboard, reason="size_limit", screen=screen)

    bot = message.bot
    chat_id = message.chat.id

    # Remove previous banner+widget pair (or the triggering message).
    if isinstance(target, CallbackQuery):
        await _cleanup_previous(chat_id, bot, message)
    else:
        # Fresh /start-style entry: still clear any tracked pair.
        await _cleanup_previous(chat_id, bot, None)

    banner_msg: Message | None = None
    media = _banner_media(screen) if screen else None
    if media is not None:
        try:
            banner_msg = await bot.send_photo(chat_id=chat_id, photo=media)
            _remember_banner(screen or "", banner_msg)
        except (TelegramBadRequest, TelegramAPIError) as exc:
            logger.warning("banner send failed screen=%s err_type=%s", screen, type(exc).__name__)
            banner_msg = None

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
        logger.warning("widget send failed err_type=%s — using text fallback", type(exc).__name__)
        if banner_msg is not None:
            await try_delete(banner_msg)
        return await _fallback(
            target,
            text_fallback,
            keyboard,
            reason=type(exc).__name__,
            screen=screen,
        )

    _LAST_PAIR[chat_id] = (
        banner_msg.message_id if banner_msg is not None else None,
        sent.message_id,
    )
    return sent


async def _fallback(
    target: Message | CallbackQuery,
    text: str,
    keyboard,
    *,
    reason: str,
    screen: str | None = None,
) -> Message | None:
    notice = (
        f"{text}\n\n"
        f"<i>Widget unavailable ({reason}). Showing standard message.</i>"
    )
    if "Widget unavailable" in text:
        notice = text
    # Prefer classic banner photo+caption when Widget fails and a banner exists.
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
    html: str | None = None,
    text_fallback: str,
    height: int | None = None,
    caption: str | None = None,
    wrap_caption_as_prompt: bool = False,
) -> Message | None:
    content = html
    if content is None and wrap_caption_as_prompt:
        content = prompt_html(screen=screen, caption_html=text_fallback)
    if content is None:
        return await safe_edit(target, text_fallback, keyboard)

    h = SCREEN_HEIGHTS.get(screen) if height is None else height
    return await present_widget(
        target,
        content,
        keyboard,
        text_fallback=text_fallback,
        height=h,
        caption=caption,
        screen=screen,
    )
