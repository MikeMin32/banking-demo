"""Decimal money helpers. Never use floating-point for financial values."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# ISO 4217 minor-unit exponents. Unlisted currencies default to 2.
CURRENCY_EXPONENTS: dict[str, int] = {
    "BIF": 0,
    "CLP": 0,
    "DJF": 0,
    "GNF": 0,
    "ISK": 0,
    "JPY": 0,
    "KMF": 0,
    "KRW": 0,
    "PYG": 0,
    "RWF": 0,
    "UGX": 0,
    "UYI": 0,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
    "BHD": 3,
    "IQD": 3,
    "JOD": 3,
    "KWD": 3,
    "LYD": 3,
    "OMR": 3,
    "TND": 3,
}

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_AMOUNT_RE = re.compile(r"^[+-]?\d{1,18}(?:[.,]\d{1,8})?$")

UI_CURRENCIES = ("USD", "EUR")


class MoneyError(ValueError):
    """Raised when an amount or currency cannot be accepted."""


def normalize_currency(raw: str) -> str:
    code = (raw or "").strip().upper()
    if not _CURRENCY_RE.match(code):
        raise MoneyError("Currency must be a 3-letter ISO 4217 code, for example USD or EUR.")
    return code


def normalize_ui_currency(raw: str) -> str:
    code = normalize_currency(raw)
    if code not in UI_CURRENCIES:
        raise MoneyError("Please choose USD or EUR.")
    return code


def exponent_for(currency: str) -> int:
    return CURRENCY_EXPONENTS.get(normalize_currency(currency), 2)


def quantizer(currency: str) -> Decimal:
    places = exponent_for(currency)
    return Decimal("1").scaleb(-places)


def parse_amount(raw: str, currency: str) -> Decimal:
    """Parse user input into a Decimal quantized to the currency exponent."""
    text = (raw or "").strip().replace(" ", "").replace("\u00a0", "").replace("'", "")
    if not text:
        raise MoneyError("Please enter an amount.")
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    if text.startswith("+"):
        text = text[1:]
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        raise MoneyError("Enter a number such as 1250.50 (use a dot as the decimal separator).")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError("That amount is not a valid number.") from exc
    places = exponent_for(currency)
    as_tuple = value.as_tuple()
    decimals = -as_tuple.exponent if as_tuple.exponent < 0 else 0
    if decimals > places:
        raise MoneyError(
            f"{normalize_currency(currency)} amounts can have at most {places} decimal place(s)."
        )
    quantized = value.quantize(quantizer(currency), rounding=ROUND_HALF_UP)
    return quantized


def to_minor(amount: Decimal, currency: str) -> int:
    places = exponent_for(currency)
    quantized = amount.quantize(quantizer(currency), rounding=ROUND_HALF_UP)
    minor = (quantized * (Decimal(10) ** places)).to_integral_value(rounding=ROUND_HALF_UP)
    return int(minor)


def from_minor(minor: int, currency: str) -> Decimal:
    places = exponent_for(currency)
    value = Decimal(minor) / (Decimal(10) ** places)
    return value.quantize(quantizer(currency))


def parse_to_minor(raw: str, currency: str) -> int:
    return to_minor(parse_amount(raw, currency), currency)


def format_amount(minor: int, currency: str, *, with_code: bool = True) -> str:
    currency = normalize_currency(currency)
    value = from_minor(minor, currency)
    places = exponent_for(currency)
    formatted = f"{value:,.{places}f}"
    if with_code:
        return f"{formatted} {currency}"
    return formatted


def difference_label(old_minor: int, new_minor: int, currency: str) -> str:
    delta = new_minor - old_minor
    sign = "+" if delta > 0 else ""
    return f"{sign}{format_amount(delta, currency)}"
