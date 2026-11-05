import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from training_contracts.inference import Binding, GrantRequest

from pms_api.core.common import AppError
from pms_api.modules.devices import validate_details
from pms_api.modules.inference import allow_operation, binding_for


def test_device_binding_validation_does_not_allow_credentials_or_unknown_fields():
    value = {
        "inference": {
            "host_id": str(uuid4()),
            "origin": "https://gpu.example:8791/",
            "tts_voices": ["en_US-test-medium"],
        }
    }
    validate_details(value)
    assert binding_for(SimpleNamespace(details=value)).origin == "https://gpu.example:8791"
    for origin in ("http://gpu", "https://user:secret@gpu", "https://gpu/path", "https://gpu?token=secret"):
        with pytest.raises(AppError):
            validate_details({"inference": {**value["inference"], "origin": origin}})
    with pytest.raises(AppError):
        validate_details({"inference": {**value["inference"], "api_key": "secret"}})
    with pytest.raises(AppError):
        binding_for(SimpleNamespace(details={"inference": None}))


@pytest.mark.parametrize(
    "path,model,voice,accepted",
    [
        ("/v1/infer/llm", "assigned", None, True),
        ("/v1/infer/llm", "other", None, False),
        ("/v1/infer/asr", "large-v3", None, True),
        ("/v1/infer/tts", None, "en_voice", True),
        ("/v1/infer/tts", None, "unassigned", False),
    ],
)
def test_grant_operations_match_assigned_routes(path, model, voice, accepted):
    target = Binding(host_id=uuid4(), origin="https://gpu", tts_voices=["en_voice"])
    body = GrantRequest(
        host_id=target.host_id,
        origin=target.origin,
        request_id=uuid4(),
        method="POST",
        path=path,
        body_sha256=hashlib.sha256(b"{}").hexdigest(),
        model=model,
        voice=voice,
    )
    route = {
        "llm": {"mode": "local", "model": "assigned"},
        "audio": {"enabled": True, "mode": "local", "model": "large-v3"},
        "platform_media": {"audio_output": {"settings": {"enabled": True, "mode": "local"}}},
    }
    if accepted:
        allow_operation(body, target, route)
    else:
        with pytest.raises(AppError):
            allow_operation(body, target, route)


def test_device_grants_require_enrollment_scope_and_bound_host(platform, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    h = platform
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "training.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    h.settings.training_key_file = key_path
    token, _ = h.user("pi-owner")
    org = h.organization(token)["id"]
    device = h.device(token, org)
    credential = h.enroll(token, org, device["id"])
    target = {"host_id": str(uuid4()), "origin": "https://gpu.example:8791", "tts_voices": []}
    device_path = f"/organizations/{org}/devices/{device['id']}"
    current = h.call("GET", device_path, token)
    h.call(
        "PATCH",
        device_path,
        token,
        json={"expected_etag": current["management_etag"], "details": {"inference": target}},
    )
    assert h.call("GET", "/device/inference", credential)["host_id"] == target["host_id"]
    h.call("GET", "/device/inference", token, expected=403)
    body = {
        **{k: target[k] for k in ("host_id", "origin")},
        "request_id": str(uuid4()),
        "method": "GET",
        "path": "/v1/capabilities",
        "body_sha256": hashlib.sha256(b"").hexdigest(),
    }
    h.call(
        "POST", "/device/inference/grants", credential, json={**body, "host_id": str(uuid4())}, expected=403
    )
    h.call(
        "POST",
        "/device/inference/grants",
        credential,
        json={**body, "path": "/v1/actions/start"},
        expected=422,
    )
    current = h.call("GET", device_path, token)
    h.call(
        "PATCH", device_path, token, json={"expected_etag": current["management_etag"], "is_active": False}
    )
    h.call("GET", "/device/inference", credential, expected=409)
