from __future__ import annotations

from tests.conftest import draft
from app.services.container import Services
from app.services.dashboard import format_currency_lines


async def test_currencies_are_never_combined(services: Services) -> None:
    usd = await services.accounts.create(
        draft(display_name="USD Acc", bank_name="Chase", currency="USD", balance_raw="100")
    )
    await services.accounts.create(
        draft(display_name="EUR Acc", bank_name="Wise", currency="EUR", balance_raw="40")
    )
    await services.withdrawals.create(usd.id, "10")
    snap = await services.dashboard.snapshot(stale_hours=24)
    assert snap.active_count == 2
    assert snap.pending_withdrawal_count == 1
    assert set(snap.by_currency) == {"EUR", "USD"}
    assert snap.by_currency["USD"].balance_minor == 10000
    assert snap.by_currency["EUR"].balance_minor == 4000
    assert snap.by_currency["USD"].pending_minor == 1000
    assert snap.by_currency["USD"].projected_minor == 9000
    assert snap.by_currency["EUR"].projected_minor == 4000
    # No combined grand total exists on the snapshot.
    assert not hasattr(snap, "grand_total")
    lines = format_currency_lines(snap.by_currency, "balance_minor")
    assert "USD" in lines and "EUR" in lines


async def test_archived_excluded_from_active_totals(services: Services) -> None:
    keep = await services.accounts.create(
        draft(display_name="Keep", bank_name="Bank", currency="USD", balance_raw="50")
    )
    gone = await services.accounts.create(
        draft(display_name="Gone", bank_name="Bank", currency="USD", balance_raw="50")
    )
    await services.accounts.archive(gone.id)
    snap = await services.dashboard.snapshot(stale_hours=24)
    assert snap.active_count == 1
    assert snap.archived_count == 1
    assert snap.by_currency["USD"].balance_minor == 5000
    assert keep.id in {account.id for account in snap.accounts}
    assert gone.id not in {account.id for account in snap.accounts}
