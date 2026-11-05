"""Private bounded store. All operations run on one dedicated recording thread."""

import errno
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID

import av

from .config import Settings
from .privacy import StorageError, no_link, private_directory
from .protocol import Frame, Start
from .retries import DiskRetries

FORMAT = "device-video-recording-v1"
MANIFEST_BUDGET = 8192
SEGMENT_BUDGET = 65536
FILE_NAME = re.compile(r"(?:session\.json(?:\.part)?|segment-\d{6}\.(?:mkv|json)(?:\.part)?)")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def checked_directory(root: Path, identity: str) -> Path:
    if str(UUID(identity)) != identity:
        raise StorageError("unsafe_path")
    directory = root / identity
    no_link(root)
    no_link(directory)
    if not directory.is_dir():
        raise StorageError("unsafe_path")
    return directory


def checked_files(directory: Path) -> list[Path]:
    result = []
    for path in directory.iterdir():
        no_link(path)
        if not path.is_file() or not FILE_NAME.fullmatch(path.name):
            raise StorageError("unmanaged_directory")
        result.append(path)
    return result


class LimitedBuffer(io.BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data: Any) -> int:
        if self.tell() + len(data) > self.limit:
            raise StorageError("segment_limit")
        return super().write(data)


def remux(frames: list[Frame], start: Start) -> bytes:
    """Copy compressed packets into Matroska; never decode or encode frames."""
    buffer = LimitedBuffer(sum(len(frame.jpeg) for frame in frames) + SEGMENT_BUDGET // 2)
    with av.open(buffer, "w", format="matroska") as output:
        stream = cast(av.VideoStream, output.add_stream("mjpeg", rate=start.fps))
        stream.width, stream.height = start.width, start.height
        stream.pix_fmt = "yuvj420p"
        stream.codec_context.thread_count = 1
        stream.time_base = Fraction(1, 1000000)
        for frame in frames:
            packet = av.Packet(frame.jpeg)
            packet.stream = stream
            packet.pts = packet.dts = frame.timestamp_us - frames[0].timestamp_us
            packet.duration = round(1000000 / start.fps)
            packet.time_base = Fraction(1, 1000000)
            packet.is_keyframe = True
            output.mux(packet)
    return buffer.getvalue()


@dataclass
class Session:
    data: dict[str, Any]
    start: Start
    frames: list[Frame] = field(default_factory=list)
    buffer_bytes: int = 0
    buffered_at: float = 0
    failed: bool = False


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.recording_dir.absolute()
        self.records: dict[str, dict[str, Any]] = {}
        self.active: dict[str, Session] = {}
        self.charges: dict[str, int] = {}
        self.lock: BinaryIO | None = None
        self.retry = DiskRetries(settings.retry_attempts, settings.retry_delay_seconds)

    def initialize(self, *, prune: bool = True) -> None:
        for path in (*reversed(self.root.parents), self.root):
            if path.exists() or path.is_symlink():
                no_link(path)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = self.root / ".store.json"
        if not marker.exists() and any(self.root.iterdir()):
            raise StorageError("unmanaged_directory")
        private_directory(self.root)
        lock_path = self.root / ".writer.lock"
        if lock_path.exists():
            no_link(lock_path)
        self.lock = lock_path.open("a+b")
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
        if marker.exists():
            no_link(marker)
            if marker.stat().st_size > 128 or json.loads(marker.read_bytes()) != {"format": FORMAT}:
                raise StorageError("unmanaged_directory")
        else:
            with marker.open("xb") as target:
                target.write(json_bytes({"format": FORMAT}))
        for path in self.root.iterdir():
            if path.name in {".store.json", ".writer.lock"}:
                continue
            directory = checked_directory(self.root, path.name)
            files = checked_files(directory)
            manifest = directory / "session.json"
            if not manifest.exists():
                # A crash while creating the initial manifest cannot have accepted
                # video yet: start is acknowledged only after that manifest commits.
                # Remove only the empty session or its bounded initial temporary file.
                if any(p.name != "session.json.part" for p in files):
                    raise StorageError("invalid_manifest")
                for orphan in files:
                    if orphan.stat().st_size > MANIFEST_BUDGET // 2:
                        raise StorageError("invalid_manifest")
                    orphan.unlink()
                directory.rmdir()
                continue
            if manifest.stat().st_size > MANIFEST_BUDGET // 2:
                raise StorageError("invalid_manifest")
            data = json.loads(manifest.read_bytes())
            if (
                data.get("format") != FORMAT
                or data.get("id") != path.name
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(data.get("client_id", "")))
                or type(data.get("created_at")) not in {float, int}
                or not 0 < data["created_at"] < 1e12
                or (
                    "expires_at" in data
                    and (
                        type(data["expires_at"]) not in {float, int}
                        or not data["created_at"]
                        <= data["expires_at"]
                        <= data["created_at"] + 8760 * 3600 + 1
                    )
                )
            ):
                raise StorageError("invalid_manifest")
            valid = self.verify_segments(directory, data)
            if data.get("status") != "saved" or not valid:
                data.update(
                    status="incomplete",
                    finalized=True,
                    reason=(data.get("reason") or "interrupted")
                    if data.get("status") != "saved"
                    else "integrity_mismatch",
                )
                self.manifest(directory, data)
            self.records[path.name] = data
            self.charges[path.name] = (
                sum(p.stat().st_size for p in checked_files(directory)) + MANIFEST_BUDGET
            )
        if prune:
            self.prune()

    @staticmethod
    def verify_segments(directory: Path, data: dict[str, Any]) -> bool:
        count = data.get("segments")
        if type(count) is not int or not 0 <= count <= 108000:
            return False
        expected = {f"segment-{i:06d}.{ext}" for i in range(count) for ext in ("mkv", "json")}
        if {p.name for p in directory.iterdir() if p.name != "session.json"} != expected:
            return False
        frames = 0
        for i in range(count):
            sidecar, video = directory / f"segment-{i:06d}.json", directory / f"segment-{i:06d}.mkv"
            if sidecar.stat().st_size > 131072:
                return False
            try:
                index = json.loads(sidecar.read_bytes())
                if index["index"] != i or index["bytes"] != video.stat().st_size:
                    return False
                # Content hashes are checked during offline extraction; startup stays bounded by metadata.
                frames += len(index["frames"])
            except (KeyError, ValueError, TypeError):
                return False
        return frames == data.get("saved_frames")

    def atomic(self, path: Path, content: bytes, *, replace: bool = False) -> None:
        temporary = path.with_name(path.name + ".part")

        def write() -> None:
            no_link(path.parent)
            for candidate in (temporary, path):
                if candidate.exists() or candidate.is_symlink():
                    no_link(candidate)
            if path.exists() and not replace:
                if path.stat().st_size != len(content) or path.read_bytes() != content:
                    raise StorageError("conflicting_segment")
                return  # The previous atomic rename succeeded before an uncertain I/O error.
            with temporary.open("wb") as target:
                offset = 0
                while offset < len(content):
                    count = target.write(content[offset:])
                    if count is None or count <= 0:
                        raise OSError(errno.EIO, "write made no progress")
                    offset += count
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
            if sys.platform != "win32":
                descriptor = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        self.retry.run(write)

    def manifest(self, directory: Path, data: dict[str, Any]) -> None:
        content = json_bytes(data)
        if len(content) > MANIFEST_BUDGET // 2:
            raise StorageError("metadata_limit")
        self.atomic(directory / "session.json", content, replace=True)

    def prune(self, extra: int = 0, *, new_session: bool = False) -> None:
        now = time.time()
        used = 4096 + sum(self.charges.values())
        for identity, data in sorted(self.records.items(), key=lambda pair: pair[1]["created_at"]):
            expired = now >= min(
                data.get("expires_at", float("inf")),
                data["created_at"] + self.settings.retention_hours * 3600,
            )
            full = used + extra > self.settings.recording_max_bytes
            too_many = len(self.records) + int(new_session) > self.settings.recording_max_sessions
            if identity in self.active or not (expired or full or too_many):
                continue
            directory = checked_directory(self.root, identity)
            for path in checked_files(directory):
                path.unlink()
            directory.rmdir()
            self.records.pop(identity)
            used -= self.charges.pop(identity)
        if (
            used + extra > self.settings.recording_max_bytes
            or len(self.records) + int(new_session) > self.settings.recording_max_sessions
        ):
            raise StorageError("storage_quota")
        pending = sum(session.buffer_bytes for session in self.active.values())
        if shutil.disk_usage(self.root).free < self.settings.min_free_bytes + pending + extra:
            raise StorageError("disk_space")

    def start(self, identity: str, owner: str, start: Start) -> dict[str, Any]:
        if len(self.active) >= self.settings.max_sessions:
            raise StorageError("session_limit")
        self.prune(MANIFEST_BUDGET, new_session=True)
        directory = self.root / identity
        directory.mkdir(mode=0o700)
        data = dict(
            format=FORMAT,
            id=identity,
            client_id=owner,
            created_at=time.time(),
            expires_at=time.time()
            + min(start.retention_hours or self.settings.retention_hours, self.settings.retention_hours)
            * 3600,
            capture_id=str(start.capture_id) if start.capture_id else None,
            capture_start_unix_ms=start.capture_start_unix_ms,
            width=start.width,
            height=start.height,
            fps=start.fps,
            status="pending",
            finalized=False,
            reason=None,
            received_frames=0,
            saved_frames=0,
            segments=0,
            video_bytes=0,
        )
        self.records[identity] = data
        self.charges[identity] = MANIFEST_BUDGET
        self.active[identity] = Session(data, start)
        self.manifest(directory, data)
        return data

    def frame(self, identity: str, frame: Frame) -> None:
        session = self.active[identity]
        if session.failed:
            raise StorageError("recording_failed")
        if session.frames and (
            session.buffer_bytes + len(frame.jpeg) > self.settings.segment_bytes
            or frame.timestamp_us - session.frames[0].timestamp_us >= self.settings.segment_seconds * 1e6
        ):
            self.flush(identity)
        charge = len(frame.jpeg) + 256 + (SEGMENT_BUDGET if not session.frames else 0)
        try:
            self.prune(charge)
        except StorageError:
            # Existing buffered frames already have a quota reservation. Preserve
            # that accepted prefix when the next frame cannot be admitted.
            self.flush(identity)
            raise
        self.charges[identity] += charge
        if not session.frames:
            session.buffered_at = time.monotonic()
        session.frames.append(frame)
        session.buffer_bytes += len(frame.jpeg)
        session.data["received_frames"] += 1

    def flush(self, identity: str) -> None:
        session = self.active[identity]
        if not session.frames or session.failed:
            return
        directory = checked_directory(self.root, identity)
        index = session.data["segments"]
        content = remux(session.frames, session.start)
        metadata = json_bytes(
            dict(
                index=index,
                bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                frames=[dict(sequence=f.sequence, timestamp_us=f.timestamp_us) for f in session.frames],
            )
        )
        if len(content) + len(metadata) > session.buffer_bytes + SEGMENT_BUDGET + len(session.frames) * 256:
            raise StorageError("segment_limit")
        self.atomic(directory / f"segment-{index:06d}.mkv", content)
        self.atomic(directory / f"segment-{index:06d}.json", metadata)
        session.data["saved_frames"] += len(session.frames)
        session.data["segments"] += 1
        session.data["video_bytes"] += len(content)
        session.frames.clear()
        session.buffer_bytes = 0
        self.manifest(directory, session.data)

    def fail(self, identity: str, reason: str) -> None:
        session = self.active.get(identity)
        if session:
            session.failed = True
            session.frames.clear()
            session.buffer_bytes = 0
            session.data.update(status="incomplete", reason=reason)

    def finish(self, identity: str, reason: str | None, received: int) -> dict[str, Any]:
        session = self.active[identity]
        self.flush(identity)
        complete = not session.failed and reason is None and received == session.data["saved_frames"]
        session.data.update(
            status="saved" if complete else "incomplete",
            finalized=True,
            reason=session.data["reason"] or reason or (None if complete else "missing_frames"),
            received_frames=received,
        )
        self.manifest(checked_directory(self.root, identity), session.data)
        self.active.pop(identity)
        return session.data

    def close(self) -> None:
        if self.lock:
            self.lock.close()
            self.lock = None
