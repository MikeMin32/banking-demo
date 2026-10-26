"""Structured logging that avoids sensitive banking fields."""

from __future__ import annotations

import logging
import sys

SENSITIVE_KEYS = frozenset(
    {
        "iban",
        "account_number",
        "routing_number",
        "sort_code",
        "swift",
        "swift_bic",
        "login_url",
        "login_username",
        "password",
        "password_manager_ref",
        "otp",
        "token",
        "bot_token",
        "payment_reference",
        "deposit",
        "credential",
        "secret",
        "holder_name",
        "notes",
    }
)


class RedactingFilter(logging.Filter):
    """Drop or mask extra fields that look like banking secrets."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if hasattr(record, "__dict__"):
            for key in list(record.__dict__.keys()):
                if key.lower() in SENSITIVE_KEYS:
                    record.__dict__[key] = "[redacted]"
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
