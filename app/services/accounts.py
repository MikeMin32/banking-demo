"""Account management business rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.database.repositories.accounts import Account, AccountRepository
from app.services.credentials import CredentialError, CredentialVault
from app.services.money import MoneyError, normalize_ui_currency, parse_to_minor
from app.services.naming import (
    NamingError,
    clean_company_name,
    clean_provider,
    parse_vm_number,
    resolve_display_name,
)
from app.utils.time import utc_now_iso

ACCOUNT_EDITABLE_FIELDS = frozenset(
    {
        "vm_number",
        "company_name",
        "bank_name",
        "currency",
        "login_url",
        "login_username",
        "password_manager_ref",
        "notes",
        "line_name",
        "linked_vm",
        "stored_where",
        "iban",
        "bin",
        "login_mobile",
        "login_email",
        "login_password",
        "two_fa_method",
    }
)

MAX_NOTES = 1000
MAX_URL = 500
MAX_FIELD = 200


class AccountError(ValueError):
    pass


class CurrencyChangeNeedsConfirm(AccountError):
    pass


@dataclass(slots=True)
class AccountDraft:
    vm_number: int | str = 0
    company_name: str = ""
    bank_name: str = ""
    currency: str = ""
    balance_raw: str = "0"
    login_url: str | None = None
    login_username: str | None = None
    password_manager_ref: str | None = None
    notes: str | None = None
    line_name: str | None = None
    linked_vm: str | None = None
    stored_where: str | None = None
    iban: str | None = None
    bin: str | None = None
    login_mobile: str | None = None
    login_email: str | None = None
    login_password: str | None = None
    two_fa_method: str | None = None


def _clean_optional(value: str | None, label: str, *, max_len: int = 200) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > max_len:
        raise AccountError(f"{label} is too long (max {max_len} characters).")
    return text


def _vm_number(value: object) -> int:
    try:
        return parse_vm_number(str(value))
    except NamingError as exc:
        raise AccountError(str(exc)) from exc


def parse_linked_vm(raw: str | None) -> tuple[str | None, int | None]:
    text = _clean_optional(raw, "VM", max_len=MAX_FIELD)
    if text is None:
        return None, None
    compact = re.fullmatch(r"(?:VM\s*)?(\d+)$", text, re.IGNORECASE)
    if compact:
        number = int(compact.group(1))
        if 1 <= number <= 1_000_000:
            return text, number
    return text, None


class AccountService:
    def __init__(self, repo: AccountRepository, vault: CredentialVault | None = None) -> None:
        self.repo = repo
        self.vault = vault or CredentialVault("")

    async def create(self, draft: AccountDraft) -> Account:
        try:
            bank_name = clean_provider(draft.bank_name)
            currency = normalize_ui_currency(draft.currency)
            balance_minor = parse_to_minor(draft.balance_raw or "0", currency)
        except (NamingError, MoneyError) as exc:
            raise AccountError(str(exc)) from exc

        line_name = _clean_optional(draft.line_name, "Line")
        linked_vm, parsed_vm = parse_linked_vm(draft.linked_vm)
        company_raw = (draft.company_name or "").strip()
        vm_raw = draft.vm_number

        vm_number: int | None
        company_name: str | None
        if company_raw or (vm_raw not in {0, "0", "", None}):
            vm_number = _vm_number(vm_raw)
            try:
                company_name = clean_company_name(company_raw or (line_name or ""))
            except NamingError as exc:
                raise AccountError(str(exc)) from exc
            if line_name is None:
                line_name = company_name
            if linked_vm is None and vm_number is not None:
                linked_vm = f"VM {vm_number}"
        else:
            if line_name is None:
                raise AccountError("Line is required.")
            company_name = line_name
            vm_number = parsed_vm

        now = utc_now_iso()
        display_name = resolve_display_name(vm_number, company_name, fallback=line_name)
        try:
            password_enc = self.vault.encrypt(draft.login_password)
        except CredentialError as exc:
            raise AccountError(str(exc)) from exc
        return await self.repo.create(
            display_name=display_name,
            bank_name=bank_name,
            currency=currency,
            balance_minor=balance_minor,
            created_at=now,
            vm_number=vm_number,
            company_name=company_name,
            login_url=_clean_optional(draft.login_url, "Login URL", max_len=MAX_URL),
            login_username=_clean_optional(draft.login_username, "Login username"),
            password_manager_ref=_clean_optional(
                draft.password_manager_ref, "Password manager reference", max_len=MAX_URL
            ),
            notes=_clean_optional(draft.notes, "Notes", max_len=MAX_NOTES),
            last_updated_at=now,
            last_checked_at=now,
            line_name=line_name,
            linked_vm=linked_vm,
            stored_where=_clean_optional(draft.stored_where, "Stored where"),
            iban=_clean_optional(draft.iban, "IBAN", max_len=64),
            bin=_clean_optional(draft.bin, "BIN", max_len=32),
            login_mobile=_clean_optional(draft.login_mobile, "Mobile number"),
            login_email=_clean_optional(draft.login_email, "Email"),
            login_password_encrypted=password_enc,
            two_fa_method=_clean_optional(draft.two_fa_method, "2FA method"),
        )

    async def get(self, account_id: int) -> Account:
        account = await self.repo.get(account_id)
        if account is None:
            raise AccountError("That account no longer exists.")
        return account

    async def list_active(self) -> list[Account]:
        return await self.repo.list_all(archived=False)

    async def list_archived(self) -> list[Account]:
        return await self.repo.list_all(archived=True)

    async def page(self, *, archived: bool, page: int, page_size: int) -> tuple[list[Account], int]:
        page = max(page, 0)
        total = await self.repo.count(archived=archived)
        items = await self.repo.list_accounts(
            archived=archived, offset=page * page_size, limit=page_size
        )
        return items, total

    async def update(self, account_id: int, **changes: object) -> Account:
        account = await self.get(account_id)
        fields: dict[str, object] = {}
        for key, value in changes.items():
            if key not in ACCOUNT_EDITABLE_FIELDS:
                raise AccountError("That field cannot be edited.")
            if key == "vm_number":
                fields[key] = _vm_number(value)
            elif key == "company_name":
                try:
                    fields[key] = clean_company_name(str(value or ""))
                except NamingError as exc:
                    raise AccountError(str(exc)) from exc
            elif key == "bank_name":
                try:
                    fields[key] = clean_provider(str(value or ""))
                except NamingError as exc:
                    raise AccountError(str(exc)) from exc
            elif key == "currency":
                try:
                    fields[key] = normalize_ui_currency(str(value or ""))
                except MoneyError as exc:
                    raise AccountError(str(exc)) from exc
            elif key == "notes":
                fields[key] = _clean_optional(None if value is None else str(value), "Notes", max_len=MAX_NOTES)
            elif key in {"login_url", "password_manager_ref"}:
                fields[key] = _clean_optional(
                    None if value is None else str(value), key.replace("_", " ").title(), max_len=MAX_URL
                )
            elif key == "linked_vm":
                linked, parsed = parse_linked_vm(None if value is None else str(value))
                fields["linked_vm"] = linked
                if parsed is not None:
                    fields["vm_number"] = parsed
            elif key == "login_password":
                try:
                    fields["login_password_encrypted"] = self.vault.encrypt(
                        None if value is None else str(value)
                    )
                except CredentialError as exc:
                    raise AccountError(str(exc)) from exc
            elif key in {"iban", "bin"}:
                limit = 64 if key == "iban" else 32
                fields[key] = _clean_optional(None if value is None else str(value), key.upper(), max_len=limit)
            else:
                fields[key] = _clean_optional(None if value is None else str(value), key.replace("_", " ").title())

        next_vm = fields.get("vm_number", account.vm_number)
        next_company = fields.get("company_name", account.company_name)
        next_line = fields.get("line_name", account.line_name)
        fields["display_name"] = resolve_display_name(
            next_vm if isinstance(next_vm, int) or next_vm is None else account.vm_number,
            str(next_company) if next_company is not None else (str(next_line) if next_line else None),
            fallback=account.display_name,
        )
        updated = await self.repo.update_fields(account.id, fields, utc_now_iso())
        if updated is None:
            raise AccountError("That account no longer exists.")
        return updated

    async def archive(self, account_id: int) -> Account:
        account = await self.get(account_id)
        if account.is_archived:
            return account
        updated = await self.repo.set_archived(account.id, True, utc_now_iso())
        assert updated is not None
        return updated

    async def unarchive(self, account_id: int) -> Account:
        account = await self.get(account_id)
        if not account.is_archived:
            return account
        updated = await self.repo.set_archived(account.id, False, utc_now_iso())
        assert updated is not None
        return updated

    async def delete(self, account_id: int) -> None:
        await self.get(account_id)
        await self.repo.delete(account_id)

    async def change_currency(
        self,
        account_id: int,
        currency: str,
        *,
        confirmed: bool = False,
        history_count: int = 0,
        withdrawal_count: int = 0,
    ) -> Account:
        account = await self.get(account_id)
        try:
            code = normalize_ui_currency(currency)
        except MoneyError as exc:
            raise AccountError(str(exc)) from exc
        if account.currency == code:
            return account
        risky = account.balance_minor != 0 or history_count > 0 or withdrawal_count > 0
        if risky and not confirmed:
            raise CurrencyChangeNeedsConfirm(
                "This changes the currency label only. Amounts are not converted."
            )
        return await self.update(account_id, currency=code)

    async def find_by_vm_company(self, vm_number: int, company_name: str) -> Account | None:
        return await self.repo.find_by_vm_company(vm_number, company_name)

    def reveal_password(self, account: Account) -> str | None:
        if not account.login_password_encrypted:
            return None
        try:
            return self.vault.decrypt(account.login_password_encrypted)
        except CredentialError as exc:
            raise AccountError(str(exc)) from exc
