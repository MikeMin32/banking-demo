"""Reusable compact account identity header for nested screens."""

from __future__ import annotations

from app.database.repositories.accounts import Account
from app.services.container import Services
from app.services.money import format_amount
from app.services.totals import AccountTotals
from app.utils.formatting import e


def account_context_header(
    account: Account,
    available_minor: int,
    pending_minor: int = 0,
    *,
    current_minor: int | None = None,
) -> str:
    """Compact header for nested prompts. Available == projected."""
    line = e(account.line_label.upper())
    provider = e(account.banking_provider.upper())
    current = format_amount(
        account.balance_minor if current_minor is None else current_minor,
        account.currency,
        with_symbol=True,
    )
    projected = format_amount(available_minor, account.currency, with_symbol=True)
    del pending_minor
    return (
        f"🏦 <b>{line} · {provider}</b>\n"
        f"💰 Current: <b>{current}</b>\n"
        f"📊 Projected: {projected}"
    )


def totals_block(totals: AccountTotals, *, compact: bool = False) -> str:
    currency = totals.account.currency
    inn = format_amount(totals.in_minor, currency, with_symbol=True)
    out = format_amount(totals.out_minor, currency, with_symbol=True)
    expected = format_amount(totals.expected_minor, currency, with_symbol=True)
    current = format_amount(totals.current_minor, currency, with_symbol=True)
    projected = format_amount(totals.projected_minor, currency, with_symbol=True)
    if compact:
        return (
            f"🟢 {inn}  ·  🔴 {out}  ·  ⏳ {expected}\n"
            f"💰 {current}  →  📊 {projected}"
        )
    return (
        f"🟢 In: {inn}\n"
        f"🔴 Out: {out}\n"
        f"⏳ Expected: {expected}\n\n"
        f"💰 Current Balance: <b>{current}</b>\n"
        f"📊 Projected Balance: <b>{projected}</b>"
    )


def account_identity_line(account: Account) -> str:
    return f"🏦 <b>{e(account.line_label.upper())} · {e(account.banking_provider.upper())}</b>"


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
        account,
        projection.available_minor,
        projection.pending_minor,
        current_minor=projection.recorded_minor,
    )
    return account, projection.available_minor, projection.pending_minor, header


async def account_body(services: Services, account_id: int, body: str) -> tuple[Account, str]:
    account, available, pending, _ = await fresh_account_header(services, account_id)
    return account, with_account_header(account, available, body, pending_minor=pending)
