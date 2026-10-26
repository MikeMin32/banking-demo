from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tests.conftest import draft
from app.services.container import Services
from app.services.reminders import ReminderService
from app.utils.time import local_today


async def test_selects_only_stale_accounts(services: Services) -> None:
    fresh = await services.accounts.create(
        draft(display_name="Fresh", bank_name="Bank", currency="USD", balance_raw="1")
    )
    stale = await services.accounts.create(
        draft(display_name="Stale", bank_name="Bank", currency="USD", balance_raw="2")
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    await services.account_repo.mark_checked(stale.id, old)
    settings, accounts = await services.reminders.stale_accounts()
    assert settings.stale_hours == 24
    ids = {account.id for account in accounts}
    assert stale.id in ids
    assert fresh.id not in ids


async def test_delivery_log_prevents_duplicates(services: Services) -> None:
    plan1 = await services.reminders.build_plan(force=False)
    assert plan1.should_send is True
    await services.reminders.mark_sent(plan1.delivery_date, 1)
    plan2 = await services.reminders.build_plan(force=False)
    assert plan2.should_send is False
    plan3 = await services.reminders.build_plan(force=True)
    assert plan3.should_send is True


async def test_disabled_reminders_do_not_send(services: Services) -> None:
    await services.reminders.set_enabled(False)
    plan = await services.reminders.build_plan()
    assert plan.should_send is False


async def test_local_time_reached() -> None:
    tz = ZoneInfo("Europe/Kyiv")
    service = ReminderService  # type: ignore[misc]
    dummy = object.__new__(ReminderService)
    dummy.timezone = tz
    morning = datetime(2026, 5, 1, 8, 59, tzinfo=tz)
    later = datetime(2026, 5, 1, 9, 0, tzinfo=tz)
    assert dummy.local_time_reached("09:00", now=morning) is False
    assert dummy.local_time_reached("09:00", now=later) is True


async def test_settings_persist(services: Services) -> None:
    await services.reminders.set_time("18:30")
    await services.reminders.set_stale_hours(48)
    await services.reminders.set_compact_overview(True)
    loaded = await services.reminders.get_settings()
    assert loaded.reminder_time == "18:30"
    assert loaded.stale_hours == 48
    assert loaded.compact_overview is True
    assert local_today(services.tz).isoformat()
