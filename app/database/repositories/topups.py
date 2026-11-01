"""Top-up persistence. Incoming funds already received."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database


@dataclass(slots=True)
class TopUp:
    id: int
    account_id: int
    amount_minor: int
    currency: str
    created_at: str
    applied_to_balance: bool
    reversed_at: str | None
    updated_at: str

    @property
    def is_reversed(self) -> bool:
        return bool(self.reversed_at)

    @classmethod
    def from_row(cls, row) -> TopUp:
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            amount_minor=int(row["amount_minor"]),
            currency=row["currency"],
            created_at=row["created_at"],
            applied_to_balance=bool(row["applied_to_balance"]),
            reversed_at=row["reversed_at"],
            updated_at=row["updated_at"],
        )


class TopUpRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        *,
        account_id: int,
        amount_minor: int,
        currency: str,
        created_at: str,
    ) -> TopUp:
        cursor = await self.db.execute(
            """
            INSERT INTO top_ups (
                account_id, amount_minor, currency, created_at,
                applied_to_balance, reversed_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, NULL, ?)
            """,
            (account_id, amount_minor, currency, created_at, created_at),
        )
        top_up = await self.get(int(cursor.lastrowid))
        assert top_up is not None
        return top_up

    async def get(self, top_up_id: int) -> TopUp | None:
        row = await self.db.fetchone("SELECT * FROM top_ups WHERE id = ?", (top_up_id,))
        return TopUp.from_row(row) if row else None

    async def mark_applied_if_needed(self, top_up_id: int, updated_at: str) -> int:
        cursor = await self.db.execute(
            """
            UPDATE top_ups
            SET applied_to_balance = 1, updated_at = ?
            WHERE id = ? AND applied_to_balance = 0 AND reversed_at IS NULL
            """,
            (updated_at, top_up_id),
        )
        return int(cursor.rowcount or 0)

    async def mark_reversed_if_applied(self, top_up_id: int, now: str) -> int:
        cursor = await self.db.execute(
            """
            UPDATE top_ups
            SET reversed_at = ?, updated_at = ?
            WHERE id = ? AND applied_to_balance = 1 AND reversed_at IS NULL
            """,
            (now, now, top_up_id),
        )
        return int(cursor.rowcount or 0)

    async def list_for_account(
        self, account_id: int, *, offset: int = 0, limit: int = 20
    ) -> list[TopUp]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM top_ups
            WHERE account_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (account_id, limit, offset),
        )
        return [TopUp.from_row(row) for row in rows]

    async def count_for_account(self, account_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM top_ups WHERE account_id = ?",
            (account_id,),
        )
        return int(row["n"]) if row else 0
