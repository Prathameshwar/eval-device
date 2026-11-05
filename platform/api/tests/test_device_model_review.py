"""Device model configuration isolation, lifecycle and optional speech regressions."""

from uuid import uuid4

import pytest
from test_direct_models import local_model, setup


def assign(p, admin, device, models, version=0, mode="local"):
    return p.call(
        "PUT",
        f"/platform/devices/{device}/models",
        admin,
        json={
            "mode": mode,
            "expected_version": version,
            **{row["kind"] + "_model_id": row["id"] for row in models},
            "model_revisions": {row["id"]: row["revision"] for row in models},
        },
    )


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("kind", ["llm", "asr", "tts", "video"])
def test_fleet_model_status_counts_any_selection_and_cleared_configuration(platform, mode, kind):
    p = platform
    tenant, admin, org = setup(p)
    device = p.device(tenant, org)
    other = p.device(tenant, org, is_active=False)
    path = f"/platform/devices/{device['id']}"

    def statuses():
        return {
            row["id"]: row["models_configured"] for row in p.call("GET", "/platform/devices", admin)["items"]
        }

    assert statuses() == {device["id"]: False, other["id"]: False}
    assert p.call("GET", path, admin)["models_configured"] is False
    # The flag is platform summary metadata, not tenant configuration disclosure.
    assert "models_configured" not in p.call("GET", f"/organizations/{org}/devices/{device['id']}", tenant)
    # Use a catalog fixture for each kind/location without contacting any provider.
    if mode == "local" and kind != "video":
        model = next(
            row for row in p.call("GET", "/platform/runtime-models", admin)["items"] if row["kind"] == kind
        )
    else:
        draft = (
            {
                **local_model("Fleet status"),
                "kind": "video",
                "engine": "opencv_motion",
                "model_key": "opencv_motion",
            }
            if mode == "local"
            else {
                "name": "Fleet status",
                "kind": kind,
                "location": "cloud",
                "provider": "openai" if kind == "llm" else "aws",
                "engine": {
                    "llm": "llm",
                    "asr": "aws_transcribe",
                    "tts": "aws_polly",
                    "video": "aws_rekognition",
                }[kind],
                "model_key": "test-model"
                if kind == "llm"
                else {"asr": "transcribe", "tts": "Joanna", "video": "rekognition"}[kind],
                "settings": {"base_url": "https://api.openai.com/v1"}
                if kind == "llm"
                else {
                    "region": "us-east-1",
                    "auth_mode": "access_key",
                    **({"staging_bucket": "private-test-bucket"} if kind != "tts" else {}),
                },
                "credentials": {"api_key": "mock-cloud-key"}
                if kind == "llm"
                else {"access_key_id": "mock-access-key", "secret_access_key": "mock-secret-key"},
            }
        )
        p.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
        model = p.call("POST", "/platform/runtime-models", admin, expected=201, json=draft)
    assign(p, admin, device["id"], [model], mode=mode)
    assert statuses() == {device["id"]: True, other["id"]: False}
    assert p.call("GET", path, admin)["models_configured"] is True
    assign(p, admin, device["id"], [], version=1, mode=mode)
    assert statuses() == {device["id"]: False, other["id"]: False}


def test_clearing_models_is_device_specific_and_invalidates_old_execution(platform):
    p = platform
    tenant, _ = p.user("device-isolation-tenant")
    admin, _ = p.admin()
    org = p.organization(tenant, plan="advanced")["id"]
    first = p.device(tenant, org)
    second = p.device(tenant, org)
    credential = p.enroll(tenant, org, first["id"])
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    video = p.call(
        "POST",
        "/platform/runtime-models",
        admin,
        expected=201,
        json={
            "name": "Local video",
            "kind": "video",
            "location": "local",
            "provider": "local",
            "engine": "opencv_motion",
            "model_key": "opencv_motion",
        },
    )
    models.append(video)
    assign(p, admin, first["id"], models)
    assign(p, admin, second["id"], models)
    before = p.call("GET", "/device/config", credential)
    second_path = f"/organizations/{org}/devices/{second['id']}/configuration"
    other_config = p.call("GET", second_path, tenant)
    p.call(
        "POST",
        "/device/heartbeat",
        credential,
        json={
            "boot_id": str(uuid4()),
            "sequence_number": 0,
            "applied_profile_revision_id": before["profile_revision_id"],
            "applied_configuration_hash": before["configuration_hash"],
        },
    )
    run = {
        "request_key": str(uuid4()),
        "operation": "audio.synthesize",
        "profile_revision_id": before["profile_revision_id"],
        "text": "Fixture",
    }
    selected = assign(p, admin, first["id"], [], version=1)
    assert all(selected[kind + "_model_id"] is None for kind in ("llm", "asr", "tts", "video"))
    after = p.call("GET", "/device/config", credential)
    assert after["configuration_hash"] != before["configuration_hash"]
    assert not any(
        after["settings"][section]["enabled"]
        for section in ("conversation", "audio_input", "audio_output", "video")
    )
    assert after["connections"] == {}
    p.call("POST", "/device/runs", credential, expected=409, json=run)
    result = p.call(
        "POST",
        f"/organizations/{org}/runs",
        tenant,
        expected=409,
        json={**run, "device_id": first["id"], "profile_revision_id": after["profile_revision_id"]},
    )
    assert result["error"]["code"] == "operation_disabled"
    assert p.call("GET", second_path, tenant) == other_config


def test_configuration_dialog_and_save_share_lifecycle_guards(platform):
    p = platform
    tenant, admin, org = setup(p)
    department = p.call(
        "POST", f"/organizations/{org}/departments", tenant, expected=201, json={"name": "Lab"}
    )
    device = p.device(tenant, org, department_id=department["id"])
    path = f"/platform/devices/{device['id']}/models"
    assert p.call("GET", path, admin)["configuration_allowed"]
    cases = [
        (
            "UPDATE device_platform.organizations SET is_active=false,suspension_source='platform' WHERE id=%s",
            org,
            "organization_inactive",
            "tenant",
            "UPDATE device_platform.organizations SET is_active=true,suspension_source=NULL WHERE id=%s",
        ),
        (
            "UPDATE device_platform.departments SET is_active=false WHERE id=%s",
            department["id"],
            "department_inactive",
            "department",
            "UPDATE device_platform.departments SET is_active=true WHERE id=%s",
        ),
        (
            "UPDATE device_platform.devices SET is_active=false WHERE id=%s",
            device["id"],
            "device_inactive",
            "device",
            "UPDATE device_platform.devices SET is_active=true WHERE id=%s",
        ),
    ]
    for update, ident, code, reason, restore in cases:
        p.sql(update, (ident,))
        choices = p.call("GET", path, admin)
        assert choices["configuration_allowed"] is False and reason in choices["configuration_blocked_reason"]
        blocked = p.call("PUT", path, admin, expected=409, json={"mode": "local", "expected_version": 0})
        assert blocked["error"]["code"] == code
        assert choices["selection"]["version"] == 0
        p.sql(restore, (ident,))
    assert p.call("GET", path, admin)["configuration_allowed"]


def test_disabling_optional_cloud_speech_does_not_break_conversation_configuration(platform):
    p = platform
    tenant, admin, org = setup(p)
    device = p.device(tenant, org)
    p.enroll(tenant, org, device["id"])
    p.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
    llm = p.call(
        "POST",
        "/platform/runtime-models",
        admin,
        expected=201,
        json={
            "name": "Conversation",
            "kind": "llm",
            "location": "cloud",
            "provider": "openai",
            "engine": "llm",
            "model_key": "fixture",
            "settings": {"base_url": "https://api.openai.com/v1"},
            "credentials": {"api_key": "fixture-key"},
        },
    )
    body = {
        "name": "Speech",
        "kind": "asr",
        "location": "cloud",
        "provider": "azure",
        "engine": "azure_speech",
        "model_key": "azure_speech",
        "settings": {"region": "centralindia", "auth_mode": "api_key"},
        "credentials": {"api_key": "fixture-key"},
    }
    speech = p.call("POST", "/platform/runtime-models", admin, expected=201, json=body)
    assign(p, admin, device["id"], [llm, speech], mode="cloud")
    route = f"/organizations/{org}/model-config?device_id={device['id']}"
    before = p.call("GET", route, tenant)
    assert before["audio"]["enabled"]
    p.call(
        "PUT",
        "/platform/runtime-models/" + speech["id"],
        admin,
        json={**body, "expected_revision": 1, "is_active": False},
    )
    after = p.call("GET", route, tenant)
    assert not after["audio"]["enabled"] and after["audio"]["connection_id"] is None
    assert after["audio"]["mode"] == "cloud" and after["audio"]["provider"] == "azure"
    assert after["llm"]["connection_id"] == llm["id"]
    assert after["configuration_hash"] != before["configuration_hash"]
    p.settings.speech_enabled = True
    blocked = p.call(
        "GET", f"/organizations/{org}/speech/status?profile_id={device['id']}", tenant, expected=409
    )
    assert blocked["error"]["code"] == "interactive_speech_unavailable"
    p.call(
        "PUT",
        "/platform/runtime-models/" + speech["id"],
        admin,
        json={**body, "expected_revision": 2, "is_active": True},
    )
    assert p.call("GET", route, tenant)["audio"]["enabled"]


def test_transfer_keeps_identity_but_never_copies_model_assignments(platform):
    p = platform
    tenant, admin, org = setup(p)
    device = p.device(tenant, org)
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    assign(p, admin, device["id"], models)
    target_org = p.organization(tenant, "Transfer target")["id"]
    current = p.call("GET", f"/platform/devices/{device['id']}", admin)
    transferred = p.call(
        "POST",
        f"/platform/devices/{device['id']}/transfer",
        admin,
        json={
            "expected_etag": current["management_etag"],
            "organization_id": target_org,
            "name": device["name"],
            "is_active": True,
        },
    )
    target = transferred["device"]
    assert target["device_unique_id"] == device["device_unique_id"]
    choices = p.call("GET", f"/platform/devices/{target['id']}/models", admin)
    assert choices["selection"]["version"] == 0
    assert all(choices["selection"][kind + "_model_id"] is None for kind in ("llm", "asr", "tts", "video"))
    source = p.call("GET", f"/platform/devices/{device['id']}/models", admin)
    assert not source["configuration_allowed"] and "retired" in source["configuration_blocked_reason"]
