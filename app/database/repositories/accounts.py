"""Account persistence."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database
from app.services.naming import resolve_display_name

_ACCOUNT_ORDER = (
    "ORDER BY (vm_number IS NULL), vm_number ASC, company_name COLLATE NOCASE ASC, id ASC"
)


@dataclass(slots=True)
class Account:
    id: int
    display_name: str
    bank_name: str
    vm_number: int | None
    company_name: str | None
    currency: str
    balance_minor: int
    last_updated_at: str | None
    last_checked_at: str | None
    login_url: str | None
    login_username: str | None
    password_manager_ref: str | None
    notes: str | None
    created_at: str
    updated_at: str
    is_archived: bool

    @property
    def banking_provider(self) -> str:
        return self.bank_name

    @classmethod
    def from_row(cls, row) -> Account:
        keys = set(row.keys())
        vm_number = row["vm_number"] if "vm_number" in keys else None
        company_name = row["company_name"] if "company_name" in keys else None
        return cls(
            id=row["id"],
            display_name=row["display_name"],
            bank_name=row["bank_name"],
            vm_number=int(vm_number) if vm_number is not None else None,
            company_name=company_name,
            currency=row["currency"],
            balance_minor=int(row["balance_minor"]),
            last_updated_at=row["last_updated_at"],
            last_checked_at=row["last_checked_at"],
            login_url=row["login_url"],
            login_username=row["login_username"],
            password_manager_ref=row["password_manager_ref"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_archived=bool(row["is_archived"]),
        )


class AccountRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        *,
        display_name: str,
        bank_name: str,
        currency: str,
        balance_minor: int,
        created_at: str,
        vm_number: int | None = None,
        company_name: str | None = None,
        login_url: str | None = None,
        login_username: str | None = None,
        password_manager_ref: str | None = None,
        notes: str | None = None,
        last_updated_at: str | None = None,
        last_checked_at: str | None = None,
    ) -> Account:
        display_name = resolve_display_name(vm_number, company_name, fallback=display_name)
        cursor = await self.db.execute(
            """
            INSERT INTO accounts (
                display_name, bank_name, vm_number, company_name, currency,
                balance_minor, last_updated_at, last_checked_at,
                login_url, login_username, password_manager_ref, notes,
                created_at, updated_at, is_archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                display_name,
                bank_name,
                vm_number,
                company_name,
                currency,
                balance_minor,
                last_updated_at,
                last_checked_at,
                login_url,
                login_username,
                password_manager_ref,
                notes,
                created_at,
                created_at,
            ),
        )
        account_id = cursor.lastrowid
        account = await self.get(int(account_id))
        assert account is not None
        return account

    async def get(self, account_id: int) -> Account | None:
        row = await self.db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return Account.from_row(row) if row else None

    async def find_by_vm_company(self, vm_number: int, company_name: str) -> Account | None:
        row = await self.db.fetchone(
            """
            SELECT * FROM accounts
            WHERE vm_number = ? AND company_name = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (vm_number, company_name),
        )
        return Account.from_row(row) if row else None

    async def list_accounts(self, *, archived: bool, offset: int = 0, limit: int = 50) -> list[Account]:
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM accounts
            WHERE is_archived = ?
            {_ACCOUNT_ORDER}
            LIMIT ? OFFSET ?
            """,
            (1 if archived else 0, limit, offset),
        )
        return [Account.from_row(row) for row in rows]

    async def list_all(self, *, archived: bool | None = False) -> list[Account]:
        if archived is None:
            rows = await self.db.fetchall(
                f"SELECT * FROM accounts ORDER BY is_archived ASC, (vm_number IS NULL), vm_number ASC, company_name COLLATE NOCASE ASC, id ASC"
            )
        else:
            rows = await self.db.fetchall(
                f"""
                SELECT * FROM accounts
                WHERE is_archived = ?
                {_ACCOUNT_ORDER}
                """,
                (1 if archived else 0,),
            )
        return [Account.from_row(row) for row in rows]

    async def count(self, *, archived: bool) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM accounts WHERE is_archived = ?",
            (1 if archived else 0,),
        )
        return int(row["n"]) if row else 0

    async def update_fields(self, account_id: int, fields: dict[str, object], updated_at: str) -> Account | None:
        if not fields:
            return await self.get(account_id)
        allowed = {
            "display_name",
            "bank_name",
            "vm_number",
            "company_name",
            "currency",
            "login_url",
            "login_username",
            "password_manager_ref",
            "notes",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown account fields: {unknown}")
        assignments = ", ".join(f"{column} = ?" for column in fields)
        values = list(fields.values())
        values.extend([updated_at, account_id])
        await self.db.execute(
            f"UPDATE accounts SET {assignments}, updated_at = ? WHERE id = ?",
            tuple(values),
        )
        return await self.get(account_id)

    async def set_archived(self, account_id: int, archived: bool, updated_at: str) -> Account | None:
        await self.db.execute(
            "UPDATE accounts SET is_archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, updated_at, account_id),
        )
        return await self.get(account_id)

    async def delete(self, account_id: int) -> bool:
        cursor = await self.db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cursor.rowcount > 0

    async def set_balance(
        self,
        account_id: int,
        balance_minor: int,
        *,
        last_updated_at: str,
        last_checked_at: str,
        updated_at: str,
    ) -> Account | None:
        await self.db.execute(
            """
            UPDATE accounts
            SET balance_minor = ?, last_updated_at = ?, last_checked_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (balance_minor, last_updated_at, last_checked_at, updated_at, account_id),
        )
        return await self.get(account_id)

    async def mark_checked(self, account_id: int, checked_at: str) -> Account | None:
        await self.db.execute(
            "UPDATE accounts SET last_checked_at = ?, updated_at = ? WHERE id = ?",
            (checked_at, checked_at, account_id),
        )
        return await self.get(account_id)

    async def mark_all_checked(self, checked_at: str, *, archived: bool = False) -> int:
        cursor = await self.db.execute(
            "UPDATE accounts SET last_checked_at = ?, updated_at = ? WHERE is_archived = ?",
            (checked_at, checked_at, 1 if archived else 0),
        )
        return cursor.rowcount

    async def latest_update(self) -> tuple[str, str] | None:
        row = await self.db.fetchone(
            """
            SELECT display_name, last_updated_at
            FROM accounts
            WHERE last_updated_at IS NOT NULL
            ORDER BY last_updated_at DESC
            LIMIT 1
            """
        )
        if not row or not row["last_updated_at"]:
            return None
        return row["display_name"], row["last_updated_at"]
