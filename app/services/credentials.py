"""Authenticated encryption for login passwords. Key stays outside the database."""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class CredentialError(ValueError):
    pass


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


class CredentialVault:
    def __init__(self, key: str | None) -> None:
        self._fernet: Fernet | None = None
        raw = (key or "").strip()
        if raw:
            try:
                self._fernet = Fernet(raw.encode("ascii") if isinstance(raw, str) else raw)
            except Exception as exc:
                raise CredentialError("ACCOUNT_CREDENTIALS_KEY is not a valid Fernet key.") from exc

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        text = plaintext.strip()
        if not text:
            return None
        if self._fernet is None:
            raise CredentialError(
                "Passwords cannot be stored until ACCOUNT_CREDENTIALS_KEY is set."
            )
        return self._fernet.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str | None) -> str | None:
        if not token:
            return None
        if self._fernet is None:
            raise CredentialError("Password vault is not configured.")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            logger.warning("credential decrypt failed")
            raise CredentialError("Stored password could not be decrypted.") from exc
