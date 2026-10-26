"""Daily reminder selection. Pure logic is kept testable without Telegram."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.database.repositories.accounts import Account
from app.database.repositories.settings import ReminderLogRepository, ReminderSettings, SettingsRepository
from app.services.dashboard import DashboardService, is_stale
from app.utils.time import local_today, utc_now, utc_now_iso


@dataclass(slots=True)
class ReminderPlan:
    should_send: bool
    delivery_date: str
    settings: ReminderSettings
    stale_accounts: list[Account]


class ReminderService:
    def __init__(
        self,
        settings_repo: SettingsRepository,
        log_repo: ReminderLogRepository,
        dashboard: DashboardService,
        timezone: ZoneInfo,
    ) -> None:
        self.settings_repo = settings_repo
        self.log_repo = log_repo
        self.dashboard = dashboard
        self.timezone = timezone

    async def get_settings(self) -> ReminderSettings:
        return await self.settings_repo.get()

    async def set_enabled(self, enabled: bool) -> ReminderSettings:
        return await self.settings_repo.update(enabled=1 if enabled else 0)

    async def set_time(self, hh_mm: str) -> ReminderSettings:
        hour, minute = hh_mm.split(":")
        time(int(hour), int(minute))  # validate
        return await self.settings_repo.update(reminder_time=hh_mm)

    async def set_stale_hours(self, hours: int) -> ReminderSettings:
        if hours < 1 or hours > 720:
            raise ValueError("Stale threshold must be between 1 and 720 hours.")
        return await self.settings_repo.update(stale_hours=hours)

    async def set_compact_overview(self, compact: bool) -> ReminderSettings:
        return await self.settings_repo.update(compact_overview=1 if compact else 0)

    async def stale_accounts(self, *, now: datetime | None = None) -> tuple[ReminderSettings, list[Account]]:
        settings = await self.get_settings()
        snapshot = await self.dashboard.snapshot(stale_hours=settings.stale_hours, now=now)
        stale = [account for account in snapshot.accounts if account.id in snapshot.stale_ids]
        return settings, stale

    async def build_plan(self, *, now: datetime | None = None, force: bool = False) -> ReminderPlan:
        moment = now or utc_now()
        settings, stale = await self.stale_accounts(now=moment)
        delivery_date = local_today(self.timezone).isoformat()
        already_sent = await self.log_repo.was_sent_on(delivery_date)
        should = force or (settings.enabled and not already_sent)
        return ReminderPlan(
            should_send=should,
            delivery_date=delivery_date,
            settings=settings,
            stale_accounts=stale,
        )

    def local_time_reached(self, reminder_time: str, *, now: datetime | None = None) -> bool:
        moment = (now or utc_now()).astimezone(self.timezone)
        hour, minute = reminder_time.split(":")
        scheduled = time(int(hour), int(minute))
        return moment.timetz().replace(tzinfo=None) >= scheduled

    async def mark_sent(self, delivery_date: str, recipient_count: int) -> None:
        await self.log_repo.record(delivery_date, utc_now_iso(), recipient_count)

    @staticmethod
    def select_stale(accounts: list[Account], *, stale_hours: int, now: datetime) -> list[Account]:
        return [account for account in accounts if is_stale(account, now=now, stale_hours=stale_hours)]
