import time
from uuid import UUID

import jwt
from fastapi import HTTPException
from training_contracts.privacy import no_link


class Grants:
    def __init__(self, settings):
        no_link(settings.public_key_file)
        self.key = settings.public_key_file.read_bytes()
        self.org, self.device = str(settings.organization_id), str(settings.device_id)

    def verify(self, authorization, scopes, session_id=None):
        try:
            if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 8192:
                raise ValueError()
            c = jwt.decode(
                authorization[7:],
                self.key,
                algorithms=["EdDSA"],
                audience="device-training",
                issuer="pms-training-v1",
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "sub",
                        "jti",
                        "scope",
                        "session_id",
                        "organization_id",
                        "device_id",
                        "scenario_hash",
                        "session_deadline",
                    ]
                },
            )
            for name in ("session_id", "organization_id", "device_id", "sub", "jti"):
                UUID(c[name])
            if c["organization_id"] != self.org or c["device_id"] != self.device or c["scope"] not in scopes:
                raise ValueError()
            if c["exp"] - c["iat"] > 60 or (session_id and c["session_id"] != str(session_id)):
                raise ValueError()
            if c["scope"] != "read" and c["session_deadline"] <= time.time():
                raise ValueError()
            return c
        except Exception:
            raise HTTPException(401, "session_authorization_required") from None
