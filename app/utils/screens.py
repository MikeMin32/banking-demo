"""Render major screens as Telegram HTML Widgets (with text fallback)."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from app.ui.render import render_app_screen
from app.ui.screens import prompt_html


async def render_screen(
    target: Message | CallbackQuery,
    screen: str,
    caption: str,
    keyboard,
    *,
    html: str | None = None,
    height: int | None = None,
    caption_label: str | None = None,
) -> Message | None:
    """Present an app screen.

    Prefer an explicit Widget `html` payload. When omitted, wrap the existing
    Telegram HTML `caption` in the shared Widget chrome so nested prompts stay
    visually consistent. On API/size failure, fall back to a standard message
    and state that the Widget was unavailable.
    """
    content = html if html is not None else prompt_html(screen=screen, caption_html=caption)
    return await render_app_screen(
        target,
        screen,
        keyboard,
        html=content,
        text_fallback=caption,
        height=height,
        caption=caption_label,
    )
