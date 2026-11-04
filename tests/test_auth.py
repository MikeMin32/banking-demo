from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, User
from pydantic import ValidationError

from app.config import Settings
from app.middleware.auth import AuthMiddleware, extract_user_and_chat
from app.services.auth import AuthService
from app.services.container import Services
from tests.conftest import draft


def test_owner_and_allow_list(settings: Settings) -> None:
    auth = AuthService(settings)
    assert auth.is_authorized(1001)
    assert auth.is_authorized(1002)
    assert auth.is_authorized(1003)
    assert not auth.is_authorized(9999)
    assert not auth.is_authorized(None)
    assert auth.is_owner(1001)
    assert not auth.is_owner(1002)
    assert auth.can_view_credentials(1001)
    assert not auth.can_view_credentials(1002)


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


def test_no_unauthorized_reply_text() -> None:
    import app.middleware.auth as auth_mod

    assert not hasattr(auth_mod, "UNAUTHORIZED_TEXT")
    source = auth_mod.__file__ and open(auth_mod.__file__, encoding="utf-8").read()
    assert source is not None
    assert "This bot is private" not in source
    assert "Access denied" not in source
    assert "not authorized" not in source.lower()


async def test_unauthorized_message_is_silent(services: Services, monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = AuthMiddleware(services)
    answered = AsyncMock()
    monkeypatch.setattr(Message, "answer", answered)
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=9999, type="private"),
        from_user=User(id=9999, is_bot=False, first_name="X"),
        text="/start",
    )
    handler = AsyncMock(return_value="ran")
    result = await middleware(handler, message, {})
    assert result is None
    handler.assert_not_awaited()
    answered.assert_not_awaited()


async def test_unauthorized_callback_acks_without_text(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    middleware = AuthMiddleware(services)
    ack = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", ack)
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=9999, type="private"),
        from_user=User(id=9999, is_bot=False, first_name="X"),
    )
    query = CallbackQuery(
        id="1",
        from_user=User(id=9999, is_bot=False, first_name="X"),
        chat_instance="x",
        message=message,
        data="m:menu",
    )
    handler = AsyncMock(return_value="ran")
    result = await middleware(handler, query, {})
    assert result is None
    handler.assert_not_awaited()
    ack.assert_awaited_once()
    assert ack.await_args.args == () or ack.await_args.kwargs.get("text") in (None, "")
    # No alert / notification text.
    assert ack.await_args.kwargs.get("show_alert") in (None, False)
    assert ack.await_args.kwargs.get("text") in (None, "")


async def test_authorized_user_still_reaches_handler(services: Services) -> None:
    middleware = AuthMiddleware(services)
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=1001, type="private"),
        from_user=User(id=1001, is_bot=False, first_name="Owner"),
        text="/start",
    )
    handler = AsyncMock(return_value="ok")
    result = await middleware(handler, message, {})
    assert result == "ok"
    handler.assert_awaited_once()
    assert handler.await_args.args[1]["is_owner"] is True
    assert handler.await_args.args[1]["can_view_credentials"] is True


def test_dev_allow_any_user_false_enforces_allowlist(tmp_path) -> None:
    settings = Settings(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        allowed_user_ids="1002",
        database_path=str(tmp_path / "t.db"),
        timezone="Europe/Kyiv",
        reminder_time="09:00",
        log_level="WARNING",
        dev_allow_any_user=False,
    )
    auth = AuthService(settings)
    assert auth.is_authorized(1001)
    assert auth.is_authorized(1002)
    assert not auth.is_authorized(9999)


async def test_unauthorized_path_does_not_mutate_via_middleware(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    middleware = AuthMiddleware(services)
    monkeypatch.setattr(Message, "answer", AsyncMock())
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=424242, type="private"),
        from_user=User(id=424242, is_bot=False, first_name="Nope"),
        text="/start",
    )

    async def dangerous_handler(event, data):
        await services.accounts.create(draft(balance_raw="999"))
        return "created"

    before = len(await services.accounts.list_active())
    result = await middleware(dangerous_handler, message, {})
    after = len(await services.accounts.list_active())
    assert result is None
    assert before == after
