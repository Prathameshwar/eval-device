"""Opt-in local webcam recording with isolated capture, private storage and bounded previews."""

import json
import multiprocessing as mp
import os
import queue
import shutil
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

from training_contracts.privacy import no_link, private_directory

MIB = 1024 * 1024
FPS = 10
PREVIEW_FPS = 5
PREVIEW_WIDTH, PREVIEW_HEIGHT = 200, 150
SEGMENT_SECONDS = 60


class VideoError(Exception):
    """Only these operator-safe messages may leave the worker."""


@dataclass(frozen=True)
class Options:
    directory: Path
    camera: int = 0
    archive_id: str | None = None
    archive_namespace: str | None = None
    max_seconds: int = 3600
    quota_bytes: int = 5120 * MIB
    min_free_bytes: int = 512 * MIB

    @classmethod
    def from_settings(cls, settings, camera):
        path = settings.resolve_path(settings.video_recording_dir)
        return cls(
            directory=Path(os.path.abspath(path)),
            camera=camera,
            max_seconds=settings.video_max_session_seconds,
            quota_bytes=settings.video_quota_mb * MIB,
            min_free_bytes=settings.video_min_free_mb * MIB,
        )


def safe_directory(path):
    # Check every ancestor before following it, including Windows junctions.
    for parent in (*reversed(path.parents), path):
        if parent.exists():
            no_link(parent)
        else:
            parent.mkdir(mode=0o700)
        if not parent.is_dir():
            raise VideoError("The video folder is not a directory.")


class Store:
    """One recorder per root; a byte budget includes existing and incomplete recordings."""

    def __init__(self, options):
        self.options = options
        self.root = options.directory
        self.lock = None
        self.used = 0

    def __enter__(self):
        safe_directory(self.root)
        private_directory(self.root)
        lock_path = self.root / ".camera.lock"
        if lock_path.exists():
            no_link(lock_path)
        self.lock = lock_path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                if not lock_path.stat().st_size:
                    self.lock.write(b"\0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise VideoError("Another desktop is recording to this video folder.") from None
        try:
            count = 0
            for directory, folders, files in os.walk(self.root, followlinks=False):
                for name in folders + files:
                    path = Path(directory) / name
                    no_link(path)
                    count += 1
                    if count > 100000:
                        raise VideoError("The video folder has too many files; archive old recordings.")
                    if path.is_file():
                        self.used += path.stat().st_size
            if reason := self.limit():
                raise VideoError(reason)
        except Exception:
            self.lock.close()
            raise
        return self

    def __exit__(self, *args):
        self.lock.close()

    def limit(self, check_disk=True):
        # Leave space for a final encoded frame, Matroska trailer and session receipt.
        if self.used >= self.options.quota_bytes - 4 * MIB:
            return "Video storage limit reached; archive old recordings before starting again."
        if check_disk and shutil.disk_usage(self.root).free < self.options.min_free_bytes:
            return "Recording stopped because free disk space is low."
        return None

    def session(self):
        now = datetime.now().astimezone()
        day = self.root
        for component in now.strftime("%Y/%m/%d").split("/"):
            day = day / component
            safe_directory(day)
            # Windows mkdir(mode=0700) can install an explicit administrator ACL;
            # replace it so every new recording inherits only account/SYSTEM access.
            private_directory(day)
        path = day / (now.strftime("%H-%M-%S") + "_" + uuid4().hex[:12])
        path.mkdir(mode=0o700)
        private_directory(path)
        return path, now.isoformat()


class BudgetFile:
    """Hard byte bound, including buffered mux writes and seeks when finalizing a file."""

    def __init__(self, path, store):
        self.file = path.open("x+b")
        self.store, self.size = store, 0

    def write(self, data):
        end = self.file.tell() + len(data)
        growth = max(0, end - self.size)
        if self.store.used + growth > self.store.options.quota_bytes - 65536:
            raise VideoError("Video storage limit reached; the last segment may be incomplete.")
        count = self.file.write(data)
        self.store.used += growth
        self.size = max(self.size, end)
        return count

    def tell(self):
        return self.file.tell()

    def seek(self, offset, whence=0):
        return self.file.seek(offset, whence)


class Segment:
    def __init__(self, path, store, shape):
        import av

        self.path = path
        self.file = BudgetFile(path.with_suffix(".mkv.part"), store)
        try:
            self.output = av.open(self.file, "w", format="matroska")
            self.stream = self.output.add_stream("mjpeg", rate=FPS)
            self.stream.width, self.stream.height = shape[1], shape[0]
            self.stream.pix_fmt = "yuvj420p"
            self.stream.codec_context.thread_count = 1
            self.stream.codec_context.time_base = Fraction(1, 1000)
            self.stream.time_base = Fraction(1, 1000)
        except Exception:
            self.file.file.close()
            raise
        self.last_pts = -1

    def write(self, pixels, elapsed):
        import av

        frame = av.VideoFrame.from_ndarray(pixels, format="bgr24")
        frame.pts = max(self.last_pts + 1, round(elapsed * 1000))
        frame.time_base = Fraction(1, 1000)
        self.last_pts = frame.pts
        for packet in self.stream.encode(frame):
            self.output.mux(packet)

    def close(self):
        try:
            for packet in self.stream.encode():
                self.output.mux(packet)
            self.output.close()
            self.file.file.flush()
            os.fsync(self.file.file.fileno())
        finally:
            with suppress(Exception):
                self.output.close()
            self.file.file.close()
        # Only a finalized recording gets the playable extension.
        from training_contracts.durability import durable_replace

        durable_replace(self.path.with_suffix(".mkv.part"), self.path)


def open_camera(index):
    import cv2

    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
    if not camera.isOpened():
        camera.release()
        raise VideoError("Cannot open camera. Check the camera number, privacy settings, or another app.")
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, FPS)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return camera


def receipt(path, data):
    temporary = path / "session.json.tmp"
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(data, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    from training_contracts.durability import durable_replace

    durable_replace(temporary, path / "session.json")


class PreviewBuffer:
    """One bounded frame, without a pipe that a terminated camera driver could leave half-written."""

    def __init__(self, context):
        self.bytes = context.RawArray("B", PREVIEW_WIDTH * PREVIEW_HEIGHT * 3 + 64)
        self.length = context.RawValue("i", 0)
        self.sequence = context.RawValue("q", 0)
        self.seen = 0

    def publish(self, frame):
        if len(frame) > len(self.bytes):
            raise VideoError("Camera preview exceeded its size limit.")
        self.sequence.value += 1  # odd means the writer is changing the buffer
        memoryview(self.bytes).cast("B")[: len(frame)] = frame
        self.length.value = len(frame)
        self.sequence.value += 1

    def take(self):
        sequence = self.sequence.value
        if sequence == self.seen or sequence % 2:
            return None
        frame = bytes(memoryview(self.bytes).cast("B")[: self.length.value])
        if self.sequence.value != sequence:
            return None
        self.seen = sequence
        return frame


def record(options, stop, previews, events, heartbeat, camera_factory=open_camera):
    """Child process entry. Fixtures inject pixels; production accepts only a camera index."""
    camera = segment = path = None
    data = {}
    error = None
    reason = "Recording stopped."
    frames = 0
    try:
        import cv2

        cv2.setNumThreads(1)
        with Store(options) as store:
            try:
                if stop.is_set():
                    return
                camera = camera_factory(options.camera)
                heartbeat.value = time.monotonic()
                if stop.is_set():
                    return
                path, started = store.session()
                data = {
                    "started_at": started,
                    "state": "recording",
                    "camera": options.camera,
                    "video_only": True,
                    "archive_id": options.archive_id,
                    "archive_namespace": options.archive_namespace,
                    "segments": [],
                    "frames": 0,
                }
                receipt(path, data)
                events.put(("started", str(path)))
                began = segment_start = time.monotonic()
                next_frame = began
                last_disk_check = last_preview = 0.0
                while not stop.is_set():
                    now = time.monotonic()
                    heartbeat.value = now
                    if now - began >= options.max_seconds:
                        reason = "Video duration limit reached."
                        break
                    check_disk = now - last_disk_check >= 1
                    if reason_limit := store.limit(check_disk=check_disk):
                        reason = reason_limit
                        break
                    if check_disk:
                        last_disk_check = now
                    ok, pixels = camera.read()
                    if stop.is_set():
                        break
                    if not ok or pixels is None:
                        raise VideoError("Camera disconnected; recording stopped.")
                    now = time.monotonic()
                    heartbeat.value = now
                    # Drivers can ignore requested sizes. Keep encoded frames and IPC bounded.
                    height, width = pixels.shape[:2]
                    if not (1 <= height <= 4320 and 1 <= width <= 7680) or pixels.ndim != 3:
                        raise VideoError("Camera returned an unsupported frame.")
                    scale = min(640 / width, 480 / height, 1)
                    size = (max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2))
                    if size != (width, height):
                        pixels = cv2.resize(pixels, size)
                    if segment is not None and now - segment_start >= SEGMENT_SECONDS:
                        completed = segment
                        segment = None
                        completed.close()
                        data["segments"].append(completed.path.name)
                        events.put(("segment", str(completed.path)))
                        data["frames"] = frames
                        receipt(path, data)
                    if segment is None:
                        segment_start = now
                        segment = Segment(
                            path / f"video-{len(data['segments']) + 1:04d}.mkv", store, pixels.shape
                        )
                    segment.write(pixels, now - segment_start)
                    frames += 1
                    if now - last_preview >= 1 / PREVIEW_FPS:
                        preview_scale = min(PREVIEW_WIDTH / size[0], PREVIEW_HEIGHT / size[1])
                        preview = cv2.resize(
                            pixels, (int(size[0] * preview_scale), int(size[1] * preview_scale))
                        )
                        rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                        ppm = f"P6\n{rgb.shape[1]} {rgb.shape[0]}\n255\n".encode() + rgb.tobytes()
                        previews.publish(ppm)
                        last_preview = now
                    next_frame = max(next_frame + 1 / FPS, now)
                    stop.wait(max(0, next_frame - time.monotonic()))
            except Exception as exc:
                error = (
                    str(exc)
                    if isinstance(exc, VideoError)
                    else "Video capture or saving failed. Check camera access and disk space."
                )
            finally:
                if segment is not None:
                    try:
                        segment.close()
                        data["segments"].append(segment.path.name)
                        events.put(("segment", str(segment.path)))
                    except Exception:
                        error = "Could not finish the last video segment; completed segments remain saved."
                if path is not None:
                    data.update(
                        state="failed" if error else "complete",
                        frames=frames,
                        ended_at=datetime.now().astimezone().isoformat(),
                        message=error or reason,
                    )
                    receipt(path, data)
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, VideoError)
            else "Cannot save video. Check the recording folder, permissions, and disk space."
        )
    finally:
        # Report saved status before release, which can block in a broken driver.
        events.put(
            (
                "finished",
                {
                    "path": str(path) if path else None,
                    "error": error,
                    "message": error or reason,
                    "segments": len(data.get("segments", [])),
                },
            )
        )
        if camera is not None:
            camera.release()


def run_worker(target, args):
    # Lower only this child, never the desktop or speech/LLM processes.
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):  # BELOW_NORMAL_PRIORITY_CLASS
            raise OSError("Could not set camera process priority")
    else:
        os.nice(10)
    target(*args)


class Recorder:
    """Polled process handle with bounded shutdown for a stalled camera driver."""

    def __init__(self, camera_factory=None):
        self.camera_factory = camera_factory
        self.process = None
        self.stop_at = None
        self.finished = False

    @property
    def busy(self):
        return self.process is not None

    def start(self, options):
        if self.busy:
            raise VideoError("Wait for the current video to finish saving.")
        context = mp.get_context("spawn")
        self.stop_event = context.Event()
        self.previews = PreviewBuffer(context)
        self.events = context.Queue(maxsize=4)
        self.heartbeat = context.RawValue("d", time.monotonic())
        self.stop_at, self.finished = None, False
        self.process = context.Process(
            target=run_worker,
            args=(
                record,
                (options, self.stop_event, self.previews, self.events, self.heartbeat)
                + ((self.camera_factory,) if self.camera_factory is not None else ()),
            ),
            daemon=True,
        )
        try:
            self.process.start()
        except Exception:
            self.process = None
            self.events.close()
            raise VideoError("Could not start the camera worker.") from None

    def stop(self):
        if self.busy and self.stop_at is None:
            self.stop_at = time.monotonic()
            self.stop_event.set()

    def abort(self):
        """Release an unresponsive worker after a monitor failure; no UI required."""
        if self.process is None:
            return
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
        if self.process.is_alive():
            raise VideoError("Camera worker did not stop")
        self.process.close()
        self.process = None
        self.events.close()

    def poll(self):
        events, preview = [], None
        if not self.busy:
            return events, preview

        def collect():
            while True:
                try:
                    event = self.events.get_nowait()
                    events.append(event)
                    if event[0] == "finished":
                        self.finished = True
                        self.stop()
                except queue.Empty:
                    break

        collect()
        preview = self.previews.take()
        now = time.monotonic()
        if self.process.is_alive() and (
            (self.stop_at is not None and now - self.stop_at > 5) or now - self.heartbeat.value > 15
        ):
            self.abort()
            if not self.finished:
                events.append(("interrupted", None))
                self.finished = True
            events.append(("idle", None))
            return events, None
        if not self.process.is_alive():
            self.process.join(timeout=0)
            collect()
            self.process.close()
            self.process = None
            self.events.close()
            if not self.finished:
                events.append(("interrupted", None))
            events.append(("idle", None))
            preview = None
        return events, preview
