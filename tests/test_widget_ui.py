"""Widget design-system: tabs, accordions, banners, size limits."""

from __future__ import annotations

import re

import pytest

from app.ui.render import banner_exists, present_widget, widget_size_ok
from app.ui.screens import (
    account_details_from_totals,
    account_details_html,
    accounts_overview_html,
    balance_summary_html,
    login_html,
    settings_html,
    transactions_html,
)
from app.utils.ui_preview import assert_no_secrets, sample_account_details
from tests.conftest import draft


def test_account_details_has_real_tabs_and_accordion() -> None:
    html = account_details_html(sample_account_details())
    assert 'data-tab="overview"' in html
    assert 'data-tab="activity"' in html
    assert 'data-tab="details"' in html
    assert 'data-panel="overview"' in html
    assert 'data-panel="activity"' in html
    assert 'data-panel="details"' in html
    assert "<script" in html
    assert "<details" in html and "<summary" in html
    assert "Account Information" in html
    # Only overview panel visible by default
    assert re.search(r'data-panel="overview"(?! hidden)', html)
    assert 'data-panel="activity" hidden' in html
    assert 'data-panel="details" hidden' in html
    # Details accordion closed by default (no open attribute)
    assert re.search(r"<details class=\"accbox\">\s*<summary>Account Information", html)
    assert "Current Balance" in html
    assert "$5,000.00" in html
    assert "Projected" in html and "Expected" in html
    assert "class=\"rows\"" in html or 'class="rows"' in html
    ok, _, compressed = widget_size_ok(html)
    assert ok and compressed <= 4096
    assert_no_secrets(html)


def test_tab_script_is_presentation_only() -> None:
    html = account_details_html(sample_account_details())
    assert "TelegramWidget.request" not in html
    assert "allow_queries" not in html
    assert "addEventListener('click'" in html or 'addEventListener("click"' in html


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
    assert "data-tab=" in details
    overview = accounts_overview_html([account], {account.id: totals}, archived=False)
    assert "Automation Direct" in overview
    assert "Expected" in overview
    assert "Activity" not in overview
    assert banner_exists("account-details")
    assert banner_exists("accounts")


async def test_transactions_widget_ledger(services) -> None:
    account = await services.accounts.create(
        draft(company_name="Ledger Co", bank_name="Airwallex", currency="USD", balance_raw="100")
    )
    await services.topups.create(account.id, "25.00")
    page = await services.ledger.page(account.id, page=0, tz=services.tz)
    html = transactions_html(page, services.tz)
    assert "data-tab=\"ledger\"" in html or "data-tab='ledger'" in html
    assert "Page 1 /" in html
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
    assert 'data-tab="overview"' in html


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
    assert "<details" in html
    settings = settings_html(reminders_enabled=True, reminder_time="09:00")
    assert "data-tab=" in settings
    assert "Enabled" in settings
    ok, _, c = widget_size_ok(settings)
    assert ok and c <= 4096


async def test_balance_summary_widget(services) -> None:
    await services.accounts.create(draft(company_name="A", currency="USD", balance_raw="10"))
    await services.accounts.create(draft(company_name="B", currency="EUR", balance_raw="20", vm_number=2))
    reminder = await services.reminders.get_settings()
    snap = await services.dashboard.snapshot(stale_hours=reminder.stale_hours)
    html = balance_summary_html(snap)
    assert "data-tab=" in html
    ok, _, c = widget_size_ok(html)
    assert ok and c <= 4096


@pytest.mark.asyncio
async def test_present_widget_falls_back_honestly() -> None:
    class FakeBot:
        async def send_widget(self, **kwargs):
            raise Exception("boom")

        async def send_photo(self, **kwargs):
            raise Exception("no photo")

        async def delete_message(self, *a, **k):
            return None

    class FakeMessage:
        bot = FakeBot()
        chat = type("C", (), {"id": 1})()

        async def edit_text(self, text, reply_markup=None):
            self.last = text
            return self

        async def answer(self, text, reply_markup=None):
            self.last = text
            return self

        async def answer_photo(self, *a, **k):
            raise Exception("no")

        async def delete(self):
            return None

    msg = FakeMessage()
    huge = "x" * 50_000
    result = await present_widget(msg, huge, None, text_fallback="<b>Account</b>", screen="dashboard")  # type: ignore[arg-type]
    assert result is msg
    assert "Native rich UI unavailable" in msg.last
