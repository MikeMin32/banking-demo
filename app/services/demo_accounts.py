"""Idempotent DEMO/TEST seed for the three VM accounts.

This module is never called on bot startup. Run scripts/seed_demo_accounts.py.
All generated balances, history, and withdrawals are DEMO/TEST data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.config import Settings
from app.database.connection import Database
from app.database.repositories.accounts import Account
from app.services.accounts import AccountDraft
from app.services.backup import backup_database
from app.services.container import Services, build_services
from app.services.money import parse_to_minor
from app.utils.time import parse_iso, utc_now, utc_now_iso

TARGET_DEMO_ACCOUNTS: tuple[dict[str, object], ...] = (
    {"vm_number": 9, "company_name": "LeBon Shoppe", "bank_name": "Airwallex", "currency": "USD"},
    {"vm_number": 4, "company_name": "Automation Direct", "bank_name": "Airwallex", "currency": "USD"},
    {"vm_number": 32, "company_name": "Graphics Press", "bank_name": "Airwallex", "currency": "USD"},
)

# Fingerprints of the original seed_demo.py rows. Safe to replace.
OBSOLETE_DEMO_KEYS = frozenset(
    {
        ("Operating", "Chase"),
        ("Europe", "Wise"),
        ("Savings", "Revolut"),
    }
)


@dataclass
class SeedReport:
    database_path: str
    backup_path: str | None
    created: list[str]
    updated: list[str]
    removed: list[str]
    preserved: list[str]
    withdrawals_upserted: int = 0
    history_written: int = 0
    activity_skipped: list[str] = field(default_factory=list)


class DemoSeedBlocked(RuntimeError):
    """Raised when the configured database looks like production."""


def _is_target(account: Account) -> bool:
    return any(
        account.vm_number == int(item["vm_number"]) and account.company_name == item["company_name"]
        for item in TARGET_DEMO_ACCOUNTS
    )


def _is_obsolete_demo(account: Account) -> bool:
    names = {account.display_name, account.company_name}
    for name in names:
        if name and (name, account.bank_name) in OBSOLETE_DEMO_KEYS:
            return True
    return False


def _production_block_reason(settings: Settings) -> str | None:
    env = (os.environ.get("BANK_MANAGER_ENV") or os.environ.get("ENVIRONMENT") or "").strip().lower()
    if env in {"prod", "production"}:
        return f"ENVIRONMENT={env}"
    resolved = Path(settings.database_path).expanduser().resolve()
    path = str(resolved).lower()
    if "production" in resolved.name.lower() or "/prod/" in f"{path}/":
        return f"database path looks like production: {resolved}"
    return None


async def apply_demo_accounts(settings: Settings) -> SeedReport:
    blocked = _production_block_reason(settings)
    if blocked:
        raise DemoSeedBlocked(
            f"Refusing to seed DEMO/TEST data ({blocked}). "
            "This script is only for the development/demo database."
        )
    db = Database(settings.database_path)
    await db.connect()
    await db.init()
    services = build_services(db, settings)
    backup_path: str | None = None
    try:
        dest = Path(settings.database_path).resolve().parent / "backups"
        backup = await backup_database(db, dest)
        backup_path = str(backup)
        report = await _sync_accounts(services)
        await _populate_demo_activity(services, report)
        report.database_path = str(Path(settings.database_path).resolve())
        report.backup_path = backup_path
        return report
    finally:
        await db.close()


async def _sync_accounts(services: Services) -> SeedReport:
    created: list[str] = []
    updated: list[str] = []
    removed: list[str] = []
    preserved: list[str] = []

    existing = await services.account_repo.list_all(archived=None)
    for account in existing:
        if _is_target(account):
            continue
        if _is_obsolete_demo(account):
            label = f"{account.display_name} (id={account.id}, {account.bank_name})"
            await services.accounts.delete(account.id)
            removed.append(label)
        else:
            preserved.append(f"{account.display_name} (id={account.id})")

    for item in TARGET_DEMO_ACCOUNTS:
        vm_number = int(item["vm_number"])
        company = str(item["company_name"])
        provider = str(item["bank_name"])
        currency = str(item["currency"])
        found = await services.accounts.find_by_vm_company(vm_number, company)
        if found is None:
            account = await services.accounts.create(
                AccountDraft(
                    vm_number=vm_number,
                    company_name=company,
                    bank_name=provider,
                    currency=currency,
                    balance_raw="0",
                )
            )
            created.append(account.display_name)
            continue
        changes: dict[str, object] = {}
        if found.bank_name != provider:
            changes["bank_name"] = provider
        if found.currency != currency:
            # Keep existing amounts; only relabel if already USD/EUR request.
            changes["currency"] = currency
        if found.is_archived:
            await services.accounts.unarchive(found.id)
        if changes:
            await services.accounts.update(found.id, **changes)
            updated.append(found.display_name)
        else:
            updated.append(f"{found.display_name} (unchanged)")

    return SeedReport(
        database_path="",
        backup_path=None,
        created=created,
        updated=updated,
        removed=removed,
        preserved=preserved,
    )


# DEMO/TEST activity only. Never attached to non-target accounts.
# Amounts are USD decimal strings; history is oldest → newest (last = current).
DEMO_ACTIVITY: dict[int, dict[str, object]] = {
    9: {
        "balance": "12450.75",
        "history": [
            "10580.00",
            "10950.50",
            "11420.00",
            "12180.25",
            "11860.00",
            "13010.40",
            "11990.15",
            "12450.75",
        ],
        "withdrawals": [
            {"amount": "2500.00", "status": "pending", "description": "Supplier Payment", "days": 5},
            {"amount": "1200.00", "status": "pending", "description": "Operational Expenses", "days": 12},
            {"amount": "850.00", "status": "completed", "description": "Previous Withdrawal", "days": -6},
        ],
    },
    4: {
        "balance": "8725.40",
        "history": [
            "6980.00",
            "7450.20",
            "8020.00",
            "7688.50",
            "8410.00",
            "8195.75",
            "8510.00",
            "8725.40",
        ],
        "withdrawals": [
            {"amount": "1500.00", "status": "pending", "description": "Vendor Payment", "days": 7},
            {"amount": "620.00", "status": "completed", "description": "Software Subscription", "days": -10},
            {"amount": "950.00", "status": "cancelled", "description": "Cancelled Transfer", "days": -3},
        ],
    },
    32: {
        "balance": "5340.20",
        "history": [
            "4025.00",
            "4380.60",
            "4890.10",
            "4610.00",
            "5120.80",
            "4980.00",
            "5210.45",
            "5340.20",
        ],
        "withdrawals": [
            {"amount": "1000.00", "status": "pending", "description": "Printing Equipment", "days": 9},
            {"amount": "450.00", "status": "pending", "description": "Materials", "days": 3},
            {"amount": "300.00", "status": "completed", "description": "Previous Withdrawal", "days": -8},
        ],
    },
}


_HISTORY_SPAN_DAYS = (29, 25, 21, 16, 12, 8, 4, 0)
_OPENING_BALANCES = {"9": "9800.00", "4": "6500.00", "32": "3750.00"}


async def _populate_demo_activity(services: Services, report: SeedReport) -> None:
    now = utc_now()
    for item in TARGET_DEMO_ACCOUNTS:
        vm_number = int(item["vm_number"])
        account = await services.accounts.find_by_vm_company(vm_number, str(item["company_name"]))
        if account is None:
            continue
        spec = DEMO_ACTIVITY[vm_number]
        currency = "USD"
        final_minor = parse_to_minor(str(spec["balance"]), currency)
        planned_history = [parse_to_minor(value, currency) for value in spec["history"]]  # type: ignore[arg-type]
        demo_withdrawals = spec["withdrawals"]  # type: ignore[assignment]

        existing_history = await services.balances.history.list_for_account(account.id, limit=100)
        existing_new = list(reversed([entry.new_balance_minor for entry in existing_history]))
        extra_history = bool(existing_history) and existing_new != planned_history
        extra_withdrawals = await _has_unexpected_withdrawals(services, account.id, demo_withdrawals, currency)
        if extra_withdrawals or (extra_history and account.balance_minor != 0):
            report.activity_skipped.append(account.display_name)
            continue

        last_ts = (now - timedelta(hours=1)).replace(second=0, microsecond=0).isoformat()
        checked = now.replace(second=0, microsecond=0).isoformat()
        if existing_new != planned_history:
            report.history_written += await _rewrite_demo_history(
                services, account.id, vm_number, planned_history, currency, now
            )
            await services.account_repo.set_balance(
                account.id,
                final_minor,
                last_updated_at=last_ts,
                last_checked_at=checked,
                updated_at=utc_now_iso(),
            )
        elif account.balance_minor != final_minor:
            await services.account_repo.set_balance(
                account.id,
                final_minor,
                last_updated_at=last_ts,
                last_checked_at=checked,
                updated_at=utc_now_iso(),
            )
        else:
            updated = parse_iso(account.last_updated_at)
            if updated is not None and updated > now:
                await services.account_repo.set_balance(
                    account.id,
                    final_minor,
                    last_updated_at=last_ts,
                    last_checked_at=checked,
                    updated_at=utc_now_iso(),
                )

        report.withdrawals_upserted += await _upsert_demo_withdrawals(
            services, account.id, demo_withdrawals, currency, now
        )


async def _rewrite_demo_history(
    services: Services,
    account_id: int,
    vm_number: int,
    planned_history: list[int],
    currency: str,
    now: datetime,
) -> int:
    await services.balances.history.delete_for_account(account_id)
    opening = parse_to_minor(_OPENING_BALANCES[str(vm_number)], currency)
    written = 0
    for index, new_minor in enumerate(planned_history):
        recorded = (now - timedelta(days=_HISTORY_SPAN_DAYS[index])).replace(
            hour=10 + index % 5, minute=15, second=0, microsecond=0
        )
        old_minor = planned_history[index - 1] if index else opening
        await services.balances.history.add(
            account_id=account_id,
            old_balance_minor=old_minor,
            new_balance_minor=new_minor,
            recorded_at=recorded.isoformat(),
        )
        written += 1
    return written


async def _has_unexpected_withdrawals(services: Services, account_id: int, spec: list, currency: str) -> bool:
    expected = {(item["description"], parse_to_minor(item["amount"], currency)) for item in spec}
    existing = await services.withdrawals.withdrawals.list_withdrawals(account_id=account_id, limit=100)
    return any((item.description, item.amount_minor) not in expected for item in existing)


async def _upsert_demo_withdrawals(
    services: Services,
    account_id: int,
    spec: list,
    currency: str,
    now: datetime,
) -> int:
    existing = await services.withdrawals.withdrawals.list_withdrawals(account_id=account_id, limit=100)
    by_key = {(item.description, item.amount_minor): item for item in existing}
    changed = 0
    for item in spec:
        amount = parse_to_minor(item["amount"], currency)
        key = (item["description"], amount)
        expected_date = (now + timedelta(days=int(item["days"]))).date().isoformat()
        found = by_key.get(key)
        if found is None:
            created_offset = -2 if item["status"] == "pending" else min(int(item["days"]), -1)
            created = await services.withdrawals.withdrawals.create(
                account_id=account_id,
                amount_minor=amount,
                created_at=(now + timedelta(days=created_offset)).isoformat(),
                expected_date=expected_date,
                description=item["description"],
            )
            if item["status"] != "pending":
                closed_at = (now + timedelta(days=int(item["days"]))).isoformat()
                await services.withdrawals.withdrawals.update_fields(
                    created.id,
                    {"status": item["status"], "completed_at": closed_at},
                    closed_at,
                )
            changed += 1
            continue
        fields: dict[str, object] = {}
        if found.status != item["status"]:
            fields["status"] = item["status"]
        if item["status"] == "pending" and found.completed_at:
            fields["completed_at"] = None
        elif item["status"] != "pending" and not found.completed_at:
            fields["completed_at"] = now.isoformat()
        if fields:
            await services.withdrawals.withdrawals.update_fields(found.id, fields, now.isoformat())
            changed += 1
    return changed
