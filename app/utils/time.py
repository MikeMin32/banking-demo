"""UTC-first timestamp helpers. Display conversion uses the configured timezone."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_local(value: datetime | str | None, tz: ZoneInfo) -> datetime | None:
    dt = parse_iso(value) if isinstance(value, str) else value
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def format_dt(value: datetime | str | None, tz: ZoneInfo, *, with_seconds: bool = False) -> str:
    local = to_local(value, tz)
    if local is None:
        return "never"
    pattern = "%d %b %Y, %H:%M:%S" if with_seconds else "%d %b %Y, %H:%M"
    return local.strftime(pattern)


def format_date(value: date | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        if not value.strip():
            return "—"
        return value
    return value.isoformat()


def local_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def parse_user_date(raw: str, tz: ZoneInfo) -> date:
    """Parse a user-supplied date. Accepts YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, today, tomorrow."""
    text = raw.strip().lower()
    if not text:
        raise ValueError("Please enter a date.")
    today = local_today(tz)
    if text in {"today", "now"}:
        return today
    if text == "tomorrow":
        from datetime import timedelta

        return today + timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD, DD.MM.YYYY, today, or tomorrow.")
