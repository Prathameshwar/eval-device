"""A failed turn does not end the operator's microphone session or replay old input.

The guarantees here predate continuous capture and are unchanged by it. What changed is how
they are kept: the device is held open for the whole session and a failed question is reported
on the processing surface, instead of the microphone being closed and reopened on a timer.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from test_busy_retry import answer_ok, client, frames, speech_ok
from test_speech import FakeWindow
from training_client.pms_client import ClientError

from human_test.app import Window


@pytest.mark.parametrize(
    ("listening", "busy", "expected"),
    [(True, False, "session_ended"), (True, True, "cancelled"), (False, False, "cancelled")],
)
async def test_pause_distinguishes_idle_listening_from_interrupted_question(listening, busy, expected):
    started = asyncio.Event()

    async def operation():
        started.set()
        await asyncio.Event().wait()

    window = FakeWindow(
        running=False,
        listening=listening,
        closing=False,
        controller=SimpleNamespace(busy=busy),
        loop=asyncio.get_running_loop(),
    )
    Window.submit(window, operation(), "session_ended" if listening else "turn_complete")
    await started.wait()
    task = window.active
    Window.pause(window)
    await asyncio.gather(task, return_exceptions=True)
    assert list(window.events.queue) == [(expected, None)]
    assert task.cancelled() and not window.listening


@pytest.mark.parametrize("recognized", ["", "...?"])
async def test_unrecognized_audio_does_not_stop_display_updates(recognized):
    """The real no-speech event sequence must leave the UI pump and next turn alive."""
    import time

    from test_flow import settings
    from training_client.controller import Controller

    timings = []
    window = FakeWindow(
        listening=True,
        running=True,
        capture_quality=None,
        timing=SimpleNamespace(set=timings.append),
        question=object(),
        answer=SimpleNamespace(get=lambda *args: "A previous reply."),
        replace=lambda *args: None,
    )
    window.manikin.stop_animation = lambda: None
    controller = Controller(settings(), window.emit)
    window.controller = controller
    try:
        window.emit("state", "Transcribing")
        result = await controller.respond({"text": recognized, "asr_finalize_ms": 230}, time.monotonic())
        window.drain()
        assert result["ignored"] and result["answer"] is None
        assert window.status[-1] == "No question to answer. Still listening."
        assert window.modes[-1] == "Listening" and window.listening and window.running
        assert window.speaker.requests == [] and window.displayed == []
        assert "not requested" in timings[-1]
        assert window.events.empty() and window.scheduled == [30]
        window.emit("state", "Listening")
        window.drain()
        assert window.status[-1] == "Listening" and window.scheduled == [30, 30]
        assert not controller.history
    finally:
        await controller.close()


def test_failed_transcription_clears_the_processing_badge():
    window = FakeWindow(listening=True, running=True)
    window.emit("state", "Transcribing")
    window.emit("turn_failed", "Audio failed: inference_timeout")
    window.drain()
    assert window.modes[-1] == "Listening"
    assert window.listening and window.running


@pytest.mark.parametrize(
    "message",
    [
        "The transcription outcome is unknown. Use Check last request; audio was not replayed.",
        "Daily cloud speech capacity has been reached.",
        "Microphone disconnected",
        "PMS: permission_denied",
        "Unexpected service failure",
    ],
)
def test_failed_question_keeps_the_session_listening(message):
    """One bad question costs that question, never the rest of the interview."""
    warnings = []
    window = FakeWindow(
        listening=True,
        running=True,
        turn_warning=SimpleNamespace(set=warnings.append),
    )
    window.emit("turn_failed", message)
    window.drain()
    # The session still owns the device, so both flags stay set and nothing is rescheduled.
    assert window.listening and window.running
    assert warnings == [message]
    assert message in window.status[-1] and "still listening" in window.status[-1]
    # The microphone surface is not touched by a processing failure.
    assert window.mic_states == []
    # 30 ms is drain re-arming itself; the old 400/3000 ms reopen timers are gone.
    assert not {400, 3000} & set(window.scheduled), "a held-open device needs no reopening timer"


@pytest.mark.parametrize("action", ["pause", "close", "leave"])
def test_a_manual_stop_leaves_nothing_pending(action):
    """Stopping used to have to outrun a queued reopen; now there is nothing to outrun."""
    window = FakeWindow(listening=True, running=True)
    window.emit("turn_failed", "Speech interrupted")
    window.drain()
    if action == "pause":
        Window.pause(window)
    elif action == "close":
        window.closing = True
    else:
        window.page = "setup"
    assert not {400, 3000} & set(window.scheduled) and window.started == []
    if action == "pause":
        assert not window.listening and window.mic_states[-1] == "Microphone off"
        # Stopping cancels the live session rather than leaving work to fire later.
        assert len(window.cancellations) == 1


@pytest.mark.parametrize("event", ["error", "cancelled", "session_ended"])
def test_a_session_ending_closes_the_microphone_and_stays_off(event):
    """The session owns the device for its whole life, so its end is the microphone's end."""
    window = FakeWindow(listening=True, running=True)
    window.emit(event, "Failure")
    window.drain()
    assert not window.listening and not window.running
    assert window.mic_states[-1] == "Microphone off"
    assert not {400, 3000} & set(window.scheduled) and window.started == []
    assert "Start the microphone" in window.status[-1]


def test_a_display_backlog_can_never_kill_the_session():
    """A full display queue discards status refreshes while preserving a turn outcome.

    Reporting a failure displaces a stale event. Microphone, queue-depth, and streamed-answer
    updates can be dropped without tearing down the listening session.
    """
    window = FakeWindow(listening=True, running=True)
    for _ in range(window.events.maxsize):
        Window.emit(window, "state", "Generating")
    Window.emit(window, "answer_delta", "More text")
    assert all(kind == "state" for kind, _ in window.events.queue)
    # Cosmetic surfaces never raise, whatever the backlog.
    Window.emit(window, "mic", "Hearing you")
    Window.emit(window, "queued", 1)
    # The per-question failure gets through by displacing a stale event.
    Window.emit(window, "turn_failed", "Display backlog; question cancelled")
    window.drain()
    assert window.listening and window.running
    assert not {400, 3000} & set(window.scheduled)


@pytest.mark.parametrize("stage", ["speech", "answer"])
async def test_unknown_turn_then_success_uses_new_audio_and_preserves_recovery(stage):
    calls, events = [], []
    failed = False

    def handler(request):
        nonlocal failed
        calls.append(request)
        speech = request.url.path.endswith("/speech/transcriptions")
        if not failed and speech == (stage == "speech"):
            failed = True
            return httpx.Response(
                502,
                json={"error": {"code": "speech_submission_unknown" if speech else "llm_transport_unknown"}},
            )
        return speech_ok(request) if speech else answer_ok(json.loads(request.content))

    controller = await client(handler, events)
    try:
        with pytest.raises(ClientError):
            await controller.turn(frames())
        recovery = controller.pms.recovery_request
        assert recovery[0] == stage and recovery[1]
        assert not controller.history and not controller.busy
        first_count = len(calls)
        await controller.turn(frames())
        assert len(calls) == first_count + 2
        assert len(controller.history) == 2
        assert controller.pms.recovery_request == recovery
        assert controller.pms.last_speech_request != recovery[1]
        assert controller.pms.last_request != recovery[1]
        controller.reset()
        assert controller.pms.recovery_request is None
    finally:
        await controller.close()


async def test_the_worker_processes_questions_in_order_and_survives_a_failure(monkeypatch):
    """One worker, one order, and a failure that costs only its own question.

    Spoken and typed questions share the worker deliberately: the conversation history they
    build is sequential, so they cannot be allowed to overtake one another.
    """
    from test_listening import settings
    from test_speech import WindowSpeaker
    from training_client.capture import CaptureQuality
    from training_client.listening import Utterance
    from training_client.runtime import Runtime

    listeners = []

    class FakeListener:
        def __init__(self, *args, **kwargs):
            self.ready = asyncio.Queue(maxsize=4)
            self.failure = None
            self.started = False
            listeners.append(self)

        async def run(self):
            self.started = True
            await asyncio.Event().wait()

    class FakeController:
        async def refresh_local_models(self):
            return False

        def __init__(self):
            self.calls = []
            self.preflights = 0

        async def preflight(self):
            self.preflights += 1

        async def turn(self, frames):
            captured = [frame async for frame in frames]
            self.calls.append(("voice", len(captured)))
            if len(self.calls) == 2:
                raise ClientError("Speech service failed")

        async def text_turn(self, text):
            self.calls.append(("text", text))

    controller = FakeController()
    events = []
    runtime = Runtime(
        settings(),
        lambda kind, value: events.append((kind, value)),
        controller=controller,
        speaker=WindowSpeaker(),
        listener_factory=FakeListener,
    )

    def question(blocks=1):
        utterance = Utterance(runtime.settings, CaptureQuality())
        for _ in range(blocks):
            utterance.add(b"\x00\x00", (0.0, 0, 0))
        utterance.close("endpoint")
        return utterance

    task = asyncio.create_task(runtime.listen())
    for _ in range(50):
        if listeners and listeners[0].started:
            break
        await asyncio.sleep(0.01)
    listener = listeners[0]
    assert listener.started and runtime.work is listener.ready
    # Three spoken questions with a typed one between them; the second spoken one fails.
    listener.ready.put_nowait(question())
    listener.ready.put_nowait(question())
    listener.ready.put_nowait("typed question")
    listener.ready.put_nowait(question())
    for _ in range(80):
        if len(controller.calls) == 4:
            break
        await asyncio.sleep(0.01)
    assert controller.calls == [("voice", 1), ("voice", 1), ("text", "typed question"), ("voice", 1)]
    # The failure was reported and the session kept going rather than tearing down.
    assert ("turn_failed", "Speech service failed") in events
    assert not task.done(), "one failed question must not end the session"
    # Configuration is re-checked per question, after capture rather than before it.
    assert controller.preflights == 5
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert runtime.work is None, "the queue is released with the session"
