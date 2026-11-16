"""Rich Message + HTML Widget Account Details prototypes."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import aiogram
import pytest
from aiogram.types import InputRichBlockDetails, InputRichBlockSectionHeading, InputRichBlockTable

from app.handlers.ui_preview import can_access_ui_preview
from app.utils.ui_preview import (
    AccountDetailsSnapshot,
    assert_no_secrets,
    build_fallback_notice,
    build_rich_account_details,
    build_widget_account_details,
    preview_actions_kb,
    preview_menu_kb,
    sample_account_details,
    snapshot_from_totals,
    widget_size_ok,
)
from app.services.totals import AccountTotals
from tests.conftest import draft


def test_aiogram_supports_rich_and_widget() -> None:
    assert tuple(int(p) for p in aiogram.__version__.split(".")[:2]) >= (3, 32)
    from aiogram import Bot

    assert hasattr(Bot, "send_rich_message")
    assert hasattr(Bot, "send_widget")


def test_sample_snapshot_matches_brief() -> None:
    snap = sample_account_details()
    assert snap.line_name == "Automation Direct"
    assert snap.provider == "Airwallex"
    assert snap.currency == "USD"
    assert snap.money(snap.current_minor) == "$5,000.00"
    assert snap.money(snap.projected_minor) == "$3,000.00"
    assert snap.money(snap.expected_minor) == "$2,000.00"
    assert snap.money(snap.in_minor) == "$0.00"
    assert snap.money(snap.out_minor) == "$0.00"
    assert snap.vm == "VM 4"
    assert snap.updated_label == "16 Nov 2026"


def test_rich_message_uses_structured_blocks() -> None:
    snap = sample_account_details()
    rich = build_rich_account_details(snap)
    types = [getattr(b, "type", None) for b in rich.blocks or []]
    type_values = [t.value if hasattr(t, "value") else t for t in types]
    assert "heading" in type_values
    assert "table" in type_values
    assert "divider" in type_values
    assert "details" in type_values

    tables = [b for b in rich.blocks or [] if isinstance(b, InputRichBlockTable)]
    assert tables
    assert all(t.is_striped for t in tables)
    headings = [b for b in rich.blocks or [] if isinstance(b, InputRichBlockSectionHeading)]
    assert any(h.size == 1 and "$5,000.00" in str(h.text) for h in headings)
    details = [b for b in rich.blocks or [] if isinstance(b, InputRichBlockDetails)]
    assert details and details[0].is_open is False

    payload = rich.model_dump_json(exclude_none=True)
    assert "OPERATION GREENLINE" in payload
    assert "Automation Direct" in payload
    assert_no_secrets(payload)
    assert "password" not in payload.lower()


def test_widget_html_structure_and_size() -> None:
    snap = sample_account_details()
    html = build_widget_account_details(snap)
    assert "<!DOCTYPE html>" in html
    assert "--tg-theme-bg-color" in html
    assert "--tg-theme-accent-text-color" in html
    assert "Current Balance" in html
    assert "$5,000.00" in html
    assert "Projected" in html
    assert "Expected" in html
    assert "Account Information" in html
    assert "OPERATION GREENLINE" in html
    assert 'data-tab="overview"' in html
    assert "<details" in html
    assert "<script" in html.lower()  # in-widget tab switcher only
    assert "http://" not in html
    assert "https://" not in html
    assert_no_secrets(html)
    ok, raw, compressed = widget_size_ok(html)
    assert ok, f"widget too large raw={raw} compressed={compressed}"
    assert compressed <= 4096
    assert raw <= 32768


def test_long_line_name_and_negative_balance() -> None:
    snap = AccountDetailsSnapshot(
        account_id=None,
        line_name="Very Long Automation Direct Partnership Line Name That Should Stay Readable",
        provider="Airwallex",
        currency="USD",
        current_minor=-125_050,
        projected_minor=-325_050,
        expected_minor=200_000,
        in_minor=10_000,
        out_minor=50_000,
        vm="VM 12",
        stored="Vault A",
        iban="—",
        bin="—",
        updated_label="16 Nov 2026",
    )
    assert snap.money(snap.current_minor) == "$-1,250.50"
    rich = build_rich_account_details(snap)
    payload = rich.model_dump_json(exclude_none=True)
    assert "Very Long Automation Direct" in payload
    assert "$-1,250.50" in payload
    html = build_widget_account_details(snap)
    assert "Very Long Automation Direct" in html
    assert "$-1,250.50" in html
    ok, _, compressed = widget_size_ok(html)
    assert ok and compressed <= 4096


def test_preview_keyboards() -> None:
    menu = preview_menu_kb()
    labels = [btn.text for row in menu.inline_keyboard for btn in row]
    assert "A · Rich Message" in labels
    assert "B · HTML Widget" in labels

    stub = preview_actions_kb(None)
    stub_labels = [[btn.text for btn in row] for row in stub.inline_keyboard]
    assert stub_labels[0] == ["💰 Update Balance", "📋 Transactions"]
    assert stub_labels[1] == ["➕ Add Charge", "💵 Deposit"]
    assert stub_labels[2] == ["🔐 Login Details", "✏️ Edit Account"]
    assert stub_labels[3][0] == "⬅️ Back"
    assert stub_labels[3][1] == "🏠 Home"
    assert all(btn.callback_data.startswith("uip:") or btn.callback_data.startswith("m:") for row in stub.inline_keyboard for btn in row)


async def test_preview_actions_reuse_real_callbacks(services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Automation Direct",
            bank_name="Airwallex",
            currency="USD",
            balance_raw="5000",
            linked_vm="VM 4",
        )
    )
    markup = preview_actions_kb(account)
    flat = [btn for row in markup.inline_keyboard for btn in row]
    assert flat[0].style == "primary"
    assert flat[0].callback_data.startswith("a:")
    assert any(btn.style == "success" for btn in flat)
    assert any(btn.style == "danger" for btn in flat)


async def test_snapshot_from_live_account(services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Automation Direct",
            bank_name="Airwallex",
            currency="EUR",
            balance_raw="100.00",
            linked_vm="VM 4",
            iban="",
            bin="",
        )
    )
    totals = await services.totals.for_account(account.id)
    snap = snapshot_from_totals(totals, ZoneInfo("Europe/Kyiv"))
    assert snap.account_id == account.id
    assert snap.currency == "EUR"
    assert "€" in snap.money(snap.current_minor) or snap.money(snap.current_minor).endswith("EUR") or "100.00" in snap.money(snap.current_minor)
    html = build_widget_account_details(snap)
    assert_no_secrets(html)
    assert "password" not in html.lower()


def test_can_access_ui_preview_matches_bot_auth(services) -> None:
    assert can_access_ui_preview(services, 1001)
    assert can_access_ui_preview(services, 1002)
    assert not can_access_ui_preview(services, 9999)
    assert not can_access_ui_preview(services, None)

    services.settings.dev_allow_any_user = True
    assert can_access_ui_preview(services, 4242)


def test_fallback_notice_is_honest() -> None:
    text = build_fallback_notice("Rich Message", "TelegramBadRequest: unsupported")
    assert "Could not render" in text
    assert "Rich Message" in text
    assert "unchanged" in text


def test_assert_no_secrets_blocks_password() -> None:
    with pytest.raises(AssertionError):
        assert_no_secrets("login password value")
