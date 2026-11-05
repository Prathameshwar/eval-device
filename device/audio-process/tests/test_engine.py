from types import SimpleNamespace

import numpy as np
import pytest
from conftest import SPEECH
from fastapi.testclient import TestClient

from device_audio.app import create_app
from device_audio.audio import AudioChunk
from device_audio.engine import FasterWhisperEngine


def test_native_adapter_loads_once_warms_both_models_and_preserves_hindi(settings, tmp_path, monkeypatch):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    loads, calls, vad_warmups = [], [], []

    class Model:
        def __init__(self, path, **kwargs):
            loads.append(kwargs)

        def transcribe(self, audio, **kwargs):
            calls.append((audio, kwargs))
            segment = SimpleNamespace(text="\u0928\u092e\u0938\u094d\u0924\u0947 hello", start=0, end=50)
            return iter([segment]), SimpleNamespace(language="hi")

    monkeypatch.setattr("faster_whisper.WhisperModel", Model)
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda audio: vad_warmups.append(audio))
    engine = FasterWhisperEngine(settings)
    chunk = AudioChunk(SPEECH * 6, 16000, 18880)
    for language in ("auto", "hi", "en"):
        result = engine.transcribe(chunk, language)
        assert result.text == "\u0928\u092e\u0938\u094d\u0924\u0947 hello"
        assert result.segments[0]["start_seconds"] == 1
        assert result.segments[0]["end_seconds"] == pytest.approx(1.18)
    assert len(loads) == len(vad_warmups) == 1
    assert loads[0]["local_files_only"] is True
    assert loads[0]["compute_type"] == "int8"
    assert loads[0]["num_workers"] == 1
    assert len(calls) == 4  # One warmup, followed by three actual clips.
    assert [options["language"] for _, options in calls] == ["en", None, "hi", "en"]
    assert calls[1][0].dtype == np.float32


def test_failed_startup_does_not_report_ready(settings):
    def failed_factory(_):
        raise RuntimeError("model could not initialize")

    app = create_app(settings, failed_factory)
    with pytest.raises(RuntimeError, match="could not initialize"):
        with TestClient(app):
            pass
    assert app.state.runtime.ready is False
    assert app.state.runtime.worker is None


def test_output_limit_is_enforced_in_native_adapter(settings, tmp_path, monkeypatch):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            segment = SimpleNamespace(text="x" * (settings.max_text_chars + 1), start=0, end=1)
            return iter([segment]), SimpleNamespace(language="en")

    monkeypatch.setattr("faster_whisper.WhisperModel", Model)
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda _: [])
    engine = FasterWhisperEngine(settings)
    with pytest.raises(RuntimeError, match="output limit"):
        engine.transcribe(AudioChunk(SPEECH * 6, 0, 2880), "en")


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ([("ur", 0.7), ("en", 0.05), ("hi", 0.25)], "hi"),
        ([("ur", 0.7), ("hi", 0.05), ("en", 0.25)], "en"),
        ([("ur", 1.0)], None),
        (None, None),
    ],
)
def test_auto_language_stays_within_advertised_choices(
    settings, tmp_path, monkeypatch, probabilities, expected
):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio, **options):
            language = options["language"]
            calls.append(options)

            def segments():
                assert language is not None, "unsupported-language output must never be decoded"
                yield SimpleNamespace(
                    text="\u0928\u093e\u092e" if language == "hi" else "name", start=0, end=0.1
                )

            return segments(), SimpleNamespace(language=language or "ur", all_language_probs=probabilities)

    monkeypatch.setattr("faster_whisper.WhisperModel", Model)
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda _: [])
    engine = FasterWhisperEngine(settings)
    chunk = AudioChunk(SPEECH * 6, 0, 2880)
    if expected is None:
        with pytest.raises(RuntimeError, match="supported language"):
            engine.transcribe(chunk, "auto")
        assert [call["language"] for call in calls] == ["en", None]
    else:
        result = engine.transcribe(chunk, "auto")
        assert result.language == expected
        assert result.text == ("\u0928\u093e\u092e" if expected == "hi" else "name")
        assert [call["language"] for call in calls] == ["en", None, expected]
        assert all(call["task"] == "transcribe" for call in calls[1:])
