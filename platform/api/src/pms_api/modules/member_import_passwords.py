"""Short-lived encrypted escrow for passwords created by member imports."""

import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pms_api.core.common import AppError
from pms_api.integrations.vault import CredentialVault


def _context(batch) -> bytes:
    return f"member-import:{batch.organization_id}:{batch.id}".encode()


def seal(batch, settings, passwords: dict[str, str]) -> None:
    if not passwords:
        batch.passwords_encrypted = None
        batch.passwords_key_id = None
        return
    key_id = settings.active_credential_key
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(passwords, ensure_ascii=False, separators=(",", ":")).encode()
    batch.passwords_encrypted = nonce + AESGCM(CredentialVault(settings).key(key_id)).encrypt(
        nonce, plaintext, _context(batch)
    )
    batch.passwords_key_id = key_id


def open_passwords(batch, settings) -> dict[str, str]:
    if batch.passwords_encrypted is None or batch.passwords_key_id is None:
        return {}
    try:
        data = batch.passwords_encrypted
        plaintext = AESGCM(CredentialVault(settings).key(batch.passwords_key_id)).decrypt(
            data[:12], data[12:], _context(batch)
        )
        values = json.loads(plaintext)
        if not isinstance(values, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()
        ):
            raise ValueError("Invalid password escrow")
        return values
    except Exception as error:
        raise AppError(503, "import_password_unavailable", "Import passwords are unavailable") from error
