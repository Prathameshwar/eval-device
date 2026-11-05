# Offline models and processing final review — 2026-09-19

Scope: installed local ASR and Qwen models, PMS patient answering, the desktop
controller, GPU/CPU execution, recording, startup and failure handling. Existing
application services, database contents and configuration were preserved. Native
PMS checks used a separate disposable PostgreSQL 17 cluster; provider calls were
to the real local Qwen server with external calls disabled.

“Offline” here means local model inference without internet services. The patient
workflow still needs its local PMS API, PostgreSQL and authorized patient setup;
it is not a standalone disconnected-Pi implementation.

## Findings and fixes

| Finding | Fix or verified boundary | Evidence |
|---|---|---|
| The desktop trusted cached ASR readiness without checking the newly accepted stream | Verify model, device, supported language and disabled callbacks in the stream handshake before consuming microphone frames | Five regressions reject changed model/device/language and enabled or missing callback metadata without capturing/sending PCM |
| Some documentation still described one-call scripted answering and deferred speech output | Document the current routing-plus-wording calls, authored fallback, token accounting and installed English speech output | Local-LLM and desktop README updates |
| Optional model assets are incomplete | Separate native verification of installed models from missing model assets | QwenMedic, Whisper Medical and Vosk are not installed completely on this machine; their inference remains unverified |
| Functional success does not establish Hindi/Hinglish transcription accuracy | Retain actual transcripts, error scores and timing separately from transport/recording checks | Synthetic Hindi and mixed-language examples still contain substantial recognition errors |
| Hindi speech output is not configured | Verify English synthesis and the documented Hindi text-only fallback | The current voice lock contains English only; English native synthesis passes |

The first review checked model residency, offline file loading, authentication,
language/device compatibility, bounded queues, timeouts, recording privacy,
non-replay of uncertain requests and GPU sharing. It produced the stream-handshake
fix. The second inspection checked that fix and its regressions, the actual native
patient flow, package contents and compatibility with concurrent changes.

No production API logic, migration, model weights or user model configuration was
changed. The new native integration test is explicitly opt-in and uses the
existing disposable-database fixture.

## Real local patient flow

The current laptop has an NVIDIA RTX 500 Ada GPU with 4,094 MiB reported VRAM.
Qwen3 4B Q4_K_M ran with **16 GPU layers** and a **2,048-token context**, alongside
resident Whisper large-v3 CUDA `int8_float16`. Both reused their loaded models.

The desktop controller sent a paced 2.317-second English WAV through the actual
authenticated audio WebSocket API, submitted its transcript through the real PMS
authentication/authorization and patient APIs, and received an actual Qwen answer.
PMS HTTP transport ran in-process for the test; ASR and Qwen used network loopback.
No model answer was mocked.

Question: “When did the chest pain start?”
Answer: “It began two days ago.”

| Response mode | ASR after input ended | PMS round trip | Total including input audio |
|---|---:|---:|---:|
| Non-streaming | 1.672 s | 2.516 s | 6.516 s |
| Streaming | 0.890 s | 3.047 s | 6.265 s |

Patient wording is checked before release, so the streaming mode does not promise
immediate unvalidated model tokens. The test verifies the final screen-output
events, history, saved result and speaker-dispatch event; it does not play audio or
open a physical microphone.

The native PMS tests also passed name, Hindi age, temperature, meals, sleep,
backchannel, movement acknowledgement and unknown-question cases. Routing prompts
used **726–741 tokens**, reserving 96 output tokens and 64 safety tokens. Wording
prompts used **112–137 tokens**, reserving 192 output and 64 safety tokens. Each
prompt fit the actual native 2,048-token window. These are fixture measurements,
not a claim about unlimited conversation history or clinical validation.

## Available models and measured speech processing

Each completed ASR configuration is exercised with five fixed clips: a synthetic
English interview question, synthetic Hindi, synthetic mixed Hindi/English, human
English and human Hindi. Models load once per service process; exact recorded PCM
and delivered/saved transcript equality are checked for every clip. Missing model
files fail locally rather than triggering a serving-time download or cloud fallback.

All **30 native audio streams passed transport, completion and recording checks**
across six execution configurations. Each configuration loaded its model once.

| Model / execution | English interview after input | Human English after input | Human Hindi after input |
|---|---:|---:|---:|
| Whisper large-v3 / GPU | 1.090 s | 1.175 s | 3.075 s |
| Whisper turbo / GPU | 0.482 s | 0.047 s | 1.000 s |
| Whisper medium / GPU | 0.795 s | 0.001 s | 2.139 s |
| Whisper small / GPU | 0.235 s | 0.001 s | 1.258 s |
| Nemotron / CPU | 0.437 s | 0.581 s | 0.208 s |
| Whisper large-v3 / CPU | 16.025 s | 15.314 s | 22.230 s |

“After input” starts when the complete clip finishes sending. Very small values
mean recognition completed during the clip's trailing silence; they are not the
model's total inference time. The measurements include real paced transport and
recording, but concurrent development/test activity means these are functional
latency observations, not controlled hardware benchmarks or model-quality rankings.

Qwen3 4B also passed separate CPU-only English and Hindi generation checks, reporting
zero GPU layers and reusing the model. Those short direct requests took 2.162 and
2.260 seconds respectively; they do not measure the two-call patient workflow on CPU.
Automatic device probing detected CUDA index 0. Launcher regressions cover automatic
CPU selection when CUDA is unavailable, explicit CPU selection and 16-layer GPU
sharing; no GPU/CPU setting was persisted by these verification scripts.

The human English large-v3 result, “He built a Wi-Fi doorbell, he said,” preserved
the reference characters; word-joining/hyphenation inflated its word-error score.
The human Hindi example retained the event and no-injury meaning with spelling and
word-boundary errors. The synthetic Hindi and mixed-voice fixtures performed poorly;
they must not be used to claim natural clinical Hindi/Hinglish accuracy.

Nemotron is verified at the standalone audio-service level. The current PMS-driven
desktop selector and combined launcher are for local Whisper or Azure Whisper;
this review does not add Nemotron/Vosk to that profile contract.

English Piper reused its loaded CPU voice and synthesized 2.704 seconds of audio
in 0.495 seconds. Initial voice load took 5.369 seconds in this run. Hindi has no
pinned/installed voice in the current configuration and remains text-only.

## Verification

| Check | Result |
|---|---|
| Audio regression suite | 163 passed (30.22 s) |
| Local-LLM regression suite | 33 passed |
| Desktop suite, including native English voice test | 49 passed (17.39 s), no skips |
| Launcher regression suite | 68 passed (8.63 s) |
| Video recording regression suite | 85 passed (18.18 s) |
| Native PMS Qwen tests | 2 passed (43.64 s), including eight patient cases |
| Native ASR → desktop → PMS → Qwen integration | 1 passed (20.14 s), both response modes |
| Installed ASR engines | 30 real audio streams passed across six model/device configurations; saved PCM and text matched |
| CPU-only Qwen | Two real English/Hindi requests passed with zero GPU layers |
| Full API/database suite | 263 passed, 3 opt-in native tests skipped (688.88 s); all three native tests passed separately as recorded above; no database skips |
| Static checks | API/audio/desktop Ruff and format checks passed; API mypy passed for 55 sources, audio mypy for 20 |
| Packaging | API and desktop wheel/sdist builds passed; four archives exclude private environment, model and runtime-state directories |

An initial combined desktop/launcher test invocation used the desktop environment,
which intentionally lacks PMS launcher dependencies. Rerunning the launcher suite
under the API environment passed. There was no package installation or dependency
change to work around that invocation error.

Private run evidence is in `.test_artifacts/offline-final-review`. All review-owned
ASR and Qwen servers and the disposable PostgreSQL server stopped cleanly; no
existing user process was terminated. GPU memory returned to zero after the model
servers stopped. The final source comparison found only the intended edits to
existing Python files and the new opt-in integration test; existing migrations
were unchanged. Upstream test-client/WebSocket deprecation warnings remain.

Raspberry Pi hardware, Wi-Fi reliability, physical microphone/speaker behavior,
natural clinical speech quality and long-run load remain outside this verification.
