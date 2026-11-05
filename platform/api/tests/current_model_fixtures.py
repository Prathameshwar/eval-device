"""Processing fixtures using the public direct-model API, with no cloud calls."""

from uuid import uuid4


def cloud_model_body():
    return {
        "name": "Review cloud voice",
        "kind": "tts",
        "location": "cloud",
        "provider": "azure",
        "engine": "azure_speech",
        "model_key": "azure_speech",
        "settings": {"region": "centralindia", "auth_mode": "api_key"},
        "defaults": {"format": "wav"},
        "credentials": {"api_key": "mocked-key"},
    }


def assign_model(p, token, org, device, model, mode="local"):
    path = f"/platform/devices/{device}/models"
    current = p.call("GET", path, token)["selection"]
    p.call(
        "PUT",
        path,
        token,
        json={
            "mode": mode,
            "expected_version": current["version"],
            model["kind"] + "_model_id": model["id"],
            "model_revisions": {model["id"]: model["revision"]},
        },
    )
    config = p.call("GET", f"/organizations/{org}/devices/{device}/configuration", token)
    return {"id": config["profile_revision_id"]}


def local_revision(p, token, org, device, credential):
    model = next(
        row
        for row in p.call("GET", "/platform/runtime-models", token)["items"]
        if row["kind"] == "asr" and row["location"] == "local"
    )
    p.call(
        "POST",
        "/device/heartbeat",
        credential,
        json={
            "boot_id": str(uuid4()),
            "sequence_number": 0,
            "capabilities": {"engines": [model["engine"]]},
        },
    )
    return assign_model(p, token, org, device, model)


def cloud_run(p, monkeypatch, adapter):
    monkeypatch.setattr(
        "pms_api.integrations.providers.ProviderFactory.for_connection", lambda self, row: adapter
    )
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    did = p.device(token, oid)["id"]
    credential = p.enroll(token, oid, did)
    options = p.call("GET", "/platform/settings", token)
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        json={
            "expected_version": options["configuration_version"],
            "enabled_providers": ["azure"],
        },
    )
    model = p.call("POST", "/platform/runtime-models", token, expected=201, json=cloud_model_body())
    p.review_cloud_model = model
    revision = assign_model(p, token, oid, did, model, "cloud")
    run = p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=202,
        json={
            "device_id": did,
            "request_key": str(uuid4()),
            "operation": "audio.synthesize",
            "profile_revision_id": revision["id"],
            "text": "Hello",
        },
    )
    return token, oid, did, credential, run["run"]["id"]
