# Audio implementation and latency review

Completed 2026-09-19. Scope: standalone audio API, Pi microphone capture and upload, laptop transcription adapter, training coordinator, recording/delivery, and playback handoff. This is a source/test/native-loopback review. Live Pi hardware, Wi-Fi/TLS deployment, target 16 GB acceptance and live cloud integration remain deferred.

## Decision

The resident-model/background-recording architecture is sound for the pilot, but the interactive latency gate is **not met**. Native Whisper inference dominates this host's measured delay. `large-v3` is unsuitable for prompt patient replies in the measured CPU configuration. Keep the existing selectable models and the training profile's `small` setting pending human-speech accuracy/performance acceptance; no model/configuration was silently replaced.

The existing transport is WebSocket over TCP, using TLS for remote links. There is no separate raw TCP listener. The training Pi sends an incremental HTTP audio body to the coordinator, which forwards PCM over a local WebSocket; video has a separate WebSocket. The standalone audio API accepts WebSocket PCM directly. Neither path makes a new HTTP request per PCM frame. The [existing transport decision](local-media-transport.md) remains appropriate; a socket change would not remove the measured native inference cost.

## Confirmed findings and fixes

| ID | Finding | Resolution and regression evidence |
|---|---|---|
| L-01 | A chunk waiting in the per-stream buffer received a fresh inference timeout when finally submitted. Queue memory was bounded, but age was not included in the timeout. | The request budget starts at segmentation/enqueue time. Already-expired audio is rejected without model work. Audio latency regression verifies no inference occurs. |
| L-02 | A permanently blocked native call could leave readiness true after callers timed out. Shutdown was bounded, but normal operation did not retire the stuck worker. | Native execution has its own deadline; expiry fails readiness, stops further native admissions and resolves queued callers. Authenticated status reports `native_inference_timeout`. No parallel replacement model or automatic retry. Regression blocks native work without calling shutdown and verifies refusal of further work. |
| L-03 | Microphone bytes were captured in one event-loop callback per hardware block before reaching the bounded asyncio queue. A stalled loop could accumulate callbacks and their bytes. | A thread-safe bridge caps retained blocks at 20 (about 400 ms at 20 ms/block), coalesces pending wakeups, and explicitly fails on overflow. A 1,000-block stalled-loop test proves two configured slots and one pending wakeup remain bounded. |
| L-04 | One short noise burst below the speech threshold disabled the five-second no-speech exit, potentially holding capture for the full 30-second turn. | The no-speech exit applies until the minimum voiced-block count is reached. A simulated clock/device regression exits near five seconds after a brief burst. This does not establish real microphone VAD quality. |
| L-05 | The training response timeout covered transcription only. Selection, TTS and persistence could each add more delay afterward. | At input EOF, one response deadline now covers remaining ASR, selection, TTS and successful persistence. Slow selection/TTS tests cancel and fail the turn. Error cleanup/storage reporting can take additional bounded time. |
| L-06 | `processing_seconds` subtracted PCM duration from elapsed time. Burst uploads could report negative latency and paced uploads mixed unrelated stages. | Measure actual input EOF and record nonnegative receive, post-input ASR, selection, TTS, response save and response-ready durations. Burst-upload regression checks the measurements. |
| L-07 | Authorization was checked after transcription and after TTS, but not immediately after awaited answer selection. | Recheck before speech generation; a selection-time expiry regression verifies TTS does not start. Existing lease limits and playback checks remain. |
| L-08 | Early upload failure did not explicitly close the capture generator and its nested hardware generator. Cleanup depended on generator finalization. | Upload cleanup always closes its source; capture closes the underlying microphone in `finally`. Regression verifies nested microphone cleanup. |
| L-09 | A failed durable turn-admission write happened before the processing error handler and could leave an active session with a processing row. | Admission failure marks the turn/session failed before ASR. A storage fault regression verifies no transcription starts. |

Relevant source: [runtime](../device/audio-process/src/device_audio/runtime.py), [audio status](../device/audio-process/src/device_audio/app.py), [hardware](../device/training/src/device_training/hardware.py), [agent](../device/training/src/device_training/agent.py), [coordinator](../device/training/src/device_training/coordinator.py). Regressions: [audio](../device/audio-process/tests/test_latency_review.py), [training](../device/training/tests/test_latency_review.py).

## What was preserved and checked

- One local CPU INT8 Whisper model per service process, loaded and warmed before readiness. Inference stays serialized through cancellation; no per-request loading or silent model/cloud fallback.
- Bounded stream and shared inference queues, explicit overload errors, frame/input/session limits, authenticated client admission and TLS requirements for remote clients.
- Standalone audio recording runs on a separate bounded disk worker. Slow/broken disk does not wait on transcript delivery; receipts distinguish pending, saved and incomplete. Existing exact-byte, blocked-disk, overflow, retry and recovery regressions pass.
- Callback/console delivery remains separate from transcript emission. Completion can wait for bounded delivery results when enabled. Only failures known to precede POST submission are retried; unknown outcomes are not replayed.
- Training preflight requires standalone ASR recording, console and callbacks disabled. The coordinator owns training media and deliberately waits for durable admission/output saving. It does not promise zero recording latency.
- Local session/turn/authorization checks, approved-answer selection, TTS budget, private storage and no automatic replay of uncertain playback remain intact. The audio service itself has no PMS connection.
- Video remains receive-and-record only. No detection, model or live frame extraction was introduced; the training network regression still exercises its real recorder.

## Native measurements

Host: Windows, Intel Core Ultra 7 165H (16 cores/22 logical processors), approximately 64 GB installed RAM. Four Whisper CPU threads, INT8, beam size 1, explicit `en`/`hi`, one warmed model/service at a time. Existing local weights were used; no download or cloud request.

Inputs: synthetic eSpeak questions, English 1.929 seconds and Hindi 2.016 seconds. Eight paced 20 ms loopback WebSocket streams per model: recording off/on/on/off, each with both languages. Each produced one nonempty transcript chunk. This is **not** a transcript-correctness, human-speech or mixed-language benchmark. Model construction occurred once per eight streams.

| Model | Startup + warmup | English: input EOF to complete | Hindi: input EOF to complete |
|---|---:|---:|---:|
| Whisper small | 3.17 s | 2.10-3.98 s | 4.09-5.26 s |
| Whisper large-v3 | 15.17 s | 12.15-34.88 s | 12.31-35.71 s |

Startup measurements do not establish uncached disk/cold-machine performance. Complete includes delivery bookkeeping with console/callbacks disabled; background recording finalization was polled separately. Neither row includes dialogue, reply TTS, speaker playback, Pi capture or Wi-Fi. The clip was paced and explicitly finished; these measurements do not establish real acoustic end-of-speech delay. Live energy/VAD gating normally waits about 600 ms of silence and is hardware-dependent.

The largest reported queue wait was 0.16 ms in these single-stream runs. EOF-to-complete exceeded summed native inference by at most 2.67 ms for small and 5.29 ms for large-v3. This comparison isolates this particular single-chunk loopback path; it is not a general network latency guarantee or a concurrency result.

| Model | Mean EOF-to-complete, recording off | Mean EOF-to-complete, recording on |
|---|---:|---:|
| small | 3.65 s | 3.76 s |
| large-v3 | 24.20 s | 14.21 s |

Large run-to-run variation dominates these tiny samples. The small-model observed difference is about 0.12 s; the large-model runs with recording happened to be faster. Neither is evidence of a causal recording penalty/improvement or zero overhead. All eight recordings finalized as saved with the expected audio byte count. Existing regression tests separately verify byte-for-byte integrity and progress under blocked disk I/O. These runs do not measure target memory pressure, thermal stability, sustained capture, simultaneous video or multi-client inference.

Reproduction script and raw non-sensitive metrics: `.test_artifacts/audio-latency-review/measure.py`, `native-stream-metrics.json`, `native-progress.txt`. The script creates private synthetic recordings and uses ephemeral loopback ports and random in-memory credentials. It never reads operational environment secrets. All measurement servers were stopped.

## Timing and operational interpretation

- Audio `queue_ms` includes stream/shared waiting; `inference_ms` includes native dispatch/execution. Neither measures microphone-to-text or acoustic speech-end-to-text. Timeout age now uses the same original enqueue point.
- Training `input_receive_seconds` measures wall time until input EOF after admission, including forwarding setup. `input_duration_ms` remains PCM duration. `asr_after_input_seconds`, `dialogue_seconds` and `tts_seconds` separate remaining stages. `processing_seconds` now means EOF through synthesized response, excluding persistence. This corrects its previous meaning.
- `response_save_seconds` and `response_ready_seconds` include the final output save; they are immediately returned/in memory and become durable on the next state save (normally playback claim). They are not guaranteed in the first saved turn snapshot. Neither includes HTTP return, Pi claim/download, speaker buffering or audible playback.
- `TRAINING_RESPONSE_SECONDS` bounds post-input work. The initial capture/transcription window also has an overall bound. On expiry the turn fails; cleanup may need the separately bounded storage deadline. The Pi's HTTP read timeout and issued session lease remain additional bounds.
- If `native_inference_timeout` occurs, readiness becomes false. Inspect the selected model/settings and restart the process after resolving the cause. Python cannot safely kill the native call; it may remain in its daemon thread until it returns or the process exits. No restart within the same runtime is allowed.
- Keep the dedicated training profile on one session (`AUDIO_MAX_SESSIONS=1`) and align its inference timeout with the chosen training response budget when deploying. These are explicit deployment settings; this review did not overwrite private `.env` files or tune the standalone service globally.

## Verification and final review

- Platform: **110 passed, no skips**, including four coordinated retirement/lease/control races and the complete kidney API lifecycle. A-01/A-02 are closed in the [API audit](patient-scenario-api-audit.md#audit-follow-up-closure-2026-09-19). No platform production code or migration changed.
- Audio: **106 passed**, including the two new latency regressions and existing real transport, model reuse, storage, retry, shutdown and privacy tests.
- Training: **21 passed**, including nine new review regressions and the existing real HTTP/WebSocket/video-store integration with explicit ASR/dialogue/hardware doubles.
- Ruff, format and mypy pass for all three packages. Audio/training dependency locks validate. Wheel/source builds and archive inspection are recorded with hashes in `.test_artifacts/audio-latency-review/package-verification.json`.
- First review traced capture through playback and recording/delivery, implemented the fixes above and ran focused tests. Final review checked cancellation, generator cleanup, timeout/readiness behavior, authorization before TTS, durable admission, metric definitions, package contents and the fresh complete test results. No additional confirmed issue remains open within this review scope.

This closes the software review, **not** the interactive pilot acceptance gate. Next acceptance work is representative human Hindi/English/mixed speech on the actual 16 GB laptop and Pi, with camera recording enabled, measured acoustic speech-end-to-audible-response p50/p95, accuracy scoring, noise/echo tests and sustained memory/CPU pressure. Those results should determine the model/profile; the current measurements do not justify choosing large-v3 for live patient conversation.

Follow-up: the [four-model CPU comparison](whisper-model-comparison.md) adds downloaded medium/turbo assets, a fixed human/synthetic quality set and new API measurements. It expands model-selection evidence; the hardware, microphone and complete-response acceptance limits above remain.
