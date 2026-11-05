"""Speaker output: no model or audio device is required except in the opt-in native check."""

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_flow import settings
from training_client import speech
from training_client.runtime import Runtime
from training_client.speech import Speaker
from training_contracts.patient_conversation import resolved_language

from human_test.app import SPEECH_STALL_LIMIT_MS, Window


class FakeEngine:
    """Records playback without touching a sound device."""

    def __init__(self, seconds=0.2):
        self.seconds = seconds
        self.played = []
        self.loaded = []
        self.genders = []
        self.closed = False
        self._interrupt = threading.Event()
        self.started = threading.Event()

    def load(self, language, gender="male", preferred=None):
        self.loaded.append(language)
        self.genders.append(gender)
        return object()

    def interrupt(self):
        self._interrupt.set()

    def play(self, text, language, still_current, gender="male", preferred=None, on_progress=None):
        self.genders.append(gender)
        self._interrupt.clear()
        self.started.set()
        deadline = time.monotonic() + self.seconds
        while time.monotonic() < deadline:
            if self._interrupt.is_set() or not still_current():
                self.played.append((text, language, "interrupted"))
                return
            if on_progress:
                on_progress()
            time.sleep(0.01)
        self.played.append((text, language, "complete"))

    def close(self):
        self.closed = True


def wait_until(predicate, limit=5):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_speaker_archives_played_frames_and_balances_busy_even_on_failure(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch)
    events = []

    class Archive:
        def busy(self, value):
            events.append(("busy", value))

        def audio_start(self, sid, stream):
            events.append(("start", sid, stream))

        def audio(self, sid, stream, pcm, rate, kind):
            events.append(("audio", sid, pcm, rate, kind))

        def audio_end(self, sid, stream):
            events.append(("end", sid, stream))

    class Engine(FakeEngine):
        def play(self, *args, on_audio=None, **kwargs):
            on_audio(b"\x01\x00", 22050)
            raise RuntimeError("playback stopped")

    speaker = Speaker(engine=Engine())
    try:
        assert speaker.speak("Fictional answer", "en", archive=(Archive(), "session"))
        assert wait_until(lambda: len(events) == 5)
        assert events[0] == ("busy", True) and events[-1] == ("busy", False)
        assert events[2] == ("audio", "session", b"\x01\x00", 22050, "patient_audio")
        assert events[1][2] == events[3][2]
    finally:
        speaker.close()


def test_speaker_controls_in_separate_tk_interpreter():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("speaker_smoke.py"))],
        env={key: value for key, value in os.environ.items() if not key.startswith("HUMAN_")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_disabled_or_unavailable_language_declines_without_audio(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en",))
    engine = FakeEngine()
    speaker = Speaker(enabled=False, engine=engine)
    assert speaker.speak("Hello", "en") is False and not speaker.speaking
    speaker.enabled = True
    # Hindi is pinned nowhere in this fixture: decline with a message, never raise.
    assert speaker.speak("मुझे तकलीफ़ है।", "hi") is False
    assert "hi" in speaker.last_error and not speaker.speaking
    assert speaker.speak("   ", "en") is False
    assert engine.played == []
    speaker.close()


def test_speaks_then_clears_and_newest_answer_supersedes(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en",))
    engine = FakeEngine(seconds=0.15)
    speaker = Speaker(engine=engine)
    try:
        assert speaker.speak("First answer.", "en") is True
        assert speaker.speaking
        assert wait_until(lambda: not speaker.speaking), "speech never finished"
        assert engine.played == [("First answer.", "en", "complete")]
        engine.played.clear()
        speaker.speak("Second answer.", "en")
        assert wait_until(lambda: engine.started.is_set())
        speaker.speak("Third answer.", "en")
        assert wait_until(lambda: any(p[0] == "Third answer." for p in engine.played))
        # The superseded answer is abandoned, not queued behind the newest one.
        assert ("Second answer.", "en", "complete") not in engine.played
    finally:
        speaker.close()
    assert engine.closed


def test_stop_interrupts_playback_and_close_is_idempotent(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en",))
    engine = FakeEngine(seconds=5)
    speaker = Speaker(engine=engine)
    speaker.speak("A long answer that must stop early.", "en")
    assert wait_until(lambda: engine.started.is_set())
    speaker.stop()
    assert not speaker.speaking
    assert wait_until(lambda: engine.played and engine.played[0][2] == "interrupted")
    speaker.close()
    speaker.close()


def test_warm_loads_only_installed_languages(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en",))
    engine = FakeEngine()
    speaker = Speaker(engine=engine)
    try:
        speaker.warm("hi")
        speaker.warm("en")
        assert wait_until(lambda: engine.loaded == ["en"])
    finally:
        speaker.close()


def test_answer_language_remains_explicit_even_with_mixed_input():
    assert resolved_language("en", "Bonjour Alex") == "en"
    assert resolved_language("en", "") == "en"
    with pytest.raises(ValueError):
        resolved_language("auto", "Hello")


class WindowSpeaker:
    """Speaker stand-in for window tests; no thread, no model, no device."""

    def __init__(self):
        self.enabled = True
        self.speaking = False
        self.requests = []
        self.stops = 0
        self.warmed = []
        self.last_error = None
        self.progress = 0

    def prefer(self, key):
        return None

    def catalogue(self):
        return []

    def speak(self, text, language, gender="male"):
        self.requests.append((text, language, gender))
        if not self.enabled:
            return False
        self.speaking = True
        return True

    def warm(self, language, gender="male"):
        self.warmed.append((language, gender))

    def stop(self):
        self.stops += 1
        self.speaking = False

    def close(self):
        self.stop()


class FakeWindow:
    """Minimal stand-in that carries only what the window methods under test touch.

    Tcl cannot reliably initialize a second interpreter in one process on Windows, and
    `tests/test_patient_workflow.py` already creates the one real root, so these tests call
    the production methods directly instead of building a second window.
    """

    def __init__(self, **overrides):
        self.closing = False
        self.listening = False
        self.running = False
        self.retrying = False
        self.retry_exhausted = False
        self.controller = None
        self.lock_options = lambda locked: None
        self.turn_warning = SimpleNamespace(set=lambda note: None)
        self.warning_label = SimpleNamespace(grid=lambda **kw: None, grid_remove=lambda: None)
        self.retry_updates = []
        self.retry_notice = SimpleNamespace(
            show=self.retry_updates.append, hide=lambda: self.retry_updates.append(None)
        )
        self.page = "talk"
        self.speaker = WindowSpeaker()
        self.camera_view = SimpleNamespace(poll=lambda: None, recording=False)
        self.record_label = SimpleNamespace(grid=lambda **kw: None, grid_remove=lambda: None)
        self.events = queue.Queue(maxsize=64)
        self.settings = settings()
        self.started = []
        self.status = []
        self.held = 0
        self.scheduled = []
        self.displayed = []
        self.modes = []
        self.button_states = []
        self.question_states = []
        self.ask_states = []
        self.question_entry = SimpleNamespace(configure=lambda **values: self.question_states.append(values))
        self.ask_button = SimpleNamespace(configure=lambda **values: self.ask_states.append(values))
        self.gesture_prepared = []
        self.gesture_playback = []
        self.gesture_stops = 0
        self.idle_gestures = []
        self.blink_visibility = []
        self.answer = object()
        self.active = None
        # Cancelling a live session is scheduled on the worker's loop, so record it instead.
        self.cancellations = []
        self.loop = SimpleNamespace(call_soon_threadsafe=self.cancellations.append)
        self.work = None
        self.playback_progress = self.playback_stalled_at = None
        self.mic_states = []
        self.state = SimpleNamespace(set=self.status.append)
        self.mic_state = SimpleNamespace(set=self.mic_states.append)
        self.manikin = SimpleNamespace(
            hold_speaking=self.hold,
            speak=self.displayed.append,
            set_status=self.modes.append,
            prepare_speech_gesture=self.gesture_prepared.append,
            update_speech_gesture=lambda *args: self.gesture_playback.append(args),
            stop_speech_gesture=self.stop_gesture,
            update_idle_gesture=self.idle_gestures.append,
            update_blink=self.blink_visibility.append,
        )
        self.start_button = SimpleNamespace(configure=lambda **values: self.button_states.append(values))
        self.root = SimpleNamespace(after=lambda delay, callback=None: self.scheduled.append(delay))
        self.speaker_output = SimpleNamespace(get=lambda: self.settings.speaker_output)
        self.history_message = SimpleNamespace(set=lambda value: None)
        self.history_turn = None
        self.__dict__.update(overrides)
        from human_test import app

        self.runtime = Runtime(self.settings, self._observe, speaker=self.speaker, clock=lambda: app._now())
        self.runtime.controller = self.controller
        self.runtime.retrying = self.retrying
        self.runtime.work = self.work

    def hold(self):
        self.held += 1

    def show_warning(self, note):
        self.turn_warning.set(note)
        self.warning_label.grid()

    def stop_gesture(self):
        self.gesture_stops += 1

    def replace(self, widget, text, append=False):
        assert widget is self.answer

    def begin(self):
        self.started.append({})

    def emit(self, kind, value):
        self.runtime.controller = self.controller
        self.runtime.emit(kind, value)

    def _observe(self, kind, value):
        self.events.put_nowait((kind, value))

    def drain(self):
        Window.drain(self)


def test_speaker_output_defaults_to_enabled():
    assert settings().speaker_output is True, "speaker output must default to checked"


@pytest.mark.parametrize(
    "state,allowed",
    [
        ({}, True),
        ({"running": True, "listening": True}, True),
        ({"running": True}, False),
        ({"page": "setup"}, False),
        ({"retrying": True}, False),
    ],
)
def test_idle_leg_movement_is_only_allowed_in_quiet_conversation(state, allowed):
    window = FakeWindow(**state)
    window.drain()
    assert window.idle_gestures == [allowed]
    window.speaker.speaking = True
    window.drain()
    assert window.idle_gestures[-1] is False


@pytest.mark.parametrize("state", [{}, {"listening": True}, {"running": True}, {"retrying": True}])
def test_blinking_remains_available_in_all_visible_conversation_states(state):
    window = FakeWindow(**state)
    window.drain()
    window.speaker.speaking = True
    window.drain()
    assert window.blink_visibility == [True, True]
    window.page = "setup"
    window.drain()
    assert window.blink_visibility[-1] is False


def test_gestures_are_armed_only_for_accepted_patient_audio_and_muting_resets():
    window = FakeWindow()
    window.emit("answer", "Text-only or recovered answer")
    window.drain()
    assert window.gesture_prepared == []
    window.speaker.progress = 12
    window.emit("speak", {"text": "New patient reply", "language": "en"})
    window.drain()
    assert window.gesture_prepared == [12]
    assert window.gesture_playback[-1] == (True, 12)
    window.speaker.progress += 1
    window.drain()
    assert window.gesture_prepared == [12], "Polling must not rearm a gesture"
    assert window.gesture_playback[-1] == (True, 13)
    window.settings.speaker_output = False
    before = window.gesture_stops
    Window.apply_speaker_output(window)
    assert window.gesture_stops == before + 1 and not window.speaker.speaking
    window.emit("speak", {"text": "Muted reply", "language": "en"})
    window.drain()
    assert window.gesture_prepared == [12] and window.gesture_playback[-1] == (False, 13)
    window.speaker.enabled = True
    window.speaker.speak = lambda *args: False  # Unavailable voice or refused audio.
    window.emit("speak", {"text": "Unspoken reply", "language": "en"})
    window.drain()
    assert window.gesture_prepared == [12]


def test_only_new_answers_are_spoken_and_redisplayed_text_is_silent():
    window = FakeWindow()
    window.emit("speak", {"text": "मेरा नाम Alex है।", "language": "hi"})
    window.drain()
    assert window.speaker.requests == [("मेरा नाम Alex है।", "hi", "male")]
    # A recovered or redisplayed answer must never be spoken.
    window.emit("answer", "Recovered answer text")
    window.drain()
    assert window.speaker.requests == [("मेरा नाम Alex है।", "hi", "male")]


def test_playing_speech_drives_the_expression_and_failures_are_reported_once():
    window = FakeWindow()
    window.speaker.speaking = True
    window.drain()
    assert window.held == 1 and window.status == []
    window.speaker.speaking = False
    window.speaker.last_error = "No installed hi voice; the answer is shown as text only"
    window.drain()
    assert window.status == ["No installed hi voice; the answer is shown as text only"]
    assert window.speaker.last_error is None
    window.drain()
    assert len(window.status) == 1, "a speech problem must be reported once, not every tick"


def test_capture_is_muted_while_the_patient_speaks_and_a_stall_releases_it(monkeypatch):
    """The device now stays open, so the answer is kept out by muting, not by closing it.

    The two guarantees are unchanged from when capture was reopened per question: the patient's
    own answer is never captured back, and a device that stops progressing releases the
    microphone instead of stranding input. What decides is playback progress, not elapsed time,
    so a long answer is never cut into.
    """
    clock = [1000.0]
    monkeypatch.setattr("human_test.app._now", lambda: clock[0])
    window = FakeWindow(listening=True)

    window.speaker.speaking = False
    assert Window.capture_allowed(window) is True

    # Speech reaching the device mutes capture and starts the stall budget.
    window.speaker.speaking = True
    window.speaker.progress = 5
    assert Window.capture_allowed(window) is False
    clock[0] += SPEECH_STALL_LIMIT_MS / 1000 - 0.1
    assert Window.capture_allowed(window) is False, "a long answer must not be cut into"

    # Real playback progress resets the budget, however long the answer runs.
    window.speaker.progress = 6
    assert Window.capture_allowed(window) is False
    clock[0] += SPEECH_STALL_LIMIT_MS / 1000 - 0.1
    assert Window.capture_allowed(window) is False

    # Progress that stops for the whole budget releases the microphone.
    clock[0] += 0.2
    assert Window.capture_allowed(window) is True

    # Playback ending clears the budget, so the next answer starts from a clean state.
    window.speaker.speaking = False
    assert Window.capture_allowed(window) is True
    assert window.playback_progress is None and window.playback_stalled_at is None


def test_retry_state_stops_speech_and_defers_new_playback_until_success():
    window = FakeWindow(listening=True, running=True)
    window.speaker.speaking = True
    window.emit("retrying", True)
    window.emit("state", "Speech busy; audio retained. Retry 1/5 in 1 s.")
    progress = {"phase": "waiting", "round": 1, "rounds": 10, "retry": 1}
    window.emit("retry_status", progress)
    window.emit("speak", {"text": "Must not play while retrying", "language": "en"})
    window.drain()
    assert window.retrying and not window.speaker.speaking
    assert window.speaker.stops == 1 and window.speaker.requests == []
    assert window.modes == ["Retrying", "Retrying"]
    assert window.button_states[-1]["text"] == "Cancel queued question"
    assert window.question_states[-1] == window.ask_states[-1] == {"state": "disabled"}
    assert window.retry_updates == [progress]
    # A retry keeps the microphone open: the learner must not have to wait for the service.
    assert Window.capture_allowed(window) is True
    window.emit("retrying", False)
    window.emit("speak", {"text": "Successful answer", "language": "en"})
    window.drain()
    assert window.speaker.requests == [("Successful answer", "en", "male")]
    assert not window.retrying
    assert window.question_states[-1] == window.ask_states[-1] == {"state": "normal"}
    assert window.retry_updates == [progress, None]
    window.emit("retry_status", progress)
    window.drain()
    assert window.retry_updates == [progress, None], "stale progress must not reopen the panel"


def test_typed_question_retry_can_be_cancelled_with_microphone_button():
    cancelled = []
    window = FakeWindow(retrying=True, running=True, pause=lambda: cancelled.append(True))
    Window.toggle(window)
    assert cancelled == [True] and window.started == []


def test_toggling_speaker_output_off_stops_playback_immediately():
    window = FakeWindow()
    window.settings.speaker_output = False
    Window.apply_speaker_output(window)
    assert window.speaker.enabled is False and window.speaker.stops == 1
    window.settings.speaker_output = True
    Window.apply_speaker_output(window)
    assert window.speaker.enabled is True and window.speaker.stops == 1


def installed_voice(tmp_path, monkeypatch, languages=("en",)):
    entries = [
        {
            "key": key,
            "label": key,
            "language": key.split("-")[0],
            "gender": "female" if "female" in key else "male",
            "default": True,
        }
        for key in languages
    ]
    monkeypatch.setattr(speech, "catalogue", lambda: entries)
    return entries


def test_available_and_missing_report_central_metadata(tmp_path, monkeypatch):
    entries = installed_voice(tmp_path, monkeypatch, ("en", "hi"))
    assert speech.available("en") and speech.available("hi")
    entries[:] = [v for v in entries if v["language"] != "hi"]
    assert speech.available("hi") is None and speech.missing_languages() == ["hi"]
    assert speech.available("fr") is None


def test_chosen_voice_stays_with_its_language_and_defaults_are_preferred(tmp_path, monkeypatch):
    entries = installed_voice(tmp_path, monkeypatch, ("en-male", "en-male-alt", "hi-male"))
    entries[0]["label"] = "Default male"
    entries[1].update(default=False, label="Other male")
    assert speech.selected_voice("en", "male")[0] == "en-male"
    assert speech.selected_voice("en", "male", "en-male-alt")[0] == "en-male-alt"
    assert speech.selected_voice("hi", "male", "en-male-alt")[0] == "hi-male"
    assert speech.selected_voice("en", "female")[0] == "en-male"
    speaker = Speaker(engine=FakeEngine())
    try:
        assert speaker.prefer("en-male-alt")["label"] == "Other male"
        assert speaker.preference("en") == "en-male-alt" and speaker.preference("hi") is None
        assert speaker.prefer("unknown") is None and speaker.preference("en") == "en-male-alt"
        speaker.prefer(None)
        assert speaker.preference("en") is None
    finally:
        speaker.close()
