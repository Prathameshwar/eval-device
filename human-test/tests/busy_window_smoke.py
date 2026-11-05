"""Native Tk retry flow, real 1/2/3/4/5-second waits, synthetic PCM and busy HTTP responses.

No cloud access, microphone, speaker playback, camera capture or credentials are used.
"""

import argparse
import asyncio
import json
import runpy
import time
import tkinter as tk
from pathlib import Path

import httpx
from test_busy_retry import answer_ok, speech_ok
from test_cloud_models import frames, route, settings
from training_client import capture as capture_module
from training_client import runtime
from training_client.capture import CaptureQuality
from training_client.controller import Controller
from training_client.listening import Utterance
from training_client.performance import TurnTiming

from human_test import app


class SpeakerProbe:
    def __init__(self):
        self.enabled = True
        self.speaking = False
        self.last_error = None
        self.progress = 0
        self.requests = []

    def speak(self, text, language, gender, **kwargs):
        self.requests.append((text, language, gender))
        self.speaking = True
        return True

    def stop(self):
        self.speaking = False

    def close(self):
        self.stop()

    def catalogue(self):
        return []


async def initialize(self):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save test-window screenshots and check results here")
    args = parser.parse_args()
    snapshots = set()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        capture_window = runpy.run_path(
            str(Path(__file__).resolve().parents[2] / "docs/simulations/alex-cardiology/window_capture.py")
        )["save_window"]
    captured, closed, calls = [], [], {"speech": [], "response": []}
    selected = route()
    scenario = "recover"

    async def capture(*args):
        captured.append(time.monotonic())
        try:
            async for frame in frames():
                yield frame
        finally:
            closed.append(time.monotonic())

    class SyntheticUtterance(Utterance):
        def __init__(self):
            self.quality = CaptureQuality()
            self.performance = TurnTiming()

        def frames(self):
            return capture()

    class SyntheticListener:
        def __init__(self, *args, **kwargs):
            self.ready = asyncio.Queue(maxsize=2)
            self.failure = None

        async def run(self):
            self.ready.put_nowait(SyntheticUtterance())
            await asyncio.Event().wait()

    def forbid_hardware(*args, **kwargs):
        raise AssertionError("Native retry smoke must not open an audio input device")

    async def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200, json=selected if request.url.path.endswith("/model-config") else {"status": "ready"}
            )
        stage = "speech" if request.url.path.endswith("/speech/transcriptions") else "response"
        assert len(captured) == len(closed), "capture remained open during submission"
        calls[stage].append((time.monotonic(), request))
        # Keep a retry request visible long enough to check the real UI state.
        await asyncio.sleep(0.2)
        if scenario in {"cancel", "cancel_round", "exhaust"} or len(calls[stage]) <= (
            6 if stage == "speech" else 5
        ):
            return httpx.Response(429, json={"error": {"code": "llm_busy"}})
        return speech_ok(request) if stage == "speech" else answer_ok(json.loads(request.content))

    app.Window.initialize = initialize
    app.microphones = lambda: []
    runtime.Listener = SyntheticListener
    capture_module._reader = forbid_hardware
    root = tk.Tk()
    root.withdraw()
    window = app.Window(root, settings())
    window.speaker.close()
    window.speaker = SpeakerProbe()
    window.runtime.speaker = window.speaker
    root.geometry("1080x800")
    root.attributes("-alpha", 0.0)
    root.deiconify()

    def until(predicate, timeout=10, check_retry=True):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            # Windows may minimize a transparent test window between scenarios.
            # Keep it mapped for geometry assertions; alpha remains zero throughout.
            if root.state() == "iconic":
                root.deiconify()
            root.update()
            if window.retrying and window.runtime.retrying and check_retry:
                assert window.running
                assert len(captured) == len(closed)
                assert not window.runtime.retrying or not window.speaker.speaking
                assert window.start_button.cget("text") == "Cancel queued question"
                assert str(window.question_entry.cget("state")) == "disabled"
                assert str(window.preview_button.cget("state")) == "disabled"
                assert window.manikin.mode == "Waiting for model"
                assert window.manikin.animation_job is None
                notice = window.retry_notice
                root.update_idletasks()
                # Tk maps placed children after processing their Configure events.
                layout_deadline = time.monotonic() + 0.25
                while not notice.winfo_ismapped() and time.monotonic() < layout_deadline:
                    root.update()
                    time.sleep(0.01)
                assert notice.winfo_ismapped() and notice.job is not None, (
                    notice.place_info(),
                    notice.job,
                    notice.started,
                    window.state.get(),
                    root.state(),
                    root.winfo_ismapped(),
                    notice.master.winfo_ismapped(),
                )
                assert notice.cancel_button.winfo_ismapped()
                assert notice.master.winfo_width() >= notice.winfo_width()
                assert 0 <= notice.winfo_y() <= notice.master.winfo_height() - notice.winfo_height()
                assert abs(notice.winfo_x() + notice.winfo_width() / 2 - notice.master.winfo_width() / 2) <= 1
                assert notice.master is window.patient_panel and notice.toolbar is window.stage_head
                toolbar_bottom = notice.toolbar.winfo_y() + notice.toolbar.winfo_height() + 12
                center_y = (notice.master.winfo_height() + toolbar_bottom) / 2
                assert abs(notice.winfo_y() + notice.winfo_height() / 2 - center_y) <= 1, (
                    notice.winfo_y(),
                    notice.winfo_height(),
                    center_y,
                    notice.place_info(),
                    notice.toolbar.winfo_height(),
                )
                assert notice.winfo_y() >= toolbar_bottom
                assert notice.position.get() and notice.countdown.get() and notice.elapsed.get()
                snapshot = notice.phase
                if args.output and snapshot not in snapshots and "speech" in notice.title.get().lower():
                    capture_window(root.winfo_id(), args.output / f"speech-{snapshot}.png")
                    snapshots.add(snapshot)
            time.sleep(0.01)
        assert predicate(), window.state.get()

    async def setup():
        controller = Controller(window.settings, window.runtime.emit, inference=window.runtime.inference)
        controller.use_models(selected)
        await controller.pms.http.aclose()
        controller.pms.http = httpx.AsyncClient(
            base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
        )
        window.controller = controller
        window.runtime.controller = controller

    try:
        until(lambda: not window.running)
        asyncio.run_coroutine_threadsafe(setup(), window.loop).result(5)
        window.saved = {"language": "en"}
        window.page = "talk"
        window.setup_frame.pack_forget()
        window.talk_frame.pack(fill="both", expand=True)
        # Drive the actual microphone button and production preflight/turn path.
        window.speaker.speaking = True
        window.start_button.invoke()
        assert not window.speaker.speaking
        # Playback now starts on the runtime thread before Tk consumes its notice.
        until(lambda: len(window.speaker.requests) == 1 and not window.retrying, timeout=55)
        assert window.running and window.listening, window.state.get()
        assert str(window.question_entry.cget("state")) == "normal"
        assert not window.retry_notice.winfo_ismapped() and window.retry_notice.job is None
        assert len(captured) == len(closed) == 1
        assert len(window.speaker.requests) == 1 and len(window.controller.history) == 2
        assert window.answer.get("1.0", "end-1c") == "My name is Alex."
        for stage, attempts in calls.items():
            expected = [1, 2, 3, 4, 5] + ([4] if stage == "speech" else [])
            assert len(attempts) == len(expected) + 1, (stage, len(attempts))
            gaps = [attempts[i + 1][0] - attempts[i][0] for i in range(len(expected))]
            assert all(delay - 0.05 <= gap < delay + 1 for delay, gap in zip(expected, gaps, strict=True)), (
                gaps
            )
            print(stage, "retry delays (seconds):", [round(gap, 2) for gap in gaps], flush=True)
        assert len({request.content for _, request in calls["speech"]}) == 1
        messages = [json.loads(request.content)["messages"] for _, request in calls["response"]]
        assert all(message == messages[0] for message in messages)
        assert not window.capture_allowed()
        assert len(captured) == 1, "reopened microphone during the final spoken answer"
        window.pause()
        until(lambda: not window.running, check_retry=False)

        # A typed question stops previous playback before its first request. The same
        # microphone button can cancel it even though continuous listening is off.
        scenario = "cancel"
        window.speaker.speaking = True
        window.typed_question.set("What is your name?")
        window.ask_button.invoke()
        assert window.running and not window.speaker.speaking
        until(lambda: window.retrying)
        before = len(calls["response"])
        window.retry_notice.cancel_button.invoke()
        until(lambda: not window.running, check_retry=False)
        assert not window.retrying and not window.listening
        assert not window.retry_notice.winfo_ismapped() and window.retry_notice.job is None
        assert len(captured) == 1 and len(calls["response"]) == before
        assert len(window.speaker.requests) == 1
        assert str(window.question_entry.cget("state")) == "normal"
        assert "Start microphone" in window.start_button.cget("text")
        print("native retry retention, microphone/speaker interlocks and cancellation verified", flush=True)

        scenario = "exhaust"
        before = len(calls["response"])
        window.typed_question.set("What is your name?")
        window.ask_button.invoke()
        until(lambda: not window.running, timeout=25)
        assert len(calls["response"]) == before + 6
        assert "still busy after 5 retries" in window.state.get()
        assert not window.listening and not window.retrying
        assert not window.retry_notice.winfo_ismapped() and window.retry_notice.job is None
        assert "Start microphone" in window.start_button.cget("text")
        assert str(window.question_entry.cget("state")) == "normal"
        assert len(captured) == 1 and len(window.speaker.requests) == 1
        assert len(window.controller.history) == 2, "failed turn changed completed history"
        print(
            "six rejected attempts return controls to Start microphone without replay or speech", flush=True
        )
        scenario = "cancel_round"
        before = len(calls["speech"])
        root.geometry("1180x860")
        window.start_button.invoke()
        until(lambda: window.retrying and window.retry_notice.phase == "between_rounds", timeout=25)
        assert window.retry_notice.countdown.get() == "Next round in 3 s"
        first_hand = window.retry_notice.clock.coords(window.retry_notice.hand)
        until(lambda: window.retry_notice.countdown.get() == "Next round in 2 s", timeout=2)
        assert window.retry_notice.clock.coords(window.retry_notice.hand) != first_hand
        if args.output:
            capture_window(root.winfo_id(), args.output / "speech-round-countdown.png")
        window.retry_notice.cancel_button.invoke()
        until(lambda: not window.running, check_retry=False)
        assert len(calls["speech"]) == before + 6
        assert not window.retry_notice.winfo_ismapped() and window.retry_notice.job is None
        assert len(window.speaker.requests) == 1 and len(window.controller.history) == 2
        print("centered clock panel, live countdown and between-round cancellation verified", flush=True)
        if args.output:
            assert snapshots == {"waiting", "submitting", "between_rounds"}
            (args.output / "ui-result.json").write_text(
                json.dumps({"passed": True, "snapshots": sorted(snapshots), "cloud_calls": 0}, indent=2),
                encoding="utf-8",
            )
    finally:
        window.retry_notice.hide()
        for job in root.tk.splitlist(root.tk.call("after", "info")):
            root.after_cancel(job)
        window.close()
        deadline = time.monotonic() + 10
        while window.worker.is_alive() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)


if __name__ == "__main__":
    main()
