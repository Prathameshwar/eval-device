from fractions import Fraction

import av
import pytest

from device_video.config import Settings
from device_video.protocol import Frame, Start

TOKEN = "a" * 40
OTHER = "b" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
START = dict(type="start", version=1, format="jpeg", width=64, height=48, fps=10)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        client_tokens={"pi-1": TOKEN, "pi-2": OTHER},
        recording_dir=tmp_path / "recordings",
        min_free_bytes=0,
        segment_seconds=0.2,
        idle_seconds=1,
        disk_wait_seconds=2,
    )


@pytest.fixture
def jpeg():
    codec = av.CodecContext.create("mjpeg", "w")
    codec.width, codec.height = 64, 48
    codec.pix_fmt, codec.time_base = "yuvj420p", Fraction(1, 10)
    frame = av.VideoFrame(64, 48, "yuvj420p")
    for plane in frame.planes:
        plane.update(bytes([128]) * plane.buffer_size)
    return bytes(codec.encode(frame)[0])


@pytest.fixture
def start():
    return Start(**START)


@pytest.fixture
def frames(jpeg):
    return [Frame(i, i * 100000, jpeg) for i in range(5)]
