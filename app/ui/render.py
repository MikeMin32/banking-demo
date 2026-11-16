"""Screen presentation: Rich Message primary, Widget optional, banners preserved.

Banners are embedded as InputRichBlockPhoto inside the same Rich Message so
Telegram lays them out in one bubble (aligned with card content). Fallback to
a separate sendPhoto remains if embedding is rejected.

Central screen transition manager tracks banner_message_id + content_message_id
per chat so navigation removes the previous screen instead of stacking it.
"""

from __future__ import annotations

import logging
import zlib
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    InputRichBlockPhoto,
    InputRichMessage,
    InputRichMessageMedia,
    Message,
)

from app.ui.screen_session import ActiveScreen, get_screen_session_store
from app.utils.telegram import safe_edit, try_delete

logger = logging.getLogger(__name__)

WIDGET_MAX_HTML = 32_768
WIDGET_MAX_COMPRESSED = 4_096

BANNER_DIR = Path(__file__).resolve().parents[2] / "assets" / "banners"
_BANNER_FILE_IDS: dict[str, str] = {}


def widget_size_ok(html: str) -> tuple[bool, int, int]:
    raw = len(html.encode("utf-8"))
    compressed = len(zlib.compress(html.encode("utf-8"), 9))
    return raw <= WIDGET_MAX_HTML and compressed <= WIDGET_MAX_COMPRESSED, raw, compressed


def banner_path(screen: str) -> Path:
    return BANNER_DIR / f"{screen}.png"


def banner_exists(screen: str) -> bool:
    return banner_path(screen).is_file()


def _is_callback(target: object) -> bool:
    """True for CallbackQuery or duck-typed callback (has .message + .data)."""
    if isinstance(target, CallbackQuery):
        return True
    return getattr(target, "message", None) is not None and hasattr(target, "data")


def _message(target: Message | CallbackQuery) -> Message | None:
    if _is_callback(target):
        return getattr(target, "message", None)
    return target  # type: ignore[return-value]


def _banner_media(screen: str) -> BufferedInputFile | str | None:
    if not banner_exists(screen):
        return None
    cached = _BANNER_FILE_IDS.get(screen)
    if cached:
        return cached
    return BufferedInputFile(banner_path(screen).read_bytes(), filename=f"{screen}.png")


def _block_type_value(block: object) -> str | None:
    t = getattr(block, "type", None)
    if t is None:
        return None
    return str(getattr(t, "value", t))


def _content_lacks_embedded_banner(message: Message | None) -> bool:
    """True when message looks like legacy separate-photo content (no leading photo block)."""
    if message is None:
        return True
    rm = getattr(message, "rich_message", None)
    blocks = getattr(rm, "blocks", None) if rm is not None else None
    if not blocks:
        return True
    return _block_type_value(blocks[0]) != "photo"


def _remember_banner(screen: str, message: Message | None) -> None:
    if message and message.photo:
        _BANNER_FILE_IDS[screen] = message.photo[-1].file_id
        return
    _remember_banner_from_rich(screen, message)


def _remember_banner_from_rich(screen: str, message: Message | None) -> None:
    """Cache file_id from an embedded InputRichBlockPhoto / returned RichBlockPhoto."""
    if message is None:
        return
    rm = getattr(message, "rich_message", None)
    blocks = getattr(rm, "blocks", None) if rm is not None else None
    if not blocks:
        return
    first = blocks[0]
    if _block_type_value(first) != "photo":
        return
    photos = getattr(first, "photo", None)
    if isinstance(photos, list) and photos:
        file_id = getattr(photos[-1], "file_id", None)
        if file_id:
            _BANNER_FILE_IDS[screen] = file_id
            return
    # Outgoing shape: InputMediaPhoto on the block
    media_obj = photos if photos is not None else getattr(first, "photo", None)
    media = getattr(media_obj, "media", None)
    if isinstance(media, str) and media and not media.startswith("attach://"):
        _BANNER_FILE_IDS[screen] = media


def embed_banner(rich: InputRichMessage, screen: str | None) -> tuple[InputRichMessage, bool]:
    """Return rich message with OG banner as the first photo block when available.

    Uses original PNG bytes or a cached Telegram file_id — never base64, never
    stretched. Returns (message, embedded) where embedded indicates a photo was added.
    """
    if not screen:
        return rich, False
    media = _banner_media(screen)
    if media is None:
        return rich, False
    photo = InputMediaPhoto(media=media)
    photo_block = InputRichBlockPhoto(photo=photo)

    if rich.blocks is not None:
        # Avoid double-embedding if a caller already prefixed a photo.
        if rich.blocks and _block_type_value(rich.blocks[0]) == "photo":
            return rich, True
        return (
            InputRichMessage(
                blocks=[photo_block, *rich.blocks],
                is_rtl=rich.is_rtl,
                skip_entity_detection=rich.skip_entity_detection,
            ),
            True,
        )

    # HTML / Markdown rich messages: reference media via tg://photo?id=
    media_id = "ogbanner"
    prefix = f'<img src="tg://photo?id={media_id}">\n'
    if rich.html is not None:
        return (
            InputRichMessage(
                html=prefix + rich.html,
                is_rtl=rich.is_rtl,
                skip_entity_detection=rich.skip_entity_detection,
                media=[InputRichMessageMedia(id=media_id, media=photo)],
            ),
            True,
        )
    if rich.markdown is not None:
        return (
            InputRichMessage(
                markdown=prefix + rich.markdown,
                is_rtl=rich.is_rtl,
                skip_entity_detection=rich.skip_entity_detection,
                media=[InputRichMessageMedia(id=media_id, media=photo)],
            ),
            True,
        )
    return rich, False


def _error_description(exc: BaseException) -> str:
    """Safe Telegram error text for logs (no tokens/secrets)."""
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()[:500]
    text = str(exc).strip()
    return text[:500] if text else type(exc).__name__


async def _delete_message_id(bot, chat_id: int, message_id: int | None, *, label: str) -> bool:
    if message_id is None:
        return True
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except TelegramBadRequest as exc:
        desc = _error_description(exc).lower()
        # Already gone is fine; anything else is logged without claiming success.
        if any(token in desc for token in ("message to delete not found", "message can't be deleted", "message not found")):
            logger.info(
                "screen cleanup skipped label=%s chat_id=%s message_id=%s description=%s",
                label,
                chat_id,
                message_id,
                _error_description(exc),
            )
            return True
        logger.warning(
            "screen cleanup failed label=%s chat_id=%s message_id=%s description=%s",
            label,
            chat_id,
            message_id,
            _error_description(exc),
        )
        return False
    except TelegramAPIError as exc:
        logger.warning(
            "screen cleanup failed label=%s chat_id=%s message_id=%s description=%s",
            label,
            chat_id,
            message_id,
            _error_description(exc),
        )
        return False


async def cleanup_active_screen(
    bot,
    chat_id: int,
    *,
    callback_message: Message | None = None,
) -> None:
    """Remove the previously tracked banner+content pair for this chat.

    Embedded banners live inside content_message_id (banner_message_id is None).
    Legacy separate-photo screens still track both IDs.

    If tracking was lost (bot restart), delete the callback content message and,
    only for legacy separate-photo content, attempt content_id - 1 as the banner.
    Never deletes arbitrary older history.
    """
    store = get_screen_session_store()
    previous = await store.pop(chat_id)
    deleted_ids: set[int] = set()

    if previous is not None:
        for mid, label in (
            (previous.content_message_id, "content"),
            (previous.banner_message_id, "banner"),
        ):
            if mid is None or mid in deleted_ids:
                continue
            await _delete_message_id(bot, chat_id, mid, label=label)
            deleted_ids.add(mid)
        # If the callback points at a different message (race), still try it.
        if callback_message is not None and callback_message.message_id not in deleted_ids:
            await _delete_message_id(
                bot,
                chat_id,
                callback_message.message_id,
                label="callback_content",
            )
        return

    # No tracked pair: recover best-effort from the callback message only.
    if callback_message is None:
        return
    content_id = callback_message.message_id
    await _delete_message_id(bot, chat_id, content_id, label="untracked_content")
    # Legacy: separate photo was sent immediately before content.
    if _content_lacks_embedded_banner(callback_message):
        probable_banner_id = content_id - 1
        if probable_banner_id > 0:
            await _delete_message_id(
                bot,
                chat_id,
                probable_banner_id,
                label="probable_banner",
            )


async def _send_banner(bot, chat_id: int, screen: str | None) -> Message | None:
    """Legacy separate-photo banner (fallback when embedding is unavailable)."""
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


async def _remember_active(
    chat_id: int,
    *,
    banner_msg: Message | None,
    content_msg: Message,
    screen: str | None,
) -> ActiveScreen:
    store = get_screen_session_store()
    return await store.set(
        chat_id,
        banner_message_id=banner_msg.message_id if banner_msg is not None else None,
        content_message_id=content_msg.message_id,
        screen=screen,
    )


async def present_rich(
    target: Message | CallbackQuery,
    rich: InputRichMessage,
    keyboard,
    *,
    text_fallback: str,
    screen: str | None = None,
    skip_cleanup: bool = False,
) -> Message | None:
    """Primary presentation: OG banner embedded in the same Rich Message bubble."""
    message = _message(target)
    if message is None:
        return None
    bot = message.bot
    chat_id = message.chat.id
    store = get_screen_session_store()
    lock = await store.lock_for(chat_id)

    async with lock:
        if not skip_cleanup:
            await cleanup_active_screen(
                bot,
                chat_id,
                callback_message=message if _is_callback(target) else None,
            )

        combined, embedded = embed_banner(rich, screen)
        try:
            sent = await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=combined,
                reply_markup=keyboard,
            )
        except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
            if not embedded:
                logger.warning(
                    "rich_message send failed err_type=%s description=%s",
                    type(exc).__name__,
                    _error_description(exc),
                )
                return await _last_resort_text(
                    target, text_fallback, keyboard, screen=screen, reason=type(exc).__name__
                )
            logger.warning(
                "embedded banner rich_message failed err_type=%s description=%s — falling back to separate photo",
                type(exc).__name__,
                _error_description(exc),
            )
            return await _present_rich_separate_banner(
                target,
                rich,
                keyboard,
                text_fallback=text_fallback,
                screen=screen,
            )

        if screen and embedded:
            _remember_banner_from_rich(screen, sent)
        await _remember_active(chat_id, banner_msg=None, content_msg=sent, screen=screen)
        logger.info(
            "rich_message sent chat_id=%s screen=%s embedded_banner=%s content_id=%s",
            chat_id,
            screen,
            embedded,
            sent.message_id,
        )
        return sent


async def _present_rich_separate_banner(
    target: Message | CallbackQuery,
    rich: InputRichMessage,
    keyboard,
    *,
    text_fallback: str,
    screen: str | None,
) -> Message | None:
    """Fallback: separate sendPhoto + Rich Message (legacy dual-bubble layout)."""
    message = _message(target)
    if message is None:
        return None
    bot = message.bot
    chat_id = message.chat.id

    banner_msg = await _send_banner(bot, chat_id, screen)
    try:
        sent = await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=rich,
            reply_markup=keyboard,
        )
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "rich_message send failed (separate banner path) err_type=%s description=%s",
            type(exc).__name__,
            _error_description(exc),
        )
        if banner_msg is not None:
            await _delete_message_id(bot, chat_id, banner_msg.message_id, label="orphan_banner")
        return await _last_resort_text(
            target, text_fallback, keyboard, screen=screen, reason=type(exc).__name__
        )

    await _remember_active(chat_id, banner_msg=banner_msg, content_msg=sent, screen=screen)
    logger.info(
        "rich_message sent (separate banner) chat_id=%s screen=%s banner_id=%s content_id=%s",
        chat_id,
        screen,
        banner_msg.message_id if banner_msg else None,
        sent.message_id,
    )
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
    store = get_screen_session_store()
    lock = await store.lock_for(chat_id)

    async with lock:
        await cleanup_active_screen(
            bot,
            chat_id,
            callback_message=message if _is_callback(target) else None,
        )

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
                await _delete_message_id(bot, chat_id, banner_msg.message_id, label="orphan_banner")
            # Fall back outside the lock to avoid nested lock on the same chat.
            pass
        else:
            await _remember_active(chat_id, banner_msg=banner_msg, content_msg=sent, screen=screen)
            return sent

    if rich_fallback is not None:
        return await present_rich(
            target,
            rich_fallback,
            keyboard,
            text_fallback=text_fallback,
            screen=screen,
            skip_cleanup=True,
        )
    return await _last_resort_text(target, text_fallback, keyboard, screen=screen, reason=desc)


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
    if message is None:
        return None
    bot = message.bot
    chat_id = message.chat.id
    if screen and banner_exists(screen):
        media = _banner_media(screen)
        if media is not None:
            try:
                sent = await bot.send_photo(
                    chat_id=chat_id,
                    photo=media,
                    caption=notice[:1024],
                    reply_markup=keyboard,
                )
                _remember_banner(screen, sent)
                await _remember_active(
                    chat_id,
                    banner_msg=None,  # captioned photo is the sole content message
                    content_msg=sent,
                    screen=screen,
                )
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
    del wrap_caption_as_prompt

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
