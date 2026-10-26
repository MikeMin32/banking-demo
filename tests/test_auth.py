from __future__ import annotations

import pytest
from aiogram.enums import ChatType
from pydantic import ValidationError

from app.config import Settings
from app.middleware.auth import extract_user_and_chat
from app.services.auth import AuthService


def test_owner_and_allow_list(settings: Settings) -> None:
    auth = AuthService(settings)
    assert auth.is_authorized(1001)
    assert auth.is_authorized(1002)
    assert auth.is_authorized(1003)
    assert not auth.is_authorized(9999)
    assert not auth.is_authorized(None)
    assert auth.is_owner(1001)
    assert not auth.is_owner(1002)


def test_private_chat_required(settings: Settings) -> None:
    auth = AuthService(settings)
    assert auth.is_private_chat(ChatType.PRIVATE)
    assert auth.is_private_chat("private")
    assert not auth.is_private_chat(ChatType.GROUP)
    assert not auth.is_private_chat("supergroup")
    assert not auth.is_private_chat(None)


def test_unauthorized_does_not_depend_on_account_data(settings: Settings) -> None:
    auth = AuthService(settings)
    # Rejection is based only on the numeric user id.
    assert settings.authorized_user_ids == frozenset({1001, 1002, 1003})
    assert not auth.is_authorized(0)


def test_extract_user_from_empty_update() -> None:
    user, chat = extract_user_and_chat(object(), {})  # type: ignore[arg-type]
    assert user is None
    assert chat is None


def test_missing_token_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(bot_token=" ", owner_telegram_id=1)
    with pytest.raises(ValidationError):
        Settings(bot_token="x", owner_telegram_id=0)
    with pytest.raises(ValidationError):
        Settings(bot_token="x", owner_telegram_id=1, reminder_time="9am")
    with pytest.raises(ValidationError):
        Settings(bot_token="x", owner_telegram_id=1, timezone="Not/AZone")
