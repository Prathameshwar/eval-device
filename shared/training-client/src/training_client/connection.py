"""Device pairing and private persistence; no user account or database access."""

import json
import os
import secrets
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from training_contracts.privacy import no_link, private_directory

DEFAULT_PLATFORM = "https://eval.centralindia.cloudapp.azure.com"


class ConnectionError(RuntimeError):
    def __init__(self, message, code="connection_failed"):
        super().__init__(message)
        self.code = code


def platform_origin(value):
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and (parsed.scheme == "https" or parsed.hostname in {"127.0.0.1", "::1"})
            and parsed.port not in {8766, 8769, 8787}
        )
    except ValueError:
        valid = False
    if not valid:
        raise ConnectionError("Enter the platform HTTPS address, without a page path.", "invalid_address")
    return value


def read_connection(path):
    if not path.exists():
        return None
    try:
        no_link(path.parent.parent)
        no_link(path.parent)
        no_link(path)
        if path.stat().st_size > 16384:
            raise ValueError()
        data = json.loads(path.read_text(encoding="utf-8"))
        if data == {"version": 1, "unpaired": True}:
            return None
        if (
            data.get("version") != 1
            or not data["credential"].startswith("dev_")
            or len(data["credential"]) > 512
        ):
            raise ValueError()
        if platform_origin(data["pms_url"]) != data["pms_url"]:
            raise ValueError()
        PairingClient.identity(data)
        return data
    except Exception:
        raise ConnectionError(
            "Saved connection cannot be read. Pair this desktop again.", "saved_connection_invalid"
        ) from None


def save_connection(data, path):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        for directory in (path.parent.parent, path.parent):
            if directory.exists():
                no_link(directory)
            directory.mkdir(exist_ok=True)
            private_directory(directory)
        if path.exists():
            no_link(path)
        with temporary.open("x", encoding="utf-8") as output:
            private_directory(temporary)
            json.dump(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        raise ConnectionError(
            "Could not save this device credential securely. Check folder permissions and pair again with a new token.",
            "save_failed",
        ) from None
    finally:
        temporary.unlink(missing_ok=True)


ERRORS = {
    "invalid_enrollment": "The device ID or enrollment token is incorrect or expired. Check the ID and issue a new token in Devices.",
    "invalid_device_credential": "Device access was revoked or replaced. Issue a new enrollment token and pair again.",
    "device_inactive": "This device, tenant or department is inactive. Ask the tenant administrator to activate it.",
    "device_not_enrolled": "The device is not enrolled. Issue a new enrollment token and pair again.",
    "maintenance_mode": "The platform is in maintenance mode. Wait and retry.",
    "model_profile_incomplete": "Pairing is saved. Assign a conversation model in Devices > Configure model, then retry.",
    "model_selection_required": "Pairing is saved. Configure this device's models in the platform, then retry.",
    "llm_connection_inactive": "The assigned conversation model is inactive. Update Configure model, then retry.",
    "permission_denied": "This device cannot use the requested feature. Check its tenant configuration.",
    "rate_limit_exceeded": "Too many connection attempts. Wait a minute and retry.",
}


class PairingClient:
    def __init__(self, origin, *, path, transport=None):
        self.origin = platform_origin(origin)
        self.path = path
        self.http = httpx.Client(
            base_url=self.origin,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(15, connect=5),
            transport=transport,
        )

    def close(self):
        self.http.close()

    def request(self, method, path, *, credential=None, body=None):
        if getattr(self, "cancelled", lambda: False)():
            raise ConnectionError("Connection cancelled. No further request was sent.", "cancelled")
        try:
            with self.http.stream(
                method,
                path,
                json=body,
                headers={"Authorization": "Bearer " + credential} if credential else {},
            ) as response:
                data = bytearray()
                for part in response.iter_bytes():
                    data.extend(part)
                    if len(data) > 131072:
                        raise ConnectionError("The platform returned an invalid response.")
                try:
                    value = json.loads(data)
                except (ValueError, RecursionError):
                    value = {}
                if response.status_code != 200:
                    error = value.get("error", {}) if isinstance(value, dict) else {}
                    code = (
                        error.get("code", "request_rejected")
                        if isinstance(error, dict)
                        else "request_rejected"
                    )
                    if not isinstance(code, str):
                        code = "request_rejected"
                    if response.status_code == 404 and path == "/api/v1/health/ready":
                        raise ConnectionError(
                            "This platform needs the desktop pairing API update. Update the API, then retry.",
                            "api_update_required",
                        )
                    raise ConnectionError(
                        ERRORS.get(
                            code,
                            f"Platform rejected the request (HTTP {response.status_code}). Check device status and try again.",
                        ),
                        code if code in ERRORS else "request_rejected",
                    )
                if not isinstance(value, dict):
                    raise ConnectionError("The platform returned an invalid response.")
                return value
        except httpx.HTTPError:
            raise ConnectionError(
                "Cannot reach the platform securely. Check the address, internet connection and certificate, then retry.",
                "network_failed",
            ) from None

    def check(self):
        data = self.request("GET", "/api/v1/health/ready")
        if data.get("service") != "pms_api" or data.get("status") != "ready":
            raise ConnectionError("This address is not a ready platform API. Check the platform address.")

    @staticmethod
    def identity(value):
        try:
            for key, limit in (("device_unique_id", 50), ("device_name", 256), ("organization_name", 256)):
                if not isinstance(value[key], str) or not 1 <= len(value[key]) <= limit:
                    raise ValueError()
            return {
                "device_id": str(UUID(value["device_id"])),
                "organization_id": str(UUID(value["organization_id"])),
                "department_id": str(UUID(value["department_id"])) if value.get("department_id") else None,
                "device_unique_id": str(value["device_unique_id"])[:50],
                "device_name": str(value["device_name"])[:256],
                "organization_name": str(value["organization_name"])[:256],
            }
        except (ValueError, KeyError, TypeError):
            raise ConnectionError(
                "The platform returned an incomplete device identity. Update the API and retry."
            ) from None

    def pair(self, identifier, token, progress=lambda text: None):
        identifier, token = identifier.strip(), token.strip()
        if not 1 <= len(identifier) <= 50 or any(ord(c) < 32 or ord(c) == 127 for c in identifier):
            raise ConnectionError("Enter the device unique ID or registration UUID (maximum 50 characters).")
        if not token.startswith("enr_") or not 20 <= len(token) <= 256:
            raise ConnectionError("Paste the enrollment token issued in the tenant Devices page.")
        progress("Checking the platform connection…")
        self.check()
        progress("Enrolling this device…")
        try:
            value = self.request(
                "POST", "/api/v1/device/enroll", body={"device_identifier": identifier, "token": token}
            )
        except ConnectionError as error:
            if error.code == "network_failed":
                raise ConnectionError(
                    "The enrollment response was lost. Check the device in the platform and issue a new enrollment token before trying again. No automatic retry was made.",
                    "enrollment_uncertain",
                ) from None
            raise
        data = self.identity(value)
        if identifier.lower() not in {data["device_id"].lower(), data["device_unique_id"].lower()}:
            raise ConnectionError("The platform returned a different device. Pairing was not saved.")
        credential = value.get("credential")
        if not isinstance(credential, str) or not credential.startswith("dev_") or len(credential) > 512:
            raise ConnectionError(
                "Enrollment did not return a usable device credential. Issue a new token and retry."
            )
        data.update(version=1, pms_url=self.origin, credential=credential)
        progress("Saving the private device connection…")
        save_connection(data, self.path)
        return data

    def resume(self, saved, progress=lambda text: None):
        if saved["pms_url"] != self.origin:
            raise ConnectionError("Saved credentials belong to a different platform. Pair again.")
        progress("Checking the platform connection…")
        self.check()
        progress("Verifying device access…")
        identity = self.identity(
            self.request("GET", "/api/v1/device/identity", credential=saved["credential"])
        )
        if any(identity[key] != saved[key] for key in ("device_id", "organization_id")):
            raise ConnectionError("Device registration changed. Pair this desktop again.")
        data = {**saved, **identity}
        if data != saved:
            save_connection(data, self.path)
        return data


def connection_values(data):
    return {
        "pms_url": data["pms_url"],
        "pms_token": data["credential"],
        "device_token": data["credential"],
        "device_id": data["device_id"],
        "organization_id": data["organization_id"],
        "department_id": data.get("department_id"),
    }
