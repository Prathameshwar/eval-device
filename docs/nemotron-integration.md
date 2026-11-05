# Nemotron CPU integration and validation

Completed 2026-09-19. The standalone laptop audio API now supports Nemotron 3.5 ASR Streaming 0.6B in addition to all six existing Whisper choices. Existing service settings and Whisper model files were preserved. No platform/database/video runtime behavior changed.

## Selection and installation

See the [audio runbook](../device/audio-process/README.md#select-nemotron-for-incremental-cpu-recognition). From `device/audio-process`, run `uv sync --frozen`, then explicitly install with `uv run audio-api download-model --model nemotron-3.5-asr-streaming-0.6b`. The model is already installed on this workspace laptop.

Configure the existing private `.env` and restart the audio service:

```dotenv
AUDIO_MODEL_NAME=nemotron-3.5-asr-streaming-0.6b
AUDIO_MODEL_PATH=.models/nemotron-3.5-asr-streaming-0.6b
AUDIO_CPU_THREADS=4
AUDIO_STREAMING_QUEUE_MS=5000
```

The name selects `sherpa-onnx`; a separate engine switch is unnecessary. Model paths must match the selected family. To return to Whisper, select its existing name/path and restart. The training profile still requires console output, duplicate ASR recording and callbacks disabled, as its coordinator owns the recording. Standalone recording remains enabled by default.

Downloaded export: multilingual 560 ms INT8, archive size 475,271,763 bytes. Published archive SHA-256: `c6bf5e0df765f9d5b43bc9e0536d4b4b3e7d40bdf5ecf13e45f134c51c05ae3a`. The installer checks size/hash before copying four exact allowlisted regular files, refuses overwrites and publishes the complete model directory. Source and per-file hashes are in `.models/nemotron-3.5-asr-streaming-0.6b/download-manifest.json`. Runtime versions tested: sherpa-onnx 1.13.8, ONNX Runtime 1.30.0, Python 3.12.9, CPU INT8/four threads/greedy decoding.

Sources: [NVIDIA model card and OpenMDW-1.1 license](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b), [sherpa multilingual export and usage](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html).

## Runtime behavior

- One resident model is loaded/warmed before readiness. Per-connection recognition state is created and used on the existing serialized native worker; model weights are shared.
- Incremental 150 ms PCM blocks are decoded while audio arrives. The model uses its own 560 ms cadence. State is reset after silence, the configured maximum utterance duration, or explicit flush. Every real sample is retained; synthetic end padding is excluded from recording/timestamps.
- Final transcript, console, recording and optional callback behavior remains compatible. Partial results are not delivered. Model/engine metadata reflects the selected adapter. In auto mode language stays `auto`; segments describe utterance intervals rather than aligned words.
- Streaming queues are bounded separately from Whisper chunk queues. Existing client authentication, TLS requirements, capacity, recording quotas and inference deadlines apply. A stuck native call retires readiness; it never launches a second model.
- Model selection is operator configuration. No automatic model switch, cloud fallback, PMS connection or external transcript destination is introduced.

## Three real audio tests

The same three inputs from the prior Whisper demonstration were sent as paced 20 ms frames over authenticated loopback WebSockets, with local recording enabled and console/callbacks disabled. This is the available Windows/Core Ultra 7 165H/64 GB host, not the intended 16 GB laptop or Pi/Wi-Fi environment. Tests ran sequentially with one load. Timings are single samples.

Load plus warmup: **3.87 s**. Measured process peak working set: **883 MB**; private commit: **1595 MB**. These are different memory measures and exclude the rest of the patient-response/video platform.

| Input | Audio duration | Input end to API complete | Total stream | Native work for returned utterance |
|---|---:|---:|---:|---:|
| Test 1: en | 3.30 s | 0.382 s | 3.686 s | 1.040 s |
| Test 2: hi | 5.58 s | 0.204 s | 5.798 s | 2.073 s |
| Test 3: auto | 3.96 s | 0.450 s | 4.394 s | 1.545 s |

Native work largely overlaps audio arrival. Completion timing includes API finalization; it is not speech-end-to-audible-patient-response latency. Empty trailing windows do not produce transcript events. The English test had two processed windows and one transcript.

### Test 1

[Play/download input WAV](../.test_artifacts/nemotron-validation/audio/test-1.wav)

Reference: He built a WiFi door bell, he said.

Nemotron: He built a Wi Fi doorbell

Quality: Main clause recognized; omitted the reference phrase "he said". WiFi spacing also raises strict word error counts. Strict word edits: 5/8.

### Test 2

[Play/download input WAV](../.test_artifacts/nemotron-validation/audio/test-2.wav)

Reference: हालांकि तीन लोग घर के अन्दर थे फिर भी जब कार टकराई तब किसी को भी चोट नहीं आई।

Nemotron: हालांकि तीन लोग घर के अंदर थे, फिर भी जब काटी तब किसी को भी चोट नहीं आई

Quality: Most of the sentence and the no-injury statement are retained, but the car-collision phrase is changed. This is a meaningful content error, despite the relatively low strict word error count. Strict word edits: 3/19.

### Test 3

[Play/download input WAV](../.test_artifacts/nemotron-validation/audio/test-3.wav)

Reference: मुझे chest pain तीन दिन से है।

Nemotron: तीन दिन से है

Quality: Synthetic mixed-language input, not natural Hinglish. The time phrase is retained but "chest pain" is missing. Not acceptable symptom extraction. Strict word edits: 3/7.

English/Hindi human recordings come from [Google FLEURS](https://huggingface.co/datasets/google/fleurs), CC BY 4.0. Clip IDs and PCM hashes are retained in the case manifests. The third clip combines synthetic Hindi and English voices; its quality cannot establish natural code-switching accuracy. Normalization/scoring matches the prior [three-audio report](whisper-three-audio-tests.md). These familiar clips are smoke tests, not a new held-out quality benchmark.

The initial three results are promising for CPU latency. Quality still requires natural clinical Hindi/English/Hinglish acceptance; lower delay does not establish better clinical accuracy or a production-ready patient conversation.

## Review and verification

First review covered model selection, startup residency, per-client state, sample continuity, endpoint/flush behavior, cancellation, native deadlines, bounded queues, metadata, Windows dependencies, installation integrity and recording/callback isolation. Fixed a confirmed Windows runtime conflict: sherpa initially resolved a system ONNX DLL exposing API 17 while requesting API 28. The adapter now explicitly loads the installed environment DLL; system files are untouched. A regression test checks its path and one-time loading.

The expanded suite exposed test-only header contamination: Starlette added WebSocket handshake headers to a shared dictionary in a new test. The test now passes a copy and asserts the shared headers remain unchanged. The complete suite was rerun successfully.

Final review revisited the completed code and tests after fixes. It checked that Whisper remains selectable, model/context state is not shared across clients, output is emitted only once per final utterance, padding cannot affect recording lengths, native timeout cannot spawn replacement inference, invalid archives cannot write paths, and built artifacts exclude private data and weights. Reviews were performed by the same implementation agent.

- **124 audio tests passed** (106 existing plus 18 new). Audio Ruff, format and mypy passed; lockfile consistency passed.
- **21 training tests passed**. The coordinator consumes the existing final-transcript contract.
- **42 platform tests passed; 68 PostgreSQL integration tests skipped** because no dedicated disposable `PMS_TEST_ADMIN_DSN` was configured. Platform Ruff, format and mypy passed. No database/schema changes were made.
- **7 real Nemotron API streams plus 1 existing Whisper-small stream** passed: the three demonstration inputs, concurrent Hindi/English streams, nine seconds of silence across an utterance reset, a repeated English stream and the Whisper compatibility check. All eight saved input PCM and delivered/saved text pairs were checked exactly.
- The four-stream Nemotron smoke process loaded one model, allocated four session states, and executed **138 incremental native calls**. No text was emitted for long silence. Repeated English output matched. Smoke timing ran alongside other checks and is not used as benchmark data.
- Audio wheel/source builds passed. Final verification hashes model files, preserved medium/turbo manifests, benchmark outputs and package sources. Existing dependency deprecation warnings remain.

Evidence: `.test_artifacts/nemotron-validation/{run.py,smoke.py,verify.py,cases.json,verification.json}`, model result JSONs and private recordings. The wheel/source archives are in `device/audio-process/dist`. Test servers exited; this task does not leave a service running or change the operational model selection.

Remaining acceptance: natural clinical speech, actual Pi/microphone, Wi-Fi, the target 16 GB laptop, concurrent camera recording, and complete dialogue/TTS/playback latency. No live cloud or hardware verification is claimed.
