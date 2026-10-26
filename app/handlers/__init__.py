"""Register all routers on the dispatcher."""

from __future__ import annotations

from aiogram import Dispatcher

from app.handlers.accounts import router as accounts_router
from app.handlers.balances import router as balances_router
from app.handlers.deposits import router as deposits_router
from app.handlers.login import router as login_router
from app.handlers.reminders import router as reminders_router
from app.handlers.settings import router as settings_router
from app.handlers.start import router as start_router
from app.handlers.withdrawals import router as withdrawals_router
from app.handlers.fallback import router as fallback_router


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(start_router)
    dp.include_router(accounts_router)
    dp.include_router(balances_router)
    dp.include_router(withdrawals_router)
    dp.include_router(deposits_router)
    dp.include_router(login_router)
    dp.include_router(reminders_router)
    dp.include_router(settings_router)
    dp.include_router(fallback_router)
