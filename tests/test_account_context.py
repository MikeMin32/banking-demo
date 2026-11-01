from __future__ import annotations

from app.utils.account_context import account_body, account_context_header, with_account_header
from app.services.container import Services
from tests.conftest import draft


def test_header_compact_mobile_layout() -> None:
    class Fake:
        line_label = "Line 1"
        banking_provider = "Airwallex"
        currency = "USD"

    text = with_account_header(
        Fake(), 80000, "Enter top-up amount (USD):", pending_minor=20000  # type: ignore[arg-type]
    )
    assert "Active Balance" in text
    assert "$800.00" in text
    assert "Active Charges" in text
    assert "$200.00" in text
    assert "─" not in text
    assert "Enter top-up amount" in text
    assert account_context_header(Fake(), 80000, 20000).count("\n") == 2  # type: ignore[arg-type]


async def test_nested_screens_share_live_header(services: Services) -> None:
    account = await services.accounts.create(
        draft(line_name="Ops Line", bank_name="Airwallex", currency="USD", balance_raw="2000")
    )
    await services.withdrawals.create(account.id, "500")
    await services.topups.create(account.id, "100")

    screens = [
        "Enter charge amount (USD):",
        "Enter top-up amount (USD):",
        "Mobile: —",
        "Change a field, or use the actions below.",
        "No balance updates yet.",
    ]
    for body in screens:
        _, text = await account_body(services, account.id, body)
        assert "OPS LINE · AIRWALLEX" in text
        assert "$1,600.00" in text
        assert "Active Charges" in text
        assert "$500.00" in text
        assert body.splitlines()[0] in text
