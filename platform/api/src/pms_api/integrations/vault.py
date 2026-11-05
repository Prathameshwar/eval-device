import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pms_api.core.common import AppError, canonical


class CredentialVault:
    """AES-256-GCM; AAD binds ciphertext to the owning organization and connection."""

    def __init__(self, settings):
        self.settings = settings

    def key(self, key_id: str) -> bytes:
        try:
            key = base64.b64decode(self.settings.credential_keys[key_id].get_secret_value(), validate=True)
            if len(key) != 32:
                raise ValueError("AES-256 requires 32 bytes")
            return key
        except (KeyError, ValueError) as error:
            raise AppError(
                503, "credential_key_unavailable", "The configured encryption key is unavailable"
            ) from error

    @staticmethod
    def aad(org_id, connection_id):
        return f"pms:credentials:v1:{org_id}:{connection_id}".encode()

    def encrypt(self, org_id, connection_id, credentials: dict) -> tuple[bytes, str]:
        key_id = self.settings.active_credential_key
        nonce = os.urandom(12)
        encrypted = AESGCM(self.key(key_id)).encrypt(
            nonce, canonical(credentials).encode(), self.aad(org_id, connection_id)
        )
        return nonce + encrypted, key_id

    def decrypt(self, connection) -> dict:
        if not connection.encrypted_credentials:
            return {}
        try:
            value = connection.encrypted_credentials
            plaintext = AESGCM(self.key(connection.credential_key_id)).decrypt(
                value[:12],
                value[12:],
                self.aad(
                    getattr(connection, "credential_owner_org", None) or connection.organization_id,
                    getattr(connection, "credential_owner_id", None) or connection.id,
                ),
            )
            return json.loads(plaintext)
        except AppError:
            raise
        except Exception as error:
            raise AppError(
                503, "credential_decryption_failed", "Provider credentials could not be decrypted"
            ) from error
