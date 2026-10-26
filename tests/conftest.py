from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.database.connection import Database
from app.services.accounts import AccountDraft
from app.services.container import Services, build_services


def draft(**kwargs) -> AccountDraft:
    if "display_name" in kwargs and "company_name" not in kwargs:
        kwargs["company_name"] = kwargs.pop("display_name")
    else:
        kwargs.pop("display_name", None)
    kwargs.setdefault("vm_number", 1)
    kwargs.setdefault("company_name", "Test Co")
    kwargs.setdefault("bank_name", "Airwallex")
    kwargs.setdefault("currency", "USD")
    kwargs.setdefault("balance_raw", "0")
    return AccountDraft(**kwargs)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        allowed_user_ids="1002, 1003",
        database_path=str(tmp_path / "test.db"),
        timezone="Europe/Kyiv",
        reminder_time="09:00",
        log_level="WARNING",
        dev_allow_any_user=False,
    )


@pytest.fixture
async def db(settings: Settings) -> Database:
    database = Database(settings.database_path)
    await database.connect()
    await database.init()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
async def services(db: Database, settings: Settings) -> Services:
    return build_services(db, settings)
