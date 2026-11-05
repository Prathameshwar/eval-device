import errno
import hashlib
import io
import json
import os
import time
from uuid import uuid4

import av
import pytest

from device_video.extract import extract_frames
from device_video.privacy import StorageError
from device_video.store import Store, remux


def record(settings, start, frames):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    for frame in frames:
        store.frame(identity, frame)
    data = store.finish(identity, None, len(frames))
    store.close()
    return identity, data


def test_mux_preserves_compressed_payload_and_timestamps(start, frames):
    content = remux(frames, start)
    with av.open(io.BytesIO(content), mode="r") as source:
        packets = [packet for packet in source.demux(video=0) if packet.size]
        assert [bytes(packet) for packet in packets] == [frame.jpeg for frame in frames]
        assert [round(float(p.pts * p.time_base) * 1e6) for p in packets] == [f.timestamp_us for f in frames]
    with av.open(io.BytesIO(content), mode="r") as source:
        assert len(list(source.decode(video=0))) == len(frames)


def test_roundtrip_segments_recovery_and_offline_extraction(settings, start, frames, tmp_path):
    identity, data = record(settings, start, frames)
    assert data["status"] == "saved" and data["finalized"]
    assert data["segments"] == 3 and data["saved_frames"] == 5
    store = Store(settings)
    store.initialize()
    assert store.records[identity]["status"] == "saved"
    store.close()
    result = extract_frames(settings, identity, tmp_path / "images", every=2)
    assert result["frames"] == 3 and result["status"] == "complete"
    assert all(path.read_bytes() == frames[0].jpeg for path in (tmp_path / "images").glob("*.jpg"))
    assert json.loads((tmp_path / "images/extraction.json").read_bytes()) == result


def test_extraction_caps_and_requires_completed_stopped_store(settings, start, frames, tmp_path):
    identity, _ = record(settings, start, frames)
    result = extract_frames(settings, identity, tmp_path / "limited", every=1, max_frames=2)
    assert result["status"] == "limited" and result["frames"] == 2
    store = Store(settings)
    store.initialize()
    try:
        with pytest.raises((OSError, StorageError)):
            extract_frames(settings, identity, tmp_path / "active")
        assert not (tmp_path / "active").exists()
        with pytest.raises(ValueError):
            extract_frames(settings, identity, settings.recording_dir / "images")
    finally:
        store.close()


def test_crash_recovery_and_hash_validation(settings, start, frames, tmp_path):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    store.frame(identity, frames[0])
    store.flush(identity)
    store.close()
    recovered = Store(settings)
    recovered.initialize()
    assert recovered.records[identity]["status"] == "incomplete"
    assert recovered.records[identity]["finalized"]
    recovered.close()
    with pytest.raises(StorageError):
        extract_frames(settings, identity, tmp_path / "bad")
    identity, _ = record(settings, start, frames)
    video = settings.recording_dir / identity / "segment-000000.mkv"
    data = bytearray(video.read_bytes())
    data[-1] ^= 1
    video.write_bytes(data)
    with pytest.raises(StorageError, match="integrity"):
        extract_frames(settings, identity, tmp_path / "corrupt")
    assert json.loads((tmp_path / "corrupt/extraction.json").read_bytes())["status"] == "incomplete"


def test_safe_retry_after_successful_uncertain_replace(settings, start, frames, monkeypatch):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    original = os.replace
    failures = []

    def uncertain(source, target):
        original(source, target)
        if str(target).endswith(".mkv") and not failures:
            failures.append(True)
            raise OSError(errno.EIO, "uncertain")

    monkeypatch.setattr(os, "replace", uncertain)
    for frame in frames:
        store.frame(identity, frame)
    data = store.finish(identity, None, len(frames))
    assert data["saved_frames"] == len(frames) and store.retry.retries == 1
    assert not list((settings.recording_dir / identity).glob("*.part"))
    store.close()


def test_permanent_io_is_not_retried(settings, monkeypatch, tmp_path):
    store = Store(settings)
    calls = []

    def full(*args):
        calls.append(1)
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(os, "replace", full)
    with pytest.raises(OSError):
        store.atomic(tmp_path / "file", b"data")
    assert len(calls) == 1 and store.retry.retries == 0


def test_quota_protects_active_and_evicts_finished(settings, start, frames):
    settings = settings.model_copy(update={"recording_max_sessions": 1})
    store = Store(settings)
    store.initialize()
    first = str(uuid4())
    store.start(first, "pi-1", start)
    with pytest.raises(StorageError, match="quota"):
        store.start(str(uuid4()), "pi-1", start)
    store.frame(first, frames[0])
    store.finish(first, None, 1)
    second = str(uuid4())
    store.start(second, "pi-1", start)
    assert first not in store.records and not (settings.recording_dir / first).exists()
    assert sum(store.charges.values()) <= settings.recording_max_bytes
    store.close()


def test_retention_and_accounted_pending_bytes(settings, start, frames):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    store.frame(identity, frames[0])
    reserved = store.charges[identity]
    assert reserved > len(frames[0].jpeg) + 65536
    store.records[identity]["created_at"] = time.time() - settings.retention_hours * 3600 - 1
    store.prune()
    assert store.charges[identity] == reserved
    store.finish(identity, None, 1)
    store.prune()
    assert identity not in store.records
    store.close()


def test_unmanaged_and_hardlinked_files_refused(settings, tmp_path, start, frames):
    settings.recording_dir.mkdir()
    (settings.recording_dir / "unrelated.txt").write_text("preserve")
    store = Store(settings)
    with pytest.raises(StorageError, match="unmanaged"):
        store.initialize()
    assert (settings.recording_dir / "unrelated.txt").read_text() == "preserve"
    settings = settings.model_copy(update={"recording_dir": tmp_path / "safe"})
    identity, _ = record(settings, start, frames)
    original = settings.recording_dir / identity / "segment-000000.mkv"
    os.link(original, tmp_path / "link.mkv")
    store = Store(settings)
    try:
        with pytest.raises(StorageError, match="unsafe"):
            store.initialize()
    finally:
        store.close()


def test_sidecar_hash_matches_file(settings, start, frames):
    identity, _ = record(settings, start, frames)
    directory = settings.recording_dir / identity
    for path in directory.glob("segment-*.json"):
        data = json.loads(path.read_bytes())
        assert data["sha256"] == hashlib.sha256(path.with_suffix(".mkv").read_bytes()).hexdigest()


def test_session_retention_only_shortens_server_policy(settings, start, frames, monkeypatch):
    import device_video.store as module

    settings.retention_hours = 2
    for requested, expected in [(0.5, 1800), (4.0, 7200)]:
        start.retention_hours = requested
        identity, data = record(settings, start, frames)
        assert abs(data["expires_at"] - data["created_at"] - expected) < 1
        store = Store(settings)
        store.initialize()
        monkeypatch.setattr(module.time, "time", lambda data=data: data["expires_at"] + 1)
        store.prune()
        assert identity not in store.records
        store.close()
        monkeypatch.undo()
