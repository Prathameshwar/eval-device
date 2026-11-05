import pytest

from device_audio.config import Settings
from device_audio.engine import Recognition

TOKEN = "a" * 48
OTHER_TOKEN = "b" * 48
HEADERS = {"Authorization": "Bearer " + TOKEN}
SPEECH = b"\x01\x00" * 480
SILENCE = b"\x00\x00" * 480


class Detector:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        return any(frame)


class FakeEngine:
    def __init__(self):
        self.calls = []

    def transcribe(self, chunk, language):
        self.calls.append((chunk, language))
        return Recognition("\u0928\u092e\u0938\u094d\u0924\u0947, hello.", "hi", [])


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        client_tokens={"pi-1": TOKEN, "pi-2": OTHER_TOKEN},
        console_output=False,
        recording_enabled=False,
        min_speech_ms=90,
    )


def send_pcm(ws, pcm):
    for offset in range(0, len(pcm), 3200):
        ws.send_bytes(pcm[offset : offset + 3200])


def collect(ws):
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] in {"complete", "error"}:
            return events
