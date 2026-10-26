"""Balance history persistence."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database


@dataclass(slots=True)
class BalanceHistoryEntry:
    id: int
    account_id: int
    old_balance_minor: int
    new_balance_minor: int
    recorded_at: str

    @classmethod
    def from_row(cls, row) -> BalanceHistoryEntry:
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            old_balance_minor=int(row["old_balance_minor"]),
            new_balance_minor=int(row["new_balance_minor"]),
            recorded_at=row["recorded_at"],
        )


class BalanceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(
        self,
        *,
        account_id: int,
        old_balance_minor: int,
        new_balance_minor: int,
        recorded_at: str,
    ) -> BalanceHistoryEntry:
        cursor = await self.db.execute(
            """
            INSERT INTO balance_history (
                account_id, old_balance_minor, new_balance_minor, recorded_at
            ) VALUES (?, ?, ?, ?)
            """,
            (account_id, old_balance_minor, new_balance_minor, recorded_at),
        )
        entry_id = int(cursor.lastrowid)
        row = await self.db.fetchone("SELECT * FROM balance_history WHERE id = ?", (entry_id,))
        assert row is not None
        return BalanceHistoryEntry.from_row(row)

    async def list_for_account(
        self, account_id: int, *, offset: int = 0, limit: int = 20
    ) -> list[BalanceHistoryEntry]:
        rows = await self.db.fetchall(
            """
            SELECT * FROM balance_history
            WHERE account_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (account_id, limit, offset),
        )
        return [BalanceHistoryEntry.from_row(row) for row in rows]

    async def count_for_account(self, account_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM balance_history WHERE account_id = ?",
            (account_id,),
        )
        return int(row["n"]) if row else 0

    async def delete_for_account(self, account_id: int) -> int:
        cursor = await self.db.execute(
            "DELETE FROM balance_history WHERE account_id = ?",
            (account_id,),
        )
        return cursor.rowcount

    async def list_all(self) -> list[BalanceHistoryEntry]:
        rows = await self.db.fetchall(
            "SELECT * FROM balance_history ORDER BY recorded_at DESC, id DESC"
        )
        return [BalanceHistoryEntry.from_row(row) for row in rows]
