from __future__ import annotations

import pytest

from app.services.money import (
    MoneyError,
    difference_label,
    format_amount,
    from_minor,
    normalize_currency,
    parse_amount,
    parse_to_minor,
    to_minor,
)


def test_parse_and_format_usd() -> None:
    assert parse_to_minor("1250.50", "usd") == 125050
    assert format_amount(125050, "USD") == "1,250.50 USD"
    assert from_minor(1, "USD") == parse_amount("0.01", "USD")


def test_zero_and_negative() -> None:
    assert parse_to_minor("0", "EUR") == 0
    assert parse_to_minor("-10.25", "EUR") == -1025
    assert parse_to_minor("+3.5", "USD") == 350


def test_thousands_separator() -> None:
    assert parse_to_minor("1,000.50", "USD") == 100050


def test_european_comma_decimal() -> None:
    assert parse_to_minor("1000,50", "EUR") == 100050


def test_jpy_no_decimals() -> None:
    assert parse_to_minor("1500", "JPY") == 1500
    with pytest.raises(MoneyError):
        parse_to_minor("1500.5", "JPY")


def test_rejects_too_many_decimals() -> None:
    with pytest.raises(MoneyError):
        parse_to_minor("10.123", "USD")


def test_rejects_invalid() -> None:
    with pytest.raises(MoneyError):
        parse_to_minor("", "USD")
    with pytest.raises(MoneyError):
        parse_to_minor("abc", "USD")
    with pytest.raises(MoneyError):
        normalize_currency("US")
    with pytest.raises(MoneyError):
        normalize_currency("USDD")


def test_difference_label() -> None:
    assert difference_label(1000, 1500, "USD") == "+5.00 USD"
    assert difference_label(1500, 1000, "USD") == "-5.00 USD"


def test_never_uses_float() -> None:
    minor = to_minor(parse_amount("0.10", "USD"), "USD")
    minor += to_minor(parse_amount("0.20", "USD"), "USD")
    assert format_amount(minor, "USD", with_code=False) == "0.30"
