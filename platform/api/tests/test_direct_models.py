"""The simple model/device contract, including scope and stale writes."""

import pytest


@pytest.mark.parametrize("device_type", ["manikin", "laptop"])
def test_local_models_can_be_assigned_before_runtime_is_reported(platform, device_type):
    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org, device_type=device_type)
    if device_type == "laptop":
        h.enroll(tenant, org, device["id"])
        h.sql(
            "UPDATE device_platform.devices SET capabilities=jsonb_build_object("
            "'local_models',jsonb_build_object('llm','[]'::jsonb,'speech','[]'::jsonb),"
            "'local_models_source','device_report_v1','local_models_received_at',now()-interval '2 days') "
            "WHERE id=%s",
            (device["id"],),
        )
    path = f"/platform/devices/{device['id']}/models"
    choices = h.call("GET", path, admin)["models"]
    assert {row["name"] for row in choices} == {"Whisper large-v3", "qwen3.5-4b-local", "eSpeak NG"}
    assert all(row["available"] and row["location"] == "local" for row in choices)
    draft = {
        "mode": "local",
        "expected_version": 0,
        **{row["kind"] + "_model_id": row["id"] for row in choices},
        "model_revisions": {row["id"]: row["revision"] for row in choices},
    }
    h.call("GET", path, tenant, expected=403)
    h.call("PUT", path, tenant, json=draft, expected=403)
    selected = h.call("PUT", path, admin, json=draft)
    assert selected["version"] == 1 and selected["video_model_id"] is None
    assert all(selected[row["kind"] + "_model_id"] == row["id"] for row in choices)
    assert h.call("GET", path, admin)["selection"] == selected
    # Configuration does not bypass the enrollment required to execute a model.
    h.call(
        "GET",
        f"/organizations/{org}/model-config?device_id={device['id']}",
        tenant,
        expected=409 if device_type == "manikin" else 200,
    )
    inactive = h.call(
        "POST",
        "/platform/runtime-models",
        admin,
        json={**local_model("Inactive voice"), "is_active": False},
        expected=201,
    )
    assert not next(row for row in h.call("GET", path, admin)["models"] if row["id"] == inactive["id"])[
        "available"
    ]
    h.call(
        "PUT",
        path,
        admin,
        json={**draft, "expected_version": 1, "tts_model_id": inactive["id"]},
        expected=422,
    )


def test_configured_cloud_models_are_selectable_for_each_type_on_pending_manikin(platform):
    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org, device_type="manikin")
    h.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
    assert not h.settings.external_calls_enabled
    drafts = [
        {
            "name": "Configured cloud conversation",
            "kind": "llm",
            "location": "cloud",
            "provider": "openai",
            "engine": "llm",
            "model_key": "test-cloud-model",
            "settings": {"base_url": "https://api.openai.com/v1"},
            "credentials": {"api_key": "mock-cloud-key"},
        }
    ]
    for kind, engine in (("asr", "aws_transcribe"), ("tts", "aws_polly"), ("video", "aws_rekognition")):
        drafts.append(
            {
                "name": f"Configured cloud {kind}",
                "kind": kind,
                "location": "cloud",
                "provider": "aws",
                "engine": engine,
                "model_key": engine,
                "settings": {
                    "region": "ap-south-1",
                    "auth_mode": "access_key",
                    **({"staging_bucket": "private-test-bucket"} if kind != "tts" else {}),
                },
                "credentials": {"access_key_id": "mock-id", "secret_access_key": "mock-secret"},
            }
        )
    models = [h.call("POST", "/platform/runtime-models", admin, json=draft, expected=201) for draft in drafts]
    path = f"/platform/devices/{device['id']}/models"
    choices = h.call("GET", path, admin)["models"]
    cloud = [row for row in choices if row["location"] == "cloud"]
    assert {row["id"] for row in cloud} == {row["id"] for row in models}
    assert all(row["available"] for row in cloud)
    assert "mock-secret" not in str(choices) and "mock-cloud-key" not in str(choices)
    selected = h.call(
        "PUT",
        path,
        admin,
        json={
            "mode": "cloud",
            "expected_version": 0,
            **{row["kind"] + "_model_id": row["id"] for row in models},
            "model_revisions": {row["id"]: row["revision"] for row in models},
        },
    )
    assert all(selected[row["kind"] + "_model_id"] == row["id"] for row in models)
    assert h.call("GET", path, admin)["selection"] == selected
    h.call(
        "PUT",
        f"/platform/runtime-models/{models[0]['id']}",
        admin,
        json={
            **drafts[0],
            "expected_revision": models[0]["revision"],
            "is_active": False,
        },
    )
    choices = h.call("GET", path, admin)["models"]
    assert not next(row for row in choices if row["id"] == models[0]["id"])["available"]


def setup(h):
    tenant, _ = h.user("direct-tenant")
    org = h.organization(tenant)["id"]
    admin, _ = h.admin("direct-admin")
    return tenant, admin, org


def local_model(name="Local voice"):
    return {
        "name": name,
        "kind": "tts",
        "location": "local",
        "provider": "local",
        "engine": "espeak_ng",
        "model_key": "espeak_ng",
    }


def test_direct_model_crud_and_secrets(platform):
    h = platform
    tenant, admin, _ = setup(h)
    path = "/platform/runtime-models"
    h.call("POST", path, tenant, json=local_model(), expected=403)
    row = h.call("POST", path, admin, json=local_model(), expected=201)
    assert row["kind"] == "tts" and not row["has_credentials"]
    h.call("POST", path, admin, json={**local_model(), "settings": {"api_key": "invalid"}}, expected=422)
    for defaults in ({"language": "invalid language"}, {"format": "exe"}, {"voice": ""}):
        h.call("POST", path, admin, json={**local_model(), "defaults": defaults}, expected=422)
    changed = h.call(
        "PUT",
        path + "/" + row["id"],
        admin,
        json={**local_model("Renamed"), "expected_revision": row["revision"]},
    )
    assert changed["revision"] == 2
    h.call("PUT", path + "/" + row["id"], admin, json={**local_model(), "expected_revision": 1}, expected=409)
    h.call("DELETE", path + "/" + row["id"] + "?expected_revision=2", admin)
    rows = h.call("GET", path, admin)["items"]
    assert row["id"] not in [r["id"] for r in rows]


def test_device_direct_selection_runtime_and_stale_edits(platform):
    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org)
    credential = h.enroll(tenant, org, device["id"])
    row = h.call("POST", "/platform/runtime-models", admin, json=local_model(), expected=201)
    path = f"/platform/devices/{device['id']}/models"
    choices = h.call("GET", path, admin)
    assert choices["selection"]["version"] == 0
    draft = {
        "mode": "local",
        "expected_version": 0,
        "tts_model_id": row["id"],
        "model_revisions": {row["id"]: row["revision"]},
    }
    h.call("PUT", path, tenant, json=draft, expected=403)
    saved = h.call("PUT", path, admin, json=draft)
    assert saved["version"] == 1 and saved["tts_model_id"] == row["id"]
    h.call("PUT", path, admin, json=draft, expected=409)
    assert h.sql("SELECT count(*) FROM device_platform.processing_profiles")[0][0] == 0
    assert h.sql("SELECT count(*) FROM device_platform.provider_connections")[0][0] == 0
    config = h.call("GET", "/device/config", credential)
    assert config["settings"]["audio_output"]["engine"] == "espeak_ng"
    h.call("DELETE", f"/platform/runtime-models/{row['id']}?expected_revision=1", admin, expected=409)
    h.call(
        "PUT",
        f"/platform/runtime-models/{row['id']}",
        admin,
        json={**local_model(), "expected_revision": 1, "is_active": False},
    )
    config = h.call("GET", "/device/config", credential)
    assert config["settings"]["audio_output"]["enabled"] is False
    assert h.call("GET", path, admin)["selection"]["version"] == 2
    h.call("PUT", path, admin, json={"mode": "cloud", "expected_version": 2})
    h.call("DELETE", f"/platform/runtime-models/{row['id']}?expected_revision=2", admin)


def test_cloud_model_encryption_scope_and_direct_llm_route(platform):
    from uuid import UUID

    from pms_api.database.models import RuntimeModel
    from pms_api.integrations.vault import CredentialVault

    h = platform
    tenant, admin, org = setup(h)
    h.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
    device = h.device(tenant, org)
    h.enroll(tenant, org, device["id"])
    payload = {
        "name": "Cloud LLM",
        "kind": "llm",
        "location": "cloud",
        "provider": "openai",
        "engine": "llm",
        "model_key": "test-model",
        "settings": {"base_url": "https://api.openai.com/v1"},
        "credentials": {"api_key": "mock-secret"},
    }
    h.call(
        "POST",
        "/platform/runtime-models",
        admin,
        json={**payload, "settings": {"base_url": 123}},
        expected=422,
    )
    row = h.call("POST", "/platform/runtime-models", admin, json=payload, expected=201)
    assert row["has_credentials"] and "mock-secret" not in str(row)
    encrypted, key_id = h.sql(
        "SELECT encrypted_credentials,credential_key_id FROM device_platform.runtime_models WHERE id=%s",
        (row["id"],),
    )[0]
    assert b"mock-secret" not in encrypted
    model = RuntimeModel(
        id=UUID(row["id"]),
        organization_id=None,
        credential_owner_org=UUID(int=0),
        credential_owner_id=UUID(row["id"]),
        encrypted_credentials=encrypted,
        credential_key_id=key_id,
    )
    assert CredentialVault(h.settings).decrypt(model) == {"api_key": "mock-secret"}
    path = f"/platform/devices/{device['id']}/models"
    h.call(
        "PUT",
        path,
        admin,
        json={
            "mode": "cloud",
            "expected_version": 0,
            "llm_model_id": row["id"],
            "model_revisions": {row["id"]: 1},
        },
    )
    route = h.call("GET", f"/organizations/{org}/model-config?device_id={device['id']}", tenant)
    assert route["llm"]["connection_id"] == row["id"]
    assert route["llm"]["execution"] == "platform"
    assert not route["audio"]["enabled"]
    assert h.sql("SELECT count(*) FROM device_platform.llm_connections")[0][0] == 0
    h.call("GET", f"/organizations/{org}/model-config?device_id={device['id']}", admin, expected=404)
    from uuid import uuid4

    from test_llm_api import Model

    h.settings.llm_enabled = h.settings.external_calls_enabled = True
    mock = Model()
    h.client.app.state.llm = mock
    request = {
        "request_key": str(uuid4()),
        "connection_id": row["id"],
        "stream": False,
        "messages": [{"role": "user", "content": "Hello"}],
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    # Policy changes participate in the hash; fetch the current route.
    route = h.call("GET", f"/organizations/{org}/model-config?device_id={device['id']}", tenant)
    request["configuration_hash"] = route["configuration_hash"]
    response = h.call("POST", f"/organizations/{org}/llm/completions", tenant, json=request)
    assert response["text"] == "hello"
    assert h.call("POST", f"/organizations/{org}/llm/completions", tenant, json=request)["cached"]
    assert mock.calls == 1
    h.call(
        "POST",
        f"/organizations/{org}/llm/completions",
        tenant,
        json={
            **request,
            "request_key": str(uuid4()),
            "profile_revision_id": None,
            "configuration_hash": None,
        },
        expected=409,
    )
    from test_patient_conversations import start_conversation
    from test_patient_practice import setup as practice_setup

    _, _, practice = practice_setup(h, tenant, org)
    _, _, started = start_conversation(
        h,
        tenant,
        org,
        row,
        practice,
        profile_revision_id=route["profile_revision_id"],
        configuration_hash=route["configuration_hash"],
    )
    assert started["context"]["connection_id"] == row["id"]


def test_direct_media_run_uses_model_credentials_and_worker_scope(platform):
    import asyncio
    from uuid import uuid4

    from test_worker import Adapter

    from pms_api.database.session import engine_for, sessions_for
    from pms_api.integrations.vault import CredentialVault
    from pms_api.worker.service import Worker

    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org)
    credential = h.enroll(tenant, org, device["id"])
    options = h.call("GET", "/platform/settings", admin)
    h.call(
        "PATCH",
        "/platform/settings",
        admin,
        json={"expected_version": options["configuration_version"], "enabled_providers": ["aws"]},
    )
    model = h.call(
        "POST",
        "/platform/runtime-models",
        admin,
        expected=201,
        json={
            "name": "Cloud voice",
            "kind": "tts",
            "location": "cloud",
            "provider": "aws",
            "engine": "aws_polly",
            "model_key": "aws_polly",
            "settings": {"region": "ap-south-1", "auth_mode": "access_key"},
            "credentials": {"access_key_id": "mock-id", "secret_access_key": "mock-key"},
        },
    )
    h.call(
        "PUT",
        f"/platform/devices/{device['id']}/models",
        admin,
        json={
            "mode": "cloud",
            "expected_version": 0,
            "tts_model_id": model["id"],
            "model_revisions": {model["id"]: 1},
        },
    )
    config = h.call("GET", "/device/config", credential)
    run = h.call(
        "POST",
        f"/organizations/{org}/runs",
        tenant,
        expected=202,
        json={
            "device_id": device["id"],
            "request_key": str(uuid4()),
            "operation": "audio.synthesize",
            "profile_revision_id": config["profile_revision_id"],
            "text": "Hello",
        },
    )
    adapter = Adapter()

    class Factory:
        def for_connection(self, connection):
            assert CredentialVault(h.settings).decrypt(connection) == {
                "access_key_id": "mock-id",
                "secret_access_key": "mock-key",
            }
            return adapter

    async def execute():
        engine = engine_for(h.settings, "worker")
        try:
            worker = Worker(h.settings, sessions_for(engine), factory=Factory())
            await worker.tick()
        finally:
            await engine.dispose()

    asyncio.run(execute())
    assert adapter.submissions == 1
    assert (
        h.sql("SELECT status FROM device_platform.processing_runs WHERE id=%s", (run["run"]["id"],))[0][0]
        == "succeeded"
    )


def test_selection_scope_constraints_availability_and_concurrent_saves(platform):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    import psycopg
    import pytest
    from sqlalchemy.engine import make_url

    h = platform
    tenant, admin, org = setup(h)
    other, _ = h.user("other-model-tenant")
    other_org = h.organization(other)["id"]
    device = h.device(tenant, org)
    h.enroll(tenant, org, device["id"])
    model = h.call("POST", "/platform/runtime-models", admin, json=local_model(), expected=201)
    private_id = str(uuid4())
    h.sql(
        "INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,model_key) VALUES(%s,%s,'Private','tts','local','local','espeak_ng','espeak_ng')",
        (private_id, other_org),
    )
    path = f"/platform/devices/{device['id']}/models"
    choices = h.call("GET", path, admin)["models"]
    assert private_id not in [m["id"] for m in choices]
    draft = {
        "mode": "local",
        "expected_version": 0,
        "tts_model_id": model["id"],
        "model_revisions": {model["id"]: 1},
    }
    h.call("PUT", path, admin, json={**draft, "tts_model_id": private_id}, expected=404)
    h.call("PUT", path, admin, json={**draft, "mode": "cloud"}, expected=422)
    h.call("PUT", path, admin, json={**draft, "asr_model_id": model["id"]}, expected=422)
    local_llm = next(m for m in choices if m["kind"] == "llm" and m["location"] == "local")
    h.call(
        "PUT",
        path,
        admin,
        json={
            **draft,
            "llm_model_id": local_llm["id"],
            "model_revisions": {**draft["model_revisions"], local_llm["id"]: local_llm["revision"] + 1},
        },
        expected=409,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: h.client.put("/api/v1" + path, headers=h.headers(admin), json=draft).status_code,
                range(2),
            )
        )
    assert sorted(results) == [200, 409]
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "UPDATE device_platform.device_model_selections SET tts_model_id=%s WHERE device_id=%s",
            (private_id, device["id"]),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("UPDATE device_platform.runtime_models SET organization_id=%s WHERE id=%s", (org, private_id))
    worker_dsn = (
        make_url(h.settings.worker_database_url.get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(worker_dsn) as worker:
        assert (
            worker.execute("SELECT count(*) FROM device_platform.runtime_models WHERE kind='llm'").fetchone()[
                0
            ]
            == 0
        )
        assert (
            worker.execute(
                "SELECT count(*) FROM device_platform.runtime_models WHERE id=%s", (model["id"],)
            ).fetchone()[0]
            == 1
        )
    h.sql(
        "UPDATE device_platform.organizations SET is_active=false,suspension_source='platform' WHERE id=%s",
        (org,),
    )
    h.call("PUT", path, admin, json={**draft, "expected_version": 1}, expected=409)


def test_model_edit_preserves_capture_limits_and_clears_optional_defaults(platform):
    from uuid import uuid4

    from psycopg.types.json import Jsonb

    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org)
    h.enroll(tenant, org, device["id"])
    model = h.call(
        "POST",
        "/platform/runtime-models",
        admin,
        json={**local_model(), "defaults": {"voice": "en"}},
        expected=201,
    )
    path = f"/platform/devices/{device['id']}/models"
    h.call(
        "PUT",
        path,
        admin,
        json={
            "mode": "local",
            "expected_version": 0,
            "tts_model_id": model["id"],
            "model_revisions": {model["id"]: 1},
        },
    )
    previous_id = str(uuid4())
    previous = h.sql(
        "SELECT r.settings FROM device_platform.processing_profile_revisions r JOIN device_platform.device_model_selections s ON s.execution_revision_id=r.id WHERE s.device_id=%s",
        (device["id"],),
    )[0][0]
    previous["capture"] = {"activation": "manual", "max_session_seconds": 7}
    previous["limits"] = {"capture_limits": {"max_audio_seconds": 5}}
    h.sql(
        "INSERT INTO device_platform.processing_profile_revisions(id,organization_id,device_id,version,settings,published_by) SELECT %s,%s,%s,2,%s,updated_by FROM device_platform.device_model_selections WHERE device_id=%s",
        (previous_id, org, device["id"], Jsonb(previous), device["id"]),
    )
    h.sql(
        "UPDATE device_platform.device_model_selections SET execution_revision_id=%s,version=2 WHERE device_id=%s",
        (previous_id, device["id"]),
    )
    h.sql(
        "UPDATE device_platform.runtime_models SET legacy=%s WHERE id=%s",
        (Jsonb({"section": {"voice": "old", "volume_limit": 0.5}}), model["id"]),
    )
    h.call(
        "PUT",
        f"/platform/runtime-models/{model['id']}",
        admin,
        json={**local_model(), "expected_revision": 1, "defaults": {}},
    )
    latest = h.sql(
        "SELECT r.settings FROM device_platform.processing_profile_revisions r JOIN device_platform.device_model_selections s ON s.execution_revision_id=r.id WHERE s.device_id=%s",
        (device["id"],),
    )[0][0]
    assert latest["capture"] == previous["capture"] and latest["limits"] == previous["limits"]
    assert "voice" not in latest["audio_output"] and latest["audio_output"]["volume_limit"] == 0.5
    assert (
        h.sql(
            "SELECT settings FROM device_platform.processing_profile_revisions WHERE id=%s", (previous_id,)
        )[0][0]
        == previous
    )


@pytest.mark.parametrize("device_type", ["manikin", "laptop"])
def test_reported_local_models_resolve_without_platform_credentials(platform, device_type):
    h = platform
    tenant, admin, org = setup(h)
    device = h.device(tenant, org, device_type=device_type)
    credential = h.enroll(tenant, org, device["id"])
    report = {"device_id": device["id"], "llm": [], "speech": []}
    h.call("POST", "/device/local-models", tenant, json=report, expected=403)
    h.call(
        "POST",
        "/device/local-models",
        credential,
        json={**report, "device_id": org},
        expected=403,
    )
    for invalid in (["unknown-model"], ["qwen3.5-4b-local", "qwen3.5-4b-local"]):
        h.call("POST", "/device/local-models", credential, json={**report, "llm": invalid}, expected=422)
    h.call(
        "POST",
        "/device/local-models",
        credential,
        json={
            "device_id": device["id"],
            "llm": ["qwen3.5-4b-local"],
            "speech": ["large-v3"],
        },
    )
    inventory = h.call("GET", f"/platform/devices/{device['id']}/local-models", admin)
    assert inventory["fresh"] and inventory["llm"] == ["qwen3.5-4b-local"]
    assert inventory["speech"] == ["large-v3"]
    models = h.call("GET", "/platform/runtime-models", admin)["items"]
    llm = next(m for m in models if m["model_key"] == "qwen3.5-4b-local")
    speech = next(m for m in models if m["model_key"] == "large-v3")
    assert not llm["has_credentials"] and not speech["has_credentials"]
    path = f"/platform/devices/{device['id']}/models"
    draft = {
        "mode": "local",
        "expected_version": 0,
        "llm_model_id": llm["id"],
        "asr_model_id": speech["id"],
        "model_revisions": {llm["id"]: llm["revision"], speech["id"]: speech["revision"]},
    }
    h.call("PUT", path, admin, json=draft)
    route = h.call("GET", f"/organizations/{org}/model-config?device_id={device['id']}", tenant)
    assert route["llm"]["mode"] == "local" and route["llm"]["model"] == "qwen3.5-4b-local"
    assert route["audio"]["provider"] == "local_whisper" and route["audio"]["model"] == "large-v3"
    assert route["audio"]["enabled"]
    h.sql(
        "UPDATE device_platform.devices SET capabilities=capabilities || jsonb_build_object('local_models_received_at',(now()-interval '25 hours')::text) WHERE id=%s",
        (device["id"],),
    )
    inventory = h.call("GET", f"/platform/devices/{device['id']}/local-models", admin)
    assert not inventory["fresh"]
    saved = h.call("PUT", path, admin, json={**draft, "expected_version": 1})
    assert saved["version"] == 2 and saved["llm_model_id"] == llm["id"]
