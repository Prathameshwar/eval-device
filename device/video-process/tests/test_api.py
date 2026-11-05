import time

import pytest
from conftest import AUTH, OTHER, START
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from device_video.app import create_app
from device_video.protocol import HEADER


def client(settings):
    return TestClient(create_app(settings), client=("127.0.0.1", 1234))


def finish(socket):
    messages = []
    while True:
        message = socket.receive_json()
        messages.append(message)
        if message["type"] == "complete":
            return message, messages


def test_stream_saved_and_receipts_owner_scoped(settings, frames):
    with client(settings) as http:
        assert http.get("/health/live").status_code == 200
        assert http.get("/health/ready").status_code == 401
        assert http.get("/health/ready", headers=AUTH.copy()).status_code == 200
        with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()) as socket:
            socket.send_json(START)
            ready = socket.receive_json()
            assert ready["type"] == "ready"
            for frame in frames:
                socket.send_bytes(HEADER.pack(b"VPF1", frame.sequence, frame.timestamp_us) + frame.jpeg)
                assert socket.receive_json()["status"] == "pending"
            socket.send_json({"type": "stop"})
            complete, _ = finish(socket)
        assert complete["recording"]["status"] == "saved"
        assert complete["recording"]["saved_frames"] == len(frames)
        url = "/v1/recordings/" + ready["recording_id"]
        assert http.get(url, headers=AUTH.copy()).json()["finalized"]
        assert http.get(url, headers={"Authorization": f"Bearer {OTHER}"}).status_code == 404
        assert http.get(url).status_code == 401
        assert http.get("/v1/recordings/unknown", headers=AUTH.copy()).status_code == 404


@pytest.mark.parametrize(
    "headers,query",
    [
        ({}, ""),
        ({"Authorization": "Bearer wrong"}, ""),
        (AUTH | {"Origin": "https://example.test"}, ""),
        (AUTH, "?token=secret"),
    ],
)
def test_websocket_authentication(settings, headers, query):
    with client(settings) as http:
        with pytest.raises(WebSocketDisconnect) as error:
            with http.websocket_connect("/v1/video/stream" + query, headers=headers.copy()):
                pass
        assert error.value.code == 1008


def test_remote_plaintext_and_untrusted_proxy_headers(settings):
    with TestClient(create_app(settings), client=("192.168.1.100", 1234)) as http:
        headers = AUTH | {"X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1"}
        assert http.get("/health/ready", headers=headers.copy()).status_code == 401
    with TestClient(
        create_app(settings), base_url="https://video.test", client=("192.168.1.100", 1234)
    ) as http:
        assert http.get("/health/ready", headers=AUTH.copy()).status_code == 200


def test_disconnect_retains_accepted_prefix_and_marks_incomplete(settings, frames):
    with client(settings) as http:
        with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()) as socket:
            socket.send_json(START)
            identity = socket.receive_json()["recording_id"]
            socket.send_bytes(HEADER.pack(b"VPF1", 0, 0) + frames[0].jpeg)
            socket.receive_json()
            socket.close()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                receipt = http.get("/v1/recordings/" + identity, headers=AUTH.copy()).json()
                if receipt["finalized"]:
                    break
                time.sleep(0.01)
            assert receipt["status"] == "incomplete" and receipt["saved_frames"] == 1


def test_invalid_frame_keeps_saved_prefix(settings, frames):
    with client(settings) as http:
        with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()) as socket:
            socket.send_json(START)
            socket.receive_json()
            socket.send_bytes(HEADER.pack(b"VPF1", 0, 0) + frames[0].jpeg)
            socket.receive_json()
            socket.send_bytes(HEADER.pack(b"VPF1", 0, 0) + frames[0].jpeg)
            complete, messages = finish(socket)
            assert messages[0]["type"] == "error"
            assert complete["recording"]["status"] == "incomplete"
            assert complete["recording"]["saved_frames"] == 1


def test_idle_and_capacity(settings):
    settings = settings.model_copy(update={"max_sessions": 1, "idle_seconds": 0.1})
    with client(settings) as http:
        with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()) as socket:
            socket.send_json(START)
            socket.receive_json()
            with pytest.raises(WebSocketDisconnect) as error:
                with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()):
                    pass
            assert error.value.code == 1013
            complete, messages = finish(socket)
            assert messages[0]["code"] == "stream_timeout"
            assert complete["recording"]["status"] == "incomplete"


def test_storage_startup_failure_does_not_accept_unrecordable_stream(settings):
    settings.recording_dir.mkdir()
    (settings.recording_dir / "keep.txt").write_text("unmanaged")
    with client(settings) as http:
        assert http.get("/health/live").status_code == 200
        assert http.get("/health/ready", headers=AUTH.copy()).status_code == 503
        with pytest.raises(WebSocketDisconnect) as error:
            with http.websocket_connect("/v1/video/stream", headers=AUTH.copy()):
                pass
        assert error.value.code == 1013
