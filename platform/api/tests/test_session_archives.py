"""Private archive admission, resume, retention and desktop protocol on disposable PG."""

import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_session_queue import queue_device  # noqa: F401

from pms_api.core.common import AppError
from pms_api.modules import session_archives as archives


@pytest.fixture
def archive_device(queue_device):  # noqa: F811
    p, instructor, admin, org, device, token, path, item, case = queue_device
    base = f"/organizations/{org}/patient-practice"
    selection = p.call(
        "PUT",
        base + "/scenario-selection",
        token,
        json={
            "expected_revision": 0,
            "scenario_id": case["id"],
            "language": "en",
            "vitals": case["vitals"],
        },
    )["selection"]
    route = p.call("GET", f"/organizations/{org}/model-config", token)
    result = p.call(
        "POST",
        base + "/conversations",
        token,
        json={
            "request_key": str(uuid4()),
            "practice_id": selection["id"],
            "practice_revision": selection["revision"],
            "connection_id": route["llm"]["connection_id"],
            "language": "en",
            "profile_revision_id": route["profile_revision_id"],
            "configuration_hash": route["configuration_hash"],
        },
    )
    sid = result["context"]["conversation_id"]
    return p, instructor, admin, org, device, token, sid


def metadata(data, kind="microphone", sequence=0):
    return dict(
        kind=kind,
        byte_size=len(data),
        sequence=sequence,
        hashes=[
            hashlib.sha256(data[i : i + archives.CHUNK]).hexdigest()
            for i in range(0, len(data), archives.CHUNK)
        ],
    )


def test_archive_resume_manifest_scope_and_private_download(archive_device):
    p, instructor, admin, org, device, token, sid = archive_device
    base = f"/device/session-archives/{sid}"
    read = f"/organizations/{org}/session-archives"
    assert p.call("GET", base, token)["learner_id"] is None
    p.call("GET", base, instructor, expected=403)
    p.call("GET", read, admin, expected=404)
    other, _ = p.user("archive-outsider")
    p.call("GET", read, other, expected=404)
    other_device = p.device(instructor, org, name="Other archive device")
    other_token = p.enroll(instructor, org, other_device["id"])
    p.call("GET", base, other_token, expected=404)
    iid = str(uuid4())
    item = base + "/items/" + iid
    data = b"fixture" * 40000
    body = metadata(data)
    assert p.call("PUT", item, token, json=body)["received"] == []
    p.call("PUT", item, token, json={**body, "sequence": 1}, expected=409)
    p.call("PUT", item + "/chunks/0", token, content=b"bad", expected=422)
    p.call("PUT", item + "/chunks/0", token, content=b"x" * (archives.CHUNK + 1), expected=413)
    first = p.call("PUT", item + "/chunks/0", token, content=data[: archives.CHUNK])
    assert p.call("PUT", item + "/chunks/0", token, content=data[: archives.CHUNK]) == first
    assert p.call("PUT", item, token, json=body)["received"] == [0]
    manifest = dict(items=[iid], incomplete=False, outcome="completed")
    p.call("PUT", base + "/manifest", token, json={**manifest, "items": []}, expected=422)
    assert p.call("PUT", base + "/manifest", token, json=manifest)["sync_status"] == "pending"
    interrupted = p.call("GET", base, token)
    assert interrupted["transfer_status"] == "pending" and interrupted["capture_status"] == "complete"
    p.call("PUT", base + "/items/" + str(uuid4()), token, json=metadata(b"late"), expected=409)
    p.call("PUT", item + "/chunks/1", token, content=data[archives.CHUNK :])
    assert p.call("PUT", base + "/manifest", token, json=manifest)["sync_status"] == "synced"
    assert p.call("GET", base, token)["transfer_status"] == "synced"
    listing = p.call("GET", read, instructor)["items"]
    assert len(listing) == 1 and listing[0]["received_items"] == 1 and listing[0]["items"] == []
    detail = p.call("GET", read + "/" + sid, instructor)
    assert detail["items"][0]["available"]
    assert detail["practice_snapshot"]["vitals"]
    assert detail["context"]["conversation_id"] == sid
    assert "practice_snapshot" not in listing[0] and "context" not in listing[0]
    # Platform admin status alone must never expose tenant recordings.
    p.call("GET", read + f"/{sid}/items/{iid}", admin, expected=404)
    response = p.client.get(
        "/api/v1" + read + f"/{sid}/items/{iid}", headers={"Authorization": "Bearer " + instructor}
    )
    assert response.status_code == 200 and response.content == data
    assert "no-store" in response.headers["cache-control"]


def test_archive_turn_validation_and_upload_after_practice_deadline(archive_device, monkeypatch):
    p, instructor, admin, org, device, token, sid = archive_device
    base = f"/device/session-archives/{sid}"
    stamp = datetime.fromisoformat(p.call("GET", base, token)["created_at"])
    # Session expiry must not discard recordings that were already captured.
    monkeypatch.setattr(archives, "now", lambda: stamp + timedelta(hours=25))
    turn = dict(
        turn_key=str(uuid4()),
        occurred_at=stamp.isoformat(),
        input_text="Fictional question",
        response_text="Fictional answer",
        outcome="completed",
        execution="local",
        input_source="text",
    )
    data = json.dumps(turn).encode()
    iid = str(uuid4())
    item = base + "/items/" + iid
    p.call("PUT", item, token, json=metadata(data, "turn"))
    p.call("PUT", item + "/chunks/0", token, content=data)
    history = p.call("GET", f"/organizations/{org}/session-archives/{sid}/turns", instructor)
    assert history["items"] == [turn] and history["provenance"] == "client_reported"
    bad = base + "/items/" + str(uuid4())
    p.call("PUT", bad, token, json=metadata(b"{}", "turn", 1))
    p.call("PUT", bad + "/chunks/0", token, content=b"{}", expected=422)
    monkeypatch.setattr(archives, "now", lambda: stamp + timedelta(days=8))
    p.call("PUT", item, token, json=metadata(data, "turn"), expected=410)


def test_concurrent_quota_and_retention_preserve_sync_receipt(archive_device, monkeypatch):
    p, instructor, admin, org, device, token, sid = archive_device
    base = f"/device/session-archives/{sid}"
    p.settings.session_archive_session_bytes = 100
    p.settings.session_archive_org_bytes = 100
    ids = [str(uuid4()), str(uuid4())]
    data = b"x" * 60

    def reserve(iid):
        return p.client.put(
            "/api/v1" + base + "/items/" + iid,
            headers={"Authorization": "Bearer " + token},
            json=metadata(data),
        )

    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(reserve, ids))
    assert sorted(r.status_code for r in result) == [200, 429]
    iid = ids[next(i for i, r in enumerate(result) if r.status_code == 200)]
    p.call("PUT", base + f"/items/{iid}/chunks/0", token, content=data)
    p.call("PUT", base + "/manifest", token, json=dict(items=[iid], incomplete=False, outcome="completed"))
    detail = p.call("GET", base, token)
    expiry = datetime.fromisoformat(detail["media_expires_at"])
    monkeypatch.setattr(archives, "now", lambda: expiry + timedelta(seconds=1))
    # Retention can remove blobs without turning an acknowledged session back into pending.
    p.client.portal.call(archives.retention_once, p.client.app.state.sessions, p.client.app.state.storage)
    assert p.sql("SELECT purged FROM device_platform.session_archive_items WHERE id=%s", (iid,))[0][0]
    read = f"/organizations/{org}/session-archives/{sid}"
    detail = p.call("GET", read, instructor)
    assert detail["sync_status"] == "synced" and not detail["items"][0]["available"]
    p.call("GET", read + f"/items/{iid}", instructor, expected=409)
    p.call("PUT", base + f"/items/{iid}", token, json=metadata(data), expected=410)


def test_capture_loss_and_pending_transfer_are_independent(archive_device):
    p, instructor, admin, org, device, token, sid = archive_device
    base = f"/device/session-archives/{sid}"
    iid = str(uuid4())
    data = b"captured before interruption"
    body = dict(items=[iid], incomplete=True, outcome="interrupted")
    pending = p.call("PUT", base + "/manifest", token, json=body)
    assert pending["sync_status"] == "incomplete"
    assert pending["capture_status"] == "incomplete" and pending["transfer_status"] == "pending"
    assert pending["media_expires_at"] < pending["upload_until"]
    path = base + f"/items/{iid}"
    p.call("PUT", path, token, json=metadata(data))
    p.call("PUT", path + "/chunks/0", token, content=data)
    finished = p.call("PUT", base + "/manifest", token, json=body)
    assert finished["sync_status"] == "incomplete" and finished["transfer_status"] == "synced"


def test_uncertain_storage_write_never_acknowledges_before_commit_and_retry_is_safe(
    archive_device, monkeypatch
):
    p, instructor, admin, org, device, token, sid = archive_device
    base = f"/device/session-archives/{sid}"
    iid = str(uuid4())
    item = base + f"/items/{iid}"
    data = b"recording written before a simulated storage interruption"
    p.call("PUT", item, token, json=metadata(data))
    original = p.client.app.state.storage.write
    attempts = 0

    async def interrupted(key, content, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        await original(key, content, *args, **kwargs)
        if attempts == 1:
            raise AppError(503, "storage_temporarily_unavailable", "Synthetic write interruption")

    monkeypatch.setattr(p.client.app.state.storage, "write", interrupted)
    p.call("PUT", item + "/chunks/0", token, content=data, expected=503)
    assert p.call("PUT", item, token, json=metadata(data))["received"] == []
    p.call("PUT", item + "/chunks/0", token, content=data)
    assert p.call("PUT", item, token, json=metadata(data))["received"] == [0]
    p.call("PUT", item + "/chunks/0", token, content=data)
    assert attempts == 2
    read = f"/organizations/{org}/session-archives/{sid}/items/{iid}"
    response = p.client.get("/api/v1" + read, headers={"Authorization": "Bearer " + instructor})
    assert response.status_code == 200 and response.content == data


def test_desktop_sync_protocol_and_trainee_scope(archive_device, monkeypatch, tmp_path):
    from test_session_queue_review import trainee

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "human-test/src"))
    from human_test.config import Settings
    from training_client.session_sync import SessionSync

    p, instructor, admin, org, device, token, sid = archive_device
    learner_token, learner = trainee(p, instructor, org, "archive-learner")
    read = f"/organizations/{org}/session-archives"
    assert p.call("GET", read, learner_token)["items"] == []
    p.call("GET", read + "/" + sid, learner_token, expected=404)
    # Actual desktop journal and uploader through the authenticated API and runtime grants.
    settings = Settings(
        _env_file=None,
        pms_url="https://testserver",
        pms_token=token,
        organization_id=org,
        device_id=device["id"],
        session_sync_background=False,
        session_sync_dir=tmp_path / "journal",
    )

    def transport(request):
        response = p.client.request(
            request.method, request.url.path, headers=dict(request.headers), content=request.content
        )
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    sync = SessionSync(settings, lambda *_: None, transport=httpx.MockTransport(transport))
    try:
        assert sync.ready.wait(5) and sync.disk_ok
        sync.activate({"context": {"conversation_id": sid}})
        sync.audio_start(sid, "mic")
        sync.audio(sid, "mic", bytes(640))
        sync.audio_end(sid, "mic")
        sync.turn(
            sid,
            dict(
                turn_key=str(uuid4()),
                occurred_at=archives.now().isoformat(),
                input_text="Fictional question",
                response_text="Fictional answer",
                outcome="completed",
                execution="cloud",
                input_source="speech",
            ),
        )
        sync.end()
        until = time.monotonic() + 15
        while time.monotonic() < until:
            status = p.call("GET", read + "/" + sid, instructor)
            if status["sync_status"] == "synced":
                break
            time.sleep(0.1)
        assert status["sync_status"] == "synced" and status["received_items"] == 2
        assert p.call("GET", read + f"/{sid}/turns", instructor)["items"][0]["execution"] == "cloud"
    finally:
        asyncio.run(sync.close())
