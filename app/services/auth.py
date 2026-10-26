"""Authorization helpers used by middleware and tests."""

from __future__ import annotations

from aiogram.enums import ChatType

from app.config import Settings


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_authorized(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        return self.settings.is_authorized(user_id)

    def is_owner(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        return self.settings.is_owner(user_id)

    def is_private_chat(self, chat_type: str | ChatType | None) -> bool:
        if chat_type is None:
            return False
        value = chat_type.value if isinstance(chat_type, ChatType) else str(chat_type)
        return value == ChatType.PRIVATE.value
