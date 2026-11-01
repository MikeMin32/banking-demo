from __future__ import annotations

import pytest

from app.config import Settings
from app.services.auth import AuthService
from app.services.container import Services
from app.services.credentials import CredentialError, CredentialVault, generate_key
from tests.conftest import draft


async def test_password_encrypted_at_rest(services: Services) -> None:
    account = await services.accounts.create(
        draft(line_name="Line 1", login_password="super-secret-pass")
    )
    row = await services.db.fetchone(
        "SELECT login_password_encrypted FROM accounts WHERE id = ?", (account.id,)
    )
    stored = row["login_password_encrypted"]
    assert stored
    assert "super-secret-pass" not in stored
    assert services.accounts.reveal_password(account) == "super-secret-pass"


async def test_password_absent_without_key(tmp_path) -> None:
    from app.database.connection import Database
    from app.services.container import build_services

    settings = Settings(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        database_path=str(tmp_path / "nokey.db"),
        account_credentials_key="",
    )
    db = Database(settings.database_path)
    await db.connect()
    await db.init()
    services = build_services(db, settings)
    with pytest.raises(Exception):
        await services.accounts.create(draft(line_name="Line 1", login_password="secret"))
    await db.close()


async def test_wrong_key_cannot_decrypt(services: Services) -> None:
    account = await services.accounts.create(draft(login_password="hidden-value"))
    other = CredentialVault(generate_key())
    with pytest.raises(CredentialError):
        other.decrypt(account.login_password_encrypted)


def test_dev_allow_any_user_does_not_grant_credentials(tmp_path) -> None:
    settings = Settings(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        allowed_user_ids="2002",
        database_path=str(tmp_path / "auth.db"),
        dev_allow_any_user=True,
        account_credentials_key=generate_key(),
    )
    auth = AuthService(settings)
    assert auth.is_authorized(9999)
    assert not auth.can_view_credentials(9999)
    assert not auth.can_view_credentials(2002)
    assert auth.can_view_credentials(1001)
    assert not auth.can_view_credentials(None)


async def test_exports_never_include_password(services: Services) -> None:
    await services.accounts.create(
        draft(
            company_name="Secretive",
            login_password="export-must-not-see-this",
            login_email="hidden@example.com",
            login_mobile="+15550001111",
        )
    )
    combined = (
        (await services.exports.accounts_csv()).decode()
        + (await services.exports.balance_history_csv()).decode()
        + (await services.exports.withdrawals_csv()).decode()
    )
    assert "export-must-not-see-this" not in combined
    assert "hidden@example.com" not in combined
    assert "+15550001111" not in combined
