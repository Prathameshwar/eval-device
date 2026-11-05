import hashlib
import io
import json
import stat
import sys
import threading
import urllib.error
import zipfile
from types import SimpleNamespace

import pytest
from conftest import HEADERS, SILENCE, SPEECH, Detector, collect, send_pcm
from fastapi.testclient import TestClient

from device_audio.app import create_app
from device_audio.audio import AudioChunk
from device_audio.config import VOSK_LANGUAGES, Settings
from device_audio.engine import create_engine
from device_audio.vosk_download import download_vosk, extract_vosk
from device_audio.vosk_engine import REQUIRED_FILES, VoskEngine

NAME = "vosk-model-small-en-us-0.15"


@pytest.fixture
def vosk_engine(settings, tmp_path, monkeypatch):
    for name in REQUIRED_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test")
    settings.model_name = NAME
    settings.model_path = tmp_path
    loads, recognizers, threads = [], [], []

    def model(**kwargs):
        loads.append(kwargs)
        threads.append(threading.current_thread().name)
        return object()

    class Recognizer:
        def __init__(self, model, sample_rate):
            assert sample_rate == 16000
            self.model = model
            self.pcm = []
            self.number = len(recognizers)
            self.endpoint_text = "early"
            self.final_text = f"final-{self.number}"
            self.endpoints = False
            self.finished = 0
            recognizers.append(self)

        def AcceptWaveform(self, pcm):
            self.pcm.append(pcm)
            threads.append(threading.current_thread().name)
            return self.endpoints

        def Result(self):
            return json.dumps({"text": self.endpoint_text})

        def FinalResult(self):
            self.finished += 1
            return json.dumps({"text": self.final_text})

    fake = SimpleNamespace(Model=model, KaldiRecognizer=Recognizer, SetLogLevel=lambda _: None)
    monkeypatch.setitem(sys.modules, "vosk", fake)
    return settings, loads, recognizers, threads


def test_model_residency_isolation_internal_endpoints_and_flush(vosk_engine):
    settings, loads, states, _ = vosk_engine
    engine = create_engine(settings)
    assert isinstance(engine, VoskEngine) and len(loads) == 1
    assert set(loads[0]) == {"model_path"}  # no auto-download convenience arguments
    assert len(states) == 1 and states[0].finished == 1  # warmup
    first, second = engine.new_session(), engine.new_session()
    assert not first.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "en").final
    second.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "en")
    assert states[1].model is states[2].model
    states[1].endpoints = True
    first.transcribe(AudioChunk(SPEECH, 480, 960, final=False), "en")
    result = first.transcribe(AudioChunk(b"", 960, 960), "en")
    assert result.text == "early final-1" and result.start_sample == 0
    assert result.segments[0]["end_seconds"] == 0.06
    assert second.transcribe(AudioChunk(b"", 480, 480), "en").text == "final-2"
    assert first.recognizer is second.recognizer is None
    assert first.transcribe(AudioChunk(SPEECH, 960, 1440), "en").text == "final-3"
    assert len(loads) == 1 and b"".join(states[1].pcm) == SPEECH * 2


def test_language_sample_contiguity_silence_and_output_bounds(vosk_engine):
    settings, _, states, _ = vosk_engine
    engine = create_engine(settings)
    for language in ("auto", "hi"):
        with pytest.raises(ValueError, match="explicit language"):
            engine.transcribe(AudioChunk(SPEECH, 0, 480), language)
    with pytest.raises(ValueError, match="session engine"):
        engine.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "en")
    with pytest.raises(ValueError, match="sample range"):
        engine.transcribe(AudioChunk(SPEECH, 0, 481), "en")
    assert engine.transcribe(AudioChunk(SILENCE, 0, 480, has_speech=False), "en").text == ""
    stream = engine.new_session()
    stream.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "en")
    with pytest.raises(ValueError, match="non-contiguous"):
        stream.transcribe(AudioChunk(SPEECH, 481, 961), "en")
    states[-1].final_text = "x" * settings.max_text_chars
    states[-1].endpoints = True
    with pytest.raises(RuntimeError, match="output limit"):
        stream.transcribe(AudioChunk(SPEECH, 480, 960), "en")


@pytest.mark.parametrize("name,language", VOSK_LANGUAGES.items())
def test_selection_gpu_guard_and_language_capability(name, language):
    settings = Settings(_env_file=None, client_tokens={"test": "x" * 48}, model_name=name)
    assert settings.engine_name == "vosk" and settings.streaming
    assert settings.supported_languages == (language,)
    assert settings.compute_type == "model_default" and settings.effective_cpu_threads is None
    with pytest.raises(ValueError, match="Whisper"):
        Settings(_env_file=None, client_tokens={"test": "x" * 48}, model_name=name, gpu_enabled=True)
    settings.gpu_enabled = True
    with pytest.raises(RuntimeError, match="CPU only"):
        create_engine(settings)


def test_missing_model_and_optional_dependency_are_local(vosk_engine, tmp_path, monkeypatch):
    settings, _, _, _ = vosk_engine
    monkeypatch.setitem(sys.modules, "vosk", None)
    with pytest.raises(RuntimeError, match="optional"):
        create_engine(settings)
    settings.model_path = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="local Vosk model missing"):
        create_engine(settings)


def test_api_worker_metadata_language_rejection_and_subsequent_success(vosk_engine):
    settings, loads, states, threads = vosk_engine
    app = create_app(settings, detector_factory=Detector)
    with TestClient(app, client=("127.0.0.1", 1)) as client:
        state = client.get("/v1/status", headers=dict(HEADERS)).json()
        assert state["engine"] == "vosk" and state["supported_languages"] == ["en"]
        assert state["cpu_threads"] is None and state["device"] == "cpu"
        for lang in ("hi", "auto"):
            with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                ws.send_json({"type": "start", "language": lang})
                assert ws.receive_json() == {"type": "error", "code": "unsupported_language"}
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            ws.send_json({"type": "start", "language": "en"})
            ready = ws.receive_json()
            assert ready["supported_languages"] == ["en"] and ready["compute_type"] == "model_default"
            send_pcm(ws, SPEECH * 10)
            ws.send_json({"type": "finish"})
            events = collect(ws)
        texts = [event for event in events if event["type"] == "transcript"]
        assert len(texts) == 1 and texts[0]["text"] == "final-1"
        assert texts[0]["engine"] == "vosk" and texts[0]["device"] == "cpu"
        assert client.get("/v1/status", headers=dict(HEADERS)).json()["active_sessions"] == 0
    assert len(loads) == 1 and len(states) == 2
    assert set(threads) == {"speech-inference"}
    assert set(HEADERS) == {"Authorization"}


def archive_bytes(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as source:
        for name in REQUIRED_FILES:
            source.writestr(NAME + "/" + name, b"model")
        if extra:
            source.writestr(*extra)
    return buffer.getvalue()


def test_archive_exact_allowlist_hashes_and_no_path_escape(tmp_path):
    archive = tmp_path / "model.zip"
    archive.write_bytes(archive_bytes((NAME + "/../../escaped", b"bad")))
    destination = tmp_path / "out"
    destination.mkdir()
    manifest = extract_vosk(archive, NAME, destination)
    assert set(manifest) == set(REQUIRED_FILES)
    assert all(item["sha256"] == hashlib.sha256(b"model").hexdigest() for item in manifest.values())
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("kind", ["duplicate", "symlink", "missing", "too_many"])
def test_reject_unsafe_or_incomplete_archive(tmp_path, kind):
    archive = tmp_path / "model.zip"
    if kind == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate"):
            archive.write_bytes(archive_bytes((NAME + "/am/final.mdl", b"other")))
    else:
        with zipfile.ZipFile(archive, "w") as source:
            member = zipfile.ZipInfo(NAME + "/am/final.mdl")
            if kind == "symlink":
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
            source.writestr(member, b"other")
            if kind == "too_many":
                for number in range(128):
                    source.writestr(str(number), b"x")
    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(ValueError):
        extract_vosk(archive, NAME, destination)


@pytest.mark.parametrize("source", ["official", "huggingface"])
def test_download_retries_integrity_atomic_publication_and_no_overwrite(tmp_path, monkeypatch, source):
    import device_audio.vosk_download as downloader

    data = archive_bytes()
    monkeypatch.setitem(downloader.MODELS, NAME, (len(data), hashlib.md5(data).hexdigest()))
    attempts = []

    def fetch(request, timeout):
        attempts.append(1)
        prefix = (
            "https://alphacephei.com/vosk/models/"
            if source == "official"
            else (
                "https://huggingface.co/rhasspy/vosk-models/resolve/e7ac2109d134b5f2404ba95389b2fb51916d4cab/en/"
            )
        )
        assert request.full_url.startswith(prefix) and timeout == 30
        assert not request.has_header("Authorization")
        if len(attempts) == 1:
            raise TimeoutError()
        return io.BytesIO(data)

    monkeypatch.setattr(downloader.urllib.request, "urlopen", fetch)
    monkeypatch.setattr(downloader.time, "sleep", lambda _: None)
    target = tmp_path / "model"
    download_vosk(NAME, target, source=source)
    manifest = json.loads((target / "download-manifest.json").read_text())
    assert manifest["sha256"] == hashlib.sha256(data).hexdigest()
    assert len(attempts) == 2 and not list(tmp_path.glob(".vosk-install-*"))
    with pytest.raises(FileExistsError):
        download_vosk(NAME, target)
    assert len(attempts) == 2


@pytest.mark.parametrize("failure", ["checksum", "oversize", "forbidden", "timeout"])
def test_download_failure_never_publishes_or_retries_integrity_errors(tmp_path, monkeypatch, failure):
    import device_audio.vosk_download as downloader

    data = archive_bytes()
    expected = len(data) - 1 if failure == "oversize" else len(data)
    monkeypatch.setitem(downloader.MODELS, NAME, (expected, "0" * 32))
    attempts = []

    def fetch(*args, **kwargs):
        attempts.append(1)
        if failure == "forbidden":
            raise urllib.error.HTTPError("https://example.invalid", 403, "Forbidden", None, None)
        if failure == "timeout":
            raise TimeoutError()
        return io.BytesIO(data)

    monkeypatch.setattr(downloader.urllib.request, "urlopen", fetch)
    monkeypatch.setattr(downloader.time, "sleep", lambda _: None)
    target = tmp_path / "model"
    with pytest.raises((ValueError, OSError)):
        download_vosk(NAME, target)
    assert len(attempts) == (3 if failure == "timeout" else 1)
    assert not target.exists() and not list(tmp_path.glob(".vosk-install-*"))
