import errno
import json
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest

from device_video.cli import init_local
from device_video.privacy import StorageError
from device_video.recorder import Recorder
from device_video.retries import DiskRetries
from device_video.store import Store


def test_private_settings_not_overwritten_or_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    init_local()
    content = (tmp_path / ".env").read_bytes()
    assert b"VIDEO_CLIENT_TOKENS=" in content and "token" not in capsys.readouterr().out.lower()
    with pytest.raises(FileExistsError):
        init_local()
    assert (tmp_path / ".env").read_bytes() == content


def test_actual_windows_acl_excludes_other_principals(settings):
    if sys.platform != "win32":
        pytest.skip("Windows ACL assertion")
    store = Store(settings)
    store.initialize()
    try:
        command = "$p=Get-Acl -LiteralPath $env:VIDEO_ACL_TEST; $p.Access | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=True,
            env=os.environ | {"VIDEO_ACL_TEST": str(settings.recording_dir)},
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sids = result.stdout.split()
        assert len(sids) == 2 and "S-1-5-18" in sids
        assert not {"S-1-1-0", "S-1-5-32-545", "S-1-5-11"}.intersection(sids)
    finally:
        store.close()


def test_bounded_transient_retries(monkeypatch):
    policy = DiskRetries(3, 0.001)
    calls = []
    monkeypatch.setattr("device_video.retries.time.sleep", lambda delay: None)

    def failed():
        calls.append(True)
        raise OSError(errno.EIO, "temporary")

    with pytest.raises(OSError):
        policy.run(failed)
    assert len(calls) == 3 and policy.retries == 2 and policy.exhausted == 1


def test_queue_byte_cap_includes_inflight_work(settings, start, frames, monkeypatch):
    recorder = Recorder(settings.model_copy(update={"queue_bytes": len(frames[0].jpeg)}))
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    entered, release = threading.Event(), threading.Event()
    original = recorder.store.frame

    def blocked(*args):
        entered.set()
        release.wait(3)
        return original(*args)

    monkeypatch.setattr(recorder.store, "frame", blocked)
    try:
        recorder.submit("frame", identity, frames[0], weight=len(frames[0].jpeg))
        assert entered.wait(1)
        with pytest.raises(StorageError):
            recorder.submit("frame", identity, frames[1], weight=len(frames[1].jpeg))
    finally:
        release.set()
        recorder.stop()


def test_stalled_shutdown_bounded_and_lock_held_until_exit(settings, start, monkeypatch):
    settings = settings.model_copy(update={"disk_wait_seconds": 0.05})
    recorder = Recorder(settings)
    recorder.started.result(3)
    entered, release = threading.Event(), threading.Event()
    original = recorder.store.start

    def blocked(*args):
        entered.set()
        release.wait(3)
        return original(*args)

    monkeypatch.setattr(recorder.store, "start", blocked)
    recorder.submit("start", str(uuid4()), "pi-1", start)
    assert entered.wait(1)
    try:
        began = time.monotonic()
        recorder.stop()
        assert time.monotonic() - began < 0.3 and recorder.thread.is_alive()
        other = Store(settings)
        try:
            with pytest.raises(OSError):
                other.initialize()
        finally:
            other.close()
    finally:
        release.set()
        recorder.thread.join(3)
    assert not recorder.thread.is_alive()


def test_periodic_flush_does_not_wait_for_next_network_frame(settings, start, frames):
    recorder = Recorder(settings.model_copy(update={"segment_seconds": 0.1}))
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    recorder.submit("frame", identity, frames[0], weight=len(frames[0].jpeg)).result(3)
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            data = recorder.status(identity, "pi-1")
            if data["saved_frames"] == 1:
                break
            time.sleep(0.01)
        assert data["saved_frames"] == 1 and not data["finalized"]
    finally:
        recorder.stop()


def test_quota_failure_preserves_reserved_prefix(settings, start, frames):
    settings = settings.model_copy(update={"segment_seconds": 10})
    recorder = Recorder(settings)
    recorder.started.result(3)
    identity = str(uuid4())
    recorder.submit("start", identity, "pi-1", start).result(3)
    recorder.submit("frame", identity, frames[0], weight=len(frames[0].jpeg)).result(3)
    settings.recording_max_bytes = 4096 + sum(recorder.store.charges.values())
    try:
        with pytest.raises(StorageError, match="quota"):
            recorder.submit("frame", identity, frames[1], weight=len(frames[1].jpeg)).result(3)
        data = recorder.submit("finish", identity, None, 2).result(3)
        assert data["status"] == "incomplete" and data["saved_frames"] == 1
    finally:
        recorder.stop()


def test_recovery_detects_missing_sidecar(settings, start, frames):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    store.frame(identity, frames[0])
    store.finish(identity, None, 1)
    path = settings.recording_dir / identity / "segment-000000.json"
    path.unlink()
    store.close()
    recovered = Store(settings)
    try:
        recovered.initialize()
        assert recovered.records[identity]["status"] == "incomplete"
        assert recovered.records[identity]["reason"] == "integrity_mismatch"
        assert json.loads((path.parent / "session.json").read_bytes())["finalized"]
    finally:
        recovered.close()


def test_restart_cleans_abandoned_initial_manifest_only(settings):
    store = Store(settings)
    store.initialize()
    store.close()
    empty = settings.recording_dir / str(uuid4())
    empty.mkdir()
    partial = settings.recording_dir / str(uuid4())
    partial.mkdir()
    (partial / "session.json.part").write_bytes(b'{"format":')
    store = Store(settings)
    try:
        store.initialize()
        assert not empty.exists() and not partial.exists()
    finally:
        store.close()
    suspicious = settings.recording_dir / str(uuid4())
    suspicious.mkdir()
    (suspicious / "segment-000000.mkv").write_bytes(b"keep")
    store = Store(settings)
    try:
        with pytest.raises(StorageError, match="invalid_manifest"):
            store.initialize()
        assert (suspicious / "segment-000000.mkv").read_bytes() == b"keep"
    finally:
        store.close()


def test_windows_junction_root_is_refused(settings, tmp_path):
    if sys.platform != "win32":
        pytest.skip("Windows reparse assertion")
    real = tmp_path / "real"
    real.mkdir()
    command = (
        "New-Item -ItemType Junction -Path $env:VIDEO_TEST_LINK -Target $env:VIDEO_TEST_TARGET | Out-Null"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        env=os.environ | {"VIDEO_TEST_LINK": str(settings.recording_dir), "VIDEO_TEST_TARGET": str(real)},
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    store = Store(settings)
    with pytest.raises(StorageError, match="unsafe"):
        store.initialize()
    assert not list(real.iterdir())


def test_restart_recounts_after_replacing_interrupted_manifest(settings, start, frames):
    store = Store(settings)
    store.initialize()
    identity = str(uuid4())
    store.start(identity, "pi-1", start)
    store.frame(identity, frames[0])
    store.flush(identity)
    store.finish(identity, "disconnected", 1)
    store.close()
    directory = settings.recording_dir / identity
    (directory / "session.json.part").write_bytes(b'{"status":')
    recovered = Store(settings)
    try:
        recovered.initialize()
        assert recovered.records[identity]["status"] == "incomplete"
        assert recovered.records[identity]["reason"] == "disconnected"
        assert not (directory / "session.json.part").exists()
        assert recovered.charges[identity] > sum(p.stat().st_size for p in directory.iterdir())
    finally:
        recovered.close()
