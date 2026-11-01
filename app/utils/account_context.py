"""Reusable compact account identity header for nested screens."""

from __future__ import annotations

from app.database.repositories.accounts import Account
from app.services.container import Services
from app.services.money import format_amount
from app.utils.formatting import e


def account_context_header(
    account: Account,
    available_minor: int,
    pending_minor: int = 0,
) -> str:
    line = e(account.line_label.upper())
    provider = e(account.banking_provider.upper())
    available = format_amount(available_minor, account.currency, with_symbol=True)
    pending = format_amount(pending_minor, account.currency, with_symbol=True)
    return (
        f"🏦 <b>{line} · {provider}</b>\n"
        f"💰 Active Balance: <b>{available}</b>\n"
        f"⏳ Active Charges: {pending}"
    )


def with_account_header(
    account: Account,
    available_minor: int,
    body: str,
    *,
    pending_minor: int = 0,
) -> str:
    body = (body or "").strip()
    header = account_context_header(account, available_minor, pending_minor)
    if not body:
        return header
    return f"{header}\n\n{body}"


async def fresh_account_header(
    services: Services, account_id: int
) -> tuple[Account, int, int, str]:
    """Load account + live available/pending. Never use FSM-cached amounts."""
    account = await services.accounts.get(account_id)
    projection = await services.withdrawals.projection(account.id)
    header = account_context_header(
        account, projection.available_minor, projection.pending_minor
    )
    return account, projection.available_minor, projection.pending_minor, header


async def account_body(services: Services, account_id: int, body: str) -> tuple[Account, str]:
    account, available, pending, _ = await fresh_account_header(services, account_id)
    return account, with_account_header(account, available, body, pending_minor=pending)
