"""Account management business rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.repositories.accounts import Account, AccountRepository
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
    }
)

MAX_NOTES = 1000
MAX_URL = 500


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


class AccountService:
    def __init__(self, repo: AccountRepository) -> None:
        self.repo = repo

    async def create(self, draft: AccountDraft) -> Account:
        try:
            vm_number = _vm_number(draft.vm_number)
            company_name = clean_company_name(draft.company_name)
            bank_name = clean_provider(draft.bank_name)
            currency = normalize_ui_currency(draft.currency)
            balance_minor = parse_to_minor(draft.balance_raw or "0", currency)
        except (NamingError, MoneyError) as exc:
            raise AccountError(str(exc)) from exc
        now = utc_now_iso()
        display_name = resolve_display_name(vm_number, company_name)
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
            else:
                fields[key] = _clean_optional(None if value is None else str(value), key.replace("_", " ").title())

        next_vm = fields.get("vm_number", account.vm_number)
        next_company = fields.get("company_name", account.company_name)
        fields["display_name"] = resolve_display_name(
            next_vm if isinstance(next_vm, int) or next_vm is None else account.vm_number,
            str(next_company) if next_company is not None else None,
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
