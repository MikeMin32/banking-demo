"""Add Charge Expected/Actual selector and Transactions ledger."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from app.keyboards.withdrawals import charge_type_kb
from app.services.container import Services
from app.services.ledger import LEDGER_PAGE_SIZE, format_ledger_message
from tests.conftest import draft


def test_charge_type_defaults_to_expected() -> None:
    markup = charge_type_kb(3, "expected")
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert labels[0] == "✅ Expected"
    assert labels[1] == "◯ Actual"


def test_charge_type_switch_to_actual_and_back() -> None:
    actual = charge_type_kb(3, "actual")
    labels = [btn.text for row in actual.inline_keyboard for btn in row]
    assert labels[0] == "◯ Expected"
    assert labels[1] == "✅ Actual"
    expected = charge_type_kb(3, "expected")
    labels = [btn.text for row in expected.inline_keyboard for btn in row]
    assert labels[0] == "✅ Expected"
    assert labels[1] == "◯ Actual"


async def test_expected_only_affects_projected(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.withdrawals.create(account.id, "150")
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 100_000
    assert totals.projected_minor == 85_000
    assert totals.expected_minor == 15_000
    assert totals.out_minor == 0


async def test_actual_affects_current_and_out(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.withdrawals.create_actual(account.id, "140", deduct=True)
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 86_000
    assert totals.out_minor == 14_000
    assert totals.expected_minor == 0


async def test_settle_expected_does_not_double_deduct(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    expected = await services.withdrawals.create(account.id, "150")
    await services.withdrawals.confirm_actual(expected.id, raw_actual="140", deduct=True)
    again = await services.withdrawals.confirm_actual(expected.id, raw_actual="140", deduct=True)
    assert again.deducted is False
    totals = await services.totals.for_account(account.id)
    assert totals.current_minor == 86_000
    assert totals.out_minor == 14_000
    assert totals.expected_minor == 0


async def test_ledger_shows_event_types_and_strikethrough(services: Services) -> None:
    account = await services.accounts.create(draft(line_name="Graphics Press", balance_raw="0"))
    await services.topups.create(account.id, "1000")
    expected = await services.withdrawals.create(account.id, "150")
    await services.withdrawals.confirm_actual(expected.id, raw_actual="140", deduct=True)
    await services.topups.create(account.id, "500")
    await services.balances.update_balance(account.id, "1360")

    page = await services.ledger.page(account.id, page=0, page_size=20, tz=services.tz)
    kinds = {e.kind for e in page.events}
    assert {"deposit", "expected", "charge", "manual"} <= kinds
    struck = [e for e in page.events if e.kind == "expected"]
    assert struck and all(e.struck for e in struck)

    text = format_ledger_message(page, ZoneInfo("Europe/Kyiv"))
    assert "GRAPHICS PRESS · AIRWALLEX" in text
    assert "🟢 In:" in text
    assert "🔴 Out:" in text
    assert "⏳ Expected:" in text
    assert "<s>-$" in text or "<s>-" in text
    assert "💰 $" in text and "→" in text
    assert "Page 1 /" in text
    # Times at start of event rows
    for line in text.splitlines():
        if line[:2].isdigit() and ":" in line[:5]:
            assert line[2] == ":"


async def test_manual_balance_does_not_change_in_out(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.topups.create(account.id, "100")
    before = await services.totals.for_account(account.id)
    await services.balances.update_balance(account.id, "2000")
    after = await services.totals.for_account(account.id)
    assert after.in_minor == before.in_minor
    assert after.out_minor == before.out_minor
    assert after.current_minor == 200_000


async def test_ledger_newest_first_and_pagination(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="0"))
    for i in range(10):
        await services.topups.create(account.id, "10")
    page0 = await services.ledger.page(account.id, page=0, page_size=LEDGER_PAGE_SIZE, tz=services.tz)
    page1 = await services.ledger.page(account.id, page=1, page_size=LEDGER_PAGE_SIZE, tz=services.tz)
    assert page0.account.id == account.id
    assert page1.account.id == account.id
    assert len(page0.events) == LEDGER_PAGE_SIZE
    assert page0.total_pages >= 2
    assert page0.events[0].at >= page0.events[-1].at
