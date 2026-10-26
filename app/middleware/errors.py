"""Global error handling. User-facing messages stay generic."""

from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

from app.services.accounts import AccountError
from app.services.money import MoneyError
from app.services.withdrawals import WithdrawalError

logger = logging.getLogger(__name__)


def setup_error_handler(dp: Dispatcher) -> None:
    @dp.error()
    async def on_error(event: ErrorEvent) -> bool:
        exc = event.exception
        if isinstance(exc, (AccountError, WithdrawalError, MoneyError, ValueError)):
            message = str(exc) or "Please check that value and try again."
        else:
            logger.exception("unhandled error")
            message = "Something went wrong. Please try again from the menu."
        update = event.update
        try:
            if update.callback_query:
                await update.callback_query.answer(message, show_alert=True)
            elif update.message:
                await update.message.answer(message)
        except Exception:
            logger.exception("failed to notify user of an error")
        return True
