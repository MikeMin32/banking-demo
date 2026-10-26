from __future__ import annotations

import pytest

from app.services.naming import (
    NamingError,
    format_account_name,
    parse_account_name,
    parse_vm_number,
    resolve_display_name,
)


def test_format_account_name() -> None:
    assert format_account_name(9, "LeBon Shoppe") == "VM 9 - LeBon Shoppe"
    assert format_account_name(4, "Automation Direct") == "VM 4 - Automation Direct"
    assert format_account_name(None, "LeBon Shoppe") is None
    assert format_account_name(9, None) is None


def test_parse_account_name() -> None:
    assert parse_account_name("VM 9 - LeBon Shoppe") == (9, "LeBon Shoppe")
    assert parse_account_name("vm 32 — Graphics Press") == (32, "Graphics Press")
    assert parse_account_name("Operating") == (None, "Operating")
    assert parse_account_name("") == (None, None)


def test_parse_vm_number() -> None:
    assert parse_vm_number("9") == 9
    with pytest.raises(NamingError):
        parse_vm_number("0")
    with pytest.raises(NamingError):
        parse_vm_number("9a")
    with pytest.raises(NamingError):
        parse_vm_number("-3")
    with pytest.raises(NamingError):
        parse_vm_number("")


def test_resolve_display_name_fallback() -> None:
    assert resolve_display_name(None, "Operating", fallback="Operating") == "Operating"
    assert resolve_display_name(1, "Co", fallback="old") == "VM 1 - Co"
