from __future__ import annotations

import pytest

from app.services.accounts import AccountError
from app.services.container import Services
from tests.conftest import draft


async def test_create_account(services: Services) -> None:
    account = await services.accounts.create(
        draft(vm_number=9, company_name="  LeBon Shoppe  ", bank_name="Airwallex", currency="usd", balance_raw="100.00")
    )
    assert account.id > 0
    assert account.display_name == "VM 9 - LeBon Shoppe"
    assert account.vm_number == 9
    assert account.company_name == "LeBon Shoppe"
    assert account.banking_provider == "Airwallex"
    assert account.currency == "USD"
    assert account.balance_minor == 10000
    assert account.last_updated_at is not None
    assert account.last_checked_at is not None
    assert not account.is_archived


async def test_create_n26_and_custom_provider(services: Services) -> None:
    n26 = await services.accounts.create(draft(vm_number=4, company_name="Automation Direct", bank_name="N26", currency="EUR"))
    other = await services.accounts.create(
        draft(vm_number=32, company_name="Graphics Press", bank_name="Revolut", currency="USD")
    )
    assert n26.banking_provider == "N26"
    assert n26.display_name == "VM 4 - Automation Direct"
    assert other.banking_provider == "Revolut"
    assert other.display_name == "VM 32 - Graphics Press"


async def test_create_rejects_invalid_identity(services: Services) -> None:
    with pytest.raises(AccountError):
        await services.accounts.create(draft(vm_number=0, company_name="Co"))
    with pytest.raises(AccountError):
        await services.accounts.create(draft(vm_number="abc", company_name="Co"))
    with pytest.raises(AccountError):
        await services.accounts.create(draft(vm_number=1, company_name="  "))
    with pytest.raises(AccountError):
        await services.accounts.create(draft(vm_number=1, company_name="Co", bank_name=""))
    with pytest.raises(AccountError):
        await services.accounts.create(draft(vm_number=1, company_name="Co", currency="US"))


async def test_edit_vm_and_company_updates_display_name(services: Services) -> None:
    account = await services.accounts.create(draft(vm_number=9, company_name="LeBon Shoppe", bank_name="Airwallex", currency="EUR"))
    updated = await services.accounts.update(account.id, vm_number=4, company_name="Automation Direct")
    assert updated.display_name == "VM 4 - Automation Direct"
    assert updated.vm_number == 4
    assert updated.company_name == "Automation Direct"
    assert updated.banking_provider == "Airwallex"


async def test_edit_provider(services: Services) -> None:
    account = await services.accounts.create(draft(vm_number=1, company_name="Co", bank_name="Airwallex"))
    updated = await services.accounts.update(account.id, bank_name="N26")
    assert updated.banking_provider == "N26"
    assert updated.display_name == "VM 1 - Co"


async def test_archive_and_unarchive(services: Services) -> None:
    account = await services.accounts.create(draft(vm_number=2, company_name="Old", bank_name="N26", currency="EUR", balance_raw="10"))
    archived = await services.accounts.archive(account.id)
    assert archived.is_archived
    assert await services.accounts.list_active() == []
    assert len(await services.accounts.list_archived()) == 1
    restored = await services.accounts.unarchive(account.id)
    assert not restored.is_archived
    assert len(await services.accounts.list_active()) == 1


async def test_currency_change_needs_confirm_when_balance_exists(services: Services) -> None:
    from app.services.accounts import CurrencyChangeNeedsConfirm

    account = await services.accounts.create(draft(vm_number=5, company_name="Co", currency="USD", balance_raw="10"))
    with pytest.raises(CurrencyChangeNeedsConfirm):
        await services.accounts.change_currency(account.id, "EUR")
    confirmed = await services.accounts.change_currency(account.id, "EUR", confirmed=True)
    assert confirmed.currency == "EUR"
    assert confirmed.balance_minor == 1000


async def test_currency_change_zero_balance_no_confirm(services: Services) -> None:
    account = await services.accounts.create(draft(vm_number=6, company_name="Co", currency="USD", balance_raw="0"))
    updated = await services.accounts.change_currency(account.id, "EUR")
    assert updated.currency == "EUR"
    assert updated.balance_minor == 0


async def test_delete_unknown(services: Services) -> None:
    with pytest.raises(AccountError):
        await services.accounts.get(999)
    with pytest.raises(AccountError):
        await services.accounts.delete(999)


async def test_delete_removes_account(services: Services) -> None:
    account = await services.accounts.create(draft(vm_number=3, company_name="Temp"))
    await services.accounts.delete(account.id)
    with pytest.raises(AccountError):
        await services.accounts.get(account.id)
