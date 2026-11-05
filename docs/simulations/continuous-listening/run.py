"""Native desktop recovery regression: synthetic audio, mocked services, no cloud calls."""

import asyncio
import itertools
import json
import runpy
import sys
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "human-test/tests"))

import httpx
from busy_window_smoke import SpeakerProbe, initialize
from human_test import app
from training_client.controller import Controller
from training_client.pms_client import ClientError
from test_busy_retry import answer_ok, speech_ok
from test_cloud_models import frames, route, settings


def main():
    output = (
        Path(__file__).parent
        / "results"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    )
    output.mkdir(parents=True)
    captured, calls, errors = [], [], []
    selected = route()

    async def capture(*args):
        captured.append(time.monotonic())
        if len(captured) == 3:
            raise ClientError("Microphone disconnected (simulated)")
        async for frame in frames():
            yield frame

    async def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json=selected
                if request.url.path.endswith("/model-config")
                else {"status": "ready"},
            )
        stage = (
            "speech"
            if request.url.path.endswith("/speech/transcriptions")
            else "response"
        )
        calls.append(stage)
        if len(captured) == 1 or (len(captured) == 2 and stage == "response"):
            return httpx.Response(
                502,
                json={
                    "error": {
                        "code": "speech_submission_unknown"
                        if stage == "speech"
                        else "llm_transport_unknown"
                    }
                },
            )
        return (
            speech_ok(request)
            if stage == "speech"
            else answer_ok(json.loads(request.content))
        )

    app.Window.initialize = initialize
    app.microphones = list
    app.microphone = capture
    root = tk.Tk()
    root.withdraw()
    window = app.Window(root, settings())
    window.speaker.close()
    window.speaker = SpeakerProbe()
    root.geometry("1080x800")
    root.attributes("-alpha", 0.0)
    root.deiconify()
    original_emit = window.emit

    def emit(kind, value):
        if kind == "error":
            errors.append(value)
        original_emit(kind, value)

    window.emit = emit

    def until(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert predicate(), window.state.get()

    async def setup():
        controller = Controller(window.settings, window.emit)
        controller.use_models(selected)
        await controller.pms.http.aclose()
        controller.pms.http = httpx.AsyncClient(
            base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
        )
        window.controller = controller

    evidence = {"passed": False, "cloud_calls": 0}
    try:
        until(lambda: not window.running)
        asyncio.run_coroutine_threadsafe(setup(), window.loop).result(5)
        window.saved = {"language": "en"}
        window.page = "talk"
        window.setup_frame.pack_forget()
        window.talk_frame.pack(fill="both", expand=True)
        window.start_button.invoke()
        until(lambda: len(errors) == 1 and not window.running)
        assert window.listening and "Pause microphone" in window.start_button.cget(
            "text"
        )
        until(lambda: window.warning_label.winfo_ismapped(), timeout=1)
        assert "unknown" in window.turn_warning.get()
        capture_window = runpy.run_path(
            str(ROOT / "docs/simulations/alex-cardiology/window_capture.py")
        )["save_window"]
        capture_window(root.winfo_id(), output / "recovering.png")
        assert len(captured) == 1 and calls == ["speech"]
        # All failures must return to fresh capture without touching the start button again.
        until(lambda: len(window.speaker.requests) == 1 and not window.running)
        assert window.listening and len(captured) == 4 and len(errors) == 3
        assert calls == ["speech", "speech", "response", "speech", "response"]
        assert len(window.controller.history) == 2
        gaps = [round(b - a, 2) for a, b in itertools.pairwise(captured)]
        assert all(2.9 <= gap <= 5 for gap in gaps), gaps
        assert window.controller.pms.recovery_request[0] == "answer"
        assert "My name is Alex" in window.answer.get("1.0", "end-1c")
        assert not window.warning_label.winfo_ismapped()
        window.pause()
        before = len(captured)
        deadline = time.monotonic() + 3.5
        while time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert len(captured) == before and not window.listening
        evidence.update(
            passed=True,
            failures=errors,
            captures=len(captured),
            submissions=calls,
            resume_gaps_seconds=gaps,
            manual_pause_respected=True,
            completed_history_messages=len(window.controller.history),
        )
    finally:
        (output / "result.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        window.retry_notice.hide()
        for job in root.tk.splitlist(root.tk.call("after", "info")):
            root.after_cancel(job)
        window.close()
        deadline = time.monotonic() + 10
        while window.worker.is_alive() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
    print(
        "PASS: continuous listening, unknown outcomes, fresh captures and manual pause"
    )
    print(output / "result.json")


if __name__ == "__main__":
    main()
