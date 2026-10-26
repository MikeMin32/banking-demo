"""VM account naming: 'VM {number} - {company_name}'."""

from __future__ import annotations

import re

_VM_NAME_RE = re.compile(r"^VM\s+(\d+)\s*[-–—]\s*(.+)$", re.IGNORECASE)
_VM_NUMBER_RE = re.compile(r"^\d+$")

MAIN_PROVIDERS = ("Airwallex", "N26")


class NamingError(ValueError):
    pass


def parse_vm_number(raw: str) -> int:
    text = (raw or "").strip()
    if not text or not _VM_NUMBER_RE.fullmatch(text):
        raise NamingError("VM number must be a positive whole number, for example 9.")
    number = int(text)
    if number < 1:
        raise NamingError("VM number must be a positive whole number, for example 9.")
    if number > 1_000_000:
        raise NamingError("That VM number is too large.")
    return number


def clean_company_name(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text:
        raise NamingError("Company name cannot be empty.")
    if len(text) > 200:
        raise NamingError("Company name is too long (max 200 characters).")
    return text


def format_account_name(vm_number: int | None, company_name: str | None) -> str | None:
    company = (company_name or "").strip()
    if vm_number is not None and company:
        return f"VM {int(vm_number)} - {company}"
    return None


def parse_account_name(display_name: str | None) -> tuple[int | None, str | None]:
    text = (display_name or "").strip()
    if not text:
        return None, None
    match = _VM_NAME_RE.match(text)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return None, text


def resolve_display_name(
    vm_number: int | None,
    company_name: str | None,
    *,
    fallback: str | None = None,
) -> str:
    generated = format_account_name(vm_number, company_name)
    if generated:
        return generated
    if fallback and fallback.strip():
        return fallback.strip()
    if company_name and company_name.strip():
        return company_name.strip()
    if vm_number is not None:
        return f"VM {int(vm_number)}"
    return "Unnamed account"


def clean_provider(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text:
        raise NamingError("Banking provider cannot be empty.")
    if len(text) > 200:
        raise NamingError("Banking provider is too long (max 200 characters).")
    return text
