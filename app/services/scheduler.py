"""Async daily reminder job. Failures must not crash the bot."""

from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.keyboards.settings import reminder_inline_kb
from app.services.container import Services
from app.utils.formatting import reminder_text

logger = logging.getLogger(__name__)


class ReminderJob:
    def __init__(self, bot: Bot, services: Services, scheduler: AsyncIOScheduler) -> None:
        self.bot = bot
        self.services = services
        self.scheduler = scheduler

    def setup(self) -> None:
        self.scheduler.add_job(
            self.tick,
            trigger=self._trigger("09:00"),
            id="daily_reminder",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    async def reschedule(self) -> None:
        settings = await self.services.reminders.get_settings()
        if "daily_reminder" in {job.id for job in self.scheduler.get_jobs()}:
            self.scheduler.reschedule_job("daily_reminder", trigger=self._trigger(settings.reminder_time))
        else:
            self.setup()
            self.scheduler.reschedule_job("daily_reminder", trigger=self._trigger(settings.reminder_time))
        logger.info("reminder job rescheduled")

    def _trigger(self, hh_mm: str) -> CronTrigger:
        hour, minute = hh_mm.split(":")
        return CronTrigger(hour=int(hour), minute=int(minute), timezone=self.services.tz)

    async def tick(self) -> None:
        try:
            await self.send_if_needed()
        except Exception:
            logger.exception("reminder tick failed")

    async def send_if_needed(self, *, force: bool = False) -> int:
        try:
            plan = await self.services.reminders.build_plan(force=force)
            if not plan.should_send:
                return 0
            if not force and not self.services.reminders.local_time_reached(plan.settings.reminder_time):
                return 0
            text = reminder_text(plan.stale_accounts, self.services.tz, plan.settings.stale_hours)
            markup = reminder_inline_kb(plan.stale_accounts)
            sent = 0
            for user_id in self.services.settings.authorized_user_ids:
                try:
                    await self.bot.send_message(user_id, text, reply_markup=markup)
                    sent += 1
                except Exception:
                    logger.exception("reminder delivery failed user_id=%s", user_id)
            await self.services.reminders.mark_sent(plan.delivery_date, sent)
            logger.info("reminder processed recipients=%s stale=%s", sent, len(plan.stale_accounts))
            return sent
        except Exception:
            logger.exception("reminder send failed")
            return 0
