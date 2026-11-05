import asyncio
import threading
import time
from uuid import uuid4

import pytest

from device_video.app import disk_result
from device_video.privacy import StorageError
from device_video.recorder import Recorder


def test_slow_disk_bounds_queue_and_preserves_control_slot(settings, start, frames, monkeypatch):
    settings = settings.model_copy(update={"queue_items": 4, "max_sessions": 1, "segment_seconds": 10})
    recorder = Recorder(settings)
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    entered, release = threading.Event(), threading.Event()
    original = recorder.store.frame

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(recorder.store, "frame", blocked)
    try:
        began = time.monotonic()
        for frame in frames[:4]:
            recorder.submit("frame", identity, frame, weight=len(frame.jpeg))
        assert time.monotonic() - began < 0.2 and entered.wait(1)
        assert recorder.queued_items == 4
        assert recorder.queued_bytes == sum(len(frame.jpeg) for frame in frames[:4])
        with pytest.raises(StorageError, match="backpressure"):
            recorder.submit("frame", identity, frames[4], weight=len(frames[4].jpeg))
        completion = recorder.submit("finish", identity, "queue_full", 4)
        with pytest.raises(StorageError):
            recorder.submit("start", str(uuid4()), "pi-1", start)
        release.set()
        data = completion.result(3)
        assert data["status"] == "incomplete" and data["saved_frames"] == 4
        assert recorder.queued_items == recorder.queued_bytes == 0
    finally:
        release.set()
        recorder.stop()


def test_segment_failure_latches_and_keeps_committed_prefix(settings, start, frames, monkeypatch):
    recorder = Recorder(settings)
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    original = recorder.store.atomic

    def failed(path, content, **kwargs):
        if path.name == "segment-000001.mkv":
            raise OSError("disk failed")
        return original(path, content, **kwargs)

    monkeypatch.setattr(recorder.store, "atomic", failed)
    try:
        for frame in frames:
            try:
                recorder.submit("frame", identity, frame, weight=len(frame.jpeg)).result(3)
            except StorageError:
                break
        data = recorder.submit("finish", identity, None, 5).result(3)
        assert data["status"] == "incomplete" and data["finalized"]
        assert data["saved_frames"] == 2
        assert (settings.recording_dir / identity / "segment-000000.mkv").exists()
    finally:
        recorder.stop()


def test_manifest_failure_never_claims_durable_completion(settings, start, frames, monkeypatch):
    recorder = Recorder(settings)
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    recorder.submit("frame", identity, frames[0], weight=len(frames[0].jpeg)).result(3)
    original = recorder.store.manifest

    def failed(path, data):
        if data["finalized"]:
            raise OSError("cannot finalize")
        return original(path, data)

    monkeypatch.setattr(recorder.store, "manifest", failed)
    try:
        with pytest.raises(StorageError):
            recorder.submit("finish", identity, None, 1).result(3)
        data = recorder.status(identity, "pi-1")
        assert data["status"] == "incomplete" and not data["finalized"]
    finally:
        recorder.stop()


@pytest.mark.asyncio
async def test_timeout_does_not_cancel_disk_work(settings, start, monkeypatch):
    recorder = Recorder(settings)
    await disk_result(recorder.started, 3)
    release, entered = threading.Event(), threading.Event()
    original = recorder.store.start

    def blocked(*args):
        entered.set()
        release.wait(3)
        return original(*args)

    monkeypatch.setattr(recorder.store, "start", blocked)
    future = recorder.submit("start", str(uuid4()), "pi-1", start)
    try:
        with pytest.raises(TimeoutError):
            await disk_result(future, 0.01)
        assert not future.cancelled()
        release.set()
        data = await disk_result(future, 3)
        assert data["status"] == "pending"
    finally:
        release.set()
        await asyncio.to_thread(recorder.stop)


def test_idle_shutdown_wakes_writer_immediately(settings):
    recorder = Recorder(settings.model_copy(update={"segment_seconds": 10}))
    recorder.started.result(3)
    began = time.monotonic()
    recorder.stop()
    assert time.monotonic() - began < 0.5 and not recorder.thread.is_alive()
