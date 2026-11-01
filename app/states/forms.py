"""FSM states for multi-step forms."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AccountForm(StatesGroup):
    bank_block = State()
    login_block = State()
    confirm = State()
    edit_value = State()


class BalanceForm(StatesGroup):
    amount = State()


class ChargeForm(StatesGroup):
    amount = State()
    edit_value = State()


class TopUpForm(StatesGroup):
    amount = State()


class LoginForm(StatesGroup):
    value = State()


class DepositForm(StatesGroup):
    value = State()


class SettingsForm(StatesGroup):
    reminder_time = State()
    stale_hours = State()


# Backward-compatible aliases used by leftover tests/imports.
class WithdrawalForm(ChargeForm):
    date = State()
    description = State()
