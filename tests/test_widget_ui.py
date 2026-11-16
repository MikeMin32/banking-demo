"""Widget design-system screens and navigation helpers."""

from __future__ import annotations

import pytest

from app.ui.render import present_widget, widget_size_ok
from app.ui.screens import (
    account_details_from_totals,
    accounts_overview_html,
    balance_summary_html,
    login_html,
    settings_html,
    transactions_html,
)
from app.utils.ui_preview import assert_no_secrets
from tests.conftest import draft


async def test_account_details_and_accounts_widgets(services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Automation Direct",
            bank_name="Airwallex",
            currency="USD",
            balance_raw="5000",
            linked_vm="VM 4",
        )
    )
    totals = await services.totals.for_account(account.id)
    details = account_details_from_totals(totals, services.tz)
    assert "Current Balance" in details
    assert "$5,000.00" in details
    assert "OPERATION GREENLINE" in details
    assert_no_secrets(details)
    ok, _, compressed = widget_size_ok(details)
    assert ok and compressed <= 4096

    overview = accounts_overview_html([account], {account.id: totals}, archived=False)
    assert "Automation Direct" in overview
    assert "Expected" in overview
    assert "In:" not in overview and ">In<" not in overview
    # Overview must not show In/Out labels from details activity.
    assert "Activity" not in overview
    ok, _, compressed = widget_size_ok(overview)
    assert ok and compressed <= 4096


async def test_transactions_widget_ledger(services) -> None:
    account = await services.accounts.create(
        draft(company_name="Ledger Co", bank_name="Airwallex", currency="USD", balance_raw="100")
    )
    await services.topups.create(account.id, "25.00")
    page = await services.ledger.page(account.id, page=0, tz=services.tz)
    html = transactions_html(page, services.tz)
    assert "Ledger" in html or "🟢" in html
    assert "Page 1 /" in html
    assert_no_secrets(html)
    ok, _, compressed = widget_size_ok(html)
    assert ok and compressed <= 4096


async def test_negative_and_long_name_in_details(services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Very Long Automation Partnership Name That Should Wrap",
            bank_name="Airwallex",
            currency="USD",
            balance_raw="-12.50",
            linked_vm="VM 99",
        )
    )
    totals = await services.totals.for_account(account.id)
    html = account_details_from_totals(totals, services.tz)
    assert "Very Long Automation" in html
    assert "$-12.50" in html
    ok, _, _ = widget_size_ok(html)
    assert ok


async def test_settings_and_login_widgets(services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Secure Co",
            login_password="super-secret-value",
            login_email="a@b.c",
        )
    )
    html = login_html(account, can_reveal=True)
    assert "••••••••" in html
    assert "super-secret-value" not in html
    assert "Password" in html  # label only
    settings = settings_html(reminders_enabled=True, reminder_time="09:00")
    assert "Enabled" in settings
    assert "09:00" in settings
    ok, _, c = widget_size_ok(settings)
    assert ok and c <= 4096


async def test_balance_summary_widget(services) -> None:
    await services.accounts.create(draft(company_name="A", currency="USD", balance_raw="10"))
    await services.accounts.create(draft(company_name="B", currency="EUR", balance_raw="20", vm_number=2))
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    html = balance_summary_html(snap)
    assert "Balance Summary" in html
    assert "USD" in html or "$" in html
    ok, _, c = widget_size_ok(html)
    assert ok and c <= 4096


@pytest.mark.asyncio
async def test_present_widget_falls_back_honestly(monkeypatch) -> None:
    class FakeBot:
        async def send_widget(self, **kwargs):
            raise Exception("boom")

    class FakeMessage:
        bot = FakeBot()
        chat = type("C", (), {"id": 1})()

        async def edit_text(self, text, reply_markup=None):
            self.last = text
            return self

        async def answer(self, text, reply_markup=None):
            self.last = text
            return self

        async def delete(self):
            return None

    msg = FakeMessage()
    # Force fallback path via size failure
    huge = "x" * 50_000
    result = await present_widget(msg, huge, None, text_fallback="<b>Account</b>")  # type: ignore[arg-type]
    assert result is msg
    assert "Widget unavailable" in msg.last
