"""Regression tests: only one active screen message per chat (embedded banner)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage
from aiogram.types import InputRichBlockPhoto

from app.ui.render import cleanup_active_screen, embed_banner, present_rich
from app.ui.rich_screens import account_details_rich, accounts_overview_rich, dashboard_rich
from app.ui.screen_session import reset_screen_session_store_for_tests
from app.utils.ui_preview import sample_account_details


class FakeBot:
    def __init__(self) -> None:
        self.next_id = 100
        self.deleted: list[int] = []
        self.photos: list[int] = []
        self.rich: list[int] = []
        self.rich_payloads: list = []
        self.fail_delete: set[int] = set()
        self.fail_rich_once: bool = False

    async def send_photo(self, chat_id: int, photo, **kwargs):
        mid = self.next_id
        self.next_id += 1
        self.photos.append(mid)
        return SimpleNamespace(
            message_id=mid,
            photo=[SimpleNamespace(file_id=f"fid-{mid}")],
            chat=SimpleNamespace(id=chat_id),
        )

    async def send_rich_message(self, chat_id: int, rich_message, reply_markup=None, **kwargs):
        if self.fail_rich_once:
            self.fail_rich_once = False
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=1),
                message="Bad Request: PHOTO_INVALID",
            )
        mid = self.next_id
        self.next_id += 1
        self.rich.append(mid)
        self.rich_payloads.append(rich_message)
        return SimpleNamespace(
            message_id=mid,
            chat=SimpleNamespace(id=chat_id),
            photo=None,
            rich_message=rich_message,
        )

    async def delete_message(self, chat_id: int, message_id: int):
        if message_id in self.fail_delete:
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=message_id),
                message="Bad Request: message to delete not found",
            )
        self.deleted.append(message_id)


def _msg(bot: FakeBot, chat_id: int, message_id: int = 1):
    return SimpleNamespace(
        message_id=message_id,
        bot=bot,
        chat=SimpleNamespace(id=chat_id),
        photo=None,
        rich_message=None,
    )


def _cb(bot: FakeBot, chat_id: int, message_id: int, *, embedded: bool = True):
    rich_message = None
    if embedded:
        rich_message = SimpleNamespace(
            blocks=[SimpleNamespace(type="photo", photo=[SimpleNamespace(file_id="x")])]
        )
    message = SimpleNamespace(
        message_id=message_id,
        bot=bot,
        chat=SimpleNamespace(id=chat_id),
        photo=None,
        rich_message=rich_message,
    )
    return SimpleNamespace(message=message, from_user=SimpleNamespace(id=chat_id), data="a:view")


@pytest.fixture
def store(tmp_path: Path):
    return reset_screen_session_store_for_tests(tmp_path / "ui_screen_state.json")


def _empty_dashboard():
    return dashboard_rich(type("S", (), {"accounts": [], "by_currency": {}})())  # type: ignore[arg-type]


def test_embed_banner_prepends_photo_block() -> None:
    rich = account_details_rich(sample_account_details())
    combined, embedded = embed_banner(rich, "accounts")
    assert embedded is True
    assert combined.blocks
    assert isinstance(combined.blocks[0], InputRichBlockPhoto)
    assert len(combined.blocks) == len(rich.blocks or []) + 1


async def test_home_to_accounts_removes_previous_screen(store) -> None:
    bot = FakeBot()
    chat_id = 111
    await present_rich(
        _msg(bot, chat_id),  # type: ignore[arg-type]
        _empty_dashboard(),
        None,
        text_fallback="home",
        screen="dashboard",
    )
    assert len(bot.photos) == 0
    assert len(bot.rich) == 1
    assert isinstance(bot.rich_payloads[0].blocks[0], InputRichBlockPhoto)
    session = await store.get(chat_id)
    assert session is not None
    assert session.banner_message_id is None
    assert session.content_message_id == bot.rich[-1]

    class Acc:
        id = 1
        line_label = "A"
        banking_provider = "Airwallex"
        currency = "USD"
        is_archived = False
        balance_minor = 0

    from app.services.totals import AccountTotals

    totals = AccountTotals(
        account=Acc(),  # type: ignore[arg-type]
        in_minor=0,
        out_minor=0,
        expected_minor=0,
        current_minor=0,
        projected_minor=0,
    )
    old_content = bot.rich[-1]
    await present_rich(
        _cb(bot, chat_id, old_content),  # type: ignore[arg-type]
        accounts_overview_rich([Acc()], {1: totals}, archived=False),  # type: ignore[arg-type]
        None,
        text_fallback="accounts",
        screen="accounts",
    )
    assert old_content in bot.deleted
    assert len(bot.photos) == 0
    session = await store.get(chat_id)
    assert session is not None
    assert session.screen == "accounts"
    assert session.banner_message_id is None
    assert session.content_message_id == bot.rich[-1]


async def test_accounts_to_details_to_transactions_and_back(store) -> None:
    bot = FakeBot()
    chat_id = 222
    await present_rich(
        _msg(bot, chat_id),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="a",
        screen="accounts",
    )
    accounts_content = bot.rich[-1]

    await present_rich(
        _cb(bot, chat_id, accounts_content),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="d",
        screen="account-details",
    )
    assert accounts_content in bot.deleted
    details_content = bot.rich[-1]

    await present_rich(
        _cb(bot, chat_id, details_content),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="t",
        screen="transactions",
    )
    assert details_content in bot.deleted
    txn_content = bot.rich[-1]

    await present_rich(
        _cb(bot, chat_id, txn_content),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="d2",
        screen="account-details",
    )
    assert txn_content in bot.deleted
    session = await store.get(chat_id)
    assert session is not None and session.screen == "account-details"
    assert session.banner_message_id is None


async def test_details_to_home(store) -> None:
    bot = FakeBot()
    chat_id = 333
    await present_rich(
        _msg(bot, chat_id),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="d",
        screen="account-details",
    )
    old_c = bot.rich[-1]
    await present_rich(
        _cb(bot, chat_id, old_c),  # type: ignore[arg-type]
        _empty_dashboard(),
        None,
        text_fallback="home",
        screen="dashboard",
    )
    assert old_c in bot.deleted
    assert (await store.get(chat_id)).screen == "dashboard"  # type: ignore[union-attr]


async def test_repeated_and_rapid_navigation(store) -> None:
    bot = FakeBot()
    chat_id = 444
    await present_rich(
        _msg(bot, chat_id),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="a",
        screen="accounts",
    )
    for _ in range(5):
        content = bot.rich[-1]
        await present_rich(
            _cb(bot, chat_id, content),  # type: ignore[arg-type]
            account_details_rich(sample_account_details()),
            None,
            text_fallback="d",
            screen="account-details",
        )
        content = bot.rich[-1]
        await present_rich(
            _cb(bot, chat_id, content),  # type: ignore[arg-type]
            account_details_rich(sample_account_details()),
            None,
            text_fallback="a",
            screen="accounts",
        )
    session = await store.get(chat_id)
    assert session is not None
    assert session.content_message_id == bot.rich[-1]
    assert session.content_message_id not in bot.deleted


async def test_missing_previous_banner_and_delete_failure(store) -> None:
    bot = FakeBot()
    chat_id = 555
    bot.fail_delete.add(49)
    # Legacy separate-photo content (no embedded photo block) still probes id-1.
    cb = _cb(bot, chat_id, 50, embedded=False)
    await cleanup_active_screen(bot, chat_id, callback_message=cb.message)
    assert 50 in bot.deleted


async def test_embedded_untracked_does_not_delete_neighbor(store) -> None:
    bot = FakeBot()
    chat_id = 556
    cb = _cb(bot, chat_id, 50, embedded=True)
    await cleanup_active_screen(bot, chat_id, callback_message=cb.message)
    assert 50 in bot.deleted
    assert 49 not in bot.deleted


async def test_independent_users_do_not_mix(store) -> None:
    bot = FakeBot()
    sessions = {}
    for chat_id in (1001, 1002):
        await present_rich(
            _msg(bot, chat_id),  # type: ignore[arg-type]
            account_details_rich(sample_account_details()),
            None,
            text_fallback="x",
            screen="accounts",
        )
        sessions[chat_id] = await store.get(chat_id)
    s1, s2 = sessions[1001], sessions[1002]
    assert s1 is not None and s2 is not None
    assert s1.content_message_id != s2.content_message_id

    await present_rich(
        _cb(bot, 1001, s1.content_message_id),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="d",
        screen="account-details",
    )
    assert s1.content_message_id in bot.deleted
    s2_after = await store.get(1002)
    assert s2_after is not None
    assert s2_after.content_message_id == s2.content_message_id
    assert s2_after.content_message_id not in bot.deleted


async def test_state_survives_store_reload(tmp_path: Path) -> None:
    path = tmp_path / "ui_screen_state.json"
    store = reset_screen_session_store_for_tests(path)
    await store.set(77, banner_message_id=10, content_message_id=11, screen="accounts")
    reloaded = reset_screen_session_store_for_tests(path)
    session = await reloaded.get(77)
    assert session is not None
    assert session.banner_message_id == 10
    assert session.content_message_id == 11
    assert session.screen == "accounts"


async def test_embed_failure_falls_back_to_separate_photo(store) -> None:
    bot = FakeBot()
    bot.fail_rich_once = True
    chat_id = 777
    await present_rich(
        _msg(bot, chat_id),  # type: ignore[arg-type]
        account_details_rich(sample_account_details()),
        None,
        text_fallback="a",
        screen="accounts",
    )
    assert len(bot.photos) == 1
    assert len(bot.rich) == 1
    session = await store.get(chat_id)
    assert session is not None
    assert session.banner_message_id == bot.photos[-1]
    assert session.content_message_id == bot.rich[-1]
