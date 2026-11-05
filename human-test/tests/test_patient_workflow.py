import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from copy import deepcopy
from pathlib import Path

import pytest
from test_flow import settings
from training_client.capture import CaptureQuality
from training_client.controller import Controller
from training_client.pms_client import ClientError, PMSClient, pms_error

from human_test.app import Window


async def test_desktop_reads_own_published_scenario_before_legacy_catalog(monkeypatch):
    client = PMSClient(settings())
    paths = []
    saved = {"id": "choice", "scenario_id": "published", "revision": 1}

    async def request(method, path, **_):
        paths.append(path)
        return {"selection": saved}

    monkeypatch.setattr(client, "json", request)
    try:
        assert await client.selection() == saved
        assert paths == [client.practice_base + "/scenario-selection"]
    finally:
        await client.close()


async def test_desktop_handles_learner_without_legacy_catalog_grant(monkeypatch):
    client = PMSClient(settings())
    paths = []

    async def request(method, path, **_):
        paths.append(path)
        if path.endswith("/scenario-selection"):
            return {"selection": None}
        raise ClientError("Permission denied", code="permission_denied")

    monkeypatch.setattr(client, "json", request)
    try:
        assert await client.selection() is None
        assert paths == [client.practice_base + "/scenario-selection", client.practice_base + "/selection"]
    finally:
        await client.close()


async def test_selected_revision_attached_and_history_reset(monkeypatch):
    c = Controller(settings(), lambda *args: None)
    c.history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old answer"}]
    selected = {
        "id": "00000000-0000-4000-8000-000000000001",
        "revision": 2,
        "language": "en",
        "document": {"patient": {"name": "Alex"}},
    }
    try:
        c.use_selection(selected)
        assert not c.history and c.settings.language == "en" and c.pms.practice["practice_revision"] == 2
        c.busy = True
        with pytest.raises(ClientError):
            c.use_selection({**selected, "revision": 3})
        c.busy = False
        captured = []

        async def answer(messages, emit):
            captured.extend(messages)
            return {"text": "Alex", "finish_reason": "stop"}

        async def context(*args):
            return None

        monkeypatch.setattr(c.pms, "ensure_conversation", context)
        monkeypatch.setattr(c.pms, "answer", answer)
        c.history = [
            {"role": role, "content": "x" * 1500} for _ in range(10) for role in ("user", "assistant")
        ]
        await c.text_turn("What is your name?")
        assert len(captured) <= 13 and sum(len(m["content"]) for m in captured) <= 16000
        assert captured[-1]["content"] == "What is your name?" and captured[0]["role"] == "user"
    finally:
        await c.close()


async def test_pms_client_submits_practice_context_only_when_selected(monkeypatch):
    client = PMSClient(settings(streaming=False))
    seen = []

    async def request(method, path, **kwargs):
        payload = kwargs["json"]
        seen.append(payload)
        return {
            "request_key": payload["request_key"],
            "status": "succeeded",
            "text": "Alex",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(client, "json", request)
    try:
        client.use_selection(
            {"id": "selection", "revision": 7, "language": "en", "document": {"patient": {"name": "Alex"}}}
        )
        await client.answer([{"role": "user", "content": "Name?"}], lambda *a: None)
        assert seen[0]["practice_id"] == "selection" and seen[0]["practice_revision"] == 7
        assert "document" not in seen[0] and "system_prompt" not in seen[0]
    finally:
        await client.close()


async def test_legacy_global_selection_cannot_start_a_new_interview(monkeypatch):
    client = PMSClient(settings())

    async def unexpected(*args, **kwargs):
        raise AssertionError("Legacy selection must not reach a conversation request")

    monkeypatch.setattr(client, "json", unexpected)
    try:
        with pytest.raises(ClientError, match="active tenant case") as error:
            client.use_selection(
                {
                    "id": "selection",
                    "revision": 4,
                    "language": "en",
                    "legacy": True,
                    "document": {"patient": {"name": "Alex"}},
                }
            )
        assert error.value.code == "legacy_patient_setup"
        assert client.practice is None
        assert await client.ensure_conversation() is None
        assert "tenant administrator" in str(pms_error({"error": {"code": "permission_denied"}}))
        assert "in this app" in str(pms_error({"error": {"code": "scenario_unavailable"}}))
        assert "selected language" in str(pms_error({"error": {"code": "scenario_language_unavailable"}}))
        assert "selected language" in str(pms_error({"error": {"code": "patient_language_unavailable"}}))
    finally:
        await client.close()


def test_desktop_save_before_conversation_and_explicit_microphone(monkeypatch):
    # Exercise the retained compatibility catalog form independently of the new
    # published-scenario startup; the latter has its own end-to-end window test.
    async def legacy_initialize(self):
        self.controller = await self.runtime.initialize()
        self.emit("catalog", (await self.controller.pms.catalog(), await self.controller.pms.selection()))
        self.emit("ready", "PMS connected")

    monkeypatch.setattr(Window, "initialize", legacy_initialize)
    fixtures = json.loads(
        (
            Path(__file__).parents[2] / "platform/api/migrations/versions/0013_patient_case_templates.json"
        ).read_text(encoding="utf-8")
    )
    rows = [{**c, "title": c["document"]["title"], "revision": 1} for c in fixtures]
    rows[0]["document"]["patient"]["name"] = "Jordan"
    casey_id = "00000000-0000-4000-8000-000000000402"
    casey_case = deepcopy(rows[1])
    casey_case["id"] = "00000000-0000-4000-8000-000000000499"
    casey_case["patient_identity_id"] = casey_id
    casey_case["title"] = "Casey interview"
    casey_case["document"]["patient"]["name"] = "Casey"
    rows.append(casey_case)
    catalog = {
        "categories": [
            {"id": rows[i]["category_id"], "name": n}
            for i, n in ((0, "Cardiology"), (3, "Nephrology"), (6, "Respiratory medicine"))
        ],
        "patients": [
            {
                "id": rows[0]["patient_identity_id"],
                "code": "jordan",
                "name": "Jordan",
                "age_years": 35,
                "sex": "male",
                "occupations": {"en": "Schoolteacher"},
                "height_cm": 175,
                "weight_kg": 75,
                "backgrounds": {"en": "Lives with family."},
            },
            {"id": casey_id, "code": "casey", "name": "Casey"},
        ],
        "cases": [{k: v for k, v in c.items() if k != "document"} for c in rows],
    }
    calls = []
    selected = None

    class FakePMS:
        async def catalog(self):
            return deepcopy(catalog)

        async def selection(self):
            return selected

        async def case(self, id):
            return deepcopy(next(c for c in rows if c["id"] == id))

        async def save_selection(self, body):
            nonlocal selected
            calls.append(body)
            selected = {
                "id": "saved",
                "revision": len(calls),
                "language": body["language"],
                "template_id": body["template_id"],
                "template_revision": body["template_revision"],
                "category_id": body["category_id"],
                "patient_identity_id": body["patient_identity_id"],
                "legacy": False,
                "document": deepcopy(next(c["document"] for c in rows if c["id"] == body["template_id"])),
            }
            selected["document"]["vitals"] = body["vitals"]
            return selected

    class FakeController:
        async def refresh_local_models(self):
            return False

        def __init__(self, *args, **kwargs):
            self.pms = FakePMS()

        def runs_locally(self):
            # This window drives a platform-executed route; local turns have their own tests.
            return False

        def use_selection(self, value):
            calls.append("bound")

        async def close(self):
            pass

        async def preflight(self):
            await asyncio.sleep(0.05)

    monkeypatch.setattr("training_client.runtime.Controller", FakeController)
    monkeypatch.setattr("human_test.app.microphones", lambda: [])
    # Opening the device is now a listening session, so that is what must not happen by itself.
    monkeypatch.setattr(
        "training_client.runtime.Listener", lambda *a, **k: pytest.fail("Microphone started automatically")
    )
    root = tk.Tk()
    root.withdraw()
    # This test drives text animation; installed voices must not start real playback.
    window = Window(root, settings(speaker_output=False))

    def settle():
        deadline = time.monotonic() + 4
        while window.running and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
        root.update()
        assert not window.running, window.state.get()

    try:
        settle()
        assert window.page == "setup" and window.loaded_case and not window.listening
        assert len(window.cases) == 3
        assert window.patient_name.get() == "Jordan"
        assert window.patient_profile.get() == "Jordan"
        window.patient_profile.set("Casey")
        window.patient_changed()
        settle()
        assert len(window.cases) == 1 and window.loaded_case["id"] == casey_case["id"]
        window.patient_profile.set("Jordan")
        window.patient_changed()
        settle()
        assert len(window.cases) == 3 and window.patient_name.get() == "Jordan"
        window.vitals["temperature_c"].set("38.2")
        window.save_setup()
        settle()
        assert window.page == "talk" and not window.listening
        assert window.active_case.get().startswith("Jordan")
        assert window.question.get("1.0", "end-1c") == ""
        assert window.answer.get("1.0", "end-1c") == ""
        assert window.manikin.patient_name == "Jordan" and "38.2" in window.manikin.observations
        # Check reports the room without starting a question. The default device is never chosen
        # from the list, so the button is the only way it ever gets tested.
        probes = []

        async def probe(settings, *args, **kw):
            probes.append(settings.microphone)
            quality = CaptureQuality()
            quality.blocks, quality.noise_floor, quality.device_name = 20, 40.0, "Fixture Mic"
            return quality

        monkeypatch.setattr("human_test.app.probe_microphone", probe)
        window.check_microphone()
        settle()
        assert probes == [None] and "Microphone ready" in window.state.get()
        window.emit("state", "Listening")
        window.emit("state", "Answering")
        root.after(40, lambda: None)
        window.drain()
        assert window.manikin.mode == "Preparing reply"
        window.emit("answer", "Hello, Alex here.")
        window.emit("state", "Complete")
        window.drain()
        assert window.answer.get("1.0", "end-1c") == "Hello, Alex here."
        assert window.manikin.mode == "Responding" and window.manikin.animation_job is not None
        window.emit("state", "Listening")
        window.drain()
        assert window.manikin.mode == "Responding" and window.manikin.resting_mode == "Listening"
        deadline = time.monotonic() + 3
        while window.manikin.animation_job is not None and time.monotonic() < deadline:
            root.update()
            time.sleep(0.025)
        assert window.manikin.mode == "Listening" and window.manikin.animation_job is None
        # A filtered utterance clears the prior answer without speech or a reply animation.
        original_speak = window.manikin.speak
        monkeypatch.setattr(
            window.manikin, "speak", lambda *args: pytest.fail("Ignored input animated a reply")
        )
        monkeypatch.setattr(window.speaker, "speak", lambda *args: pytest.fail("Ignored input reached TTS"))
        for ignored in ("hmm, thanks", "", "... ?"):
            window.emit("input_ignored", {"text": ignored, "generation": 0})
            window.drain()
            assert window.question.get("1.0", "end-1c") == ignored
            assert window.answer.get("1.0", "end-1c") == ""
            assert window.manikin.animation_job is None and "No question to answer" in window.state.get()
        monkeypatch.setattr(window.manikin, "speak", original_speak)
        assert calls[0]["vitals"]["temperature_c"] == 38.2 and calls[1] == "bound"
        gate = threading.Event()
        window.loop.call_soon_threadsafe(lambda: gate.wait(2))
        window.toggle()
        window.pause()
        gate.set()
        settle()
        assert not window.listening and "Cancelled" in window.state.get()
        window.manikin.speak("A longer reply to exercise animation cancellation")
        window.back()
        assert window.manikin.animation_job is None
        window.category.set("Nephrology")
        window.category_changed()
        settle()
        assert window.loaded_case["category_id"] == rows[3]["category_id"]
        window.reload()
        settle()
        assert window.category.get() == "Cardiology" and window.vitals["temperature_c"].get() == "38.2"
        # Saving another setup starts with a blank conversation, including after a prior reply.
        window.save_setup()
        settle()
        assert window.page == "talk" and not window.listening
        assert window.question.get("1.0", "end-1c") == ""
        assert window.answer.get("1.0", "end-1c") == ""
        # Repeated Back -> Save must reuse the window, worker and clients, without
        # adding polling/animation timers or opening the microphone automatically.
        controller, worker, speaker = window.controller, window.worker, window.speaker
        timers = len(root.tk.call("after", "info"))
        for _ in range(15):
            window.back()
            assert window.page == "setup"
            window.save_setup()
            settle()
            assert window.page == "talk" and not window.listening
            assert window.controller is controller and window.worker is worker and window.speaker is speaker
            assert window.active is None and window.events.empty()
            assert window.manikin.animation_job is None
            assert len(root.tk.call("after", "info")) <= timers
        window.back()
        catalog["cases"][1]["title"] = catalog["cases"][0]["title"]
        window.reload()
        settle()
        assert len(window.cases) == 3
        second = next(label for label, row in window.cases.items() if row["id"] == rows[1]["id"])
        window.case_choice.set(second)
        window.load_case()
        settle()
        assert window.loaded_case["id"] == rows[1]["id"]
        window.patient_profile.set("Casey")
        window.patient_changed()
        settle()
        window.save_setup()
        settle()
        assert calls[-2]["template_id"] == casey_case["id"]
        assert calls[-2]["patient_identity_id"] == casey_id
        window.back()
        selected = {**selected, "template_revision": 99}
        window.reload()
        settle()
        assert "updated" in window.setup_note.get()
        assert window.loaded_case["id"] == casey_case["id"]
        selected = {**selected, "legacy": True}
        window.reload()
        settle()
        assert "historical setup" in window.setup_note.get()
        assert window.loaded_case["id"] == rows[0]["id"]
        catalog["patients"][1]["name"] = "Jordan"
        window.reload()
        settle()
        assert len(window.patients) == 2
        casey_label = next(label for label, profile in window.patients.items() if profile["id"] == casey_id)
        assert "casey" in casey_label
        window.patient_profile.set(casey_label)
        window.patient_changed()
        settle()
        assert window.loaded_case["id"] == casey_case["id"]
        catalog["patients"][0]["name"] = "Updated Jordan"
        window.reload()
        settle()
        assert window.patient_name.get() == "Updated Jordan"
        # Published tenant drafts may use Hindi as their source, omit onset, and leave
        # observations for staff to enter in the rehearsal setup.
        rows[0]["document"]["source_language"] = "hi"
        rows[0]["document"]["presentation"] = {"chief_complaint": {"hi": "पेट में दर्द"}}
        rows[0]["document"]["vitals"].pop("pain_0_10")
        window.reload()
        settle()
        assert window.case_summary.get() == "पेट में दर्द"
        assert window.vitals["pain_0_10"].get() == ""
        window.save_setup()
        assert "finite number" in window.state.get()
        catalog["categories"] = []
        catalog["cases"] = []
        window.reload()
        settle()
        assert window.loaded_case is None and not window.cases
        assert "tenant" in window.setup_note.get()
        assert "historical global-case setup" in window.setup_note.get()
        assert window.patient_name.get() == "Patient"
        assert str(window.save_button["state"]) == "disabled"
        assert all(value.get() == "" for value in window.vitals.values())
    finally:
        window.close()
        deadline = time.monotonic() + 5
        while window.worker.is_alive() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)


def test_published_scenario_restore_save_and_refresh_stay_on_correct_threads(monkeypatch):
    # A fresh process avoids Windows Tcl state left by another destroyed Tk window.
    name = "test_published_scenario_restore_save_and_refresh_stay_on_correct_threads"
    if os.environ.get("HUMAN_TEST_TK_CHILD") != name:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(Path(__file__)) + "::" + name],
            env={**os.environ, "HUMAN_TEST_TK_CHILD": name},
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return
    document = json.loads(
        (
            Path(__file__).parents[2] / "platform/api/migrations/versions/0013_patient_case_templates.json"
        ).read_text(encoding="utf-8")
    )[0]["document"]
    document["patient"].update(height_cm=None, weight_kg=None, occupation=None)
    selected = {
        "id": "own-choice",
        "scenario_id": "published",
        "template_revision": 1,
        "revision": 1,
        "language": "en",
        "document": document,
    }
    calls = []
    main_thread = threading.get_ident()

    class FakePMS:
        async def scenario_options(self):
            return {
                "items": [
                    {
                        "id": "published",
                        "title": "Starter",
                        "version": 1,
                        "languages": ["en", "hi"],
                        "vitals": document["vitals"],
                    }
                ],
                "selection": deepcopy(selected),
                "default": {"scenario_id": "published", "language": "en"},
            }

        async def selection(self):
            return deepcopy(selected)

        async def catalog(self):
            pytest.fail("Published Practice must not require legacy author access")

        async def save_scenario_selection(self, body):
            calls.append(body)
            assert body["scenario_id"] == "published"
            assert body["expected_revision"] == selected["revision"]
            selected["revision"] += 1
            selected["document"]["vitals"] = body["vitals"]
            return deepcopy(selected)

    class FakeController:
        async def refresh_local_models(self):
            return False

        def __init__(self, *args, **kwargs):
            self.pms = FakePMS()

        def runs_locally(self):
            return False

        def use_selection(self, value):
            assert threading.get_ident() != main_thread
            calls.append("bound")

        async def close(self):
            pass

    monkeypatch.setattr("training_client.runtime.Controller", FakeController)
    monkeypatch.setattr("human_test.app.microphones", lambda: [])
    monkeypatch.setattr(
        "training_client.runtime.Listener", lambda *a, **k: pytest.fail("Unexpected microphone")
    )
    root = tk.Tk()
    root.withdraw()
    window = Window(root, settings(speaker_output=False))

    def settle():
        deadline = time.monotonic() + 4
        while window.running and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
        root.update()
        assert not window.running, window.state.get()

    try:
        settle()
        assert window.page == "setup" and window.scenario_selected
        assert not calls and "None" not in window.patient_info.get()
        assert str(window.category_box["state"]) == "disabled"
        assert str(window.case_box["state"]) == "readonly"
        window.vitals["temperature_c"].set("38.2")
        window.save_setup()
        settle()
        assert calls[0]["vitals"]["temperature_c"] == 38.2 and calls[1] == "bound"
        assert window.page == "talk" and not window.listening
        window.back()
        window.reload()
        settle()
        assert calls == [calls[0], "bound"]  # Refresh must not reset/bind a running context.
        assert window.vitals["temperature_c"].get() == "38.2"
        window.save_setup()
        settle()
        assert calls[2]["expected_revision"] == 2 and calls[3] == "bound"
    finally:
        window.close()
        deadline = time.monotonic() + 5
        while window.worker.is_alive() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)


def test_status_badge_reports_work_and_never_relabels_prose_as_ready():
    """The badge is a phase, not an echo of the status line.

    Every message used to fall through to "Ready", so a working machine looked idle while
    it transcribed, queued, or reported a failed turn. That is the confusing state this
    guards: prose leaves the badge alone, and real progress has its own label.
    """
    from human_test.manikin import phase_for

    # Progress phases, including the ones that carry detail.
    assert phase_for("Listening") == "Listening"
    assert phase_for("Transcribing") == "Transcribing"
    assert phase_for("Transcribing with whisper-audio-to-text") == "Transcribing"
    assert phase_for("Answering") == "Preparing reply"
    assert phase_for("Retrying") == "Waiting for model"
    assert phase_for("Queued: 1 question waiting") == "Question queued"
    assert phase_for("Complete") == "Ready"
    # Prose is for the status line. None means "leave the badge as it is".
    for prose in (
        "Microphone: only 9.1 dB above the room noise; move closer or reduce noise",
        "Question failed. Listening resumes in 3 seconds; ask your next question.",
        "Answer delivered; PMS did not record this local turn's metrics",
        "Loading case from PMS…",
    ):
        assert phase_for(prose) is None, prose


async def test_late_recognition_is_discarded_before_model_and_speech(monkeypatch):
    events = []
    c = Controller(settings(), lambda *args: events.append(args))
    finalized = []

    async def frames():
        try:
            yield b"audio"
        finally:
            finalized.append(True)

    async def recognize(config, source, emit, **kwargs):
        await anext(source)
        c._conversation_generation += 1  # A reset invalidates even a cancellation-resistant ASR.
        return {"text": "Name?", "asr_finalize_ms": 1}

    async def unexpected(*args):
        raise AssertionError("Stale recognition must not reach inference")

    monkeypatch.setattr("training_client.controller.audio_client.transcribe", recognize)
    monkeypatch.setattr(c.pms, "answer", unexpected)
    try:
        with pytest.raises(asyncio.CancelledError):
            await c.turn(frames())
        assert finalized and not c.busy
        assert not any(kind in {"answer", "answer_delta", "speak"} for kind, _ in events)
    finally:
        await c.close()


async def test_context_admission_failure_prevents_recognition(monkeypatch):
    c = Controller(settings(), lambda *args: None)

    async def denied(*args):
        raise ClientError("Permission revoked", code="forbidden")

    async def unexpected(*args):
        raise AssertionError("Do not recognize audio before context admission")

    async def frames():
        yield b"audio"

    monkeypatch.setattr(c.pms, "ensure_conversation", denied)
    monkeypatch.setattr("training_client.controller.audio_client.transcribe", unexpected)
    try:
        with pytest.raises(ClientError, match="Permission revoked"):
            await c.turn(frames())
        assert not c.busy
    finally:
        await c.close()


async def test_cached_local_context_rechecks_permissions_before_inference(monkeypatch):
    c = Controller(settings(), lambda *args: None)
    c.pms.practice = {"practice_id": "selected", "practice_revision": 1}
    c.pms.conversation = {"context": {"conversation_id": "context-id"}}
    requests = []

    async def revoked(method, path, **kwargs):
        requests.append((method, path))
        raise ClientError("Permission revoked", code="forbidden")

    async def unexpected(*args):
        raise AssertionError("A revoked context must not invoke inference")

    monkeypatch.setattr(c.pms, "json", revoked)
    monkeypatch.setattr(c, "local_answer", unexpected)
    monkeypatch.setattr(c.pms, "answer", unexpected)
    try:
        with pytest.raises(ClientError, match="Permission revoked"):
            await c.text_turn("What is your name?")
        assert requests == [("GET", c.pms.practice_base + "/conversations/context-id")]
        assert not c.history and not c.busy
    finally:
        c.pms.conversation = None
        await c.close()
