"""Bounded framing checks only: no live image decoding, analysis or inference."""

import struct
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings

HEADER = struct.Struct("!4sQQ")


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["start"]
    version: Literal[1]
    format: Literal["jpeg"]
    width: int = Field(ge=16)
    height: int = Field(ge=16)
    fps: int = Field(ge=1)
    retention_hours: float | None = Field(default=None, gt=0, le=8760)
    capture_id: UUID | None = None
    capture_start_unix_ms: int | None = Field(default=None, ge=0, le=9999999999999)


@dataclass(frozen=True)
class Frame:
    sequence: int
    timestamp_us: int
    jpeg: bytes


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Accept one bounded baseline JPEG; full entropy validation requires a decoder.

    Reject progressive/multiple scans, concatenated images and oversized dimensions
    without invoking native image decoders on the network receive path.
    """
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("invalid_jpeg")
    pos, dimensions, scanned = 2, None, False
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError("invalid_jpeg")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            raise ValueError("invalid_jpeg")
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            if pos != len(data) or not scanned or dimensions is None:
                raise ValueError("invalid_jpeg")
            return dimensions
        if scanned or marker in {0, 0xD8, 1} or 0xD0 <= marker <= 0xD7:
            raise ValueError("invalid_jpeg")
        if pos + 2 > len(data):
            raise ValueError("invalid_jpeg")
        size = int.from_bytes(data[pos : pos + 2], "big")
        end = pos + size
        if size < 2 or end > len(data):
            raise ValueError("invalid_jpeg")
        if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
            if marker != 0xC0 or dimensions is not None or size < 8:
                raise ValueError("baseline_jpeg_required")
            components = data[pos + 7]
            if data[pos + 2] != 8 or components not in {1, 3} or size != 8 + 3 * components:
                raise ValueError("invalid_jpeg")
            dimensions = (
                int.from_bytes(data[pos + 5 : pos + 7], "big"),
                int.from_bytes(data[pos + 3 : pos + 5], "big"),
            )
        pos = end
        if marker == 0xDA:
            if dimensions is None or size < 6:
                raise ValueError("invalid_jpeg")
            scanned = True
            # Skip entropy bytes using C-level find; only stuffed FF and restart markers
            # may occur before EOI. Native decode is deliberately outside live recording.
            while True:
                next_marker = data.find(b"\xff", pos)
                if next_marker < 0 or next_marker + 1 >= len(data):
                    raise ValueError("invalid_jpeg")
                value = data[next_marker + 1]
                if value == 0 or 0xD0 <= value <= 0xD7:
                    pos = next_marker + 2
                elif value == 255:
                    pos = next_marker + 1
                else:
                    pos = next_marker
                    break
    raise ValueError("invalid_jpeg")


class StreamRules:
    def __init__(self, start: Start, settings: Settings):
        if (
            start.width > settings.max_width
            or start.height > settings.max_height
            or start.fps > settings.max_fps
        ):
            raise ValueError("video_limits")
        self.start, self.settings = start, settings
        self.count, self.last_timestamp = 0, -1
        self.started = time.monotonic()

    def frame(self, data: bytes) -> Frame:
        if not HEADER.size < len(data) <= self.settings.max_frame_bytes + HEADER.size:
            raise ValueError("frame_size")
        magic, sequence, timestamp = HEADER.unpack_from(data)
        if magic != b"VPF1" or sequence != self.count:
            raise ValueError("frame_sequence")
        if timestamp <= self.last_timestamp or (sequence == 0 and timestamp != 0):
            raise ValueError("frame_timestamp")
        if sequence and timestamp - self.last_timestamp < 0.9 * 1_000_000 / self.start.fps:
            raise ValueError("frame_rate")
        elapsed = time.monotonic() - self.started
        if (
            timestamp > self.settings.max_session_seconds * 1_000_000
            or self.count >= self.settings.max_session_seconds * self.start.fps
        ):
            raise ValueError("duration_limit")
        if self.count > (elapsed + 1) * self.start.fps or timestamp / 1_000_000 > elapsed + 2:
            raise ValueError("send_rate")
        jpeg = data[HEADER.size :]
        if jpeg_dimensions(jpeg) != (self.start.width, self.start.height):
            raise ValueError("frame_dimensions")
        self.count += 1
        self.last_timestamp = timestamp
        return Frame(sequence, timestamp, jpeg)
