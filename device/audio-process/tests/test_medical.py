"""English gating, load reuse, integrity and installation regression coverage."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from conftest import HEADERS, SPEECH, Detector, FakeEngine, collect, send_pcm
from fastapi.testclient import TestClient

from device_audio.app import create_app
from device_audio.audio import AudioChunk
from device_audio.config import MODEL_NAMES
from device_audio.engine import FasterWhisperEngine
from device_audio.medical_download import REPO, REQUIRED, REVISION, digest, verify_medical, verify_source


def installed(path):
    for name in REQUIRED:
        (path / name).write_bytes(b"fixture")
    manifest = {
        "repo": REPO,
        "revision": REVISION,
        "quantization": "int8_float16",
        "files": {name: {"bytes": 7, "sha256": digest(path / name)} for name in REQUIRED},
    }
    (path / "medical-manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_language_gated_before_audio_and_one_worker_reused(settings):
    assert {"small", "medium", "large-v3", "large-v3-turbo", "whisper-medical-v1"} <= set(MODEL_NAMES)
    settings.model_name = "whisper-medical-v1"
    loads = []
    engine = FakeEngine()

    def factory(settings):
        loads.append(settings)
        return engine

    with TestClient(
        create_app(settings, factory, detector_factory=Detector), client=("127.0.0.1", 1)
    ) as http:
        state = http.get("/v1/status", headers=dict(HEADERS)).json()
        assert state["supported_languages"] == ["en"] and state["engine"] == "faster-whisper"
        for language in ("auto", "hi"):
            with http.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                ws.send_json({"type": "start", "language": language})
                assert ws.receive_json() == {"type": "error", "code": "unsupported_language"}
        assert not engine.calls
        for _ in range(2):
            with http.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                ws.send_json({"type": "start", "language": "en"})
                assert ws.receive_json()["supported_languages"] == ["en"]
                send_pcm(ws, SPEECH * 6)
                ws.send_json({"type": "finish"})
                assert collect(ws)[-1]["type"] == "complete"
        assert len(loads) == 1 and len(engine.calls) == 2


@pytest.mark.parametrize("gpu", [False, True])
def test_native_adapter_integrity_once_device_flag_and_language_guard(settings, tmp_path, monkeypatch, gpu):
    installed(tmp_path)
    settings.model_name, settings.model_path, settings.gpu_enabled = "whisper-medical-v1", tmp_path, gpu
    loads, calls, checks = [], [], []

    class Model:
        def __init__(self, path, **kwargs):
            loads.append(kwargs)
            self.model = SimpleNamespace(device=kwargs["device"], compute_type=kwargs["compute_type"])

        def transcribe(self, *args, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(text="no fever", start=0, end=0.1)]), SimpleNamespace(language="en")

    monkeypatch.setattr("faster_whisper.WhisperModel", Model)
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda _: [])
    monkeypatch.setattr("device_audio.gpu.prepare_whisper_cuda", lambda _: None)
    monkeypatch.setattr(
        "device_audio.medical_download.verify_medical", lambda p: (checks.append(p), verify_medical(p))
    )
    engine = FasterWhisperEngine(settings)
    for language in ("hi", "auto"):
        with pytest.raises(ValueError, match="explicit"):
            engine.transcribe(AudioChunk(SPEECH, 0, 480), language)
    for _ in range(2):
        assert engine.transcribe(AudioChunk(SPEECH, 0, 480), "en").text == "no fever"
    assert len(loads) == len(checks) == 1
    assert len(calls) == 3  # warmup plus two clips
    assert loads[0]["device"] == ("cuda" if gpu else "cpu")
    assert loads[0]["local_files_only"] and all(not c["condition_on_previous_text"] for c in calls)


@pytest.mark.parametrize("bad", ["checksum", "revision", "missing", "path"])
def test_model_manifest_failures(settings, tmp_path, monkeypatch, bad):
    manifest = installed(tmp_path)
    if bad == "checksum":
        (tmp_path / "model.bin").write_bytes(b"corrupt")
    elif bad == "revision":
        manifest["revision"] = "main"
    elif bad == "missing":
        del manifest["files"]["vocabulary.json"]
    else:
        manifest["files"]["../escape"] = {"bytes": 1, "sha256": "a" * 64}
    (tmp_path / "medical-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_medical(tmp_path)


def test_source_hash_and_size_checked(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b"fixture")
    git = hashlib.sha1(b"blob 7\0fixture", usedforsecurity=False).hexdigest()
    info = SimpleNamespace(size=7, lfs=None, blob_id=git)
    assert verify_source(path, info)["sha256"] == digest(path)
    info.lfs = SimpleNamespace(sha256=digest(path))
    verify_source(path, info)
    info.lfs.sha256 = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        verify_source(path, info)
    info.size = 8
    with pytest.raises(ValueError, match="size"):
        verify_source(path, info)
