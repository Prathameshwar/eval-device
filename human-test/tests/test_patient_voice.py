"""Saved-patient voice choice and bounded resident voices; no audio hardware."""

from types import SimpleNamespace

import pytest
from test_flow import settings
from test_speech import FakeEngine, FakeWindow, installed_voice, wait_until
from training_client import speech
from training_client.controller import Controller


@pytest.mark.parametrize(
    "value, expected",
    [
        ("male", "male"),
        ("female", "female"),
        (" Female ", "female"),
        ("unspecified", "male"),
        ("intersex", "male"),
        (None, "male"),
        ("", "male"),
    ],
)
def test_saved_patient_sex_selects_voice_with_male_default(value, expected):
    assert speech.patient_gender({"document": {"patient": {"sex": value}}}) == expected


@pytest.mark.parametrize("selection", [None, {}, {"document": None}, {"document": {"patient": None}}])
def test_missing_profile_defaults_to_male(selection):
    assert speech.patient_gender(selection) == "male"


def test_speaker_passes_gender_to_warmup_and_playback(tmp_path, monkeypatch):
    gender_voices(tmp_path, monkeypatch)
    engine = FakeEngine()
    speaker = speech.Speaker(engine=engine)
    try:
        speaker.warm("en", "female")
        assert wait_until(lambda: engine.genders == ["female"])
        assert speaker.speak("A fictional patient answer.", "en", "female")
        assert wait_until(lambda: not speaker.speaking)
        assert engine.genders == ["female", "female"]
        assert speaker.speak("Another answer.", "en")
        assert wait_until(lambda: not speaker.speaking)
        assert engine.genders[-1] == "male"
    finally:
        speaker.close()


async def test_voice_gender_follows_successfully_saved_selection(monkeypatch):
    events = []
    controller = Controller(settings(), lambda *event: events.append(event))

    async def answer(messages, emit):
        return {"text": "Hello, I am Alex.", "finish_reason": "stop"}

    async def context(*args):
        return None

    monkeypatch.setattr(controller.pms, "ensure_conversation", context)
    monkeypatch.setattr(controller.pms, "answer", answer)
    try:
        for sex, expected in (("female", "female"), ("male", "male"), (None, "male")):
            controller.use_selection(
                {"id": "practice", "revision": 1, "language": "en", "document": {"patient": {"sex": sex}}}
            )
            await controller.text_turn("What is your name?")
            assert [value for kind, value in events if kind == "speak"][-1]["gender"] == expected
        controller.busy = True
        with pytest.raises(RuntimeError):
            controller.use_selection({"document": {"patient": {"sex": "female"}}})
        assert controller.voice_gender == "male"
    finally:
        await controller.close()


def test_window_forwards_voice_choice_without_speaking_recovered_results():
    window = FakeWindow()
    window.emit("speak", {"text": "Hello", "language": "en", "gender": "female"})
    window.drain()
    assert window.speaker.requests == [("Hello", "en", "female")]
    window.emit("answer", "Recovered response")
    window.drain()
    assert len(window.speaker.requests) == 1


def test_saved_setup_warms_selected_gender_without_playing():
    window = FakeWindow()
    window.loaded_case = None
    window.manikin.configure_patient = lambda value: None
    window.active_case = window.step = SimpleNamespace(set=lambda value: None)
    window.case_choice = SimpleNamespace(get=lambda: "Practice")
    window.setup_frame = SimpleNamespace(pack_forget=lambda: None)
    window.talk_frame = SimpleNamespace(pack=lambda **kwargs: None)
    window.question = window.answer
    window.emit("saved", {"language": "en", "document": {"patient": {"name": "Jordan", "sex": "female"}}})
    window.drain()
    assert window.speaker.warmed == [("en", "female")]
    assert not window.speaker.requests and window.speaker.stops == 1


def gender_voices(tmp_path, monkeypatch):
    return installed_voice(tmp_path, monkeypatch, ("en", "en-female", "hi"))


def test_missing_female_falls_back_to_same_language_male(tmp_path, monkeypatch):
    entries = gender_voices(tmp_path, monkeypatch)
    assert speech.selected_voice("en", "female")[0] == "en-female"
    entries[:] = [v for v in entries if v["key"] != "en-female"]
    assert speech.selected_voice("en", "female")[0] == "en"
    entries[:] = [v for v in entries if v["language"] != "en"]
    assert speech.selected_voice("en", "female") is None
    assert speech.selected_voice("hi", "female")[0] == "hi"
    assert speech.selected_voice("fr", "female") is None
