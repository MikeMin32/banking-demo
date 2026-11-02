"""Account Details caption formatting and keyboard layout."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from app.keyboards.accounts import account_view_kb
from app.keyboards.callbacks import AccCB, MenuCB, TuCB, WdCB
from app.utils.formatting import account_card
from tests.conftest import draft


async def test_account_card_one_field_per_line(services) -> None:
    account = await services.accounts.create(
        draft(
            vm_number=9,
            company_name="LeBon Shoppe",
            bank_name="Airwallex",
            currency="USD",
            balance_raw="8750.75",
            iban="",
            bin="",
            stored_where="",
        )
    )
    totals = await services.totals.for_account(account.id)
    # Simulate pending charges for projected balance in the card.
    totals.expected_minor = 120_000
    totals.projected_minor = totals.current_minor - 120_000
    text = account_card(
        account, ZoneInfo("Europe/Kyiv"), pending_minor=120_000, totals=totals
    )

    assert "Current Balance" in text
    assert "Projected Balance" in text
    assert "In:" in text
    assert "Out:" in text
    assert "Expected:" in text
    assert "Account Details" not in text

    # Lower section: one field per line, preserved order.
    assert "VM:" in text
    assert "Stored:" in text
    assert "IBAN:" in text
    assert "BIN:" in text
    assert "Updated:" in text
    lower = text[text.index("VM:") :]
    lines = lower.splitlines()
    assert lines[0].startswith("VM:")
    assert lines[1].startswith("Stored:")
    assert lines[2].startswith("IBAN:")
    assert lines[3].startswith("BIN:")
    assert lines[4].startswith("Updated:")
    assert " · " not in lower


async def test_account_view_kb_four_by_two() -> None:
    class _Acc:
        id = 7
        is_archived = False

    markup = account_view_kb(_Acc(), from_page=2)
    rows = markup.inline_keyboard
    assert len(rows) == 4
    assert [len(row) for row in rows] == [2, 2, 2, 2]

    labels = [[btn.text for btn in row] for row in rows]
    assert labels == [
        ["💵 Balance", "📋 Transactions"],
        ["➕ Add Charge", "💰 Deposit"],
        ["🔐 Login Details", "✏️ Edit Account"],
        ["⬅️ Back", "🏠 Home"],
    ]

    assert rows[0][0].callback_data == AccCB(o="bal", i=7).pack()
    assert rows[0][1].callback_data == AccCB(o="txn", i=7).pack()
    assert rows[1][0].callback_data == WdCB(o="add", a=7).pack()
    assert rows[1][1].callback_data == TuCB(o="add", a=7).pack()
    assert rows[2][0].callback_data == AccCB(o="log", i=7).pack()
    assert rows[2][1].callback_data == AccCB(o="edt", i=7).pack()
    assert rows[3][0].callback_data == AccCB(o="list", p=2).pack()
    assert rows[3][1].callback_data == MenuCB(a="menu").pack()
