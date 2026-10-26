"""Application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings, load_settings
from app.database.connection import Database
from app.handlers import setup_routers
from app.middleware.auth import AuthMiddleware
from app.middleware.errors import setup_error_handler
from app.services.container import Services, build_services
from app.services.scheduler import ReminderJob
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def create_app(settings: Settings | None = None) -> tuple[Bot, Dispatcher, Database, AsyncIOScheduler, ReminderJob, Services]:
    settings = settings or load_settings()
    setup_logging(settings.log_level)

    db = Database(settings.database_path)
    await db.connect()
    await db.init()

    services = build_services(db, settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    auth = AuthMiddleware(services)
    dp.message.outer_middleware(auth)
    dp.callback_query.outer_middleware(auth)
    setup_error_handler(dp)
    setup_routers(dp)

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    job = ReminderJob(bot, services, scheduler)
    services.on_reminder_settings_changed = job.reschedule
    stored = await services.reminders.get_settings()
    job.setup()
    scheduler.reschedule_job("daily_reminder", trigger=job._trigger(stored.reminder_time))

    logger.info("app initialized timezone=%s db=%s", settings.timezone, settings.database_path)
    return bot, dp, db, scheduler, job, services


async def run() -> None:
    settings = load_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    bot, dp, db, scheduler, job, _services = await create_app(settings)
    scheduler.start()
    await job.send_if_needed(force=False)
    logger.info("bot polling started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await db.close()
        await bot.session.close()
        logger.info("bot stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
