import json

import pytest
from conftest import START, TOKEN

from device_video.config import Settings
from device_video.protocol import HEADER, Start, StreamRules, jpeg_dimensions


def test_real_baseline_jpeg_and_exact_bytes(settings, start, jpeg):
    assert jpeg_dimensions(jpeg) == (64, 48)
    frame = StreamRules(start, settings).frame(HEADER.pack(b"VPF1", 0, 0) + jpeg)
    assert frame.jpeg == jpeg


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b[:-1],
        lambda b: b + b,
        lambda b: b[2:],
        lambda b: b.replace(b"\xff\xc0", b"\xff\xc2", 1),
        lambda b: b"\xff\xd8\xff\xd9",
        lambda b: b"junk",
    ],
)
def test_bad_jpeg(change, jpeg):
    with pytest.raises(ValueError):
        jpeg_dimensions(change(jpeg))


@pytest.mark.parametrize("magic,seq,ts", [(b"XXXX", 0, 0), (b"VPF1", 1, 0), (b"VPF1", 0, 1)])
def test_initial_order(settings, start, jpeg, magic, seq, ts):
    with pytest.raises(ValueError):
        StreamRules(start, settings).frame(HEADER.pack(magic, seq, ts) + jpeg)


def test_duplicate_nonmonotonic_and_dimensions(settings, start, jpeg):
    rules = StreamRules(start, settings)
    rules.frame(HEADER.pack(b"VPF1", 0, 0) + jpeg)
    for seq, ts in ((0, 100000), (1, 0), (1, 100)):
        with pytest.raises(ValueError):
            rules.frame(HEADER.pack(b"VPF1", seq, ts) + jpeg)
    wrong = Start(**(START | {"width": 80}))
    with pytest.raises(ValueError, match="dimensions"):
        StreamRules(wrong, settings).frame(HEADER.pack(b"VPF1", 0, 0) + jpeg)


def test_size_rate_duration_and_jitter(settings, start, jpeg, monkeypatch):
    monkeypatch.setattr("device_video.protocol.time.monotonic", lambda: 100)
    rules = StreamRules(start, settings)
    with pytest.raises(ValueError, match="frame_size"):
        rules.frame(b"x" * (settings.max_frame_bytes + HEADER.size + 1))
    for i in range(11):
        rules.frame(HEADER.pack(b"VPF1", i, i * 100000) + jpeg)
    with pytest.raises(ValueError, match="send_rate"):
        rules.frame(HEADER.pack(b"VPF1", 11, 1100000) + jpeg)
    rules = StreamRules(start, settings.model_copy(update={"max_session_seconds": 0.1}))
    rules.frame(HEADER.pack(b"VPF1", 0, 0) + jpeg)
    with pytest.raises(ValueError, match="duration_limit"):
        rules.frame(HEADER.pack(b"VPF1", 1, 200000) + jpeg)


def test_start_limits(settings):
    for values in ({"fps": 100}, {"width": 9999}, {"height": 9999}):
        with pytest.raises(ValueError):
            StreamRules(Start(**(START | values)), settings)
    for values in ({"fps": "10"}, {"format": "h264"}, {"model": "anything"}, {"fps": True}):
        with pytest.raises(ValueError):
            Start.model_validate_json(json.dumps(START | values))


@pytest.mark.parametrize(
    "values",
    [
        {"client_tokens": {}},
        {"client_tokens": {"pi": "short"}},
        {"client_tokens": {"a": TOKEN, "b": TOKEN}},
        {"host": "0.0.0.0"},
        {"tls_cert": "cert.pem"},
        {"queue_bytes": 65536},
    ],
)
def test_config_validation(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **({"client_tokens": {"pi": TOKEN}} | values))
