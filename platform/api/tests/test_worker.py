import asyncio
from uuid import uuid4

from pms_api.database.session import engine_for, sessions_for
from pms_api.integrations.providers import ProviderResult
from pms_api.worker.service import Worker


class Adapter:
    def __init__(self, uncertain=False):
        self.submissions = 0
        self.uncertain = uncertain

    async def validate(self, *args):
        return True

    async def submit(self, *args, **kwargs):
        self.submissions += 1
        if self.uncertain:
            raise TimeoutError("do not log this provider payload")
        return ProviderResult("succeeded", result={"format": "wav"}, audio=b"generated audio test fixture")

    async def reconcile(self, *args):
        return ProviderResult("unknown")


class Factory:
    def __init__(self, adapter):
        self.adapter = adapter

    def for_connection(self, connection):
        return self.adapter


def cloud_run(p, monkeypatch, adapter, playback=False):
    monkeypatch.setattr(
        "pms_api.integrations.providers.ProviderFactory.for_connection", lambda self, row: adapter
    )
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    device = p.device(token, oid)
    did = device["id"]
    credential = p.enroll(token, oid, did)
    settings = p.call("GET", "/platform/settings", token)
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        json={"expected_version": settings["configuration_version"], "enabled_providers": ["azure"]},
    )
    connection = p.call(
        "POST",
        f"/organizations/{oid}/connections",
        token,
        expected=201,
        json={
            "name": "Speech",
            "provider": "azure",
            "connection_type": "azure_speech",
            "auth_mode": "api_key",
            "settings": {"region": "centralindia"},
            "credentials": {"api_key": "mocked-key"},
        },
    )
    p.call(
        "POST",
        f"/organizations/{oid}/connections/{connection['id']}/validate",
        token,
        json={"operation": "audio.synthesize"},
    )
    profile = p.call(
        "POST",
        f"/organizations/{oid}/profiles",
        token,
        expected=201,
        json={
            "name": "Speech",
            "draft_settings": {
                "audio_output": {
                    "enabled": True,
                    "operation": "audio.synthesize",
                    "execution_mode": "cloud",
                    "engine": "azure_speech",
                    "format": "wav",
                }
            },
            "draft_audio_output_connection_id": connection["id"],
        },
    )
    revision = p.call("POST", f"/organizations/{oid}/profiles/{profile['id']}/publish", token, json={})
    p.call("PATCH", f"/organizations/{oid}", token, json={"default_profile_id": profile["id"]})
    result = p.call(
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
            "playback": playback,
        },
    )
    return token, oid, did, credential, result["run"]["id"]


async def tick(p, adapter):
    engine = engine_for(p.settings, "worker")
    try:
        return await Worker(p.settings, sessions_for(engine), Factory(adapter)).tick()
    finally:
        await engine.dispose()


def test_worker_synthesis_media_revocation_and_playback(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    token, oid, did, credential, rid = cloud_run(p, monkeypatch, adapter, True)
    assert asyncio.run(tick(p, adapter))
    result = p.call("GET", f"/organizations/{oid}/runs/{rid}", token)
    assert result["status"] == "succeeded" and adapter.submissions == 1
    access = p.call("POST", f"/device/runs/{rid}/media/0/access", credential)
    assert p.client.get(access["url"]).content == b"generated audio test fixture"
    p.call("POST", f"/device/runs/{rid}/playback", credential, json={"status": "playing"})
    p.call("POST", f"/device/runs/{rid}/playback", credential, json={"status": "succeeded"})
    p.call("POST", f"/organizations/{oid}/devices/{did}/revoke", token)
    assert p.client.get(access["url"]).status_code in {401, 403}


def test_uncertain_submission_is_not_blindly_retried(platform, monkeypatch):
    p = platform
    adapter = Adapter(True)
    token, oid, _, _, rid = cloud_run(p, monkeypatch, adapter)
    asyncio.run(tick(p, adapter))
    assert p.call("GET", f"/organizations/{oid}/runs/{rid}", token)["provider_submission_status"] == "unknown"
    p.sql("UPDATE device_platform.processing_runs SET next_attempt_at=now() WHERE id=%s", (rid,))
    asyncio.run(tick(p, adapter))
    assert adapter.submissions == 1
    p.call(
        "POST",
        f"/organizations/{oid}/runs/{rid}/resolve-submission",
        token,
        json={
            "outcome": "completed_without_result",
            "reason": "Provider confirms processing completed with no retrievable output",
            "verified_with_provider": True,
        },
    )
    assert p.call("GET", f"/organizations/{oid}/runs/{rid}", token)["status"] == "failed"


def test_worker_lease_fences_stale_owner(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    _, _, _, _, rid = cloud_run(p, monkeypatch, adapter)

    async def exercise():
        engine = engine_for(p.settings, "worker")
        worker = Worker(p.settings, sessions_for(engine), Factory(adapter))
        try:
            first = await worker.claim()
            assert await worker.claim() is None
            p.sql(
                "UPDATE device_platform.processing_runs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
                (rid,),
            )
            second = await worker.claim()
            assert first.lease_token != second.lease_token
            assert not await worker.save(first, error={"code": "stale"})
            assert await worker.save(second, lease_token=None, lease_expires_at=None)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_standalone_playback_does_not_own_source_media(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    token, oid, did, credential, rid = cloud_run(p, monkeypatch, adapter)
    asyncio.run(tick(p, adapter))
    _, revision = p.profile(
        token, oid, section="audio_output", operation="audio.playback", engine="device_player"
    )
    run = p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=202,
        json={
            "device_id": did,
            "request_key": str(uuid4()),
            "operation": "audio.playback",
            "profile_revision_id": revision["id"],
            "source_run_id": rid,
        },
    )["run"]
    access = p.call("POST", f"/device/runs/{run['id']}/media/0/access", credential)
    assert p.client.get(access["url"]).status_code == 200
    p.call("POST", f"/organizations/{oid}/runs/{run['id']}/cancel", token)
    asyncio.run(tick(p, adapter))
    source = p.call("POST", f"/organizations/{oid}/runs/{rid}/media/0/access", token)
    assert p.client.get(source["url"]).content == b"generated audio test fixture"


def test_cancellation_before_submission_never_calls_provider(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    token, oid, _, _, rid = cloud_run(p, monkeypatch, adapter)

    async def exercise():
        engine = engine_for(p.settings, "worker")
        worker = Worker(p.settings, sessions_for(engine), Factory(adapter))
        try:
            row = await worker.claim()
            p.call("POST", f"/organizations/{oid}/runs/{rid}/cancel", token)
            await worker.process(row)
            assert adapter.submissions == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_retention_requires_cleanup_and_uses_restricted_role(platform, monkeypatch):
    from pms_api.worker.service import retain

    p = platform
    adapter = Adapter()
    token, oid, _, _, rid = cloud_run(p, monkeypatch, adapter)
    asyncio.run(tick(p, adapter))
    p.sql(
        "UPDATE device_platform.processing_runs SET deadline_at=created_at,media_expires_at=created_at,expires_at=created_at,cleanup_next_attempt_at=created_at WHERE id=%s",
        (rid,),
    )

    async def maintenance():
        engine = engine_for(p.settings, "retention")
        try:
            await retain(sessions_for(engine))
        finally:
            await engine.dispose()

    asyncio.run(maintenance())
    assert p.sql("SELECT result,cleanup_status FROM device_platform.processing_runs WHERE id=%s", (rid,)) == [
        (None, "pending")
    ]
    asyncio.run(tick(p, adapter))
    assert (
        p.sql("SELECT cleanup_status FROM device_platform.processing_runs WHERE id=%s", (rid,))[0][0]
        == "succeeded"
    )
    asyncio.run(maintenance())
    assert p.sql("SELECT id FROM device_platform.processing_runs WHERE id=%s", (rid,)) == []


def test_upload_finalization_and_content_replacement(platform, monkeypatch):
    from test_media import wav_bytes

    class InputAdapter(Adapter):
        async def stage(self, *args):
            return None

        async def submit(self, *args, **kwargs):
            self.submissions += 1
            return ProviderResult("succeeded", result={"text": "verified input"})

        async def cleanup(self, *args):
            return None

    p = platform
    adapter = InputAdapter()
    token, oid, did, credential, initial = cloud_run(p, monkeypatch, adapter)
    p.call("POST", f"/organizations/{oid}/runs/{initial}/cancel", token)
    asyncio.run(tick(p, adapter))
    connection = p.call("GET", f"/organizations/{oid}/connections", token)["items"][0]["id"]
    p.call(
        "POST",
        f"/organizations/{oid}/connections/{connection}/validate",
        token,
        json={"operation": "audio.transcribe"},
    )
    profile = p.call(
        "POST",
        f"/organizations/{oid}/profiles",
        token,
        expected=201,
        json={
            "name": "Transcription",
            "draft_settings": {
                "audio_input": {
                    "enabled": True,
                    "operation": "audio.transcribe",
                    "execution_mode": "cloud",
                    "engine": "azure_speech",
                    "max_duration_seconds": 1,
                }
            },
            "draft_audio_input_connection_id": connection,
        },
    )
    revision = p.call("POST", f"/organizations/{oid}/profiles/{profile['id']}/publish", token, json={})
    p.call("PATCH", f"/organizations/{oid}", token, json={"default_profile_id": profile["id"]})
    for replace in (False, True):
        rid = p.call(
            "POST",
            f"/organizations/{oid}/runs",
            token,
            expected=202,
            json={
                "device_id": did,
                "request_key": str(uuid4()),
                "operation": "audio.transcribe",
                "profile_revision_id": revision["id"],
                "media_format": "wav",
                "duration_seconds": 1,
            },
        )["run"]["id"]
        work = p.call("GET", "/device/runs", credential)["items"]
        capture = next((item for item in work if item["id"] == rid), None)
        assert capture is not None and capture["status"] == "awaiting_upload"
        # Exercise the device capture/upload flow and retain human-upload coverage.
        scope = f"/device/runs/{rid}" if not replace else f"/organizations/{oid}/runs/{rid}"
        uploader = credential if not replace else token
        access = p.call("POST", f"{scope}/media/0/access?method=PUT", uploader)
        if not replace:
            assert (
                p.client.put(access["url"], content=wav_bytes(2), headers=access["headers"]).status_code
                == 200
            )
            rejection = p.call("POST", f"{scope}/upload-complete", uploader, expected=422)
            assert rejection["error"]["code"] == "capture_limit"
        assert p.client.put(access["url"], content=wav_bytes(), headers=access["headers"]).status_code == 200
        p.call("POST", f"{scope}/upload-complete", uploader)
        if replace:
            key = p.sql("SELECT media_manifest FROM device_platform.processing_runs WHERE id=%s", (rid,))[0][
                0
            ][0]["key"]
            (p.settings.storage_root / key).write_bytes(b"replaced after finalization")
        asyncio.run(tick(p, adapter))
        result = p.call("GET", f"/organizations/{oid}/runs/{rid}", token)
        assert result["status"] == ("failed" if replace else "succeeded")
        if replace:
            assert result["error"]["code"] == "media_changed"
    assert adapter.submissions == 1


def test_retention_progresses_past_redacted_unresolved_backlog(platform, monkeypatch):
    from pms_api.worker.service import retain

    p = platform
    adapter = Adapter()
    _, _, _, _, rid = cloud_run(p, monkeypatch, adapter)
    asyncio.run(tick(p, adapter))
    p.sql(
        """UPDATE device_platform.processing_runs
        SET deadline_at=created_at,media_expires_at=created_at,expires_at=created_at,
            cleanup_next_attempt_at=created_at,provider_submission_status='unknown',
            result=NULL,error=NULL,request=request-'text'-'source_run_id' WHERE id=%s""",
        (rid,),
    )
    p.sql(
        """INSERT INTO device_platform.processing_runs
        SELECT (jsonb_populate_record(NULL::device_platform.processing_runs,
            to_jsonb(r)||jsonb_build_object('id',gen_random_uuid(),'request_key',gen_random_uuid()))).*
        FROM device_platform.processing_runs r CROSS JOIN generate_series(1,100) WHERE r.id=%s""",
        (rid,),
    )
    pending, cleaned = uuid4(), uuid4()
    for new_id, cleanup in ((pending, "pending"), (cleaned, "succeeded")):
        p.sql(
            """INSERT INTO device_platform.processing_runs
            SELECT (jsonb_populate_record(NULL::device_platform.processing_runs,
                to_jsonb(r)||jsonb_build_object('id',%s::uuid,'request_key',gen_random_uuid(),
                    'provider_submission_status','submitted','cleanup_status',%s::text,
                    'result',jsonb_build_object('text','expired private result'),
                    'request',r.request||jsonb_build_object('text','expired private input')))).*
            FROM device_platform.processing_runs r WHERE r.id=%s""",
            (new_id, cleanup, rid),
        )

    async def maintenance():
        engine = engine_for(p.settings, "retention")
        try:
            await retain(sessions_for(engine))
        finally:
            await engine.dispose()

    asyncio.run(maintenance())
    assert p.sql("SELECT id FROM device_platform.processing_runs WHERE id=%s", (cleaned,)) == []
    result, request = p.sql(
        "SELECT result,request FROM device_platform.processing_runs WHERE id=%s", (pending,)
    )[0]
    assert result is None and "text" not in request
    assert p.sql(
        "SELECT count(*) FROM device_platform.processing_runs WHERE provider_submission_status='unknown'"
    ) == [(101,)]
