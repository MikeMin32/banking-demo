"""Widget-first screen presentation with honest HTML-text fallback."""

from __future__ import annotations

import logging
import zlib

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.ui.screens import prompt_html
from app.utils.telegram import safe_edit, try_delete

logger = logging.getLogger(__name__)

WIDGET_MAX_HTML = 32_768
WIDGET_MAX_COMPRESSED = 4_096

# Default heights by screen family (logical px). Omit/None = auto where possible.
SCREEN_HEIGHTS: dict[str, int] = {
    "dashboard": 320,
    "accounts": 480,
    "account-details": 520,
    "balance-summary": 520,
    "transactions": 560,
    "settings": 280,
    "login-details": 360,
    "expected-charges": 420,
    "quick-add": 360,
    "add-account": 420,
}


def widget_size_ok(html: str) -> tuple[bool, int, int]:
    raw = len(html.encode("utf-8"))
    compressed = len(zlib.compress(html.encode("utf-8"), 9))
    return raw <= WIDGET_MAX_HTML and compressed <= WIDGET_MAX_COMPRESSED, raw, compressed


def _message(target: Message | CallbackQuery) -> Message | None:
    return target.message if isinstance(target, CallbackQuery) else target


async def present_widget(
    target: Message | CallbackQuery,
    html: str,
    keyboard,
    *,
    text_fallback: str,
    height: int | None = 420,
    caption: str | None = None,
) -> Message | None:
    """Send a Widget and delete the previous chat message when navigating via callback."""
    message = _message(target)
    if message is None:
        return None

    ok, raw, compressed = widget_size_ok(html)
    if not ok:
        logger.warning("widget oversized raw=%s compressed=%s — using text fallback", raw, compressed)
        return await _fallback(target, text_fallback, keyboard, reason="size_limit")

    bot = message.bot
    try:
        sent = await bot.send_widget(
            chat_id=message.chat.id,
            html=html,
            height=height,
            allow_queries=False,
            caption=caption,
            reply_markup=keyboard,
        )
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "widget send failed err_type=%s — using text fallback",
            type(exc).__name__,
        )
        return await _fallback(
            target,
            text_fallback,
            keyboard,
            reason=type(exc).__name__,
        )

    if isinstance(target, CallbackQuery):
        await try_delete(message)
    return sent


async def _fallback(
    target: Message | CallbackQuery,
    text: str,
    keyboard,
    *,
    reason: str,
) -> Message | None:
    # Honest: do not claim a Widget rendered.
    notice = (
        f"{text}\n\n"
        f"<i>Widget unavailable ({reason}). Showing standard message.</i>"
    )
    # Avoid stacking notices if already present.
    if "Widget unavailable" in text:
        notice = text
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
    """Preferred entry for app screens. Falls back to text without pretending success."""
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
    )
