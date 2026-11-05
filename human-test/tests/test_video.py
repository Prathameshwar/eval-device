"""Native encoder/filesystem tests use generated frames; no physical camera is opened."""

import csv
import json
import multiprocessing as mp
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace

import av
import numpy as np
import pytest
from training_client import video
from training_client.video import MIB, BudgetFile, Options, PreviewBuffer, Recorder, Store, VideoError

from human_test.camera_view import CameraView
from human_test.config import ROOT, Settings


def test_configured_recording_limits_do_not_populate_archive_identity(tmp_path):
    settings = Settings(
        _env_file=None,
        video_recording_dir=tmp_path,
        video_max_session_seconds=60,
        video_quota_mb=128,
        video_min_free_mb=64,
    )
    options = video.Options.from_settings(settings, 2)
    assert options.camera == 2
    assert options.archive_id is None and options.archive_namespace is None
    assert (options.max_seconds, options.quota_bytes, options.min_free_bytes) == (
        60,
        128 * 1024 * 1024,
        64 * 1024 * 1024,
    )


class Frames:
    def __init__(self, stop, count=4, fail=False):
        self.stop, self.count, self.fail = stop, count, fail
        self.reads, self.released = 0, False

    def read(self):
        self.reads += 1
        if self.reads > self.count:
            if self.fail:
                return False, None
            self.stop.set()
        pixels = np.zeros((240, 320, 3), dtype=np.uint8)
        pixels[:, :, 2] = 190
        pixels[50:90, self.reads * 10 : self.reads * 10 + 20] = (10, 230, 20)
        return True, pixels

    def release(self):
        self.released = True


def run_recording(tmp_path, count=4, fail=False, **kwargs):
    stop = threading.Event()
    source = Frames(stop, count, fail)
    events = queue.Queue()
    preview = PreviewBuffer(mp.get_context("spawn"))
    video.record(
        Options(tmp_path, **kwargs),
        stop,
        preview,
        events,
        SimpleNamespace(value=0),
        camera_factory=lambda index: source,
    )
    results = []
    while not events.empty():
        results.append(events.get_nowait())
    return source, results, preview.take()


def test_recording_dates_unique_names_private_playable_and_preview(tmp_path):
    before = datetime.now().astimezone()
    source, events, preview = run_recording(tmp_path)
    after = datetime.now().astimezone()
    result = events[-1][1]
    assert source.released and result["error"] is None and result["segments"] == 1
    path = next(tmp_path.glob("*/*/*/*"))
    assert preview.startswith(b"P6\n200 150\n255\n")
    info = json.loads((path / "session.json").read_text())
    assert info["state"] == "complete" and info["frames"] == 4
    started = datetime.fromisoformat(info["started_at"])
    assert started.utcoffset() is not None and before <= started <= after
    # The recording may start across a minute/day boundary after this test begins.
    assert path.parent.relative_to(tmp_path).as_posix() == started.strftime("%Y/%m/%d")
    assert path.name.startswith(started.strftime("%H-%M-%S_"))
    assert not list(path.glob("*.part"))
    with av.open(str(path / "video-0001.mkv")) as recording:
        frames = list(recording.decode(video=0))
        assert len(frames) == 4
        assert (frames[0].width, frames[0].height) == (320, 240)
        assert frames[0].to_ndarray(format="rgb24")[0, 0, 0] > 160
        offsets = [float(frame.pts * frame.time_base) for frame in frames]
        assert all(b > a for a, b in zip(offsets, offsets[1:], strict=False))
    run_recording(tmp_path, count=1)
    assert len(list(tmp_path.glob("*/*/*/*"))) == 2
    if os.name != "nt":
        assert tmp_path.stat().st_mode & 0o077 == 0


def test_segment_rotation_and_disconnection_keep_completed_video(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "SEGMENT_SECONDS", 0.15)
    source, events, _ = run_recording(tmp_path, count=5, fail=True)
    result = events[-1][1]
    assert source.released and "disconnected" in result["error"]
    assert result["segments"] >= 2
    receipts = list(tmp_path.glob("*/*/*/*/session.json"))
    info = json.loads(receipts[0].read_text())
    assert info["state"] == "failed" and info["frames"] == 5
    count = 0
    for name in info["segments"]:
        with av.open(str(receipts[0].parent / name)) as recording:
            count += len(list(recording.decode(video=0)))
    assert count == 5


def test_missing_camera_has_no_video_and_no_sensitive_error(tmp_path):
    def fail(index):
        raise OSError("sensitive driver details")

    events = queue.Queue()
    video.record(
        Options(tmp_path),
        threading.Event(),
        PreviewBuffer(mp.get_context("spawn")),
        events,
        SimpleNamespace(value=0),
        camera_factory=fail,
    )
    result = events.get_nowait()[1]
    assert result["error"] and "sensitive" not in result["error"]
    assert not result["path"] and not list(tmp_path.rglob("*.mkv"))


def test_stop_before_open_never_touches_camera(tmp_path):
    stop, events = threading.Event(), queue.Queue()
    stop.set()
    video.record(
        Options(tmp_path),
        stop,
        None,
        events,
        SimpleNamespace(value=0),
        camera_factory=lambda _: pytest.fail("opened camera after stop"),
    )
    assert events.get_nowait()[1]["segments"] == 0


def test_duration_limit_finishes_and_releases_camera(tmp_path):
    source, events, _ = run_recording(tmp_path, count=100, max_seconds=0.25)
    assert source.released
    result = events[-1][1]
    assert result["error"] is None and "duration limit" in result["message"]
    assert result["segments"] == 1


def test_failed_finalization_keeps_partial_file_and_reports_failure(tmp_path, monkeypatch):
    real_fsync = video.os.fsync
    calls = 0

    def fail_on_segment(fd):
        nonlocal calls
        calls += 1
        if calls == 2:  # first fsync is the initial receipt
            raise OSError("disk failure details")
        real_fsync(fd)

    monkeypatch.setattr(video.os, "fsync", fail_on_segment)
    source, events, _ = run_recording(tmp_path, count=1)
    result = events[-1][1]
    assert source.released and result["error"] and result["segments"] == 0
    assert len(list(tmp_path.rglob("*.mkv.part"))) == 1 and not list(tmp_path.rglob("*.mkv"))
    assert "disk failure details" not in result["error"]
    assert json.loads(next(tmp_path.rglob("session.json")).read_text())["state"] == "failed"


def test_quota_low_disk_and_exclusive_writer(tmp_path, monkeypatch):
    options = Options(tmp_path, quota_bytes=8 * MIB)
    with Store(options) as store:
        with pytest.raises(VideoError, match="Another desktop"):
            with Store(options):
                pass
        path, _ = store.session()
        output = BudgetFile(path / "test.part", store)
        try:
            output.write(b"a" * 1024)
            used = store.used
            output.seek(0)
            output.write(b"b" * 1024)
            assert store.used == used
            with pytest.raises(VideoError, match="storage limit"):
                output.write(b"x" * (8 * MIB))
            assert output.size == 1024
        finally:
            output.file.close()
    monkeypatch.setattr(video.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(VideoError, match="free disk"):
        with Store(options):
            pass


def test_existing_recordings_count_toward_quota_and_are_not_deleted(tmp_path):
    existing = tmp_path / "previous.mkv.part"
    with existing.open("wb") as output:
        output.truncate(5 * MIB)
    with pytest.raises(VideoError, match="storage limit"):
        with Store(Options(tmp_path, quota_bytes=8 * MIB)):
            pass
    assert existing.stat().st_size == 5 * MIB


def test_hardlink_in_store_rejected(tmp_path):
    source = tmp_path / "one"
    source.write_bytes(b"existing")
    os.link(source, tmp_path / "two")
    with pytest.raises(Exception, match="unsafe_path"):
        with Store(Options(tmp_path)):
            pass


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL inheritance regression")
def test_windows_date_folders_and_media_allow_only_account_and_system(tmp_path):
    run_recording(tmp_path, count=1)
    identity = subprocess.check_output(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=5,
    )
    sid = next(csv.reader([identity.strip()]))[1]
    script = (
        "Get-ChildItem -LiteralPath $env:HUMAN_ACL_TEST_PATH -Recurse | ForEach-Object { "
        "(Get-Acl -LiteralPath $_.FullName).Access | ForEach-Object { "
        "$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value } }"
    )
    allowed = subprocess.check_output(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        text=True,
        env={**os.environ, "HUMAN_ACL_TEST_PATH": str(tmp_path)},
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=15,
    )
    assert set(allowed.split()) == {sid, "S-1-5-18"}


def test_relative_path_is_independent_of_launcher_directory():
    settings = Settings(_env_file=None, video_recording_dir=".local/custom-video")
    assert Options.from_settings(settings, 0).directory == ROOT / ".local/custom-video"


def test_preview_overwrites_old_frames_without_backlog():
    buffer = PreviewBuffer(mp.get_context("spawn"))
    buffer.publish(b"first")
    buffer.publish(b"latest")
    assert buffer.take() == b"latest" and buffer.take() is None
    buffer.sequence.value += 1  # interrupted writer
    assert buffer.take() is None


def synthetic_worker(options, stop, previews, events, heartbeat):
    video.record(options, stop, previews, events, heartbeat, camera_factory=lambda _: Frames(stop, 5))


def stalled_worker(options, stop, previews, events, heartbeat):
    time.sleep(30)


def test_stalled_worker_that_ignores_terminate_is_killed(monkeypatch):
    import queue
    from types import SimpleNamespace
    from unittest.mock import Mock

    alive = [True]
    process = SimpleNamespace(
        is_alive=lambda: alive[0],
        terminate=Mock(),
        kill=Mock(side_effect=lambda: alive.__setitem__(0, False)),
        join=Mock(),
        close=Mock(),
    )
    recorder = Recorder()
    recorder.process = process
    recorder.stop_at = 1
    recorder.heartbeat = SimpleNamespace(value=1)
    recorder.previews = SimpleNamespace(take=lambda: None)
    recorder.events = SimpleNamespace(get_nowait=Mock(side_effect=queue.Empty), close=Mock())
    monkeypatch.setattr(video.time, "monotonic", lambda: 100)
    events, preview = recorder.poll()
    assert not recorder.busy
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert ("interrupted", None) in events and ("idle", None) in events


def wait_recorder(recorder, limit=10):
    events = []
    deadline = time.monotonic() + limit
    while recorder.busy and time.monotonic() < deadline:
        update, _ = recorder.poll()
        events.extend(update)
        time.sleep(0.025)
    assert not recorder.busy
    return events


def test_real_spawn_lifecycle_and_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "record", synthetic_worker)
    recorder = Recorder()
    for _ in range(2):
        recorder.start(Options(tmp_path))
        with pytest.raises(VideoError, match="Wait"):
            recorder.start(Options(tmp_path))
        events = wait_recorder(recorder)
        result = next(value for kind, value in events if kind == "finished")
        assert result["error"] is None and result["segments"] == 1
        assert events[-1][0] == "idle"


def test_stalled_driver_terminated_without_blocking_ui(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "record", stalled_worker)
    recorder = Recorder()
    recorder.start(Options(tmp_path))
    recorder.stop()
    recorder.stop_at -= 6
    assert any(kind == "interrupted" for kind, _ in wait_recorder(recorder, 3))


def test_native_tk_checkbox_preview_stop_and_error(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "record", synthetic_worker)
    root = tk.Tk()
    root.withdraw()
    view = CameraView(root, Settings(_env_file=None, video_recording_dir=tmp_path))
    view.pack()
    try:
        assert not view.enabled.get() and not view.recorder.busy
        view.checkbox.invoke()
        deadline = time.monotonic() + 10
        saw_preview = False
        while view.recorder.busy and time.monotonic() < deadline:
            root.update()
            view.poll()
            saw_preview |= view.photo is not None
            time.sleep(0.025)
        assert saw_preview and not view.recorder.busy
        view.poll()  # The worker completes independently of the UI notification pump.
        assert not view.enabled.get() and "1 video file(s) saved" in view.status.get()
        assert view.path.get().startswith(str(tmp_path))
        view.camera.set("invalid")
        view.checkbox.invoke()
        assert not view.recorder.busy and "camera number" in view.status.get()
        view.camera.set("0")
        view.checkbox.invoke()
        view.checkbox.invoke()
        assert not view.enabled.get()
        deadline = time.monotonic() + 10
        while view.recorder.busy and time.monotonic() < deadline:
            view.poll()
            time.sleep(0.025)
        assert not view.recorder.busy
        view.close()
        view.toggle()
        assert not view.recorder.busy and view.closing
        assert str(view.checkbox.cget("state")) == "disabled"
    finally:
        view.stop()
        wait_recorder(view.recorder)
        root.destroy()
