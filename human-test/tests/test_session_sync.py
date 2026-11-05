import asyncio
import hashlib
import json
import sqlite3
import threading
import time
import wave
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from training_client.session_sync import CHUNK, SessionSync

from human_test.config import Settings


def test_shutdown_reports_a_writer_that_has_not_flushed(monkeypatch):
    from training_client import session_sync as module

    monkeypatch.setattr(module, "CLOSE_FLUSH_SECONDS", 0.01)
    release = threading.Event()
    disk = threading.Thread(target=release.wait, daemon=True)
    upload = threading.Thread(target=lambda: None)
    disk.start()
    upload.start()
    messages = []
    sync = object.__new__(SessionSync)
    sync.current = None
    sync.video_pending = set()
    sync.stop = threading.Event()
    sync.disk = disk
    sync.upload = upload
    sync.disk_ok = False
    sync.transport = None
    sync.settings = SimpleNamespace(session_sync_background=False)
    sync.notify = messages.append
    try:
        with pytest.raises(RuntimeError, match="disk writer"):
            asyncio.run(sync.close())
        assert disk.is_alive()
        assert any("flush incomplete" in message for message in messages)
    finally:
        release.set()
        disk.join()


def test_rejected_turn_does_not_starve_later_session_and_retry_survives_restart(make_sync):
    server = Server()
    rejected = set()

    def handler(request):
        if any(sid in request.url.path for sid in rejected):
            return httpx.Response(429, json={"error": {"code": "archive_quota"}})
        return server(request)

    sync, _ = make_sync(handler)
    sync.busy(True)
    first = activate(sync)
    rejected.add(first)
    sync.turn(first, record())
    sync.end()
    second = activate(sync)
    sync.turn(second, record())
    sync.end()
    wait_for(lambda: len(rows(sync, "SELECT * FROM sessions WHERE state='sealed'")) == 2)
    sync.busy(False)
    wait_for(lambda: rows(sync, f"SELECT * FROM sessions WHERE id='{second}' AND acknowledged=1"))
    blocked = rows(sync, f"SELECT * FROM items WHERE session='{first}'")[0]
    assert blocked["attempts"] > 0 and blocked["retry_at"] > 0
    assert blocked["uploaded"] == 0 and blocked["error"] is None
    assert Path(blocked["path"]).exists()
    asyncio.run(sync.close())
    restarted = SessionSync(sync.settings, lambda *_: None, transport=httpx.MockTransport(server))
    try:
        assert restarted.ready.wait(5) and restarted.disk_ok
        wait_for(lambda: rows(restarted, f"SELECT * FROM sessions WHERE id='{first}' AND acknowledged=1"))
        assert len(server.items) == 2
    finally:
        asyncio.run(restarted.close())


def test_transient_journal_lock_preserves_result_and_keeps_event_loop_free(make_sync):
    sync, _ = make_sync()
    sync.busy(True)
    sid = activate(sync)
    wait_for(lambda: rows(sync, "SELECT * FROM sessions"))
    lock = sqlite3.connect(sync.root / "journal.sqlite")
    lock.execute("BEGIN IMMEDIATE")

    async def exercise():
        saving = asyncio.create_task(sync.save_turn(sid, record()))
        # Longer than the old two-second journal timeout; the event loop remains usable.
        await asyncio.sleep(2.2)
        assert sync.disk.is_alive() and not saving.done()
        lock.rollback()
        assert await saving

    try:
        asyncio.run(exercise())
        assert len(rows(sync, "SELECT * FROM items WHERE kind='turn' AND ready=1")) == 1
        assert sync.disk_ok and sync.disk.is_alive()
    finally:
        lock.close()


def test_durable_result_overtakes_recording_backlog_without_losing_pcm(make_sync, monkeypatch):
    sync, _ = make_sync()
    sync.busy(True)
    sid = activate(sync)
    entered, release_first, entered_second, release_rest = (threading.Event() for _ in range(4))
    original = wave.Wave_write.writeframesraw
    count = [0]

    def held_write(writer, pcm):
        count[0] += 1
        if count[0] == 1:
            entered.set()
            assert release_first.wait(5)
        elif count[0] == 2:
            entered_second.set()
            assert release_rest.wait(5)
        return original(writer, pcm)

    monkeypatch.setattr(wave.Wave_write, "writeframesraw", held_write)
    sync.audio_start(sid, "backlog")
    sync.audio(sid, "backlog", bytes(320))
    assert entered.wait(3)
    for _ in range(40):
        sync.audio(sid, "backlog", bytes(320))
    sync.audio_end(sid, "backlog")

    async def save():
        pending = asyncio.create_task(sync.save_turn(sid, record()))
        await asyncio.sleep(0)
        release_first.set()
        assert await pending
        assert entered_second.wait(2)
        assert sync.queue.qsize() > 0

    try:
        asyncio.run(save())
    finally:
        release_first.set()
        release_rest.set()
    wait_for(lambda: rows(sync, "SELECT * FROM items WHERE kind='microphone' AND ready=1"))
    audio = rows(sync, "SELECT * FROM items WHERE kind='microphone'")[0]
    with wave.open(audio["path"], "rb") as stored:
        assert stored.getnframes() == 41 * 160


def test_detached_uploader_waits_for_old_inflight_request(make_sync):
    entered, release = threading.Event(), threading.Event()
    server = Server()

    def slow(request):
        entered.set()
        assert release.wait(12)
        return server(request)

    sync, _ = make_sync(slow)
    sid = activate(sync)
    sync.turn(sid, record())
    assert entered.wait(4)
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE state='sealed'"))
    asyncio.run(sync.close())
    helper = SessionSync(sync.settings, lambda *_: None, transport=httpx.MockTransport(server), drain=True)
    try:
        assert helper.ready.wait(5) and helper.disk_ok
        time.sleep(0.2)
        assert helper.upload.is_alive() and sync.upload.is_alive()
        release.set()
        wait_for(lambda: rows(helper, "SELECT * FROM sessions WHERE acknowledged=1"))
        assert len(server.items) == 1
    finally:
        release.set()
        asyncio.run(helper.close())


def test_invalid_server_received_indices_never_delete_local_result(make_sync):
    server = Server()
    corrupt = True

    def handler(request):
        if corrupt and "/items/" in request.url.path and "/chunks/" not in request.url.path:
            return httpx.Response(200, json={"received": [10000]})
        return server(request)

    sync, _ = make_sync(handler)
    sid = activate(sync)
    assert asyncio.run(sync.save_turn(sid, record()))
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM items WHERE attempts>0"))
    item = rows(sync, "SELECT * FROM items")[0]
    assert item["uploaded"] == 0 and Path(item["path"]).exists()
    corrupt = False
    sync.retry()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))


def test_incomplete_capture_is_not_acknowledged_while_transfers_are_pending(make_sync):
    server = Server()
    allow = False

    def handler(request):
        if "/items/" in request.url.path and not allow:
            return httpx.Response(503)
        if request.url.path.endswith("/manifest"):
            body = json.loads(request.content)
            complete = all(i in server.parts for i in body["items"])
            server.manifests[request.url.path.split("/")[5]] = body
            return httpx.Response(
                200,
                json={"sync_status": "incomplete", "transfer_status": "synced" if complete else "pending"},
            )
        return server(request)

    sync, _ = make_sync(handler)
    sid = activate(sync)
    sync.turn(sid, record())
    sync.submit("incomplete", sid)
    sync.end()
    wait_for(lambda: sid in server.manifests)
    assert rows(sync, "SELECT acknowledged FROM sessions")[0]["acknowledged"] == 0
    allow = True
    sync.retry()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))


def test_expired_recording_is_retained_and_other_results_progress(make_sync):
    server = Server()

    def handler(request):
        if (
            "/items/" in request.url.path
            and "/chunks/" not in request.url.path
            and json.loads(request.content)["kind"] == "microphone"
        ):
            return httpx.Response(410)
        return server(request)

    sync, events = make_sync(handler)
    sync.busy(True)
    sid = activate(sync)
    sync.audio_start(sid, "mic")
    sync.audio(sid, "mic", bytes(320))
    sync.audio_end(sid, "mic")
    sync.turn(sid, record())
    sync.end()
    wait_for(lambda: len(rows(sync, "SELECT * FROM items WHERE ready=1")) == 2)
    sync.busy(False)
    wait_for(lambda: rows(sync, "SELECT * FROM items WHERE error='410'"))
    media = rows(sync, "SELECT * FROM items WHERE error='410'")[0]
    assert Path(media["path"]).exists()
    assert rows(sync, "SELECT * FROM items WHERE kind='turn'")[0]["uploaded"] == 1
    assert any("deadline passed" in value for _, value in events)


def test_failed_journal_health_rejects_new_intake_instead_of_silently_accepting(make_sync, monkeypatch):
    from training_client import session_sync as module

    sync, events = make_sync()
    sync.busy(True)
    sid = activate(sync)
    wait_for(lambda: rows(sync, "SELECT * FROM sessions"))
    real_commit = module.JournalConnection.commit

    def broken_commit(connection):
        if threading.current_thread() is sync.disk:
            raise sqlite3.DatabaseError("simulated journal corruption")
        return real_commit(connection)

    monkeypatch.setattr(module.JournalConnection, "commit", broken_commit)
    assert asyncio.run(sync.save_turn(sid, record())) is False
    sync.disk.join(3)
    assert not sync.disk.is_alive() and not sync.disk_ok
    assert sync.submit("turn", sid, record()) is False
    assert any("local storage is unavailable" in value for _, value in events)


def test_uploader_recovers_after_worker_error_without_reexecuting_model(make_sync, monkeypatch):
    from training_client import session_sync as module

    original = module.uploader_loop
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("simulated connection failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "uploader_loop", fail_once)
    server = Server()
    sync, _ = make_sync(server)
    sid = activate(sync)
    assert asyncio.run(sync.save_turn(sid, record()))
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))
    assert calls == 2 and len(server.items) == 1


def test_existing_journal_reopens_after_retry_schema_upgrade(tmp_path):
    from training_client.session_sync import database

    db = sqlite3.connect(tmp_path / "journal.sqlite")
    db.executescript(
        "CREATE TABLE control(id INTEGER PRIMARY KEY,busy_until REAL NOT NULL); INSERT INTO control VALUES(1,123);"
    )
    db.close()
    for _ in range(2):
        journal = database(tmp_path)
        assert dict(journal.execute("SELECT * FROM control").fetchone()) == {
            "id": 1,
            "busy_until": 123.0,
            "auth_until": 0.0,
        }
        assert {"attempts", "retry_at"} <= {row[1] for row in journal.execute("PRAGMA table_info(items)")}
        journal.close()


def test_explicit_retry_recovers_manifest_after_scope_access_is_restored(make_sync):
    server = Server()
    allowed = False

    def handler(request):
        if request.url.path.endswith("/manifest") and not allowed:
            return httpx.Response(403)
        return server(request)

    sync, _ = make_sync(handler)
    sid = activate(sync)
    assert asyncio.run(sync.save_turn(sid, record()))
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=-1 AND error='403'"))
    allowed = True
    sync.retry()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))
    assert len(server.items) == 1


def test_authentication_failure_pauses_all_pending_requests_until_retry(make_sync):
    server = Server()
    allowed = False
    denied = []

    def handler(request):
        if not allowed:
            denied.append(request.url.path)
            return httpx.Response(401)
        return server(request)

    sync, _ = make_sync(handler)
    sync.busy(True)
    for _ in range(2):
        sid = activate(sync)
        sync.turn(sid, record())
        sync.end()
    wait_for(lambda: len(rows(sync, "SELECT * FROM sessions WHERE state='sealed'")) == 2)
    sync.busy(False)
    wait_for(lambda: rows(sync, "SELECT * FROM control WHERE auth_until>0"))
    time.sleep(0.6)
    assert len(denied) == 1
    allowed = True
    sync.retry()
    wait_for(lambda: len(rows(sync, "SELECT * FROM sessions WHERE acknowledged=1")) == 2)
    assert len(server.items) == 2


def wait_for(condition, seconds=12):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if condition():
            return
        time.sleep(0.02)
    assert condition(), "background work did not finish"


def rows(sync, sql):
    with sqlite3.connect(sync.root / "journal.sqlite") as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql)]


def record():
    return dict(
        turn_key=str(uuid4()),
        occurred_at=datetime.now(UTC).isoformat(),
        input_text="Fictional question",
        response_text="Fictional answer",
        outcome="completed",
        execution="local",
        input_source="text",
    )


class Server:
    def __init__(self, lose_ack=False):
        self.items = {}
        self.parts = {}
        self.manifests = {}
        self.calls = []
        self.lose_ack = lose_ack

    def __call__(self, request):
        path = request.url.path.split("/")
        self.calls.append(request.url.path)
        sid = path[5]
        if path[-1] == "manifest":
            body = json.loads(request.content)
            self.manifests[sid] = body
            complete = all(
                i in self.items and len(self.parts.get(i, {})) == len(self.items[i]["hashes"])
                for i in body["items"]
            )
            return httpx.Response(
                200,
                json={
                    "sync_status": "incomplete" if body["incomplete"] else "synced" if complete else "pending"
                },
            )
        iid = path[7]
        if "chunks" not in path:
            self.items[iid] = json.loads(request.content)
            return httpx.Response(200, json={"received": list(self.parts.get(iid, {}))})
        index = int(path[-1])
        digest = hashlib.sha256(request.content).hexdigest()
        assert self.items[iid]["hashes"][index] == digest
        self.parts.setdefault(iid, {})[index] = request.content
        if self.lose_ack:
            self.lose_ack = False
            raise httpx.ReadTimeout("ack lost")
        return httpx.Response(200, json={"index": index, "sha256": digest})


@pytest.fixture
def make_sync(tmp_path):
    instances = []

    def make(server=None, **overrides):
        settings = Settings(
            _env_file=None,
            pms_url="https://example.test",
            pms_token="dev_sync_fixture",
            organization_id=uuid4(),
            device_id=uuid4(),
            session_sync_background=False,
            session_sync_dir=tmp_path / "sync",
            video_recording_dir=tmp_path / "video",
            **overrides,
        )
        events = []
        sync = SessionSync(
            settings, lambda *args: events.append(args), transport=httpx.MockTransport(server or Server())
        )
        instances.append(sync)
        assert sync.ready.wait(15) and sync.disk_ok
        return sync, events

    yield make
    for sync in instances:
        asyncio.run(sync.close())


def activate(sync):
    sid = str(uuid4())
    sync.activate({"context": {"conversation_id": sid}})
    return sid


def test_durable_wav_text_lost_ack_and_final_manifest(make_sync):
    server = Server(lose_ack=True)
    sync, events = make_sync(server)
    sync.busy(True)
    sid = activate(sync)
    sync.audio_start(sid, "mic")
    pcm = b"\x01\x00" * 16000
    sync.audio(sid, "mic", pcm)
    sync.audio_end(sid, "mic")
    turn = record()
    sync.turn(sid, turn)
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE state='sealed'"))
    assert not server.calls
    local = rows(sync, "SELECT * FROM items WHERE kind='microphone'")[0]
    with wave.open(local["path"], "rb") as wav:
        assert wav.getframerate() == 16000 and wav.readframes(16000) == pcm
    sync.busy(False)
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))
    assert len(server.items) == 2 and len(server.manifests[sid]["items"]) == 2
    assert not server.manifests[sid]["incomplete"]
    assert any(
        json.loads(b"".join(server.parts[i].values())) == turn
        for i, value in server.items.items()
        if value["kind"] == "turn"
    )
    assert not list(sync.root.glob("*.wav")) and not list(sync.root.glob("*.json"))


def test_slow_http_never_blocks_capture_and_busy_pauses_new_requests(make_sync):
    entered, release = threading.Event(), threading.Event()
    server = Server()

    def slow(request):
        entered.set()
        release.wait(5)
        return server(request)

    sync, _ = make_sync(slow)
    sid = activate(sync)
    sync.turn(sid, record())
    assert entered.wait(4)
    sync.busy(True)
    samples = []
    sync.audio_start(sid, "mic")
    for _ in range(100):
        start = time.perf_counter()
        sync.audio(sid, "mic", bytes(640))
        samples.append((time.perf_counter() - start) * 1000)
    sync.audio_end(sid, "mic")
    sync.end()
    release.set()
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    before = len(server.calls)
    time.sleep(0.6)
    assert len(server.calls) == before
    assert sorted(samples)[98] < 20  # Generous regression ceiling on shared Windows runners.
    print(f"capture enqueue p99={sorted(samples)[98]:.3f}ms; max={max(samples):.3f}ms")
    sync.busy(False)
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))


def test_end_waits_for_audio_and_video_and_does_not_delete_camera_file(make_sync):
    server = Server()
    sync, _ = make_sync(server)
    sid = activate(sync)
    sync.audio_start(sid, "speaker")
    sync.video_start(sid)
    sync.end()
    # Queue dispatch completes before the disk loop publishes its transaction.
    # Observe the committed lifecycle state rather than racing that commit.
    wait_for(lambda: rows(sync, "SELECT state FROM sessions WHERE state='closing'"))
    assert rows(sync, "SELECT state FROM sessions")[0]["state"] == "closing"
    sync.audio(sid, "speaker", bytes(320), kind="patient_audio")
    sync.audio_end(sid, "speaker")
    path = sync.settings.video_recording_dir / "video-0001.mkv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fictional-camera-data")
    sync.video_file(sid, path)
    sync.video_end(sid)
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))
    assert len(server.manifests[sid]["items"]) == 2 and path.exists()


def test_queue_overflow_and_disk_quota_are_visible_without_blocking(make_sync):
    sync, events = make_sync(session_sync_max_bytes=1048576)
    sync.busy(True)
    sid = activate(sync)
    # Exhaust pending disk reservation; no uploads can free capacity while busy.
    for n in range(10):
        sync.audio_start(sid, str(n))
        sync.audio(sid, str(n), bytes(320))
    wait_for(lambda: any("could not be saved" in e[1] for e in events))
    with sync.guard:
        sync.pending_bytes = 8 * 1024 * 1024
    assert sync.submit("turn", sid, record()) is False
    with sync.guard:
        sync.pending_bytes = 0
    for n in range(10):
        sync.audio_end(sid, str(n))
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE state='sealed'"))
    assert rows(sync, "SELECT incomplete FROM sessions")[0]["incomplete"] == 1
    assert any("queue is full" in e[1] for e in events)


def test_restart_recovers_unsealed_session_and_uploads_without_model_call(make_sync):
    first, _ = make_sync(session_sync_max_bytes=1048576)
    first.busy(True)
    sid = activate(first)
    first.audio_start(sid, "mic")
    first.audio(sid, "mic", bytes(640))
    wait_for(lambda: first.queue.unfinished_tasks == 0)
    # Simulate a stopped process without normal session finalization.
    first.stop.set()
    first.disk.join(3)
    first.upload.join(3)
    camera = first.settings.video_recording_dir / "2026/10/05/session"
    camera.mkdir(parents=True)
    (camera / "video-0001.mkv").write_bytes(b"camera fixture")
    (camera / "video-0002.mkv").write_bytes(bytes(2 * 1048576))
    (camera / "session.json").write_text(
        json.dumps(
            {
                "archive_id": sid,
                "archive_namespace": first.root.name,
                "segments": ["video-0001.mkv", "video-0002.mkv"],
            }
        ),
        encoding="utf-8",
    )
    server = Server()
    recovered = SessionSync(first.settings, lambda *_: None, transport=httpx.MockTransport(server))
    try:
        assert recovered.ready.wait(15) and recovered.disk_ok
        # Startup clears the dead process's busy lease before waiting for uploads.
        wait_for(lambda: rows(recovered, "SELECT * FROM sessions WHERE acknowledged=1"), 15)
        assert server.manifests[sid]["incomplete"] is True
        assert any(value["kind"] == "microphone" for value in server.items.values())
        assert sum(value["kind"] == "video" for value in server.items.values()) == 1
        assert (camera / "video-0002.mkv").exists()  # Over-quota originals are never silently deleted.
    finally:
        asyncio.run(recovered.close())


def test_single_disk_writer_and_private_background_credentials(make_sync, monkeypatch):
    sync, _ = make_sync()
    other = SessionSync(sync.settings, lambda *_: None, transport=httpx.MockTransport(Server()))
    try:
        assert other.ready.wait(15) and not other.disk_ok
    finally:
        asyncio.run(other.close())
    called = {}

    class Pipe:
        def write(self, data):
            called["input"] = data

        def close(self):
            pass

    class Process:
        stdin = Pipe()

    def spawn(args, **kw):
        called.update(args=args, options=kw)
        return Process()

    monkeypatch.setattr("training_client.session_sync.subprocess.Popen", spawn)
    sync._background()
    assert "dev_sync_fixture" not in str(called["args"])
    assert json.loads(called["input"])["pms_token"] == "dev_sync_fixture"


def test_chunk_protocol_resumes_large_video_after_missing_ack(make_sync):
    server = Server(lose_ack=True)
    sync, _ = make_sync(server)
    sid = activate(sync)
    sync.settings.video_recording_dir.mkdir(parents=True)
    path = sync.settings.video_recording_dir / "video-0001.mkv"
    path.write_bytes(b"x" * (CHUNK * 2 + 1))
    sync.video_file(sid, path)
    sync.end()
    wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE acknowledged=1"))
    assert len([p for p in server.calls if p.endswith("/chunks/0")]) == 1
    assert b"".join(next(iter(server.parts.values())).values()) == path.read_bytes()


def test_detached_helper_drains_journal_through_real_loopback_http(tmp_path):
    import subprocess
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    server = Server()
    finished = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            response = server(httpx.Request("PUT", "http://localhost" + self.path, content=data))
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)
            if self.path.endswith("/manifest") and response.json()["sync_status"] == "synced":
                finished.set()

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    settings = Settings(
        _env_file=None,
        pms_url=f"http://127.0.0.1:{http.server_port}",
        pms_token="dev_helper_fixture",
        organization_id=uuid4(),
        device_id=uuid4(),
        session_sync_dir=tmp_path / "journal",
        session_sync_background=False,
    )
    sync = SessionSync(settings, lambda *_: None, transport=httpx.MockTransport(Server()))
    process = None
    try:
        assert sync.ready.wait(15) and sync.disk_ok
        sync.busy(True)
        sid = activate(sync)
        sync.turn(sid, record())
        sync.end()
        wait_for(lambda: rows(sync, "SELECT * FROM sessions WHERE state='sealed'"))
        asyncio.run(sync.close())
        import sys

        process = subprocess.Popen(
            [sys.executable, "-m", "training_client.session_sync"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        values = settings.model_dump(mode="json")
        values["pms_token"] = settings.pms_token.get_secret_value()
        process.stdin.write(json.dumps(values).encode())
        process.stdin.close()
        assert finished.wait(20), "detached uploader failed to resume the saved journal"
        assert server.manifests[sid]["incomplete"] is False
    finally:
        asyncio.run(sync.close())
        if process and process.poll() is None:
            process.terminate()
            process.wait(5)
        http.shutdown()
        http.server_close()
