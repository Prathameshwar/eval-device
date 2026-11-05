"""Offline packet extraction, never called by the streaming API."""

import hashlib
import io
import json
from pathlib import Path
from uuid import UUID

import av

from .config import Settings
from .privacy import StorageError, no_link, private_directory
from .protocol import jpeg_dimensions
from .store import Store, checked_directory, json_bytes


def extract_frames(
    settings: Settings,
    identity: str,
    output: Path,
    *,
    every: int = 10,
    max_frames: int = 1000,
    max_bytes: int = 268435456,
) -> dict[str, object]:
    """Extract original JPEGs from a completed recording with the writer stopped.

    The exclusive store lock excludes simultaneous writes, retention and extraction.
    Output must be a new private directory outside the recording store.
    """
    if str(UUID(identity)) != identity or every < 1 or not 1 <= max_frames <= 10000 or max_bytes < 8192:
        raise ValueError("invalid extraction limits")
    output = output.absolute()
    root = settings.recording_dir.absolute()
    if output == root or root in output.parents:
        raise ValueError("extraction output must be outside the recording store")
    for parent in (*reversed(output.parents), output):
        if parent.exists() or parent.is_symlink():
            no_link(parent)
    store = Store(settings)
    count, size = 0, 0
    result: dict[str, object] = {"recording_id": identity, "status": "incomplete", "frames": 0, "bytes": 0}
    created = False
    try:
        store.initialize(prune=False)
        data = store.records.get(identity)
        if not data or data["status"] != "saved" or not data["finalized"]:
            raise StorageError("completed_recording_required")
        directory = checked_directory(store.root, identity)
        output.mkdir(mode=0o700)
        created = True
        private_directory(output)
        capped = False
        for index in range(data["segments"]):
            video = directory / f"segment-{index:06d}.mkv"
            metadata = json.loads((directory / f"segment-{index:06d}.json").read_bytes())
            if video.stat().st_size > 8388608 + 65536:
                raise StorageError("segment_limit")
            content = video.read_bytes()
            if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                raise StorageError("integrity_mismatch")
            with av.open(io.BytesIO(content), mode="r", format="matroska") as container:
                position = 0
                for packet in container.demux(video=0):
                    if not packet.size:
                        continue
                    if position >= len(metadata["frames"]):
                        raise StorageError("integrity_mismatch")
                    frame = metadata["frames"][position]
                    position += 1
                    if frame["sequence"] % every:
                        continue
                    jpeg = bytes(packet)
                    if jpeg_dimensions(jpeg) != (data["width"], data["height"]):
                        raise StorageError("invalid_jpeg")
                    if count >= max_frames or size + len(jpeg) > max_bytes - 8192:
                        capped = True
                        break
                    path = output / f"frame-{frame['sequence']:09d}-{frame['timestamp_us']:012d}us.jpg"
                    store.atomic(path, jpeg)
                    count += 1
                    size += len(jpeg)
                if not capped and position != len(metadata["frames"]):
                    raise StorageError("integrity_mismatch")
            if capped:
                break
        result["status"] = "limited" if capped else "complete"
        return result
    finally:
        try:
            if created:
                result.update(frames=count, bytes=size)
                store.atomic(output / "extraction.json", json_bytes(result), replace=True)
        finally:
            store.close()
