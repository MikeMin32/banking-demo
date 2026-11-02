"""Client balance-tracking example and edge cases."""

from __future__ import annotations

from app.services.container import Services
from tests.conftest import draft


async def test_client_example_flow(services: Services) -> None:
    """Deposit 1000 → Expected 150 → Actual 140 → Deposit 500."""
    account = await services.accounts.create(
        draft(line_name="Line 1", bank_name="Airwallex", currency="USD", balance_raw="0")
    )

    await services.topups.create(account.id, "1000")
    t1 = await services.totals.for_account(account.id)
    assert t1.current_minor == 100_000
    assert t1.projected_minor == 100_000
    assert t1.in_minor == 100_000
    assert t1.out_minor == 0
    assert t1.expected_minor == 0

    expected = await services.withdrawals.create(account.id, "150")
    t2 = await services.totals.for_account(account.id)
    assert t2.current_minor == 100_000
    assert t2.projected_minor == 85_000
    assert t2.expected_minor == 15_000

    result = await services.withdrawals.confirm_actual(expected.id, raw_actual="140", deduct=True)
    assert result.deducted
    assert result.withdrawal.amount_minor == 15_000
    assert result.withdrawal.actual_amount_minor == 14_000
    assert result.withdrawal.applied_to_balance
    t3 = await services.totals.for_account(account.id)
    assert t3.current_minor == 86_000
    assert t3.projected_minor == 86_000
    assert t3.expected_minor == 0
    assert t3.out_minor == 14_000

    # Duplicate completion must not deduct again.
    again = await services.withdrawals.confirm_actual(expected.id, raw_actual="140", deduct=True)
    assert again.deducted is False
    assert (await services.accounts.get(account.id)).balance_minor == 86_000
    assert (await services.totals.for_account(account.id)).out_minor == 14_000

    await services.topups.create(account.id, "500")
    t4 = await services.totals.for_account(account.id)
    assert t4.current_minor == 136_000
    assert t4.projected_minor == 136_000
    assert t4.in_minor == 150_000
    assert t4.out_minor == 14_000


async def test_multiple_pending_and_cancel(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    a = await services.withdrawals.create(account.id, "100")
    b = await services.withdrawals.create(account.id, "50")
    totals = await services.totals.for_account(account.id)
    assert totals.expected_minor == 15_000
    assert totals.projected_minor == 85_000
    await services.withdrawals.cancel(b.id)
    totals = await services.totals.for_account(account.id)
    assert totals.expected_minor == 10_000
    assert totals.projected_minor == 90_000
    await services.withdrawals.confirm_actual(a.id, deduct=True)
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 90_000
    assert totals.out_minor == 10_000
    assert totals.expected_minor == 0


async def test_standalone_actual_charge(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="500"))
    result = await services.withdrawals.create_actual(account.id, "75", deduct=True)
    assert result.deducted
    assert result.withdrawal.status == "completed"
    assert result.withdrawal.applied_to_balance
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 42_500
    assert totals.out_minor == 7_500
    assert totals.expected_minor == 0


async def test_already_reflected_in_manual_balance(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    charge = await services.withdrawals.create(account.id, "200")
    await services.balances.update_balance(account.id, "800")
    result = await services.withdrawals.confirm_actual(
        charge.id, raw_actual="200", deduct=False
    )
    assert result.deducted is False
    assert result.withdrawal.applied_to_balance
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 80_000
    assert totals.projected_minor == 80_000
    assert totals.out_minor == 20_000
    assert totals.expected_minor == 0


async def test_legacy_completed_not_in_out_totals(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.db.execute(
        """
        INSERT INTO expected_withdrawals (
            account_id, amount_minor, status, created_at, updated_at, completed_at, applied_to_balance
        ) VALUES (?, 20000, 'completed', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00',
                  '2026-01-01T00:00:00+00:00', 0)
        """,
        (account.id,),
    )
    totals = await services.totals.for_account(account.id)
    assert totals.out_minor == 0
    assert totals.current_minor == 100_000


async def test_multi_currency_totals_stay_separate(services: Services) -> None:
    usd = await services.accounts.create(draft(line_name="USD", currency="USD", balance_raw="0"))
    eur = await services.accounts.create(draft(line_name="EUR", currency="EUR", balance_raw="0"))
    await services.topups.create(usd.id, "100")
    await services.topups.create(eur.id, "50")
    await services.withdrawals.create_actual(usd.id, "10", deduct=True)
    usd_t = await services.totals.for_account(usd.id)
    eur_t = await services.totals.for_account(eur.id)
    assert usd_t.in_minor == 10_000
    assert usd_t.out_minor == 1_000
    assert usd_t.current_minor == 9_000
    assert eur_t.in_minor == 5_000
    assert eur_t.out_minor == 0
    assert eur_t.current_minor == 5_000


async def test_opening_balance_not_counted_as_in(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="2500"))
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 250_000
    assert totals.in_minor == 0
    assert totals.out_minor == 0
