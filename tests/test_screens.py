from __future__ import annotations

from app.keyboards.accounts import account_button_label
from app.keyboards.callbacks import AccCB, MenuCB, SetCB, WdCB
from app.keyboards.common import main_menu_kb
from app.ui.render import banner_exists, banner_path, widget_size_ok
from app.ui.screens import account_details_html, dashboard_html, prompt_html
from app.utils.ui_preview import sample_account_details


def test_main_menu_has_quick_update() -> None:
    markup = main_menu_kb()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels == [
        "🏦 Accounts",
        "📊 Balance Summary",
        "➕ Add Account",
        "⚙️ Settings",
        "⚡ Quick Update",
    ]


def test_account_button_includes_available_balance() -> None:
    class Fake:
        line_label = "Line 1"
        banking_provider = "Airwallex"
        stored_label = "VMOS"
        currency = "USD"

    label = account_button_label(Fake(), 125000)  # type: ignore[arg-type]
    assert "Line 1" in label
    assert "Airwallex" in label
    assert "VMOS" in label
    assert "$1,250.00" in label
    assert len(label) <= 64
    # List keyboards prefix a single bank/archive emoji without breaking the 64-char cap.
    assert len(f"🏦 {label}"[:64]) <= 64


def test_callback_routing_prefixes() -> None:
    assert MenuCB(a="accounts").pack().startswith("m:")
    assert AccCB(o="view", i=3).pack().startswith("a:")
    assert WdCB(o="alist", a=3, s="pending").pack().startswith("w:")
    assert SetCB(o="tog").pack().startswith("s:")


def test_page_banners_exist_for_widget_screens() -> None:
    for name in (
        "dashboard",
        "accounts",
        "account-details",
        "balance-summary",
        "add-account",
        "expected-charges",
        "login-details",
        "settings",
        "quick-add",
        "transactions",
    ):
        assert banner_exists(name)
        assert banner_path(name).stat().st_size > 0


def test_core_widgets_fit_telegram_limits() -> None:
    class FakeSnap:
        accounts = []
        by_currency = {}

    samples = [
        dashboard_html(FakeSnap()),  # type: ignore[arg-type]
        account_details_html(sample_account_details()),
        prompt_html(screen="quick-add", caption_html="<b>Enter amount</b>\n<code>1250.00</code>"),
    ]
    for html in samples:
        ok, raw, compressed = widget_size_ok(html)
        assert ok, f"raw={raw} compressed={compressed}"
        assert compressed <= 4096
