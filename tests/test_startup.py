from __future__ import annotations

from app.config import Settings
from app.main import create_app


async def test_app_starts_without_telegram_network(tmp_path) -> None:
    settings = Settings(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        database_path=str(tmp_path / "boot.db"),
        timezone="Europe/Kyiv",
        reminder_time="09:00",
        log_level="WARNING",
    )
    bot, dp, db, scheduler, job, services = await create_app(settings)
    try:
        assert bot is not None
        assert dp is not None
        assert services.auth.is_authorized(1001)
        assert scheduler.get_job("daily_reminder") is not None
        row = await db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
        assert row is not None
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await db.close()
        await bot.session.close()
