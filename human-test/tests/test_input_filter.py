"""No generation, speech, or history for dictionary-only utterances."""

import json
from copy import deepcopy

import pytest
from test_flow import settings
from training_client.controller import Controller
from training_client.input_filter import DEFAULT_DICTIONARY, InputFilter, InputFilterError
from training_client.pms_client import ClientError


@pytest.mark.parametrize(
    "text",
    [
        "thank",
        "Thanks!",
        "Thank you.",
        "THANKYOU",
        "thanks a lot",
        "many thanks",
        "thank you very much",
        "thank you so much",
        "much appreciated",
        "okay, thanks",
        "hmm thanks a lot",
        "hm",
        "hmm",
        "HMMMM...",
        "mm",
        "mmm",
        "ummmmm",
        "uhhh",
        "erm",
        "errrr",
        "ok",
        "Okay!",
        "all right",
        "got it",
        "I see",
        "okay then",
        "  hmm, okay okay.  ",
        "umm... all right; got it",
        "hmm\nokay",
        '"hmm"',
    ],
)
def test_whole_utterance_fillers_and_acknowledgements(text):
    assert InputFilter(DEFAULT_DICTIONARY).ignores(text, "en")


@pytest.mark.parametrize(
    "text",
    [
        "hmm, what is your name?",
        "okay, since when",
        "um no",
        "not okay",
        "right leg pain",
        "okay?",
        "hmm?",
        "huh?",
        "okay\uff1f",
        "hmm\u061f",
        "yes",
        "no",
        "hello",
        "thanks, but do you have fever?",
        "thank you since when did it start",
        "thanks?",
        "thanksgiving",
        "thankful",
        "thanks for explaining your chest pain",
        "stop",
        "repeat",
        "go on",
        "3",
        "BP?",
        "",
        "...",
        "okay + okay",
        "hmm \U0001f602",
        "okay never mind",
        "right-handed",
        "ummbrella",
        "I see pain",
        "okay okay chest pain",
    ],
)
def test_meaningful_or_uncertain_input_is_preserved(text):
    assert not InputFilter(DEFAULT_DICTIONARY).ignores(text, "en")


def dictionary_file(tmp_path):
    path = tmp_path / "ignore.json"
    path.write_bytes(DEFAULT_DICTIONARY.read_bytes())
    return path


def test_edits_are_reloaded_and_languages_are_isolated(tmp_path):
    path = dictionary_file(tmp_path)
    rule = InputFilter(path)
    assert rule.ignores("hmm", "en") and not rule.ignores("hmm", "fr")
    document = json.loads(path.read_text())
    document["languages"]["en"]["fillers"] = ["ah"]
    document["languages"]["en"]["repeat_last_letter"] = False
    document["languages"]["fr"] = {"fillers": ["euh"], "acknowledgements": []}
    path.write_text(json.dumps(document), encoding="utf-8-sig")
    assert not rule.ignores("hmm", "en")
    assert rule.ignores("ah", "en") and not rule.ignores("ahhh", "en")
    assert rule.ignores("euh", "fr") and not rule.ignores("euh", "en")
    document["languages"]["en"]["enabled"] = False
    path.write_text(json.dumps(document), encoding="utf-8")
    assert not rule.ignores("ah okay", "en")


def test_overlapping_phrases_require_complete_coverage(tmp_path):
    path = tmp_path / "ignore.json"
    path.write_text(
        json.dumps(
            {"version": 1, "languages": {"en": {"fillers": [], "acknowledgements": ["a b", "a", "b c"]}}}
        )
    )
    rule = InputFilter(path)
    assert rule.ignores("a b c", "en")
    assert not rule.ignores("a b c d", "en")


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"x" * 65537,
        b"[]",
        b'{"version":true,"languages":{}}',
        b'{"version":1,"languages":{"en":{"fillers":[".*"],"acknowledgements":[]}}}',
        b'{"version":1,"languages":{"en":{"fillers":[""],"acknowledgements":[]}}}',
        b'{"version":1,"languages":{"en":{"fillers":["two words"],"acknowledgements":[]}}}',
    ],
    ids=["malformed", "oversized", "array", "version-type", "pattern", "empty", "phrase-filler"],
)
def test_invalid_edits_are_reported_instead_of_reusing_stale_rules(tmp_path, raw):
    path = dictionary_file(tmp_path)
    rule = InputFilter(path)
    assert rule.ignores("hmm", "en")
    path.write_bytes(raw)
    with pytest.raises(InputFilterError, match="invalid or unreadable"):
        rule.ignores("hmm", "en")
    path.unlink()
    with pytest.raises(InputFilterError):
        rule.ignores("Hello", "en")


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("source", ["text", "speech"])
async def test_ignored_input_never_generates_speaks_or_changes_history(monkeypatch, local, source):
    events = []
    c = Controller(settings(), lambda *event: events.append(event))
    c.history = [{"role": "user", "content": "Name?"}, {"role": "assistant", "content": "Morgan."}]
    before = deepcopy(c.history)
    admission = []
    monkeypatch.setattr(c, "runs_locally", lambda: local)

    async def forbidden(*args, **kwargs):
        pytest.fail("Ignored input reached generation or archival")

    def no_archive(*args, **kwargs):
        pytest.fail("Ignored input reached history/metrics storage")

    async def context(*args):
        admission.append(args)
        return None

    async def asr(*args, **kwargs):
        return {"text": "hmmmm, okay okay.", "asr_finalize_ms": 12}

    async def frames():
        yield b"audio"

    monkeypatch.setattr(c.pms, "ensure_conversation", context)
    monkeypatch.setattr(c, "local_answer", forbidden)
    monkeypatch.setattr(c.pms, "answer", forbidden)
    monkeypatch.setattr(c, "archive_context", no_archive)
    monkeypatch.setattr(c.metrics_reporter, "enqueue", no_archive)
    monkeypatch.setattr("training_client.controller.audio_client.transcribe", asr)
    try:
        result = await c.text_turn("hmmmm, okay okay.") if source == "text" else await c.turn(frames())
        assert result["ignored"] and result["answer"] is None
        assert result["metrics"]["provider_calls"] == 0
        assert c.history == before and c.sequence == 0 and not c.busy
        assert not any(kind in {"answer", "answer_delta", "speak"} for kind, _ in events)
        assert [kind for kind, _ in events].count("input_ignored") == 1
        assert admission == ([] if source == "text" else [("speech",)])
    finally:
        await c.close()


async def test_filtered_filler_does_not_break_next_question_or_followup(monkeypatch):
    c = Controller(settings(), lambda *args: None)
    seen = []

    async def answer(messages, emit):
        seen.append(deepcopy(messages))
        return {"text": "Three weeks.", "finish_reason": "stop"}

    monkeypatch.setattr(c.pms, "answer", answer)
    try:
        await c.text_turn("How long have you had this?")
        await c.text_turn("hmmmm")
        await c.text_turn("okay, since when exactly?")
        assert len(seen) == 2
        assert seen[1] == [
            {"role": "user", "content": "How long have you had this?"},
            {"role": "assistant", "content": "Three weeks."},
            {"role": "user", "content": "okay, since when exactly?"},
        ]
    finally:
        await c.close()


async def test_invalid_dictionary_prevents_model_submission(monkeypatch, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("broken")
    c = Controller(settings(input_ignore_file=path), lambda *args: None)

    async def forbidden(*args):
        pytest.fail("Invalid dictionary must not silently bypass validation")

    monkeypatch.setattr(c.pms, "ensure_conversation", forbidden)
    monkeypatch.setattr(c.pms, "answer", forbidden)
    try:
        with pytest.raises(ClientError) as error:
            await c.text_turn("hmm")
        assert error.value.code == "input_ignore_configuration" and not c.busy
    finally:
        await c.close()
