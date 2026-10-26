"""Application configuration loaded from environment variables."""

from __future__ import annotations

import re
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class Settings(BaseSettings):
    """Runtime settings. Required values are validated on startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(min_length=1)
    owner_telegram_id: int
    allowed_user_ids: str = ""
    database_path: str = "./data/bank_manager.db"
    timezone: str = "Europe/Kyiv"
    reminder_time: str = "09:00"
    log_level: str = "INFO"
    dev_allow_any_user: bool = False

    @field_validator("bot_token")
    @classmethod
    def token_not_blank(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("BOT_TOKEN must not be empty")
        return token

    @field_validator("owner_telegram_id")
    @classmethod
    def owner_must_be_positive(cls, value: int) -> int:
        if value == 0:
            raise ValueError("OWNER_TELEGRAM_ID must be a real Telegram user ID")
        return value

    @field_validator("reminder_time")
    @classmethod
    def valid_hh_mm(cls, value: str) -> str:
        if not _TIME_RE.match(value.strip()):
            raise ValueError("REMINDER_TIME must be HH:MM in 24-hour format")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown TIMEZONE: {value}") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        level = value.upper().strip()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return level

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def authorized_user_ids(self) -> frozenset[int]:
        ids: set[int] = {self.owner_telegram_id}
        raw = self.allowed_user_ids.strip()
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.add(int(part))
                except ValueError as exc:
                    raise ValueError(
                        f"ALLOWED_USER_IDS must be a comma-separated list of integers, got {part!r}"
                    ) from exc
        return frozenset(ids)

    def is_authorized(self, user_id: int) -> bool:
        if self.dev_allow_any_user:
            return bool(user_id)
        return user_id in self.authorized_user_ids

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_telegram_id


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_settings(**overrides: object) -> Settings:
    """Load settings, optionally overriding env values (used in tests)."""
    if overrides:
        return Settings(**overrides)  # type: ignore[arg-type]
    return Settings()
