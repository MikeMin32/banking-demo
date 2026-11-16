"""Render major screens as Rich Messages with OG banners (Widget kept optional)."""

from __future__ import annotations

from aiogram.types import CallbackQuery, InputRichMessage, Message

from app.ui.render import render_app_screen
from app.ui.rich_screens import prompt_rich


async def render_screen(
    target: Message | CallbackQuery,
    screen: str,
    caption: str,
    keyboard,
    *,
    rich: InputRichMessage | None = None,
    html: str | None = None,
    height: int | None = None,
    caption_label: str | None = None,
    prefer_widget: bool = False,
) -> Message | None:
    """Present an app screen.

    Primary path is the approved Rich Message layout (`rich=`).
    `html=` Widget payloads are kept for future availability / explicit prefer_widget.
    Plain caption text is only a last-resort fallback — never the preferred UI when
    a Rich Message builder is available.
    """
    content_rich = rich
    if content_rich is None and html is None:
        # Nested prompts without a dedicated builder: still use Rich Message chrome.
        content_rich = prompt_rich(
            screen=screen,
            title=screen.replace("-", " ").title(),
            body_lines=caption.splitlines() or [caption],
        )
    return await render_app_screen(
        target,
        screen,
        keyboard,
        rich=content_rich,
        html=html,
        text_fallback=caption,
        height=height,
        caption=caption_label,
        prefer_widget=prefer_widget,
    )
