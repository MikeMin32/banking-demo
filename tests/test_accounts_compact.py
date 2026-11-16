"""Accounts overview compactness polish."""

from __future__ import annotations

from app.ui.rich_screens import accounts_overview_rich
from tests.conftest import draft


async def test_accounts_overview_is_two_lines_per_account(services) -> None:
    a = await services.accounts.create(
        draft(company_name="Automation Direct", bank_name="Airwallex", balance_raw="5000", linked_vm="VM 4")
    )
    b = await services.accounts.create(
        draft(
            company_name="Very Long Automation Partnership Name That Should Wrap",
            bank_name="Airwallex",
            balance_raw="100",
            vm_number=2,
        )
    )
    totals = await services.totals.for_accounts([a, b])
    rich = accounts_overview_rich([a, b], totals, archived=False)
    payload = rich.model_dump_json(exclude_none=True)
    assert "🏦 Bank accounts" in payload or "Bank accounts" in payload
    assert "Automation Direct · Airwallex" in payload
    assert "⏳" in payload and "💰" in payload and "📊" in payload
    # No tall per-account tables / In-Out on overview.
    assert '"type":"table"' not in payload
    assert "🟢 In" not in payload
    assert "🔴 Out" not in payload
    # Long names remain present.
    assert "Very Long Automation Partnership" in payload
