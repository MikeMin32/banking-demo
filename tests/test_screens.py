from __future__ import annotations

from app.keyboards.accounts import account_button_label
from app.keyboards.callbacks import AccCB, MenuCB, SetCB, WdCB
from app.keyboards.common import main_menu_kb
from app.utils.screens import CAPTION_LIMIT, banner_exists, banner_path


def test_placeholder_banners_exist() -> None:
    for name in (
        "dashboard",
        "accounts",
        "account-details",
        "balance-summary",
        "add-account",
        "expected-charges",
        "login-details",
        "settings",
    ):
        assert banner_exists(name)
        assert banner_path(name).stat().st_size > 0
    assert not banner_exists("missing-page")
    assert CAPTION_LIMIT == 1024


def test_main_menu_has_four_primary_actions() -> None:
    markup = main_menu_kb()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels == ["🏦 Bank Accounts", "💰 Balance Summary", "➕ Add Account", "⚙️ Settings"]


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


def test_callback_routing_prefixes() -> None:
    assert MenuCB(a="accounts").pack().startswith("m:")
    assert AccCB(o="view", i=3).pack().startswith("a:")
    assert WdCB(o="alist", a=3, s="pending").pack().startswith("w:")
    assert SetCB(o="tog").pack().startswith("s:")
