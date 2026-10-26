"""Central authorization and private-chat enforcement."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update, User

from app.services.container import Services

UNAUTHORIZED_TEXT = "This bot is private. You are not authorized to use it."
PRIVATE_ONLY_TEXT = "Please use this bot in a private chat."


def extract_user_and_chat(event: TelegramObject, data: dict[str, Any]) -> tuple[User | None, Chat | None]:
    user = data.get("event_from_user")
    chat = data.get("event_chat")
    if isinstance(event, Message):
        return event.from_user or user, event.chat or chat
    if isinstance(event, CallbackQuery):
        message_chat = event.message.chat if isinstance(event.message, Message) else None
        return event.from_user or user, message_chat or chat
    if isinstance(event, Update):
        if event.message:
            return event.message.from_user, event.message.chat
        if event.callback_query:
            msg = event.callback_query.message
            return event.callback_query.from_user, msg.chat if isinstance(msg, Message) else None
        if event.edited_message:
            return event.edited_message.from_user, event.edited_message.chat
    return user, chat


class AuthMiddleware(BaseMiddleware):
    def __init__(self, services: Services) -> None:
        self.services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user, chat = extract_user_and_chat(event, data)
        user_id = getattr(user, "id", None)
        chat_type = getattr(chat, "type", None)

        if not self.services.auth.is_authorized(user_id):
            await _reject(event, UNAUTHORIZED_TEXT)
            return None
        if not self.services.auth.is_private_chat(chat_type):
            await _reject(event, PRIVATE_ONLY_TEXT)
            return None

        data["services"] = self.services
        data["is_owner"] = self.services.auth.is_owner(user_id)
        return await handler(event, data)


async def _reject(event: TelegramObject, text: str) -> None:
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Update):
            if event.message:
                await event.message.answer(text)
            elif event.callback_query:
                await event.callback_query.answer(text, show_alert=True)
    except Exception:
        return
