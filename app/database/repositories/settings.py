"""Reminder and display settings persistence (singleton row)."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database


@dataclass(slots=True)
class ReminderSettings:
    enabled: bool
    reminder_time: str
    stale_hours: int
    compact_overview: bool


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self) -> ReminderSettings:
        row = await self.db.fetchone("SELECT * FROM reminder_settings WHERE id = 1")
        if row is None:
            return ReminderSettings(
                enabled=True,
                reminder_time="09:00",
                stale_hours=24,
                compact_overview=False,
            )
        return ReminderSettings(
            enabled=bool(row["enabled"]),
            reminder_time=row["reminder_time"],
            stale_hours=int(row["stale_hours"]),
            compact_overview=bool(row["compact_overview"]),
        )

    async def update(self, **fields: object) -> ReminderSettings:
        allowed = {"enabled", "reminder_time", "stale_hours", "compact_overview"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown settings fields: {unknown}")
        if fields:
            assignments = ", ".join(f"{column} = ?" for column in fields)
            values = list(fields.values())
            await self.db.execute(
                f"UPDATE reminder_settings SET {assignments} WHERE id = 1",
                tuple(values),
            )
        return await self.get()


class ReminderLogRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def was_sent_on(self, delivery_date: str) -> bool:
        row = await self.db.fetchone(
            "SELECT 1 FROM reminder_delivery_log WHERE delivery_date = ?",
            (delivery_date,),
        )
        return row is not None

    async def record(self, delivery_date: str, sent_at: str, recipient_count: int) -> None:
        await self.db.execute(
            """
            INSERT OR IGNORE INTO reminder_delivery_log (delivery_date, sent_at, recipient_count)
            VALUES (?, ?, ?)
            """,
            (delivery_date, sent_at, recipient_count),
        )
