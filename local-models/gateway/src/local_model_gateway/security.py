import hashlib
import sqlite3
import time
from pathlib import Path
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from training_contracts.inference import ISSUER, PATHS
from training_contracts.privacy import no_link, private_directory, private_tree


class Rejected(Exception):
    def __init__(self, code="unauthorized", status=403):
        self.code, self.status = code, status


class Grants:
    def __init__(self, key, host_id):
        self.key = serialization.load_pem_public_key(key)
        if not isinstance(self.key, Ed25519PublicKey):
            raise ValueError("Pin the platform's Ed25519 public key")
        self.host_id = str(UUID(str(host_id)))

    def verify(self, authorization, method, path, raw):
        try:
            if not authorization.startswith("Bearer ") or len(authorization) > 8192:
                raise ValueError()
            claims = jwt.decode(
                authorization[7:],
                self.key,
                algorithms=["EdDSA"],
                issuer=ISSUER,
                audience=self.host_id,
                options={
                    "require": [
                        "sub",
                        "org",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                        "deadline",
                        "method",
                        "path",
                        "sha256",
                    ]
                },
            )
            for field in ("sub", "org", "jti"):
                UUID(claims[field])
            if (
                path not in PATHS
                or claims["path"] != path
                or claims["method"] != method
                or claims["sha256"] != hashlib.sha256(raw).hexdigest()
                or not 0 < claims["exp"] - claims["iat"] <= 30
                or not claims["exp"] <= claims["deadline"] <= claims["iat"] + 180
                or claims["deadline"] <= time.time()
            ):
                raise ValueError()
            return claims
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise Rejected() from None


class Receipts:
    """Metadata only. Claim commits before forwarding; restart preserves unknown outcomes."""

    def __init__(self, directory, requests_per_minute=120):
        self.requests_per_minute = requests_per_minute
        root = Path(directory).absolute()
        private_tree(root)
        self.path = root / "receipts.sqlite3"
        if self.path.exists() or self.path.is_symlink():
            no_link(self.path)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, device TEXT NOT NULL, "
                "org TEXT NOT NULL, state TEXT NOT NULL, stamp REAL NOT NULL)"
            )
        private_directory(self.path)

    def connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def claim(self, claims):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM receipts WHERE stamp < ?", (time.time() - 86400,))
            recent = db.execute(
                "SELECT count(*) FROM receipts WHERE device=? AND org=? AND stamp>?",
                (claims["sub"], claims["org"], time.time() - 60),
            ).fetchone()[0]
            if recent >= self.requests_per_minute:
                raise Rejected("capacity", 429)
            if db.execute("SELECT count(*) FROM receipts").fetchone()[0] >= 100000:
                raise Rejected("capacity", 429)
            try:
                db.execute(
                    "INSERT INTO receipts VALUES (?, ?, ?, 'unknown', ?)",
                    (claims["jti"], claims["sub"], claims["org"], time.time()),
                )
            except sqlite3.IntegrityError:
                raise Rejected("replay", 409) from None

    def finish(self, identity, state):
        with self.connect() as db:
            db.execute("UPDATE receipts SET state=? WHERE id=?", (state, identity))

    def status(self, identity, device, org):
        with self.connect() as db:
            row = db.execute(
                "SELECT state FROM receipts WHERE id=? AND device=? AND org=?", (identity, device, org)
            ).fetchone()
        return row[0] if row else "not_found"
