"""Single bounded daemon writer; no unbounded executor or sensitive log output."""

import asyncio
import errno
import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from uuid import UUID

from training_contracts import canonical
from training_contracts.privacy import StorageError, no_link, private_directory
from training_contracts.retries import DiskRetries


class Store:
    def __init__(self, root: Path, maximum: int):
        self.root, self.maximum = root.absolute(), maximum
        self.queue: queue.Queue[Any] = queue.Queue(maxsize=2)
        self.poisoned = False
        self.stopping = threading.Event()
        self.retry = DiskRetries(3, 0.03)
        self.started: Future[Any] = Future()
        self.thread = threading.Thread(target=self.run, daemon=True, name="training-disk")
        self.thread.start()

    async def ready(self):
        await self.wait(self.started)

    async def wait(self, future):
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), 5)
        except TimeoutError:
            self.poisoned = True
            raise StorageError("disk_timeout") from None

    async def call(self, method, *args):
        if self.poisoned or self.stopping.is_set():
            raise StorageError("disk_unavailable")
        future: Future[Any] = Future()
        try:
            self.queue.put_nowait((future, method, args))
        except queue.Full:
            raise StorageError("disk_busy") from None
        return await self.wait(future)

    def run(self):
        lock = None
        try:
            for p in (*reversed(self.root.parents), self.root):
                if p.exists():
                    no_link(p)
            self.root.mkdir(parents=True, exist_ok=True)
            private_directory(self.root)
            marker = self.root / ".training-store"
            if not marker.exists():
                if list(self.root.iterdir()):
                    raise StorageError("unowned_store")
                marker.write_text("training-v1")
            no_link(marker)
            if marker.read_text() != "training-v1":
                raise StorageError("unowned_store")
            lock_path = self.root / ".writer.lock"
            if lock_path.exists():
                no_link(lock_path)
            lock = lock_path.open("a+b")
            if sys.platform == "win32":
                import msvcrt

                if not lock_path.stat().st_size:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.cleanup()
            self.started.set_result(True)
            while True:
                try:
                    item = self.queue.get(timeout=0.2)
                except queue.Empty:
                    if self.stopping.is_set():
                        return
                    continue
                if item is None:
                    return
                future, method, args = item
                try:
                    future.set_result(getattr(self, "do_" + method)(*args))
                except Exception:
                    future.set_exception(StorageError("storage_failed"))
        except Exception:
            self.poisoned = True
            if not self.started.done():
                self.started.set_exception(StorageError("storage_start_failed"))
        finally:
            if lock:
                lock.close()

    def directory(self, sid):
        p = self.root / str(UUID(str(sid)))
        if p.exists():
            no_link(p)
        return p

    def cleanup(self):
        for p in list(self.root.iterdir()):
            no_link(p)
            if p.name.startswith("."):
                continue
            self.directory(p.name)
            metadata = p / "session.json"
            if not metadata.exists():
                remnants = list(p.iterdir())
                if any(f.name != "session.json.part" for f in remnants):
                    raise StorageError("incomplete_store")
                for f in remnants:
                    no_link(f)
                    if not f.is_file() or f.stat().st_size > 262144:
                        raise StorageError("incomplete_store")
                    f.unlink()
                p.rmdir()
                continue
            no_link(metadata)
            if metadata.stat().st_size > 262144:
                raise StorageError("invalid_store")
            data = json.loads(metadata.read_bytes())
            if data["expires_at"] <= time.time():
                for file in p.iterdir():
                    no_link(file)
                    if not file.is_file():
                        raise StorageError("unsafe_store")
                    file.unlink()
                p.rmdir()

    def do_save(self, data, files=None):
        self.cleanup()
        files = files or {}
        directory = self.directory(data["id"])
        if not directory.exists():
            if len(list(self.root.iterdir())) >= 102:
                raise StorageError("session_quota")
            directory.mkdir()
        content = {**files, "session.json": canonical(data).encode("utf-8")}
        total = 0
        for p in self.root.rglob("*"):
            no_link(p)
            if p.is_file():
                total += p.stat().st_size
        # Includes headroom for replacement and crash remnants.
        if total + sum(len(b) for b in content.values()) > self.maximum:
            raise StorageError("storage_quota")
        for name, body in content.items():
            if (
                Path(name).name != name
                or not name.endswith((".wav", ".json", ".jpg"))
                or len(body) > 4_000_000
            ):
                raise StorageError("invalid_artifact")
            dest = directory / name
            temporary = directory / (name + ".part")
            for p in (dest, temporary):
                if p.exists():
                    no_link(p)

            def write(dest=dest, temporary=temporary, body=body):
                # Replacing the same complete bytes is safe after an uncertain rename.
                for path in (dest.parent, dest, temporary):
                    if path.exists() or path.is_symlink():
                        no_link(path)
                if dest.exists() and dest.stat().st_size == len(body) and dest.read_bytes() == body:
                    return
                with temporary.open("wb") as handle:
                    offset = 0
                    while offset < len(body):
                        count = handle.write(body[offset:])
                        if not count:
                            raise OSError(errno.EIO, "write made no progress")
                        offset += count
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, dest)
                if sys.platform != "win32":
                    descriptor = os.open(dest.parent, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)

            self.retry.run(write)
        return True

    def do_read(self, sid, name="session.json"):
        p = self.directory(sid) / name
        if Path(name).name != name:
            raise StorageError("invalid_artifact")
        no_link(p)
        if p.stat().st_size > 4_000_000:
            raise StorageError("artifact_too_large")
        return p.read_bytes()

    def stop(self):
        self.stopping.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            self.poisoned = True

    def do_cleanup(self):
        self.cleanup()

    def video_segment(self, data, root, owner, rid, index):
        import hashlib

        if not any(v["id"] == rid for v in data["video"]):
            raise StorageError("recording_not_owned")
        directory = Path(root).absolute() / str(UUID(rid))
        for path in (*reversed(directory.parents), directory):
            no_link(path)
        manifest = directory / "session.json"
        no_link(manifest)
        if manifest.stat().st_size > 65536:
            raise StorageError("invalid_manifest")
        record = json.loads(manifest.read_bytes())
        if (
            record["id"] != rid
            or record["capture_id"] != data["id"]
            or record["client_id"] != owner
            or not record["finalized"]
            or record["status"] != "saved"
            or record.get("expires_at", 0) <= time.time()
        ):
            raise StorageError("completed_owned_recording_required")
        if index is None:
            return record
        if not 0 <= index < min(record["segments"], 1000):
            raise StorageError("segment_not_found")
        metadata = directory / f"segment-{index:06d}.json"
        video = directory / f"segment-{index:06d}.mkv"
        for path in (metadata, video):
            no_link(path)
        if metadata.stat().st_size > 65536 or video.stat().st_size > 8454144:
            raise StorageError("segment_limit")
        meta, content = json.loads(metadata.read_bytes()), video.read_bytes()
        if hashlib.sha256(content).hexdigest() != meta["sha256"]:
            raise StorageError("integrity_mismatch")
        return meta, content

    def do_video(self, data, root, owner, rid, index=None):
        value = self.video_segment(data, root, owner, rid, index)
        return value if index is None else value[1]

    def do_prepare(self, data, root, owner):
        import io

        import av

        if data["status"] in {"warming", "active"}:
            raise StorageError("completed_session_required")
        files: dict[str, bytes] = {}
        frames: list[dict[str, Any]] = []
        size = 0
        for video in data["video"]:
            record = self.video_segment(data, root, owner, video["id"], None)
            if record["segments"] > 1000:
                raise StorageError("segment_limit")
            previous = -1_000_000
            for index in range(record["segments"]):
                meta, content = self.video_segment(data, root, owner, video["id"], index)
                with av.open(io.BytesIO(content), mode="r", format="matroska") as container:
                    position = 0
                    for packet in container.demux(video=0):
                        if not packet.size:
                            continue
                        if position >= len(meta["frames"]):
                            raise StorageError("integrity_mismatch")
                        frame = meta["frames"][position]
                        position += 1
                        if frame["timestamp_us"] - previous < 1_000_000:
                            continue
                        jpeg = bytes(packet)
                        if (
                            not jpeg.startswith(b"\xff\xd8")
                            or not jpeg.endswith(b"\xff\xd9")
                            or len(jpeg) > 524288
                        ):
                            raise StorageError("invalid_jpeg")
                        size += len(jpeg)
                        if size > 64_000_000 or len(frames) >= 600:
                            raise StorageError("replay_export_limit")
                        name = f"frame-{len(frames):06d}.jpg"
                        files[name] = jpeg
                        frames.append(
                            {"name": name, "offset_ms": video["start_ms"] + frame["timestamp_us"] / 1000}
                        )
                        previous = frame["timestamp_us"]
                    if position != len(meta["frames"]):
                        raise StorageError("integrity_mismatch")
        data["replay_frames"] = frames
        self.do_save(data, files)
        return data
