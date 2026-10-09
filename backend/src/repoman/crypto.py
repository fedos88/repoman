"""Encryption of secrets stored in the database (e.g. the LDAP bind password).

The Fernet key is derived from REPOMAN_SECRET_KEY with HKDF, so any sufficiently long
secret can be used. Changing REPOMAN_SECRET_KEY makes stored secrets unreadable; they
have to be entered again.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class SecretDecryptionError(Exception):
    pass


class SecretBox:
    def __init__(self, secret_key: str) -> None:
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"repoman",
            info=b"repoman/db-secrets/v1",
        ).derive(secret_key.encode())
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            raise SecretDecryptionError(
                "Stored secret cannot be decrypted (was REPOMAN_SECRET_KEY changed?)"
            ) from None
