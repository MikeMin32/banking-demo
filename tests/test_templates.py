from __future__ import annotations

import pytest

from app.services.accounts import AccountError
from app.services.templates import parse_bank_block, parse_login_block


def test_parse_bank_block() -> None:
    parsed = parse_bank_block(
        "Bank Provider: Airwallex\n"
        "IBAN: DE00\n"
        "BIN: 411111\n"
        "Currency: USD\n"
        "Line: Line 1\n"
        "VM: VM 9\n"
        "Stored Where: VMOS\n"
        "Balance: 1250.50"
    )
    assert parsed["bank_name"] == "Airwallex"
    assert parsed["iban"] == "DE00"
    assert parsed["bin"] == "411111"
    assert parsed["currency"] == "USD"
    assert parsed["line_name"] == "Line 1"
    assert parsed["linked_vm"] == "VM 9"
    assert parsed["stored_where"] == "VMOS"
    assert parsed["balance_raw"] == "1250.50"


def test_parse_bank_block_missing_required() -> None:
    with pytest.raises(AccountError):
        parse_bank_block("Bank Provider: Airwallex\nCurrency: USD")


def test_parse_login_block_allows_empty() -> None:
    parsed = parse_login_block("Mobile Number:\nEmail:\nPassword:\n2FA Method: Fanytel")
    assert parsed.get("login_mobile") == ""
    assert parsed.get("two_fa_method") == "Fanytel"
