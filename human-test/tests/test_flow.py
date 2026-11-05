import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from training_client.controller import Controller, heard
from training_client.pms_client import ClientError, PMSClient
from training_contracts.languages import get_pack

from human_test.config import Settings


def settings(**kw):
    return Settings(
        _env_file=None,
        pms_token="fixture",
        audio_token="fixture",
        organization_id=uuid4(),
        connection_id=uuid4(),
        **kw,
    )


@pytest.mark.parametrize(
    "url", ["http://example.invalid", "http://user:pass@127.0.0.1:8000", "http://127.0.0.1:8000/?token=x"]
)
def test_transport_config_rejects_unsafe_urls(url):
    with pytest.raises(ValidationError):
        settings(pms_url=url)


async def test_failed_generation_does_not_enter_history(monkeypatch):
    s = settings()
    events = []
    c = Controller(s, lambda *e: events.append(e))

    async def asr(*args, **kwargs):
        return {"text": "hello", "asr_finalize_ms": 10}

    async def fail(*args):
        raise ClientError("failed")

    monkeypatch.setattr("training_client.controller.audio_client.transcribe", asr)
    monkeypatch.setattr(c.pms, "answer", fail)

    async def frames():
        yield b"xx"

    try:
        with pytest.raises(ClientError):
            await c.turn(frames())
        assert not c.history and not c.busy
    finally:
        await c.close()


@pytest.mark.parametrize("recognized", ["", "   ", "... ?", "\u200b\ufeff", "\u0964"])
@pytest.mark.parametrize("audio_mode", ["local", "cloud"])
@pytest.mark.parametrize("local", [False, True])
async def test_unrecognized_audio_is_silent_without_generation_or_storage(
    monkeypatch, recognized, audio_mode, local
):
    """An empty/noise transcript produces neither a model reply nor a canned spoken reply."""
    events = []
    c = Controller(settings(audio_mode=audio_mode), lambda *e: events.append(e))
    history = [{"role": "user", "content": "Name?"}, {"role": "assistant", "content": "Morgan."}]
    c.history = history.copy()
    admission, closed = [], []

    async def context(source):
        admission.append(source)

    async def asr(*args, **kwargs):
        async for _ in args[-2]:
            pass
        return {"text": recognized, "asr_finalize_ms": 0}

    async def bad(*args):
        pytest.fail("Unrecognized turn reached answer generation")

    def no_storage(*args, **kwargs):
        pytest.fail("Unrecognized turn reached answer storage or the optional dictionary")

    monkeypatch.setattr("training_client.controller.audio_client.transcribe", asr)
    monkeypatch.setattr("training_client.controller.cloud_audio.transcribe", asr)
    monkeypatch.setattr(c, "runs_locally", lambda: local)
    monkeypatch.setattr(c.pms, "ensure_conversation", context)
    monkeypatch.setattr(c.pms, "answer", bad)
    monkeypatch.setattr(c, "local_answer", bad)
    monkeypatch.setattr(c, "archive_context", no_storage)
    monkeypatch.setattr(c.metrics_reporter, "enqueue", no_storage)
    monkeypatch.setattr(c.input_filter, "ignores", no_storage)

    async def frames():
        try:
            yield b"xx"
        finally:
            closed.append(True)

    try:
        result = await c.turn(frames())
        assert result["answer"] is None and result["ignored"]
        assert result["metrics"]["provider_calls"] == 0
        assert not any(kind in {"answer", "answer_delta", "speak"} for kind, _ in events)
        assert [value for kind, value in events if kind == "input_ignored"] == [
            {"text": recognized, "generation": 0}
        ]
        assert c.history == history and c.sequence == 0 and not c.busy
        assert admission == ["speech"] and closed == [True]
    finally:
        await c.close()


def test_clarification_phrase_remains_available_for_meaningful_ambiguous_input():
    line = get_pack("en").clarification
    assert line == "Could you explain what you mean?"
    assert len(line) < 200
    for language in ("auto", "hi"):
        with pytest.raises(ValueError):
            settings(language=language)


def test_a_short_question_is_still_asked():
    """Only stray punctuation is unrecognized; a real one-word question is not intercepted."""
    assert not heard("") and not heard("  ") and not heard("...?") and not heard("।")
    for question in ("bp?", "क्यों?", "3"):
        assert heard(question), question


async def test_pms_sse_and_no_replay_on_disconnect():
    calls = []
    s = settings()
    client = PMSClient(s)
    await client.http.aclose()

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b'event: delta\ndata: {"type":"delta","text":"partial"}\n\n')

    client.http = httpx.AsyncClient(base_url=s.pms_url, transport=httpx.MockTransport(handler))
    events = []
    try:
        with pytest.raises(ClientError):
            await client.answer([{"role": "user", "content": "hello"}], lambda *e: events.append(e))
        assert len(calls) == 1 and events == [("answer_delta", "partial")]
    finally:
        await client.close()


@pytest.mark.parametrize("mode", ["silence", "manual", "flood"])
async def test_microphone_ends_and_releases_capture(monkeypatch, mode):
    """Endpointing and device release. Overflow no longer fails at the first dropped block, so
    `flood` loses more than the configured budget; `test_capture_quality` covers the rest."""
    import threading
    from array import array

    import sounddevice as sd
    from training_client.capture import microphone

    closed = []
    send_now = threading.Event()

    class Stream:
        def __init__(self, **kw):
            self.callback = kw["callback"]

        def __enter__(self):
            count = 200 if mode == "flood" else 19
            for i in range(count):
                frame = array("h", [1000 if i < 3 else 0] * 800).tobytes()
                self.callback(frame, 800, None, False)
            return self

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(sd, "check_input_settings", lambda **kw: None)
    monkeypatch.setattr(sd, "query_devices", lambda: [])
    monkeypatch.setattr(sd, "RawInputStream", Stream)
    captured = 0
    frames = microphone(settings(), send_now)
    try:
        if mode == "flood":
            with pytest.raises(ClientError, match="lost about"):
                await anext(frames)
        else:
            async for _frame in frames:
                captured += 1
                if mode == "manual":
                    send_now.set()
            assert captured == (1 if mode == "manual" else 19)
    finally:
        await frames.aclose()
    assert closed == [True]


@pytest.mark.parametrize("streaming", [False, True])
async def test_empty_final_answer_does_not_enter_history(monkeypatch, streaming):
    c = Controller(settings(streaming=streaming), lambda *args: None)
    await c.pms.http.aclose()
    calls = []

    async def asr(*args, **kwargs):
        return {"text": "Hello", "asr_finalize_ms": 1}

    def handler(request):
        calls.append(1)
        body = json.loads(request.content)
        result = {"type": "done", "status": "succeeded", "request_key": body["request_key"], "text": " "}
        if streaming:
            return httpx.Response(200, content="data: " + json.dumps(result) + "\n\n")
        return httpx.Response(200, json=result)

    c.pms.http = httpx.AsyncClient(base_url=c.pms.settings.pms_url, transport=httpx.MockTransport(handler))
    monkeypatch.setattr("training_client.controller.audio_client.transcribe", asr)

    async def frames():
        yield b"xx"

    try:
        with pytest.raises(ClientError, match="incomplete"):
            await c.turn(frames())
        assert c.history == [] and calls == [1]
    finally:
        await c.close()


@pytest.mark.parametrize("language", ["auto", "hi"])
def test_medical_profile_rejects_unsupported_language(language):
    with pytest.raises(ValueError):
        settings(audio_model="whisper-medical-v1", language=language)


def test_medical_profile_english_ui_choices_and_existing_multilingual_default():
    assert settings(audio_model="whisper-medical-v1", language="en").language_choices == ("en",)
    assert settings().language_choices == ("en",)
