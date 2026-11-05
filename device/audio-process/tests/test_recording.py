import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import wave
from uuid import uuid4

import pytest
from conftest import HEADERS, OTHER_TOKEN, SILENCE, SPEECH, Detector, FakeEngine, collect, send_pcm
from fastapi.testclient import TestClient

from device_audio.app import create_app
from device_audio.recording import Recorder
from device_audio.recording_store import RESERVE, RecordingStore, StorageError, private_directory


@pytest.fixture
def recording_settings(settings, tmp_path):
    settings.recording_enabled = True
    settings.recording_dir = tmp_path / "recordings"
    settings.recording_min_free_bytes = 0
    # Most tests explicitly finalize/flush. Periodic-flush behavior has a dedicated test.
    settings.recording_flush_seconds = 10
    settings.recording_cleanup_seconds = 3600
    return settings


def make_record(recorder, client="pi-1"):
    return recorder.begin(str(uuid4()), client, str(uuid4()), "hi")


async def finalized(record, timeout=4):
    async with asyncio.timeout(timeout):
        while not record.finalized:
            await asyncio.sleep(0.01)
    return record.snapshot()


def read_audio(path):
    with wave.open(str(path), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
        return audio.readframes(audio.getnframes())


async def test_full_audio_including_silence_unicode_and_restart(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    assert recorder.available
    record = make_record(recorder)
    pcm = SILENCE * 5 + SPEECH * 6 + SILENCE * 3
    event = {"type": "transcript", "text": "\u0928\u092e\u0938\u094d\u0924\u0947 hello", "sequence": 1}
    recorder.audio(record, pcm)
    recorder.transcript(record, event)
    recorder.finish(record)
    receipt = await finalized(record)
    assert receipt["status"] == "saved"
    directory = recording_settings.recording_dir / receipt["id"]
    assert read_audio(directory / "audio.wav") == pcm
    assert json.loads((directory / "transcript.jsonl").read_text(encoding="utf-8")) == event
    assert json.loads((directory / "session.json").read_text())["status"] == "saved"
    assert recorder.lookup(receipt["id"], "pi-2") is None
    await recorder.stop()
    restarted = Recorder(recording_settings)
    await restarted.start()
    try:
        assert restarted.lookup(receipt["id"], "pi-1")["status"] == "saved"
    finally:
        await restarted.stop()


@pytest.mark.parametrize("failure", ["write", "quota"])
async def test_failed_storage_is_incomplete_and_does_not_claim_saved(recording_settings, failure):
    class FailedStore(RecordingStore):
        def audio(self, key, pcm):
            if failure == "write":
                raise OSError("private path must not be logged")
            return super().audio(key, pcm)

    if failure == "quota":
        recording_settings.recording_max_bytes = 32768
    recorder = Recorder(recording_settings, FailedStore)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 30)
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "incomplete"
        assert receipt["reason"] == ("write_failed" if failure == "write" else "storage_limit")
        assert recorder.stored_bytes <= recording_settings.recording_max_bytes
        manifest = recording_settings.recording_dir / receipt["id"] / "session.json"
        assert json.loads(manifest.read_text())["status"] == "incomplete"
    finally:
        await recorder.stop()


async def test_slow_writer_queue_is_bounded_and_finish_does_not_wait(recording_settings):
    entered, release = threading.Event(), threading.Event()

    class SlowStore(RecordingStore):
        def audio(self, key, pcm):
            entered.set()
            release.wait(5)
            return super().audio(key, pcm)

    recording_settings.recording_queue_items = 4
    recorder = Recorder(recording_settings, SlowStore)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH)
    assert await asyncio.to_thread(entered.wait, 2)
    for _ in range(20):
        recorder.audio(record, SPEECH)
    receipt = recorder.finish(record)
    assert not release.is_set()
    assert receipt["status"] == "incomplete"
    assert receipt["reason"] == "recording_queue_full"
    assert recorder.queue.qsize() <= 4
    assert recorder.pending_bytes <= recording_settings.recording_queue_bytes
    release.set()
    try:
        receipt = await finalized(record)
        assert receipt["audio_bytes"] == 5 * len(SPEECH)
        assert receipt["audio_bytes"] < receipt["received_audio_bytes"]
        assert read_audio(recording_settings.recording_dir / receipt["id"] / "audio.wav") == SPEECH * 5
        assert recorder.pending_bytes == 0
    finally:
        release.set()
        await recorder.stop()


async def test_queue_byte_limit_independent_of_item_count(recording_settings):
    recording_settings.recording_queue_bytes = 32768
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    # No event-loop yield: admission must enforce the shared byte budget immediately.
    recorder.audio(record, b"\0" * 32768)
    recorder.finish(record)
    try:
        result = await finalized(record)
        assert result["reason"] == "recording_queue_full"
        assert result["status"] == "incomplete"
    finally:
        await recorder.stop()


def api_client(settings, store_factory=RecordingStore):
    app = create_app(settings, lambda _: FakeEngine(), detector_factory=Detector)
    app.state.runtime.recorder = Recorder(settings, store_factory)
    return TestClient(app, client=("127.0.0.1", 12345))


def test_transcript_and_complete_arrive_while_disk_is_blocked_and_receipts_are_scoped(recording_settings):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class SlowStore(RecordingStore):
        def audio(self, key, pcm):
            entered.set()
            release.wait(5)
            finished.set()
            return super().audio(key, pcm)

    try:
        with api_client(recording_settings, SlowStore) as client:
            with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                ws.send_json({"type": "start"})
                ready = ws.receive_json()
                key = ready["recording"]["id"]
                send_pcm(ws, SPEECH * 6)
                assert entered.wait(2)
                ws.send_json({"type": "finish"})
                events = collect(ws)
                assert events[-1]["type"] == "complete"
                assert any(event["type"] == "transcript" for event in events)
                assert not finished.is_set(), "API waited for disk I/O"
                assert events[-1]["recording"]["status"] == "pending"
                assert not events[-1]["recording"]["finalized"]
                route = "/v1/recordings/" + key
                assert client.get(route).status_code == 401
                assert (
                    client.get(route, headers={"Authorization": "Bearer " + OTHER_TOKEN}).status_code == 404
                )
                assert client.get(route, headers=dict(HEADERS)).json()["status"] == "pending"
                assert client.get("/health/ready", headers=dict(HEADERS)).status_code == 200
                release.set()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    status = client.get(route, headers=dict(HEADERS)).json()
                    if status["status"] == "saved":
                        break
                    time.sleep(0.01)
                assert status["status"] == "saved" and status["finalized"]
                assert "text" not in status
    finally:
        release.set()


def test_disconnect_keeps_partial_audio_marked_incomplete(recording_settings):
    with api_client(recording_settings) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            ws.send_json({"type": "start"})
            key = ws.receive_json()["recording"]["id"]
            send_pcm(ws, SILENCE * 6)
            ws.close()
            # TestClient cancels the ASGI task on context exit; allow disconnect cleanup first.
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if not client.get("/v1/status", headers=dict(HEADERS)).json()["client_streaming"]:
                    break
                time.sleep(0.01)
            assert not client.get("/v1/status", headers=dict(HEADERS)).json()["client_streaming"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = client.get("/v1/recordings/" + key, headers=dict(HEADERS)).json()
            if status["status"] == "incomplete":
                break
            time.sleep(0.01)
        assert status["reason"] == "stream_interrupted"
    assert (
        json.loads((recording_settings.recording_dir / key / "session.json").read_text())["status"]
        == "incomplete"
    )

    assert read_audio(recording_settings.recording_dir / key / "audio.wav") == SILENCE * 6


async def test_store_lock_prevents_two_writers_and_unavailable_storage_keeps_api_usable(recording_settings):
    first, second = Recorder(recording_settings), Recorder(recording_settings)
    await first.start()
    await second.start()
    try:
        assert first.available
        assert not second.available
        record = make_record(second)
        assert record.data["reason"] == "storage_unavailable"
    finally:
        await second.stop()
        await first.stop()


def test_unmanaged_directory_is_preserved(recording_settings):
    root = recording_settings.recording_dir
    root.mkdir()
    sentinel = root / "keep.txt"
    sentinel.write_text("unrelated")
    store = RecordingStore(recording_settings)
    with pytest.raises(StorageError, match="unmanaged"):
        store.initialize()
    assert sentinel.read_text() == "unrelated"


async def test_retention_expires_completed_sessions_and_preserves_active(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    old = make_record(recorder)
    recorder.audio(old, SPEECH)
    recorder.finish(old)
    await finalized(old)
    active = make_record(recorder)
    recorder.audio(active, SPEECH)
    await recorder.queue.join()
    backend = recorder.disk.store
    backend.records[old.data["id"]]["created_at"] = time.time() - 8 * 86400
    backend.records[active.data["id"]]["created_at"] = time.time() - 8 * 86400
    removed = await recorder.disk.call(backend.prune)
    try:
        assert removed == [old.data["id"]]
        assert (recording_settings.recording_dir / active.data["id"]).exists()
        assert not (recording_settings.recording_dir / old.data["id"]).exists()
    finally:
        recorder.finish(active)
        await recorder.stop()


async def test_session_count_cap_evicts_oldest_completed_recording(recording_settings):
    recording_settings.recording_max_sessions = 1
    recorder = Recorder(recording_settings)
    await recorder.start()
    first = make_record(recorder)
    recorder.finish(first)
    await finalized(first)
    second = make_record(recorder)
    recorder.finish(second)
    try:
        assert (await finalized(second))["status"] == "saved"
        assert not (recording_settings.recording_dir / first.data["id"]).exists()
        assert len(recorder.disk.store.records) == 1
    finally:
        await recorder.stop()


async def test_quota_includes_other_sessions_buffered_audio(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    first, second = make_record(recorder), make_record(recorder, "pi-2")
    recorder.audio(second, SPEECH * 12)
    await recorder.queue.join()
    recorder.finish(first)
    await finalized(first)
    try:
        assert recorder.disk.store.used >= 2 * (RESERVE + 44) + 12 * len(SPEECH)
    finally:
        recorder.finish(second)
        await recorder.stop()


async def test_shutdown_is_bounded_when_disk_stalls(recording_settings):
    entered, release = threading.Event(), threading.Event()
    recording_settings.recording_shutdown_seconds = 0.1

    class StalledStore(RecordingStore):
        def audio(self, key, pcm):
            entered.set()
            release.wait(5)
            return super().audio(key, pcm)

    recorder = Recorder(recording_settings, StalledStore)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH)
    assert await asyncio.to_thread(entered.wait, 2)
    try:
        await asyncio.wait_for(recorder.stop(), 1)
        assert record.data["reason"] in {"service_stopped", "shutdown_timeout"}
        assert not release.is_set()
    finally:
        release.set()
        await asyncio.to_thread(recorder.disk.closed.wait, 3)


def test_hard_link_cannot_escape_retention(recording_settings, tmp_path):
    store = RecordingStore(recording_settings)
    store.initialize()
    key = str(uuid4())
    folder = recording_settings.recording_dir / key
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must remain")
    os.link(outside, folder / "audio.wav")
    try:
        with pytest.raises(StorageError, match="unsafe_path"):
            store._check_files(folder)
        assert outside.read_text() == "must remain"
    finally:
        store.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL assertion")
def test_private_acl_replaces_explicit_broad_grants(tmp_path):
    path = tmp_path / "acl"
    path.mkdir()
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-1-0:(OI)(CI)F"],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    private_directory(path)
    # PowerShell receives the directory as an argument; no interpolation into executable code.
    result = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", "& { param($p) (Get-Acl -LiteralPath $p).Sddl }", str(path)],
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert ";;;WD)" not in result
    assert "D:P" in result


async def test_recovery_repairs_interrupted_wav_and_trims_partial_json(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 4)
    recorder.transcript(record, {"text": "complete", "sequence": 1})
    await recorder.queue.join()
    store = recorder.disk.store
    key = record.data["id"]

    def simulate_interruption():
        store.flush()
        files = store.open_files.pop(key)
        files.wav.close()
        files.audio.close()
        files.text.close()
        folder = recording_settings.recording_dir / key
        with (folder / "audio.wav").open("r+b") as audio:
            audio.seek(40)
            audio.write(b"\0\0\0\0")  # Stale WAV length after an interrupted writer.
        with (folder / "transcript.jsonl").open("ab") as text:
            text.write(b'{"text":"unfinished')
        store.lock.close()
        store.lock = None

    await recorder.disk.call(simulate_interruption)
    recorder.worker.cancel()
    await asyncio.gather(recorder.worker, return_exceptions=True)
    recorder.disk.stop()
    await asyncio.to_thread(recorder.disk.closed.wait, 2)
    restarted = Recorder(recording_settings)
    await restarted.start()
    try:
        result = restarted.lookup(key, "pi-1")
        assert result["status"] == "incomplete"
        assert result["reason"] == "interrupted"
        assert result["transcripts"] == 1
        directory = recording_settings.recording_dir / key
        assert read_audio(directory / "audio.wav") == SPEECH * 4
        assert json.loads((directory / "transcript.jsonl").read_text())["text"] == "complete"
    finally:
        await restarted.stop()


async def test_missing_saved_data_is_not_reported_as_complete_on_restart(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 2)
    recorder.finish(record)
    await finalized(record)
    await recorder.stop()
    path = recording_settings.recording_dir / record.data["id"] / "audio.wav"
    with path.open("r+b") as audio:
        audio.truncate(44 + len(SPEECH))
    restarted = Recorder(recording_settings)
    await restarted.start()
    try:
        status = restarted.lookup(record.data["id"], "pi-1")
        assert status["status"] == "incomplete"
        assert status["reason"] == "integrity_mismatch"
    finally:
        await restarted.stop()


async def test_startup_timeout_does_not_wait_for_a_stuck_disk(recording_settings):
    entered, release = threading.Event(), threading.Event()
    recording_settings.recording_startup_seconds = 0.1
    recording_settings.recording_shutdown_seconds = 0.1

    class StalledStore(RecordingStore):
        def initialize(self):
            entered.set()
            release.wait(5)
            return super().initialize()

    recorder = Recorder(recording_settings, StalledStore)
    try:
        await asyncio.wait_for(recorder.start(), 1)
        assert entered.is_set() and not release.is_set()
        assert not recorder.available
        assert make_record(recorder).data["reason"] == "storage_unavailable"
    finally:
        release.set()
        await recorder.stop()
        await asyncio.to_thread(recorder.disk.closed.wait, 3)


def test_recording_failure_at_startup_does_not_disable_transcription(recording_settings):
    class UnavailableStore(RecordingStore):
        def initialize(self):
            raise PermissionError("private path")

    with api_client(recording_settings, UnavailableStore) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            ws.send_json({"type": "start"})
            ready = ws.receive_json()
            assert ready["recording"]["reason"] == "storage_unavailable"
            send_pcm(ws, SPEECH * 6)
            ws.send_json({"type": "finish"})
            events = collect(ws)
            assert events[-1]["type"] == "complete"
            assert any(event["type"] == "transcript" for event in events)


def test_redirected_recording_root_is_rejected(recording_settings, tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("preserve")
    link = recording_settings.recording_dir
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        link.symlink_to(target, target_is_directory=True)
    store = RecordingStore(recording_settings)
    with pytest.raises(StorageError, match="unsafe_path"):
        store.initialize()
    assert sentinel.read_text() == "preserve"
    assert list(target.iterdir()) == [sentinel]


async def test_partial_write_reservation_survives_another_sessions_recount(recording_settings):
    recorder = Recorder(recording_settings)
    await recorder.start()
    first, second = make_record(recorder), make_record(recorder, "pi-2")
    await recorder.queue.join()
    backend = recorder.disk.store
    original = backend.open_files[first.data["id"]].wav.writeframesraw

    def partial_write(pcm):
        original(pcm[:1000])
        raise OSError("partial write")

    backend.open_files[first.data["id"]].wav.writeframesraw = partial_write
    recorder.audio(first, SPEECH * 8)
    await recorder.queue.join()
    recorder.finish(second)
    await finalized(second)
    try:
        assert backend.used >= 2 * (RESERVE + 44) + 8 * len(SPEECH)
    finally:
        backend.open_files[first.data["id"]].wav.writeframesraw = original
        recorder.finish(first)
        await recorder.stop()


@pytest.mark.parametrize("failure", ["sync", "manifest"])
async def test_finalization_failure_never_claims_saved(recording_settings, monkeypatch, failure):
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH)
    await recorder.queue.join()
    store = recorder.disk.store

    def fail_sync(_):
        raise OSError("disk sync failed")

    original_manifest = store._manifest

    def fail_manifest(directory, data):
        if data["status"] == "saved":
            raise OSError("manifest write failed")
        return original_manifest(directory, data)

    with monkeypatch.context() as patch:
        if failure == "sync":
            patch.setattr("device_audio.recording_store.os.fsync", fail_sync)
        else:
            patch.setattr(store, "_manifest", fail_manifest)
        recorder.finish(record)
        try:
            receipt = await finalized(record)
            assert receipt["status"] == "incomplete"
            directory = recording_settings.recording_dir / receipt["id"]
            assert json.loads((directory / "session.json").read_text())["status"] != "saved"
            assert not store.open_files
        finally:
            await recorder.stop()
    restarted = Recorder(recording_settings)
    await restarted.start()
    try:
        assert restarted.lookup(record.data["id"], "pi-1")["status"] == "incomplete"
    finally:
        await restarted.stop()


async def test_low_disk_space_stops_recording_without_unbounded_writes(recording_settings, monkeypatch):
    from types import SimpleNamespace

    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    await recorder.queue.join()
    with monkeypatch.context() as patch:
        patch.setattr("device_audio.recording_store.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
        recorder.audio(record, SPEECH)
        recorder.finish(record)
        try:
            result = await finalized(record)
            assert result["status"] == "incomplete" and result["reason"] == "disk_space"
            assert result["audio_bytes"] == 0
        finally:
            await recorder.stop()
