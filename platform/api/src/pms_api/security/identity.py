import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import jwt

from pms_api.core.common import AppError
from pms_api.core.config import Settings


class OIDCVerifier:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.keys: dict = {}
        self.loaded_at = 0.0
        self.lock = asyncio.Lock()

    async def refresh(self):
        async with self.lock:
            if self.keys and time.monotonic() - self.loaded_at < 30:
                return
            try:
                if self.settings.oidc_jwks_file:
                    data = json.loads(Path(self.settings.oidc_jwks_file).read_text())
                else:
                    url = self.settings.oidc_jwks_url
                    if not url:
                        issuer = self.settings.oidc_issuer.rstrip("/")
                        response = await self.client.get(issuer + "/.well-known/openid-configuration")
                        response.raise_for_status()
                        discovery = response.json()
                        if discovery.get("issuer") != self.settings.oidc_issuer:
                            raise ValueError("issuer mismatch")
                        url = discovery["jwks_uri"]
                    if urlparse(url).scheme != "https":
                        raise ValueError("HTTPS JWKS required")
                    response = await self.client.get(url)
                    response.raise_for_status()
                    data = response.json()
                self.keys = {
                    key["kid"]: key
                    for key in data["keys"]
                    if key.get("kid") and key.get("use", "sig") == "sig"
                }
                self.loaded_at = time.monotonic()
            except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
                raise AppError(
                    503, "identity_unavailable", "Identity verification is temporarily unavailable"
                ) from error

    async def verify(self, token: str) -> dict:
        if not self.settings.oidc_issuer or not self.settings.oidc_audience:
            raise AppError(503, "identity_not_configured", "Configure the OIDC issuer and audience")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"RS256", "ES256"} or not isinstance(header.get("kid"), str):
                raise jwt.InvalidTokenError()
            if not self.keys or time.monotonic() - self.loaded_at > 300 or header["kid"] not in self.keys:
                await self.refresh()
            key = jwt.PyJWK.from_dict(self.keys[header["kid"]], algorithm=header["alg"])
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[header["alg"]],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=15,
            )
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise jwt.InvalidTokenError()
            return claims
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as error:
            raise AppError(401, "invalid_token", "Invalid or expired access token") from error
