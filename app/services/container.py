"""Service locator assembled once at startup and injected via middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from app.config import Settings
from app.database.connection import Database
from app.database.repositories.accounts import AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.repositories.deposits import DepositRepository
from app.database.repositories.settings import ReminderLogRepository, SettingsRepository
from app.database.repositories.withdrawals import WithdrawalRepository
from app.services.accounts import AccountService
from app.services.auth import AuthService
from app.services.balances import BalanceService
from app.services.dashboard import DashboardService
from app.services.exports import ExportService
from app.services.reminders import ReminderService
from app.services.withdrawals import WithdrawalService


@dataclass
class Services:
    settings: Settings
    db: Database
    accounts: AccountService
    balances: BalanceService
    withdrawals: WithdrawalService
    dashboard: DashboardService
    reminders: ReminderService
    exports: ExportService
    auth: AuthService
    deposits: DepositRepository
    account_repo: AccountRepository
    tz: ZoneInfo
    on_reminder_settings_changed: Callable[[], Awaitable[None]] | None = field(default=None)


def build_services(db: Database, settings: Settings) -> Services:
    account_repo = AccountRepository(db)
    balance_repo = BalanceRepository(db)
    withdrawal_repo = WithdrawalRepository(db)
    deposit_repo = DepositRepository(db)
    settings_repo = SettingsRepository(db)
    log_repo = ReminderLogRepository(db)
    dashboard = DashboardService(account_repo, withdrawal_repo)
    return Services(
        settings=settings,
        db=db,
        accounts=AccountService(account_repo),
        balances=BalanceService(account_repo, balance_repo),
        withdrawals=WithdrawalService(account_repo, withdrawal_repo),
        dashboard=dashboard,
        reminders=ReminderService(settings_repo, log_repo, dashboard, settings.tz),
        exports=ExportService(account_repo, balance_repo, withdrawal_repo),
        auth=AuthService(settings),
        deposits=deposit_repo,
        account_repo=account_repo,
        tz=settings.tz,
    )
