"""Deposit-instruction persistence. Identifiers are stored as TEXT to keep leading zeros."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import Database

DEPOSIT_FIELDS = (
    "account_holder",
    "bank_name",
    "iban",
    "account_number",
    "routing_number",
    "sort_code",
    "swift_bic",
    "payment_reference",
    "notes",
)


@dataclass(slots=True)
class DepositDetails:
    account_id: int
    account_holder: str | None
    bank_name: str | None
    iban: str | None
    account_number: str | None
    routing_number: str | None
    sort_code: str | None
    swift_bic: str | None
    payment_reference: str | None
    notes: str | None
    updated_at: str

    @classmethod
    def from_row(cls, row) -> DepositDetails:
        return cls(
            account_id=row["account_id"],
            account_holder=row["account_holder"],
            bank_name=row["bank_name"],
            iban=row["iban"],
            account_number=row["account_number"],
            routing_number=row["routing_number"],
            sort_code=row["sort_code"],
            swift_bic=row["swift_bic"],
            payment_reference=row["payment_reference"],
            notes=row["notes"],
            updated_at=row["updated_at"],
        )

    def is_empty(self) -> bool:
        return not any(
            [
                self.account_holder,
                self.bank_name,
                self.iban,
                self.account_number,
                self.routing_number,
                self.sort_code,
                self.swift_bic,
                self.payment_reference,
                self.notes,
            ]
        )


class DepositRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, account_id: int) -> DepositDetails | None:
        row = await self.db.fetchone(
            "SELECT * FROM deposit_details WHERE account_id = ?", (account_id,)
        )
        return DepositDetails.from_row(row) if row else None

    async def upsert(self, account_id: int, fields: dict[str, str | None], updated_at: str) -> DepositDetails:
        existing = await self.get(account_id)
        payload = {key: fields.get(key) for key in DEPOSIT_FIELDS}
        if existing:
            merged = {key: payload[key] if key in fields else getattr(existing, key) for key in DEPOSIT_FIELDS}
            assignments = ", ".join(f"{column} = ?" for column in DEPOSIT_FIELDS)
            values = [merged[column] for column in DEPOSIT_FIELDS]
            values.extend([updated_at, account_id])
            await self.db.execute(
                f"UPDATE deposit_details SET {assignments}, updated_at = ? WHERE account_id = ?",
                tuple(values),
            )
        else:
            columns = ", ".join(["account_id", *DEPOSIT_FIELDS, "updated_at"])
            placeholders = ", ".join("?" for _ in range(len(DEPOSIT_FIELDS) + 2))
            values = [account_id, *[payload[column] for column in DEPOSIT_FIELDS], updated_at]
            await self.db.execute(
                f"INSERT INTO deposit_details ({columns}) VALUES ({placeholders})",
                tuple(values),
            )
        details = await self.get(account_id)
        assert details is not None
        return details

    async def delete(self, account_id: int) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM deposit_details WHERE account_id = ?", (account_id,)
        )
        return cursor.rowcount > 0
