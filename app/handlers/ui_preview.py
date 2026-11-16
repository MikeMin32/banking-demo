"""Owner/allowlist-only /ui_preview for Rich Message + HTML Widget prototypes."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.common import PAGE_SIZE
from app.services.accounts import AccountError
from app.services.container import Services
from app.utils.telegram import answer_callback, clear_state
from app.utils.ui_preview import (
    AccountDetailsSnapshot,
    assert_no_secrets,
    build_fallback_notice,
    build_rich_account_details,
    build_widget_account_details,
    preview_actions_kb,
    preview_menu_kb,
    sample_account_details,
    snapshot_from_totals,
    widget_size_ok,
)

router = Router(name="ui_preview")
logger = logging.getLogger(__name__)


def can_access_ui_preview(services: Services, user_id: int | None) -> bool:
    """Same gate as the rest of the bot (respects DEV_ALLOW_ANY_USER)."""
    return services.auth.is_authorized(user_id)


async def _load_snapshot(services: Services) -> tuple[AccountDetailsSnapshot, object | None]:
    items, _total = await services.accounts.page(archived=False, page=0, page_size=PAGE_SIZE)
    if not items:
        return sample_account_details(tz=services.tz), None
    account = items[0]
    totals = await services.totals.for_account(account.id)
    return snapshot_from_totals(totals, services.tz), account


async def _deny(message: Message | None) -> None:
    # Silent for unauthorized users — no financial data, no capability hint.
    if message is None:
        return
    return None


@router.message(Command("ui_preview"))
async def cmd_ui_preview(message: Message, services: Services, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not can_access_ui_preview(services, user_id):
        await _deny(message)
        return
    await clear_state(state)
    await message.answer(
        "<b>UI Preview · Account Details</b>\n\n"
        "Compare native Telegram presentation prototypes.\n"
        "A uses Rich Messages. B uses an HTML Widget inside the chat.\n"
        "Both show the same account figures. No production screens are changed.",
        reply_markup=preview_menu_kb(),
    )


@router.callback_query(F.data == "uip:menu")
async def cb_ui_preview_menu(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    user_id = query.from_user.id if query.from_user else None
    if not can_access_ui_preview(services, user_id):
        await answer_callback(query)
        return
    await answer_callback(query)
    await clear_state(state)
    if query.message:
        await query.message.answer(
            "<b>UI Preview · Account Details</b>\n\nChoose a prototype:",
            reply_markup=preview_menu_kb(),
        )


@router.callback_query(F.data == "uip:noop")
async def cb_ui_preview_noop(query: CallbackQuery, services: Services) -> None:
    user_id = query.from_user.id if query.from_user else None
    if not can_access_ui_preview(services, user_id):
        await answer_callback(query)
        return
    await answer_callback(query, "Preview control — no change applied")


@router.callback_query(F.data.in_({"uip:a", "uip:b", "uip:both"}))
async def cb_ui_preview_render(query: CallbackQuery, services: Services, state: FSMContext) -> None:
    user_id = query.from_user.id if query.from_user else None
    if not can_access_ui_preview(services, user_id):
        await answer_callback(query)
        return
    await answer_callback(query)
    await clear_state(state)
    if query.message is None:
        return

    try:
        snap, account = await _load_snapshot(services)
    except AccountError:
        snap, account = sample_account_details(tz=services.tz), None

    mode = query.data or ""
    markup = preview_actions_kb(account)  # type: ignore[arg-type]

    if mode in {"uip:a", "uip:both"}:
        await _send_rich(query.message, snap, markup)
    if mode in {"uip:b", "uip:both"}:
        await _send_widget(query.message, snap, markup)


def _exc_description(exc: BaseException) -> str:
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()[:500]
    return str(exc).strip()[:500] or type(exc).__name__


async def _send_rich(message: Message, snap: AccountDetailsSnapshot, markup) -> None:
    rich = build_rich_account_details(snap)
    dumped = rich.model_dump_json(exclude_none=True)
    assert_no_secrets(dumped)
    try:
        await message.bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=rich,
            reply_markup=markup,
        )
        logger.info("ui_preview rich_message sent chat_id=%s account_id=%s", message.chat.id, snap.account_id)
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        desc = _exc_description(exc)
        logger.warning(
            "ui_preview rich_message failed chat_id=%s err_type=%s description=%s",
            message.chat.id,
            type(exc).__name__,
            desc,
        )
        await message.answer(
            build_fallback_notice("Rich Message", f"{type(exc).__name__}: {desc}"),
            reply_markup=preview_menu_kb(),
        )


async def _send_widget(message: Message, snap: AccountDetailsSnapshot, markup) -> None:
    html = build_widget_account_details(snap)
    assert_no_secrets(html)
    ok, raw, compressed = widget_size_ok(html)
    if not ok:
        logger.warning(
            "ui_preview widget oversized raw=%s compressed=%s — falling back to Rich Message",
            raw,
            compressed,
        )
        await _send_rich(message, snap, markup)
        return
    try:
        await message.bot.send_widget(
            chat_id=message.chat.id,
            html=html,
            height=420,
            allow_queries=False,
            caption="Account Details · HTML Widget preview",
            reply_markup=markup,
        )
        logger.info(
            "ui_preview widget sent chat_id=%s account_id=%s compressed=%s",
            message.chat.id,
            snap.account_id,
            compressed,
        )
    except (TelegramBadRequest, TelegramAPIError, AttributeError, TypeError, ValueError) as exc:
        desc = _exc_description(exc)
        logger.warning(
            "ui_preview widget failed chat_id=%s err_type=%s description=%s — falling back to Rich Message",
            message.chat.id,
            type(exc).__name__,
            desc,
        )
        # Never fall back to primitive HTML when Rich Message is available.
        await _send_rich(message, snap, markup)
