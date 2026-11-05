from types import SimpleNamespace

import pytest
from conftest import HEADERS, SPEECH, Detector, FakeEngine, collect, send_pcm
from fastapi.testclient import TestClient
from pydantic import ValidationError

from device_audio.app import create_app
from device_audio.audio import AudioChunk
from device_audio.config import Settings
from device_audio.engine import FasterWhisperEngine
from device_audio.gpu import detect_whisper_device, prepare_whisper_cuda


@pytest.mark.parametrize("enabled,device,compute", [(False, "cpu", "int8"), (True, "cuda", "int8_float16")])
def test_gpu_flag_selects_device_compute_and_loads_once(
    settings, tmp_path, monkeypatch, enabled, device, compute
):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    settings.gpu_enabled = enabled
    settings.gpu_device_index = 1
    calls, loads, prepared = [], [], []

    class Model:
        def __init__(self, path, **kwargs):
            loads.append(kwargs)
            self.model = SimpleNamespace(device=device, compute_type=compute)

        def transcribe(self, samples, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(text="hello", start=0, end=0.18)]), SimpleNamespace(language="en")

    monkeypatch.setattr("faster_whisper.WhisperModel", Model)
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda _: [])
    monkeypatch.setattr("device_audio.gpu.prepare_whisper_cuda", prepared.append)
    engine = FasterWhisperEngine(settings)
    for _ in range(2):
        assert engine.transcribe(AudioChunk(SPEECH * 6, 0, 2880), "en").text == "hello"
    assert len(loads) == 1 and len(calls) == 3
    assert prepared == ([1] if enabled else [])
    assert loads[0]["device"] == device and loads[0]["compute_type"] == compute
    assert loads[0]["device_index"] == (1 if enabled else 0)
    assert loads[0]["local_files_only"] and loads[0]["num_workers"] == 1


def test_gpu_env_flag_and_cpu_default(monkeypatch):
    monkeypatch.delenv("AUDIO_GPU_ENABLED", raising=False)
    settings = Settings(_env_file=None, client_tokens={"test": "x" * 48})
    assert not settings.gpu_enabled and settings.inference_device == "cpu"
    monkeypatch.setenv("AUDIO_GPU_ENABLED", "true")
    monkeypatch.setenv("AUDIO_GPU_DEVICE_INDEX", "1")
    settings = Settings(_env_file=None, client_tokens={"test": "x" * 48})
    assert settings.gpu_enabled and settings.gpu_device_index == 1
    assert settings.compute_type == "int8_float16"
    with pytest.raises(ValidationError, match="supports Whisper"):
        Settings(
            _env_file=None, client_tokens={"test": "x" * 48}, model_name="nemotron-3.5-asr-streaming-0.6b"
        )


@pytest.mark.parametrize("index", [-1, 16])
def test_invalid_gpu_index_rejected(index):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, client_tokens={"test": "x" * 48}, gpu_device_index=index)


def test_unavailable_gpu_never_initializes_model_or_cpu_fallback(settings, tmp_path, monkeypatch):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    settings.gpu_enabled = True
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 0)
    calls = []
    monkeypatch.setattr("faster_whisper.WhisperModel", lambda *a, **kw: calls.append(kw))
    app = create_app(settings)
    with pytest.raises(RuntimeError, match="unavailable"):
        with TestClient(app):
            pass
    assert not calls and not app.state.runtime.ready


def test_unsupported_gpu_compute_rejected_before_library_setup(monkeypatch):
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 1)
    monkeypatch.setattr("ctranslate2.get_supported_compute_types", lambda *args: {"float32"})
    calls = []
    monkeypatch.setattr("device_audio.gpu.prepare_windows_cuda", lambda: calls.append(1))
    with pytest.raises(RuntimeError, match="does not support"):
        prepare_whisper_cuda(0)
    assert not calls


@pytest.mark.parametrize("actual_device,actual_type", [("cpu", "int8"), ("cuda", "float32")])
def test_unexpected_native_device_or_precision_fails_startup(
    settings, tmp_path, monkeypatch, actual_device, actual_type
):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    settings.gpu_enabled = True
    monkeypatch.setattr("device_audio.gpu.prepare_whisper_cuda", lambda _: None)
    monkeypatch.setattr(
        "faster_whisper.WhisperModel",
        lambda *a, **kw: SimpleNamespace(
            model=SimpleNamespace(device=actual_device, compute_type=actual_type)
        ),
    )
    with pytest.raises(RuntimeError, match="did not match"):
        FasterWhisperEngine(settings)


def test_gpu_metadata_is_consistent_in_status_ready_and_transcript(settings):
    settings.gpu_enabled = True
    app = create_app(settings, lambda _: FakeEngine(), detector_factory=Detector)
    with TestClient(app, client=("127.0.0.1", 1)) as client:
        state = client.get("/v1/status", headers=dict(HEADERS)).json()
        assert state["gpu_enabled"] and state["gpu_device_index"] == 0
        assert state["device"] == "cuda" and state["compute_type"] == "int8_float16"
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            ws.send_json({"type": "start", "language": "en"})
            ready = ws.receive_json()
            assert ready["device"] == "cuda" and ready["compute_type"] == "int8_float16"
            send_pcm(ws, SPEECH * 6)
            ws.send_json({"type": "finish"})
            events = collect(ws)
        transcript = next(e for e in events if e["type"] == "transcript")
        assert transcript["device"] == "cuda" and transcript["compute_type"] == "int8_float16"


def test_windows_cuda_paths_are_project_local_and_initialized_once(tmp_path, monkeypatch):
    import ctypes

    import device_audio.gpu as gpu

    for component, filenames in {
        "cuda_runtime": ["cudart64_12.dll"],
        "cublas": ["cublasLt64_12.dll", "cublas64_12.dll"],
        "cudnn": ["cudnn64_9.dll"],
    }.items():
        directory = tmp_path / "nvidia" / component / "bin"
        directory.mkdir(parents=True)
        for name in filenames:
            (directory / name).write_bytes(b"test placeholder")
    dirs, libraries = [], []
    monkeypatch.setattr(gpu.sys, "platform", "win32")
    monkeypatch.setattr(gpu, "_windows_initialized", False)
    monkeypatch.setattr(gpu, "_dll_directories", [])
    monkeypatch.setattr(gpu, "_libraries", [])
    monkeypatch.setattr(
        gpu, "distribution", lambda _: SimpleNamespace(locate_file=lambda name: tmp_path / name)
    )
    monkeypatch.setattr(
        gpu.os, "add_dll_directory", lambda path: dirs.append(path) or object(), raising=False
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda path: libraries.append(path) or object(), raising=False)
    monkeypatch.setenv("PATH", "original")
    gpu.prepare_windows_cuda()
    gpu.prepare_windows_cuda()
    assert len(dirs) == 3 and len(libraries) == 4
    assert all(str(tmp_path) in path for path in libraries)
    assert gpu.os.environ["PATH"].endswith("original")


def test_auto_probe_without_gpu_uses_cpu_without_loading_libraries(monkeypatch):
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 0)
    monkeypatch.setattr("device_audio.gpu.prepare_windows_cuda", lambda: pytest.fail("CUDA library setup"))
    result = detect_whisper_device()
    assert result["device"] == "cpu" and result["reason"] == "no_compatible_cuda_device"


def test_auto_probe_selects_compatible_gpu_and_reads_memory(monkeypatch):
    import device_audio.gpu as gpu

    monkeypatch.setattr(gpu.sys, "platform", "linux")
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 2)
    monkeypatch.setattr(
        "ctranslate2.get_supported_compute_types",
        lambda device, index: {"int8_float16"} if index == 1 else {"float32"},
    )
    monkeypatch.setattr(gpu, "prepare_windows_cuda", lambda: None)
    monkeypatch.setattr(gpu.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="4094"))
    result = detect_whisper_device()
    assert result["device"] == "cuda" and result["gpu_device_index"] == 1
    assert result["total_vram_mib"] == 4094


def test_auto_probe_reports_runtime_failure_without_raw_error(monkeypatch):
    def broken():
        raise RuntimeError("private file and credential detail")

    monkeypatch.setattr("ctranslate2.get_cuda_device_count", broken)
    result = detect_whisper_device()
    assert result["device"] == "cpu" and result["reason"] == "cuda_runtime_unavailable"
    assert "private" not in str(result)
