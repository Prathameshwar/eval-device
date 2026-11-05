import asyncio
import io
import tarfile
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import HEADERS, OTHER_TOKEN, SILENCE, SPEECH, Detector, collect, send_pcm
from fastapi.testclient import TestClient

from device_audio.app import create_app
from device_audio.audio import SAMPLE_RATE, AudioChunk
from device_audio.config import MODEL_NAMES, VOSK_LANGUAGES, Settings
from device_audio.engine import Recognition, create_engine
from device_audio.model_download import ARCHIVE_ROOT, MODEL_FILES, NEMOTRON_NAME, extract_model
from device_audio.runtime import Runtime, ServiceError
from device_audio.session import Session
from device_audio.streaming import StreamingSegmenter


@pytest.mark.parametrize("size", [2, 158, 960, 16000])
def test_incremental_framing_preserves_every_sample_and_bounded_state(settings, size):
    settings.max_chunk_seconds = 1
    segmenter = StreamingSegmenter(settings, Detector())
    pcm = SILENCE * 3 + SPEECH * 55 + SILENCE * 25 + SPEECH * 9 + b"\x01\x00"
    chunks = []
    for i in range(0, len(pcm), size):
        chunks.extend(segmenter.feed(pcm[i : i + size]))
        assert len(segmenter.pending) < 960
        assert len(segmenter.block) < 4800
    chunks.extend(segmenter.flush())
    assert b"".join(c.pcm for c in chunks) == pcm
    assert segmenter.total_samples == len(pcm) // 2
    assert chunks[-1].final and segmenter.flush() == []
    end = 0
    for chunk in chunks:
        assert chunk.start_sample == end
        assert len(chunk.pcm) == 2 * (chunk.end_sample - chunk.start_sample)
        end = chunk.end_sample
    assert sum(c.final for c in chunks) >= 3


def test_empty_flush_and_short_noise_do_not_become_speech(settings):
    segmenter = StreamingSegmenter(settings, Detector())
    assert segmenter.flush() == []
    chunks = segmenter.feed(SPEECH + SILENCE * 20) + segmenter.flush()
    assert all(not c.has_speech for c in chunks if c.final)
    assert b"".join(c.pcm for c in chunks) == SPEECH + SILENCE * 20


class FakeModel:
    def __init__(self):
        self.streams = []
        self.decodes = []
        self.text = None

    def create_stream(self):
        stream = SimpleNamespace(samples=[], options={}, ready=False, finished=False)
        stream.set_option = lambda name, value: stream.options.update({name: value})

        def accept(rate, samples):
            assert rate == SAMPLE_RATE and samples.dtype == np.float32
            assert "language" in stream.options
            stream.samples.append(samples.copy())
            stream.ready = True

        def finish():
            stream.finished = True

        stream.accept_waveform = accept
        stream.input_finished = finish
        self.streams.append(stream)
        return stream

    def is_ready(self, stream):
        return stream.ready

    def decode_stream(self, stream):
        stream.ready = False
        self.decodes.append(stream)

    def get_result(self, stream):
        return self.text or "text-" + stream.options["language"]


@pytest.fixture
def model_engine(settings, tmp_path, monkeypatch):
    for name in MODEL_FILES:
        (tmp_path / name).write_bytes(b"test")
    settings.model_name = NEMOTRON_NAME
    settings.model_path = tmp_path
    model = FakeModel()
    loads = []
    monkeypatch.setattr("device_audio.nemotron.prepare_sherpa_runtime", lambda: None)

    def factory(**options):
        loads.append(options)
        return model

    monkeypatch.setattr("sherpa_onnx.OnlineRecognizer.from_transducer", factory)
    engine = create_engine(settings)
    return engine, model, loads


def test_one_resident_model_incremental_decode_isolated_languages_and_reset(model_engine):
    engine, model, loads = model_engine
    assert len(loads) == 1 and len(model.streams) == 1  # startup warmup
    assert loads[0]["provider"] == "cpu" and loads[0]["feature_dim"] == 128
    a, b = engine.new_session(), engine.new_session()
    chunk = AudioChunk(SPEECH * 5, 0, 2400, final=False)
    assert not a.transcribe(chunk, "hi").final
    assert not b.transcribe(chunk, "en").final
    assert len(model.decodes) == 3  # recognition work before finalization
    result_a = a.transcribe(AudioChunk(b"", 2400, 2400), "hi")
    result_b = b.transcribe(AudioChunk(b"", 2400, 2400), "en")
    assert result_a.text == "text-hi" and result_b.text == "text-en"
    assert result_a.start_sample == 0
    assert result_a.segments[0]["end_seconds"] == 0.15  # padding excluded
    assert a.stream is b.stream is None
    result = a.transcribe(AudioChunk(SPEECH, 2400, 2880), "auto")
    assert result.language == "auto" and len(model.streams) == 4
    assert len(loads) == 1


def test_native_output_limit_contiguity_and_silence(model_engine, settings):
    engine, model, _ = model_engine
    assert engine.transcribe(AudioChunk(SILENCE, 0, 480, has_speech=False), "en").text == ""
    stream = engine.new_session()
    stream.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "en")
    with pytest.raises(ValueError, match="non-contiguous"):
        stream.transcribe(AudioChunk(SPEECH, 481, 961), "en")
    model.text = "x" * (settings.max_text_chars + 1)
    with pytest.raises(RuntimeError, match="output limit"):
        engine.new_session().transcribe(AudioChunk(SPEECH, 0, 480, final=False), "hi")


def test_missing_model_fails_locally_and_all_whisper_choices_remain(settings, tmp_path, monkeypatch):
    settings.model_name = NEMOTRON_NAME
    settings.model_path = tmp_path
    with pytest.raises(RuntimeError, match="local Nemotron model missing"):
        create_engine(settings)
    calls = []
    monkeypatch.setattr("device_audio.engine.FasterWhisperEngine", lambda s: calls.append(s.model_name))
    for name in MODEL_NAMES:
        if name != NEMOTRON_NAME and name not in VOSK_LANGUAGES:
            settings.model_name = name
            create_engine(settings)
            assert settings.engine_name == "faster-whisper"
    assert calls == [name for name in MODEL_NAMES if name != NEMOTRON_NAME and name not in VOSK_LANGUAGES]
    assert Settings(_env_file=None, client_tokens={"pi": "x" * 48}).model_name == "large-v3"


class LiveDouble:
    def __init__(self):
        self.sessions = []
        self.progress = threading.Event()

    def new_session(self):
        state = SimpleNamespace(start=None, calls=[], number=len(self.sessions) + 1)

        def transcribe(chunk, language):
            state.calls.append((chunk, language, threading.current_thread().name))
            self.progress.set()
            if state.start is None:
                state.start = chunk.start_sample
            result = Recognition(
                f"{language}-{state.number}" if chunk.final and chunk.has_speech else "",
                language,
                [],
                final=chunk.final,
                start_sample=state.start,
            )
            if chunk.final:
                state.start = None
            return result

        state.transcribe = transcribe
        self.sessions.append(state)
        return state


def test_api_infers_before_finish_two_clients_flush_and_metadata(settings):
    settings.model_name = NEMOTRON_NAME
    engine = LiveDouble()
    loads = []

    def factory(_):
        loads.append(1)
        return engine

    app = create_app(settings, factory, detector_factory=Detector)
    with TestClient(app, client=("127.0.0.1", 1)) as client:
        status = client.get("/v1/status", headers=dict(HEADERS)).json()
        assert status["engine"] == "sherpa-onnx" and status["streaming"]
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as first:
            first.send_json({"type": "start", "language": "hi"})
            assert first.receive_json()["engine"] == "sherpa-onnx"
            send_pcm(first, SPEECH * 5)
            assert engine.progress.wait(2)  # no finish or speech endpoint sent yet
            with client.websocket_connect(
                "/v1/audio/stream", headers={"Authorization": "Bearer " + OTHER_TOKEN}
            ) as second:
                second.send_json({"type": "start", "language": "en"})
                second.receive_json()
                send_pcm(second, SPEECH * 6)
                second.send_json({"type": "finish"})
                other = collect(second)
            first.send_json({"type": "flush"})
            send_pcm(first, SPEECH * 5)
            first.send_json({"type": "finish"})
            events = collect(first)
        texts = [e for e in events if e["type"] == "transcript"]
        assert [e["text"] for e in texts] == ["hi-1", "hi-1"]
        assert [e["sequence"] for e in texts] == [1, 2]
        assert [e["audio_start_seconds"] for e in texts] == [0, 0.15]
        assert all(e["engine"] == "sherpa-onnx" and e["model"] == NEMOTRON_NAME for e in texts)
        assert [e["text"] for e in other if e["type"] == "transcript"] == ["en-2"]
        assert len([e for e in events if e["type"] == "delivery"]) == 2
        assert len(engine.sessions) == 2 and loads == [1]
        assert set(HEADERS) == {"Authorization"}
        assert all(call[2] == "speech-inference" for s in engine.sessions for call in s.calls)
        assert client.get("/v1/status", headers=dict(HEADERS)).json()["active_sessions"] == 0


def test_incremental_queue_remains_bounded(settings):
    settings.model_name = NEMOTRON_NAME
    settings.streaming_queue_ms = 500
    runtime = Runtime(settings)
    runtime.engine = LiveDouble()
    session = Session(None, runtime, "pi-1", Detector())
    chunk = AudioChunk(SPEECH * 5, 0, 2400, final=False)
    with pytest.raises(ServiceError, match="audio_backlog"):
        session._enqueue([chunk] * 5)
    assert session.chunks.qsize() == session.chunks.maxsize == 4


async def test_stream_native_timeout_retires_worker_without_second_call(settings):
    entered, release = threading.Event(), threading.Event()

    class Blocked:
        def transcribe(self, chunk, language):
            entered.set()
            release.wait(5)
            return Recognition("", language, [], final=False)

    settings.inference_timeout_seconds = 0.1
    engine = LiveDouble()
    runtime = Runtime(settings, lambda _: engine)
    await runtime.start()
    try:
        with pytest.raises(ServiceError, match="inference_timeout"):
            await runtime.transcribe(AudioChunk(SPEECH, 0, 480, final=False), "hi", engine=Blocked())
        assert entered.is_set()
        async with asyncio.timeout(1):
            while runtime.ready:
                await asyncio.sleep(0.01)
        assert runtime.failure == "native_inference_timeout"
        with pytest.raises(ServiceError, match="not_ready"):
            await runtime.transcribe(AudioChunk(SPEECH, 0, 480), "en", engine=Blocked())
    finally:
        release.set()
        await runtime.stop()


@pytest.mark.parametrize("bad", ["symlink", "duplicate", "missing"])
def test_model_archive_rejects_invalid_required_members(tmp_path, bad):
    archive = tmp_path / "source.tar.bz2"
    with tarfile.open(archive, "w:bz2") as target:
        for index, name in enumerate(MODEL_FILES):
            if bad == "missing" and index == 0:
                continue
            member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{name}")
            member.size = 4
            if bad == "symlink" and index == 0:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../elsewhere"
                member.size = 0
            target.addfile(member, io.BytesIO(b"test"))
            if bad == "duplicate" and index == 0:
                target.addfile(member, io.BytesIO(b"test"))
    destination = tmp_path / "model"
    destination.mkdir()
    with pytest.raises(ValueError):
        extract_model(archive, destination)


def test_archive_copies_only_allowlisted_regular_members(tmp_path):
    archive = tmp_path / "source.tar.bz2"
    with tarfile.open(archive, "w:bz2") as target:
        for name in [*(f"{ARCHIVE_ROOT}/{n}" for n in MODEL_FILES), "../../escape", f"{ARCHIVE_ROOT}/extra"]:
            member = tarfile.TarInfo(name)
            member.size = 4
            target.addfile(member, io.BytesIO(b"test"))
    destination = tmp_path / "model"
    destination.mkdir()
    manifest = extract_model(archive, destination)
    assert set(manifest) == set(MODEL_FILES)
    assert {p.name for p in destination.iterdir()} == set(MODEL_FILES)


def test_windows_runtime_uses_project_dll_once(tmp_path, monkeypatch):
    import ctypes

    import onnxruntime

    import device_audio.nemotron as adapter

    package = tmp_path / "onnxruntime"
    (package / "capi").mkdir(parents=True)
    dll = package / "capi" / "onnxruntime.dll"
    dll.write_bytes(b"test placeholder")
    calls = []
    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(adapter, "_windows_ort", None)
    monkeypatch.setattr(onnxruntime, "__file__", str(package / "__init__.py"))
    monkeypatch.setattr(ctypes, "WinDLL", lambda path: calls.append(path) or object(), raising=False)
    adapter.prepare_sherpa_runtime()
    adapter.prepare_sherpa_runtime()
    assert calls == [str(dll)]


def test_installer_checksum_failure_keeps_existing_models(tmp_path, monkeypatch):
    import device_audio.model_download as installer

    existing = tmp_path / "small"
    existing.mkdir()
    (existing / "model.bin").write_bytes(b"existing model")
    attempts = []

    def open_download(*args, **kwargs):
        attempts.append(1)
        return io.BytesIO(b"invalid")

    monkeypatch.setattr(installer.urllib.request, "urlopen", open_download)
    monkeypatch.setattr(installer, "ARCHIVE_BYTES", 7)
    with pytest.raises(ValueError, match="checksum"):
        installer.download_nemotron(tmp_path / "nemotron")
    assert attempts == [1]  # integrity failures are not transient retries
    assert not (tmp_path / "nemotron").exists()
    assert (existing / "model.bin").read_bytes() == b"existing model"
    assert list(tmp_path.iterdir()) == [existing]
    with pytest.raises(FileExistsError):
        installer.download_nemotron(existing)
    assert attempts == [1]


def test_installer_network_retries_are_bounded(tmp_path, monkeypatch):
    import device_audio.model_download as installer

    attempts, sleeps = [], []

    def fail(*args, **kwargs):
        attempts.append(1)
        raise OSError("connection failed")

    monkeypatch.setattr(installer.urllib.request, "urlopen", fail)
    monkeypatch.setattr(installer.time, "sleep", sleeps.append)
    with pytest.raises(OSError):
        installer.download_nemotron(tmp_path / "nemotron")
    assert len(attempts) == 3 and sleeps == [0.5, 1.0]
    assert not list(tmp_path.iterdir())
