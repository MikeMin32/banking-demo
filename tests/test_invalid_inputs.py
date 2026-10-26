from __future__ import annotations

import pytest

from app.services.accounts import AccountError
from tests.conftest import draft
from app.services.container import Services
from app.services.money import MoneyError, parse_to_minor
from app.services.withdrawals import WithdrawalError
from app.utils.time import parse_user_date
from zoneinfo import ZoneInfo


async def test_invalid_currency_and_amount(services: Services) -> None:
    with pytest.raises(AccountError):
        await services.accounts.create(draft(company_name="A", bank_name="B", currency="dollar"))
    with pytest.raises(AccountError):
        await services.accounts.create(draft(company_name="A", bank_name="B", currency="USD", balance_raw="ten"))


async def test_invalid_dates() -> None:
    tz = ZoneInfo("Europe/Kyiv")
    with pytest.raises(ValueError):
        parse_user_date("13/40/2026", tz)
    with pytest.raises(ValueError):
        parse_user_date("", tz)
    with pytest.raises(ValueError):
        parse_user_date("soon", tz)
    assert parse_user_date("2026-10-20", tz).isoformat() == "2026-10-20"


async def test_unknown_ids(services: Services) -> None:
    with pytest.raises(AccountError):
        await services.accounts.update(404, company_name="Nope")
    with pytest.raises(WithdrawalError):
        await services.withdrawals.complete(404)
    with pytest.raises(MoneyError):
        parse_to_minor("1.234", "USD")


async def test_stale_hours_bounds(services: Services) -> None:
    with pytest.raises(ValueError):
        await services.reminders.set_stale_hours(0)
    with pytest.raises(ValueError):
        await services.reminders.set_stale_hours(10_000)
