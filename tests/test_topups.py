from __future__ import annotations

import pytest

from app.services.container import Services
from app.services.topups import TopUpError
from app.utils.account_context import account_context_header, with_account_header
from tests.conftest import draft


async def test_topup_increases_recorded_and_available(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.withdrawals.create(account.id, "200")
    before = await services.withdrawals.projection(account.id)
    assert before.recorded_minor == 100000
    assert before.pending_minor == 20000
    assert before.available_minor == 80000

    result = await services.topups.create(account.id, "500")
    assert result.top_up.amount_minor == 50000
    assert result.top_up.applied_to_balance
    assert result.old_balance_minor == 100000
    assert result.new_balance_minor == 150000

    after = await services.withdrawals.projection(account.id)
    assert after.recorded_minor == 150000
    assert after.pending_minor == 20000
    assert after.available_minor == 130000


async def test_multiple_topups(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="100", currency="EUR"))
    await services.topups.create(account.id, "10")
    await services.topups.create(account.id, "25.50")
    reloaded = await services.accounts.get(account.id)
    assert reloaded.balance_minor == 13550
    _, items, total = await services.topups.page(account.id, page=0, page_size=10)
    assert total == 2
    assert items[0].amount_minor == 2550
    assert items[1].amount_minor == 1000
    assert items[0].currency == "EUR"


async def test_topup_apply_is_idempotent(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    result = await services.topups.create(account.id, "100")
    again = await services.topups._apply(result.top_up)
    assert (await services.accounts.get(account.id)).balance_minor == 110000
    assert again.new_balance_minor == 110000
    assert again.top_up.applied_to_balance


async def test_topup_writes_balance_history(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="50"))
    await services.topups.create(account.id, "20")
    _, entries, total = await services.balances.history_page(account.id, page=0, page_size=10)
    assert total == 1
    assert entries[0].old_balance_minor == 5000
    assert entries[0].new_balance_minor == 7000


async def test_topup_rejects_zero_and_negative(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="10"))
    with pytest.raises(TopUpError):
        await services.topups.create(account.id, "0")
    with pytest.raises(TopUpError):
        await services.topups.create(account.id, "-5")


async def test_explicit_reverse_once(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    result = await services.topups.create(account.id, "200")
    reversed_once = await services.topups.reverse(result.top_up.id)
    assert reversed_once.top_up.is_reversed
    assert (await services.accounts.get(account.id)).balance_minor == 100000
    reversed_again = await services.topups.reverse(result.top_up.id)
    assert (await services.accounts.get(account.id)).balance_minor == 100000
    assert reversed_again.new_balance_minor == 100000


async def test_charge_accounting_still_works_after_topup(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.topups.create(account.id, "500")
    charge = await services.withdrawals.create(account.id, "300")
    projection = await services.withdrawals.projection(account.id)
    assert projection.available_minor == 120000
    await services.withdrawals.complete(charge.id)
    final = await services.withdrawals.projection(account.id)
    assert final.recorded_minor == 120000
    assert final.available_minor == 120000


def test_account_context_header_format() -> None:
    class Fake:
        line_label = "Line 1"
        banking_provider = "Airwallex"
        currency = "USD"

    header = account_context_header(Fake(), 125000, 150000)  # type: ignore[arg-type]
    assert "LINE 1 · AIRWALLEX" in header
    assert "Active Balance" in header
    assert "$1,250.00" in header
    assert "Active Charges" in header
    assert "$1,500.00" in header
    assert "─" not in header
    wrapped = with_account_header(Fake(), 125000, "Enter charge amount (USD):", pending_minor=0)  # type: ignore[arg-type]
    assert wrapped.startswith("🏦")
    assert "Enter charge amount" in wrapped


async def test_header_uses_live_available(services: Services) -> None:
    account = await services.accounts.create(draft(line_name="Line 9", bank_name="N26", balance_raw="1000", currency="EUR"))
    await services.withdrawals.create(account.id, "250")
    from app.utils.account_context import account_body

    _, text = await account_body(services, account.id, "Mobile: —")
    assert "LINE 9 · N26" in text
    assert "Active Balance" in text
    assert "€750.00" in text
    assert "Active Charges" in text
    assert "€250.00" in text
