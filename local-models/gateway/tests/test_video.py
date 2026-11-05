import json
from uuid import uuid4

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_gateway import setup, token  # noqa: F401

from local_model_gateway.app import create_app
from local_model_gateway.security import Rejected
from local_model_gateway.streams import HEADER
from local_model_gateway.video import Motion, dimensions


def jpeg(color=0, width=200, height=150):
    return cv2.imencode(".jpg", np.full((height, width, 3), color, np.uint8))[1].tobytes()


def test_motion_detects_change_and_static_scene():
    moving, static = Motion(), Motion()
    for color in (0, 255, 0):
        moving.accept(jpeg(color))
        static.accept(jpeg(0))
    assert moving.result()["motion_detected"]
    assert moving.result()["moving_frames"] == 2
    assert not static.result()["motion_detected"]
    assert dimensions(jpeg()) == (200, 150)


def test_invalid_or_large_jpeg_rejected_before_decode(monkeypatch):
    oversized = jpeg(width=641)
    raw = jpeg()
    offset = raw.index(b"\xff\xc0")
    length = int.from_bytes(raw[offset + 2 : offset + 4], "big")
    duplicate = raw[:offset] + raw[offset : offset + length + 2] + raw[offset:]
    monkeypatch.setattr(cv2, "imdecode", lambda *_: pytest.fail("Decoded before checking dimensions"))
    for raw in (oversized, duplicate, b"\xff\xd8bad\xff\xd9", b"bad"):
        with pytest.raises(Rejected):
            Motion().accept(raw)


def test_video_processing_is_grant_scoped_and_obeys_reserved_frame_budget(setup):  # noqa: F811
    key, _, settings = setup
    app = create_app(settings, transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected model call")))
    run_id = str(uuid4())
    raw = json.dumps({"format": "jpeg", "model": "opencv_motion", "processing_run_id": run_id})
    with TestClient(app, base_url="https://gateway") as client:
        for count in (2, 6):
            authorization, claims = token(
                key,
                settings,
                method="GET",
                path="/v1/stream/video",
                raw=raw.encode(),
                model="opencv_motion",
                video_operation="video.motion",
                processing_run_id=run_id,
                max_video_seconds=1,
            )
            with client.websocket_connect(
                "wss://gateway/v1/stream/video", headers={"Authorization": authorization}
            ) as socket:
                socket.send_text(raw)
                assert socket.receive_json()["type"] == "ready"
                for index in range(count):
                    socket.send_bytes(HEADER.pack(index, index + 1) + jpeg(255 if index % 2 else 0))
                    if index == 5:
                        assert socket.receive()["type"] == "websocket.close"
                    else:
                        assert socket.receive_json()["type"] == "ack"
                if count == 2:
                    socket.send_text('{"type":"end"}')
                    assert socket.receive_json()["result"]["motion_detected"]
            assert app.state.receipts.status(claims["jti"], claims["sub"], claims["org"]) == (
                "completed" if count == 2 else "unknown"
            )
