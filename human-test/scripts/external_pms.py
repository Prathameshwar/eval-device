"""Configuration for a separately managed PMS API; never bootstrap identities or data."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from human_test.connection import DEFAULT_PLATFORM


class ExternalPMS(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HUMAN_", extra="ignore", hide_input_in_errors=True)
    pms_url: str = DEFAULT_PLATFORM
    pms_token: SecretStr
    organization_id: UUID
    department_id: UUID | None = None
    processing_profile_id: UUID | None = None
    device_id: UUID | None = None
    device_token: SecretStr | None = None
    history_enabled: bool = True
    local_models_port: int = Field(8790, ge=1024, le=65535)
    local_models_state_dir: Path | None = None

    @model_validator(mode="after")
    def connection(self):
        url = urlsplit(self.pms_url)
        if (
            url.scheme not in ("https", "http")
            or not url.hostname
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "::1"))
            or not self.pms_token.get_secret_value().strip()
        ):
            raise ValueError("Configure a trusted API origin and a valid authenticated token")
        if url.hostname in ("127.0.0.1", "::1") and url.port == self.local_models_port:
            raise ValueError("The central API port must be separate from the local model manager port")
        self.pms_url = self.pms_url.rstrip("/")
        if self.device_token and not self.device_id:
            raise ValueError("A device token requires HUMAN_DEVICE_ID")
        return self


def load_external(here):
    from human_test.connection import connection_values, read_connection

    saved = read_connection(here / ".local/platform-connection/connection.json")
    if saved:
        return ExternalPMS(_env_file=here / ".env", **connection_values(saved))
    if (here / ".local/platform-connection/connection.json").exists():
        raise RuntimeError(
            "Device provisioning was cleared. Connect this desktop with a new enrollment token."
        )
    try:
        return ExternalPMS(_env_file=here / ".env")
    except (ValueError, OSError):
        raise RuntimeError(
            "Configure HUMAN_PMS_URL, HUMAN_PMS_TOKEN and HUMAN_ORGANIZATION_ID in human-test/.env "
            "and HUMAN_DEVICE_ID for your running API. "
            "The platform API must be started separately; Human-test does not start it."
        ) from None


def published_route(demo, call):
    base = f"/organizations/{demo.config['organization_id']}"
    device_id = getattr(demo.external_settings, "device_id", None)
    if device_id:
        return call("GET", base + "/model-config?device_id=" + str(device_id))
    raise RuntimeError(
        "Set HUMAN_DEVICE_ID in human-test/.env. Platform Admin must select models "
        "for that device using Devices > Configure model."
    )


def report_local_models(demo, installed):
    """A paired laptop advertises verified local installs with its device credential."""
    settings = demo.external_settings
    if not settings.device_token or not settings.device_id:
        return False
    body = {
        "device_id": str(settings.device_id),
        "llm": sorted({item["alias"] for item in installed["models"] if item["capability"] == "llm"}),
        "speech": sorted(
            {
                item["id"]
                for item in installed["models"]
                if item["capability"] == "asr" and item.get("platform_speech") is True
            }
        ),
    }
    with demo.http.stream(
        "POST",
        demo.pms_url + "/api/v1/device/local-models",
        json=body,
        headers={"Authorization": "Bearer " + settings.device_token.get_secret_value()},
        timeout=15,
    ) as response:
        data = bytearray()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data) > 4096:
                raise RuntimeError("Local model inventory acknowledgement is too large")
        try:
            acknowledgement = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            acknowledgement = None
        if response.status_code != 200:
            from human_test.connection import ERRORS

            error = acknowledgement.get("error") if isinstance(acknowledgement, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            messages = {
                **ERRORS,
                "local_host_required": (
                    "The platform still restricts model inventory to laptop registrations. "
                    "Update the platform API to support this device. Your enrollment is saved."
                ),
                "invalid_local_inventory": (
                    "The platform rejected the installed model names. Update the desktop and platform "
                    "to compatible versions. Your enrollment is saved."
                ),
                "device_mismatch": "The device credential belongs to a different registration. Reconnect this device.",
            }
            detail = messages.get(code) if isinstance(code, str) else None
            raise RuntimeError(
                detail
                or f"Local model inventory was not accepted (HTTP {response.status_code}). "
                "Check that the desktop and platform API are up to date."
            )
        if not isinstance(acknowledgement, dict) or acknowledgement.get("device_id") != str(
            settings.device_id
        ):
            raise RuntimeError("The device token belongs to a different device registration")
    return True


def platform_call(demo, method, path, body=None):
    """Bounded central API calls; never expose response bodies or inherit bearer headers."""
    with demo.http.stream(
        method,
        demo.pms_url + "/api/v1" + path,
        json=body,
        headers={"Authorization": "Bearer " + demo.token},
        timeout=15,
    ) as response:
        data = bytearray()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data) > 131072:
                raise RuntimeError("The central API returned an oversized configuration response")
        if response.status_code not in (200, 201):
            if demo.token.startswith("dev_"):
                from human_test.connection import ERRORS

                try:
                    code = json.loads(data).get("error", {}).get("code")
                except (ValueError, AttributeError, RecursionError):
                    code = None
                raise RuntimeError(
                    ERRORS.get(
                        code,
                        f"Device access failed (HTTP {response.status_code}). Check its status and assigned models in the platform; reconnect with a new enrollment token if access was revoked.",
                    )
                )
            if response.status_code in (401, 403):
                raise RuntimeError("Central API access denied; renew your login and check tenant permissions")
            raise RuntimeError(f"Central API request failed (HTTP {response.status_code})")
        try:
            value = json.loads(data)
        except (ValueError, RecursionError):
            raise RuntimeError("The central API returned invalid configuration") from None
        if not isinstance(value, dict):
            raise RuntimeError("The central API returned invalid configuration")
        return value


def check_running_profile(demo):
    """A stale desktop session must not silently satisfy a different profile request."""
    route = published_route(demo, lambda method, path: platform_call(demo, method, path))
    running = demo.route or {}
    if any(
        not route.get(key) or route.get(key) != running.get(key)
        for key in ("profile_id", "profile_revision_id", "configuration_hash")
    ):
        raise RuntimeError(
            "The running models differ from this device's assigned models. "
            "Reload Models in its window or close that window and start again."
        )


def session_binding(settings):
    # A changed login (including renewal) requires a new desktop: its old token is
    # immutable. Persist only a one-way binding, never a token in launcher status.
    material = [settings.pms_token.get_secret_value(), str(settings.department_id), str(settings.device_id)]
    return hashlib.sha256(json.dumps(material).encode()).hexdigest()
