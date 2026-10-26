"""Expected withdrawal persistence."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database

VALID_STATUSES = frozenset({"pending", "completed", "cancelled"})


@dataclass(slots=True)
class Withdrawal:
    id: int
    account_id: int
    amount_minor: int
    expected_date: str | None
    description: str | None
    status: str
    created_at: str
    completed_at: str | None
    updated_at: str

    @classmethod
    def from_row(cls, row) -> Withdrawal:
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            amount_minor=int(row["amount_minor"]),
            expected_date=row["expected_date"],
            description=row["description"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            updated_at=row["updated_at"],
        )


class WithdrawalRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        *,
        account_id: int,
        amount_minor: int,
        created_at: str,
        expected_date: str | None = None,
        description: str | None = None,
    ) -> Withdrawal:
        cursor = await self.db.execute(
            """
            INSERT INTO expected_withdrawals (
                account_id, amount_minor, expected_date, description,
                status, created_at, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, NULL, ?)
            """,
            (account_id, amount_minor, expected_date, description, created_at, created_at),
        )
        withdrawal = await self.get(int(cursor.lastrowid))
        assert withdrawal is not None
        return withdrawal

    async def get(self, withdrawal_id: int) -> Withdrawal | None:
        row = await self.db.fetchone(
            "SELECT * FROM expected_withdrawals WHERE id = ?", (withdrawal_id,)
        )
        return Withdrawal.from_row(row) if row else None

    async def list_withdrawals(
        self,
        *,
        status: str | None = None,
        account_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Withdrawal]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if account_id is not None:
            clauses.append("account_id = ?")
            params.append(account_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM expected_withdrawals
            {where}
            ORDER BY
                CASE status WHEN 'pending' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END,
                expected_date IS NULL, expected_date ASC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return [Withdrawal.from_row(row) for row in rows]

    async def count(self, *, status: str | None = None, account_id: int | None = None) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if account_id is not None:
            clauses.append("account_id = ?")
            params.append(account_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = await self.db.fetchone(
            f"SELECT COUNT(*) AS n FROM expected_withdrawals {where}",
            tuple(params),
        )
        return int(row["n"]) if row else 0

    async def list_all(self, *, status: str | None = None) -> list[Withdrawal]:
        if status:
            rows = await self.db.fetchall(
                "SELECT * FROM expected_withdrawals WHERE status = ? ORDER BY id ASC",
                (status,),
            )
        else:
            rows = await self.db.fetchall("SELECT * FROM expected_withdrawals ORDER BY id ASC")
        return [Withdrawal.from_row(row) for row in rows]

    async def pending_total_for_account(self, account_id: int) -> int:
        row = await self.db.fetchone(
            """
            SELECT COALESCE(SUM(amount_minor), 0) AS total
            FROM expected_withdrawals
            WHERE account_id = ? AND status = 'pending'
            """,
            (account_id,),
        )
        return int(row["total"]) if row else 0

    async def pending_totals_by_account(self) -> dict[int, int]:
        rows = await self.db.fetchall(
            """
            SELECT account_id, COALESCE(SUM(amount_minor), 0) AS total
            FROM expected_withdrawals
            WHERE status = 'pending'
            GROUP BY account_id
            """
        )
        return {int(row["account_id"]): int(row["total"]) for row in rows}

    async def update_fields(self, withdrawal_id: int, fields: dict[str, object], updated_at: str) -> Withdrawal | None:
        if not fields:
            return await self.get(withdrawal_id)
        assignments = ", ".join(f"{column} = ?" for column in fields)
        values = list(fields.values())
        values.extend([updated_at, withdrawal_id])
        await self.db.execute(
            f"UPDATE expected_withdrawals SET {assignments}, updated_at = ? WHERE id = ?",
            tuple(values),
        )
        return await self.get(withdrawal_id)

    async def delete(self, withdrawal_id: int) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM expected_withdrawals WHERE id = ?", (withdrawal_id,)
        )
        return cursor.rowcount > 0
