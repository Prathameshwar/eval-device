# Vosk integration and evaluation status

Date: 2026-09-19. CPU adapter and checks completed; **real recognition benchmarking is deferred**. Neither English nor Hindi model weights were successfully downloaded. No Vosk accuracy, latency, recording-integrity or native CPU-recognition result is claimed.

## Implemented

- Optional pinned `vosk==0.3.45` dependency in `device/audio-process/pyproject.toml` and `uv.lock`; existing Whisper CUDA packages remain installed. Base/CPU installations do not require either extra.
- Selectable `vosk-model-small-en-us-0.15` or `vosk-model-small-hi-0.22`; existing Whisper/Nemotron selections and operational private settings are preserved.
- One warmed resident model per process, isolated per-session/utterance recognizers, serialized incremental CPU inference and bounded output. The adapter accumulates Vosk internal endpoint results before emitting the service's final transcript.
- Explicit matching `en`/`hi` language required. `auto` and mismatched language fail with `unsupported_language` before recording or audio reception. Status/ready advertise supported languages. These monolingual models do not provide automatic bilingual detection.
- Existing authentication, TLS, stream/audio limits, private recording, callbacks, native deadlines and queue limits continue to apply. No PMS/database/cloud connection was added.
- GPU flag rejected for Vosk. Metadata reports `vosk` / `cpu` / `model_default`; `cpu_threads=null` because this Python API has no equivalent per-recognizer thread-count control.
- Explicit installer supports original publisher or pinned Hugging Face mirror, bounded transient retries, publisher archive size/MD5 validation, allowlisted ZIP extraction and complete-directory publication without overwrite. File/archive SHA-256 hashes are recorded locally after success. MD5 is the available publisher checksum, not a signature. Serving never downloads models.

## Download attempts and remaining work

Original Vosk URLs returned HTTP 403. Inspection identified the corporate content filter's Access Denied response. Direct pinned LocalStack and Rhasspy Hugging Face archive URLs also returned 403. Retried outside the workspace sandbox; downloads still failed.

At the user's request, also tried Hugging Face's official `huggingface_hub` 1.32.0 client against `rhasspy/vosk-models` revision `e7ac2109d134b5f2404ba95389b2fb51916d4cab`, with account tokens disabled and normal TLS verification using Windows trust roots. Both sandboxed and elevated attempts failed: English `RemoteProtocolError`, Hindi `LocalEntryNotFoundError` with no cached file. Neither model archive was obtained. No network controls were changed and TLS verification was not disabled.

The user explicitly chose to finish code/checks and defer benchmarking, then requested the additional Hugging Face attempt. That attempt is complete, with the same outstanding need for model access. Once downloads are allowed, the repository-supported commands from `device/audio-process` are:

```powershell
uv sync --frozen --extra vosk --extra cuda
uv run --extra vosk --extra cuda audio-api download-model --model vosk-model-small-en-us-0.15 --vosk-source huggingface
uv run --extra vosk --extra cuda audio-api download-model --model vosk-model-small-hi-0.22 --vosk-source huggingface
```

Keep `--extra cuda` to retain this laptop's installed Whisper GPU libraries; omit it on a CPU-only installation. See [audio configuration](../device/audio-process/README.md#optional-vosk-cpu-streaming) for selection/start messages. The mirror is public, pinned and requires no credentials. These download commands could not be validated against real archives on this network; installer behavior was tested with fixture archives.

Deferred acceptance: install and inspect both real archives, load each model once, run matching English/Hindi reference audio through paced API streams, compare exact delivered/saved PCM/text and measure startup, post-input delay and memory. Test the existing synthetic mixed clip with each explicit language and label it accordingly; do not present it as automatic Hinglish recognition. Follow with actual patient-interview microphone data before accepting quality.

## GPU capability evidence

The installed Windows Vosk 0.3.45 library's `vosk_batch_model_new` entry point starts with machine bytes `31 c0 c3`: x86-64 `xor eax,eax; ret`, an unconditional NULL-return stub. Calling the batch constructor returned `Failed to create a model`. The constructor error alone would not prove lack of CUDA because valid weights were unavailable; the inspected stub and upstream build documentation establish this wheel's limitation. `GpuInit()` returning normally is not evidence of GPU inference.

Library SHA-256: `9331c2f6a32cf77141af27c9750e79532718f51bbc2e3cea3c60f14ca4251e4e`. The NVIDIA GPU remains available to the already verified Whisper adapter. WSL reported not installed; Docker and `nvcc` were not found. No Vosk GPU recognition or timing benchmark ran. Supporting Vosk's separate CUDA/batch implementation would require a suitable custom build and additional adapter work; the current flag deliberately fails instead of silently using CPU.

Primary references: [Vosk installation/build instructions](https://alphacephei.com/vosk/install), [CUDA-disabled native API branch](https://github.com/alphacep/vosk-api/blob/master/src/vosk_api.cc), [official GPU Docker build](https://github.com/alphacep/vosk-server/blob/master/docker/Dockerfile.kaldi-vosk-server-gpu), [publisher model metadata](https://alphacephei.com/vosk/models/model-list.json). Public mirrors: [Rhasspy English](https://huggingface.co/rhasspy/vosk-models/tree/main/en), [Rhasspy Hindi](https://huggingface.co/rhasspy/vosk-models/tree/main/hi).

## Reviews and verification

First review traced engine dispatch, startup/model residency, thread ownership, decoder isolation, finalization, language mismatch handling, output bounds, metadata and dependency separation. Fixed misleading Vosk INT8/thread-count metadata, validated the recognizer result type before trimming, and prevented permanent HTTP/checksum errors from being retried. Added regressions for completed internal endpoints being retained and for unsupported languages being rejected before audio processing.

Final review revisited the finished paths and the difference between mocked checks and native evidence. Confirmed all earlier Whisper names remain routed to faster-whisper, Nemotron remains routed to sherpa, Vosk imports are optional, GPU fails explicitly, and no operational `.env`, model weights or service defaults were replaced. Both reviews were performed by the same implementation agent.

Verification: **152 audio tests passed** (including 17 Vosk-related additions), **21 training tests passed**, audio Ruff and format checks passed, mypy passed for 19 source files, and `uv lock --check` passed (61 packages). Wheel/source builds passed with 58 exact packaged-source/asset comparisons; private settings, media and model weights are excluded. The Vosk and existing three NVIDIA runtime packages remain installed. Existing third-party deprecation warnings remain. Platform/database tests were not rerun for this isolated audio change; no database was accessed. No Pi/Wi-Fi, native Vosk recognition, clinical quality, target 16 GB or GPU-Vosk verification is claimed.

Evidence: `.test_artifacts/vosk-validation/{gpu_probe.py,gpu-capability.json,download.py,download_hf.py,hf-download-results.json}` and `device/audio-process/tests/test_vosk.py`. Final package verification is recorded in `.test_artifacts/vosk-validation/package-verification.json`.
