# Whisper Large-v3 GPU validation

Completed 2026-09-19. Optional NVIDIA execution is implemented for the existing Whisper models. CPU remains the default; model choices and resident loading are preserved. Nemotron remains CPU-only in this version.

## Enable or disable GPU

From `device/audio-process`, install the optional Windows x64 runtime dependencies:

```powershell
uv sync --frozen --extra cuda
```

Configure the existing private `.env`:

```dotenv
AUDIO_MODEL_NAME=large-v3
AUDIO_MODEL_PATH=.models/large-v3
AUDIO_GPU_ENABLED=true
AUDIO_GPU_DEVICE_INDEX=0
```

Then restart using `uv run --extra cuda audio-api serve`. Keep `--extra cuda` on later sync/run commands so uv retains the optional dependencies. Set `AUDIO_GPU_ENABLED=false` and restart for the existing CPU INT8 path. The same downloaded model assets work in either mode. No operational secrets/settings were rewritten by the validation run.

The GPU flag selects CUDA INT8/FP16 (`int8_float16`) and the configured NVIDIA index. The model loads and warms once before readiness. Requests reuse it through the existing serialized worker. Missing/unavailable GPU, incompatible compute support, missing runtime libraries and allocation failures are explicit failures; there is no silent CPU fallback. `AUDIO_GPU_ENABLED=true` with the current Nemotron model is rejected during configuration validation.

Authenticated status and ready/transcript events now report `device` and `compute_type`; status also reports the GPU flag/index. GPU mode checks the native CTranslate2 model reports CUDA and the requested precision. Audio capture/transport, speech detection, callbacks and recording still use CPU resources.

On Windows, the adapter discovers NVIDIA runtime DLLs from this Python environment, preserves their DLL-directory handles and preloads the required libraries. Search-path changes apply only to this process. System drivers/files are not replaced. CPU mode does not initialize CUDA or require these optional libraries. The locked optional wheels target Windows x64; other operating systems need operator-provisioned CUDA libraries and were not verified.

Runtime tested: CTranslate2 4.8.2, faster-whisper 1.2.1, cuBLAS 12.8.4.1, CUDA runtime 12.8.90 and cuDNN 9.7.1.26. Requirements and GPU quantization: [faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu), [CTranslate2 quantization](https://opennmt.net/CTranslate2/quantization.html).

## Actual GPU use

- NVIDIA RTX 500 Ada Generation Laptop GPU, driver 573.57, 4,094 MiB reported total memory.
- CTranslate2 confirmed actual device `cuda`, device index `[0]`, compute type `int8_float16`.
- The benchmark process was listed by NVIDIA as a GPU compute process. Per-process memory was unavailable (`N/A`) under Windows WDDM.
- NVIDIA device-wide sampling recorded a peak of **1,909 MiB (1.86 GiB)** and **100% utilization** across 45 samples, with no monitor errors. Memory was zero at the pre-run baseline and returned to zero after process exit. Sampling can miss shorter peaks; this is not a worst-case VRAM requirement.
- The model loaded once; load plus warmup took **7.74 seconds**. It was reused for all three streams.

## Same-audio comparison

Paced 20 ms authenticated loopback WebSocket streams, recording enabled, console/callbacks disabled, beam size one and four CPU threads. These are the same audio bytes as the previous three-test demonstration. CPU and GPU runs occurred at different times; only GPU uses INT8/FP16 instead of CPU INT8. This comparison measures the implemented pipelines, not a controlled hardware microbenchmark.

| Input | Audio duration | Large-v3 CPU: after input | Large-v3 GPU: after input | Nemotron CPU: after input |
|---|---:|---:|---:|---:|
| Human English | 3.30 s | 16.63 s | **0.38 s** | 0.38 s |
| Human Hindi | 5.58 s | 21.57 s | **4.26 s** | 0.20 s |
| Synthetic mixed Hindi/English | 3.96 s | 37.80 s | **1.93 s** | 0.45 s |

Timing starts when the input audio ends and stops at API completion. It excludes model startup and later answer generation/TTS/playback. English recognition starts at the speech endpoint before the entire file finishes; its GPU native inference took 1.06 s, which explains why post-input time is only 0.38 s. Hindi and synthetic mixed input native work took 4.26 s and 1.93 s. Nemotron processes smaller blocks while audio arrives, so its timing represents a different streaming design.

All three GPU transcripts exactly matched the earlier Large-v3 CPU transcripts. GPU acceleration improved speed for these clips; it did not repair recognition errors.

### Test 1

[Input audio](../.test_artifacts/whisper-three-tests/audio/test-1.wav)

Reference: He built a WiFi door bell, he said.

GPU transcript: He built a Wi-Fi doorbell, he said.

Quality: Complete meaning retained; strict word differences arise from WiFi/door bell formatting.

### Test 2

[Input audio](../.test_artifacts/whisper-three-tests/audio/test-2.wav)

Reference: हालांकि तीन लोग घर के अन्दर थे फिर भी जब कार टकराई तब किसी को भी चोट नहीं आई।

GPU transcript: हाला कि तीन लोग घर के अंदर थे फिर भी जब कार टकराई तब किसी को भी चोट नहीं आई

Quality: Closest of these model examples to the human Hindi reference, with an initial spelling/word-boundary error. The car-collision and no-injury details are retained.

### Test 3

[Input audio](../.test_artifacts/whisper-three-tests/audio/test-3.wav)

Reference: मुझे chest pain तीन दिन से है।

GPU transcript: Moogia. Cast Pie. Dean Vincey Heia.

Quality: Unusable result on this artificial mixed-voice clip. It misses the chest-pain symptom and duration; this is not evidence of natural Hinglish accuracy.

The first two recordings are from [Google FLEURS](https://huggingface.co/datasets/google/fleurs), CC BY 4.0. The third combines synthetic Hindi and English voices. Exact references, IDs, PCM hashes and prior scoring are in [the earlier three-audio report](whisper-three-audio-tests.md). These familiar examples do not establish clinical accuracy.

## Review and verification

First review checked CPU default preservation, explicit GPU selection, supported-device checks, native device/precision verification, optional dependency isolation, model residency, metadata, runtime library search and failure behavior. Fixed a static typing issue in metadata-based DLL path resolution before the hardware run. Optional package markers were narrowed to the tested Windows x64 environment.

Final review confirmed one GPU model load across all streams, unchanged transcripts versus prior CPU outputs, bounded existing processing/recording behavior, truthful GPU metadata and no automatic fallback. Reviews were by the same implementation agent.

- **135 audio tests passed**, including 11 new GPU selection, environment flag, unavailable-device, unsupported-precision, metadata and Windows DLL initialization cases.
- **21 training compatibility tests passed**. Existing dependency deprecation warnings remain.
- Audio Ruff, format and mypy passed; lockfile consistency passed.
- Real GPU verification found **3/3 exact input/saved PCM and delivered/saved transcript matches**.
- Wheel/source builds passed; the verifier compared **52 packaged source/assets**, checked the new GPU module is present, and excluded private settings, weights and media.
- GPU telemetry, model/device confirmation, result hashes and package hashes are retained in `.test_artifacts/whisper-gpu/{run.py,large-v3-cuda.json,verify.py,verification.json}`.

All benchmark servers/processes exited. Platform/database suites were not rerun for this isolated audio change; no database schema/business rule changed and no database was accessed. Pi/microphone, Wi-Fi, the target 16 GB system, long-duration GPU load, simultaneous video and full patient-response latency remain unverified. GPU memory availability may differ with other applications.
