"""Parse copy-and-paste account templates."""

from __future__ import annotations

from app.services.accounts import AccountError

BANK_LABELS = {
    "bank provider": "bank_name",
    "provider": "bank_name",
    "iban": "iban",
    "bin": "bin",
    "currency": "currency",
    "line": "line_name",
    "vm": "linked_vm",
    "stored where": "stored_where",
    "stored": "stored_where",
    "balance": "balance_raw",
}

LOGIN_LABELS = {
    "mobile number": "login_mobile",
    "mobile": "login_mobile",
    "email": "login_email",
    "password": "login_password",
    "2fa method": "two_fa_method",
    "2fa": "two_fa_method",
}

BANK_TEMPLATE = (
    "Bank Provider:\n"
    "IBAN:\n"
    "BIN:\n"
    "Currency: USD\n"
    "Line:\n"
    "VM:\n"
    "Stored Where:\n"
    "Balance: 0"
)

LOGIN_TEMPLATE = (
    "Mobile Number:\n"
    "Email:\n"
    "Password:\n"
    "2FA Method:"
)


def parse_labeled_block(text: str, labels: dict[str, str]) -> dict[str, str]:
    data: dict[str, str] = {}
    if not (text or "").strip():
        raise AccountError("Please send the filled template.")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        label, value = line.split(":", 1)
        key = labels.get(label.strip().lower())
        if key:
            data[key] = value.strip()
    return data


def parse_bank_block(text: str) -> dict[str, str]:
    data = parse_labeled_block(text, BANK_LABELS)
    missing = [name for name in ("bank_name", "currency", "line_name") if not data.get(name)]
    if missing:
        pretty = {"bank_name": "Bank Provider", "currency": "Currency", "line_name": "Line"}
        raise AccountError("Missing required fields: " + ", ".join(pretty[name] for name in missing) + ".")
    return data


def parse_login_block(text: str) -> dict[str, str]:
    return parse_labeled_block(text, LOGIN_LABELS)
