"""FSM states for multi-step forms."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AccountForm(StatesGroup):
    vm_number = State()
    company = State()
    provider = State()
    provider_other = State()
    currency = State()
    currency_other = State()
    balance = State()
    login_url = State()
    login_username = State()
    vault = State()
    notes = State()
    confirm = State()
    edit_value = State()


class BalanceForm(StatesGroup):
    amount = State()


class WithdrawalForm(StatesGroup):
    amount = State()
    date = State()
    description = State()
    edit_value = State()


class DepositForm(StatesGroup):
    value = State()


class SettingsForm(StatesGroup):
    reminder_time = State()
    stale_hours = State()
