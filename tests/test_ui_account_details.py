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

    # Three financial groups separated by exactly one blank line.
    money = text[text.index("🟢 In:") : text.index("\n\nVM:")]
    groups = money.split("\n\n")
    assert len(groups) == 3
    assert groups[0].startswith("🟢 In:")
    assert "🔴 Out:" in groups[0]
    assert groups[1].startswith("⏳ Expected:")
    assert groups[2].startswith("💰 Current Balance:")
    assert "📊 Projected Balance:" in groups[2]

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


def test_accounts_overview_compact_no_in_out_labels() -> None:
    from app.utils.account_context import account_identity_line, totals_block
    from app.utils.formatting import accounts_page_summary
    from app.services.totals import AccountTotals

    class Acc:
        line_label = "Graphics Press"
        banking_provider = "Airwallex"
        currency = "USD"
        balance_minor = 454_020

    totals = AccountTotals(
        account=Acc(),  # type: ignore[arg-type]
        in_minor=20_000,
        out_minor=100_000,
        expected_minor=45_000,
        current_minor=454_020,
        projected_minor=409_020,
    )
    block = f"{account_identity_line(Acc())}\n{totals_block(totals, compact=True)}"  # type: ignore[arg-type]
    assert block == (
        "🏦 <b>GRAPHICS PRESS · AIRWALLEX</b>\n"
        "⏳ $450.00\n"
        "💰 $4,540.20\n"
        "📊 $4,090.20"
    )
    assert "In" not in block
    assert "Out" not in block
    assert "Expected" not in block
    assert "Current" not in block
    assert "Projected" not in block

    second = AccountTotals(
        account=Acc(),  # type: ignore[arg-type]
        in_minor=0,
        out_minor=0,
        expected_minor=370_000,
        current_minor=1_245_075,
        projected_minor=875_075,
    )

    class Acc2:
        line_label = "LeBon Shoppe"
        banking_provider = "Airwallex"
        currency = "USD"

    page = accounts_page_summary(
        [
            block,
            f"{account_identity_line(Acc2())}\n{totals_block(second, compact=True)}",  # type: ignore[arg-type]
        ]
    )
    assert "\n\n🏦 <b>LEBON SHOPPE" in page
    assert "Select an account" not in page


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
