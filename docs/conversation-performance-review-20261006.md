# Conversation performance review, 2026-10-06

Scope: local-first human-test response latency, durable result saves, Piper output
and companion allocation. No web/API/schema changes, cloud calls or deployment.
Baseline source commit: `0e4af26` (GitHub publication `c219fff`).

## Measurement boundaries

Production timings are process-local monotonic stage durations with random turn
IDs, no question/answer text or media. The listening origin is the last detected
voiced frame as processed by the desktop energy gate, not acoustic ground truth.
The UI estimates audible onset from first output submission plus reported output
latency. Playback completion is separate and includes draining the device tail.

The native benchmark uses fictional English starter data and synthesized female
question speech, the authenticated ASR WebSocket client, exact native 2,048-token
Qwen fitting/source validation, real durable SQLite/filesystem result commits and
Piper speaker output. ASR and desktop journal recording are enabled. Remote
uploads are mocked unavailable. It bypasses PMS admission and the GUI/microphone,
so these runs qualify combined components, not a complete deployed session.

## First native combined run

`performance-large18-rerun-20261006`: Large-v3 CUDA, Qwen3.5-4B with 18 actual GPU
layers, six LLM CPU threads, four ASR threads, one 25-question round. Real-time
synthetic input and actual Realtek speaker playback. All 25 completed without
protocol errors. Manual review found all transcripts semantically correct and
answers consistent with the fictional fixture; extra frozen qualifiers remain.

24 warm samples: estimated first-audio median **5,725.38 ms**, p95 **9,217.88 ms**,
maximum **9,874.88 ms**; 15 exceeded 5 s. The latency gate **failed**.

| Stage | Median ms | p95 ms |
| --- | ---: | ---: |
| ASR after endpoint | 1,789 | 2,547 |
| Native fitting/preparation | 15.5 | 31 |
| Model completion | 2,320.5 | 5,953 |
| Durable save | 16 | 31 |
| First synthesized PCM after answer | 148.5 | 453 |

Reported output latency was 92.88 ms; no output underruns. Synthetic 800 ms quiet
was paced with per-frame sleeps in this initial run; Windows timer rounding made
it roughly 1 s. The runner now uses absolute deadlines to avoid accumulating
that error. Results above retain their actual measurements, without adjustment.

An earlier harness attempt supplied empty callback environment variables; the
ASR correctly rejected the configured callback. The runner now omits those
variables. Neither this failed attempt nor startup counts as a completed run.

Stereo Mix is listed locally but opening it failed with PortAudio invalid-device.
No digital loopback or acoustic onset is claimed. An explicitly requested
loopback check fails visibly rather than silently presenting estimates as sound.

## Implementation and regression evidence

- Actual ASR runtime device controls GPU reservation; CPU-only engines retain
  independent LLM CUDA eligibility.
- Current authenticated profile checks stay per question; redundant successful
  readiness probes expire after 15 seconds. Conversation checks before local
  inference and accepted ASR stream validation are preserved.
- Context/results retain FIFO order in a bounded priority queue. Eight urgent
  commands yield to one media command; media/lifecycle order is preserved. Queue
  slots and bytes are reserved for result/context admission.
- Synthesis may run during saving, but the playback gate opens only on a successful
  required durable commit. Failed, timed-out and cancelled saves never release it.
- Bounded synthesis queue, bounded PCM cache, resident output reuse, cancellation
  and low-latency fallback are covered by regressions.

Initial focused desktop checks: **102 passed / 4 opt-in voice skips**. Added timing,
priority, durable gate, cancellation/cache/fallback/warmup checks: **11 passed**.
Launcher/performance checks: **56 passed**. Initial desktop Ruff and mypy passed.
Final suite/review evidence will be recorded after native qualification.

## Shared small-model comparison

`performance-small99-playback-20261006`: installed small Whisper CUDA and Qwen
with all 33 layers offloaded, two rounds of the same 25 questions. All **50**
completed; manual review found no semantic transcription failures or unsupported
answers. Punctuation and spoken numbers were normalized by ASR without changing
meaning. One generation per answer, no prompt changes or additional repair calls.

48 warm samples: estimated first-audio median **3,577.38 ms**, p95 **5,404.88 ms**,
maximum **6,639.88 ms**; five exceeded 5 s. The strict gate **still failed**.
ASR median/p95 414/1,468 ms; model 1,343.5/3,547 ms; durable save 16/31 ms;
first PCM 148.5/547 ms. No output underruns. This comparison also precedes the
absolute-deadline pacing fix. GPU memory observed while resident was 3,213 MiB
of 4,094 MiB; it is one hardware observation, not a universal memory guarantee.

Launcher allocation now preserves configured LLM layers for this specific
small-Whisper/Qwen3.5 combination at a 2,048-token context on GPUs reporting at least 4,094 MiB. Unknown
memory, smaller GPUs, other model combinations and Large-v3 retain conservative
allocation. The actual selected LLM, rather than a stale default model name,
controls this decision. Native startup still checks its configured device/memory.
No saved ASR, model, device selection or platform profile was changed.

These combined runs recorded synthetic learner audio in ASR and durable turn
results in the desktop journal. The final runner additionally journals played
patient PCM. Neither comparison includes a real microphone, GUI scheduling,
current PMS access-check roundtrips or camera load.

## Review 1: confirmed findings and fixes

1. Result-save success was ignored by the previous playback path. The required
   save now gates audio; synthesis can overlap without weakening persistence.
2. Old timing events could replace current UI timings. Match random turn IDs,
   clear on a new turn, and discard stale events.
3. A failed first output write could appear as first audio. Publish its start
   timestamp only after successful output acceptance; interrupted completion is
   distinguished from successful playback.
4. Main-thread close could dispose native resources still used by a slow worker.
   The speech worker owns cleanup after cancellation; shutdown does not race it.
5. First synthesis remained cold after voice loading. Warm a short unsaved,
   unplayed utterance and invalidate warm state on resident voice eviction.
6. The old non-device readiness cache skipped profile access refresh. Current
   profile access remains checked; only successful technical probes are cached.
7. CPU-only ASR retained hardware CUDA reservation and an unnecessary probe.
   It skips that probe; LLM runtime eligibility stays independent.

Full initial regressions exposed a missing newly used timing import and an old
test expecting cached profile access. The import was fixed; that regression now
asserts current profile checks with cached technical readiness. The complete
suite is rerun after these corrections rather than reporting the failed run as
passing. Focused post-fix performance/journal checks: **37 passed**.

## Review 2: confirmed findings and fixes

1. A gated/preparing answer muted capture before any audio existed. Keep pending
   speech busy for session completion, but mute the microphone only when actual
   output starts. New tests cover waiting for the durable gate and microphone use.
2. Starting a low-latency stream could fail after opening it. Close it, retry
   conservative latency once, and retain a successful high-latency stream.
3. An underrun must affect the next output stream. Count it and close the low-
   latency stream after its tail; next playback uses the conservative setting.
4. Windows coarse monotonic intervals hid short saves. New stage/output timings
   use the high-resolution monotonic performance counter consistently. ASR's
   finalization duration uses the same high-resolution clock for both endpoints.
5. Synthetic pacing accumulated timer rounding; use absolute deadlines. Failed
   loopback preparation also now passes through journal/voice cleanup.

No direct model sentence streaming is introduced: patient IDs require complete
validation, and a spoken answer requires a completed durable result. Zero-call
measurement/unknown shortcuts are deferred: current platform conversation usage
contracts require one reported generation. Changing that accounting deserves a
separate compatible quota/audit change rather than misreporting calls for speed.

The 800 ms microphone default remains unchanged. A synthetic quiet interval does
not establish safe endpointing for natural pauses, accents or real room noise.

## Final combined run and remaining qualification gates

`performance-final-small99-20261006`: small Whisper CUDA, Qwen3.5-4B with all
33 layers offloaded, one 25-question round, absolute-deadline input pacing,
high-resolution stage timings and durable patient-audio recording enabled.
All **25** completed without protocol errors, with exactly one generation each.
All fitted prompts plus 128 output and 128 safety tokens fit 2,048 tokens.

24 warm samples: estimated first-audio median **4,003.31 ms**, p95 **7,806.15 ms**,
maximum **8,459.38 ms**; eight exceeded 5 s. `--require-latency` exited unsuccessfully
because the speed gate failed. The earlier faster comparison is retained as
evidence, but is not substituted for this final reviewed run.

| Stage | Median ms | p95 ms |
| --- | ---: | ---: |
| ASR after endpoint | 543.31 | 656.30 |
| Native fitting/preparation | 16.54 | 40.20 |
| Model completion | 2,392.78 | 6,232.95 |
| Durable save | 12.81 | 24.09 |
| First synthesized PCM after answer | 183.07 | 501.63 |

Cold model startup was 11.74 s; voice preparation was 2.38 s, both separate from
warm response timings. The local journal contained 25 ready result records and
28 ready patient-audio segments; the session was sealed with `incomplete=0`.
All 28 WAV headers were valid mono 16-bit PCM with nonempty audio. Remote PMS
uploads were mocked unavailable, so this is local durability verification.

Manual review found one semantic recognition error: the synthetic question
"Why does it rain?" became "Why does it ring?" and received a clarification.
The other 24 final answers/transcripts matched the fixture, with no unsupported
patient claims found. Across the three completed runs, 100 answers completed;
one observed semantic transcription failure remains. Replaying the exact saved
clip reproduced the error with small Whisper; installed Large-v3 correctly
recognized rain. The isolated replay is accuracy evidence, not combined timing.
No saved recognizer/model/profile was changed.

During the final run the GPU reported a 25 W current power limit against a 35 W
default and an active software power-cap reason; temperature was 77-78 C.
Hardware/software thermal slowdown reasons were inactive. This is an observed
hardware constraint, not proof that it caused the latency tail; power settings
were not changed. Model inference remains the measured dominant delay.

Physical microphone/endpoint behavior, digital/acoustic onset, camera load and
the complete authenticated PMS/GUI session remain unqualified. Listed Stereo
Mix could not be opened. These estimates cannot certify a deployed five-second
experience. Further model/runtime and recognition qualification is required;
the implementation retains complete answer validation and save-before-playback.

## Final review fixes and verification

- UI delivery failure before saving could discard a generated result. Persist
  the result even if `prepare_speech` delivery fails, withhold playback and then
  report the delivery failure. A regression covers this case.
- Bulk frames could consume capacity needed to close recordings. Reserve eight
  slots and 128 KiB from audio/video frames for result and closure commands;
  closure/media FIFO order and the single writer remain intact.
- The allocation exception also checks the 2,048-token context size; larger
  contexts retain conservative GPU reservation. Startup regressions exercise
  the actual selected model and CPU-only ASR path.
- A recording-close test observed queue dispatch before transaction publication.
  It now waits for committed lifecycle state. The isolated test passed; the
  complete rerun also passed. This changes the asynchronous assertion, not the
  journal durability contract.
- A benchmark cannot pass its speed gate by omitting failed/missing samples;
  require every expected warm sample and zero protocol errors.
- A failed device drain could report completed playback and leave a broken
  stream resident. Completion now requires successful draining; failed or
  cancelled output is interrupted and its stream is closed. A regression covers
  failed draining and verifies that the following answer creates a fresh stream.
  This completion-only fix followed the native run; first-output timing and
  latency conclusions are unchanged.
- The final rerun exposed a preexisting camera-test minute-boundary assumption
  (`21:29:59` test start, `21:30:00` recording start). Validate the folder against
  the recording's own start timestamp and bound it by the test interval. Camera
  runtime code is unchanged; the corrected assertion also covers day boundaries.
- Another rerun exposed a synthesis-test startup timeout alongside Tk variable
  destructor warnings on background threads. Collect unreachable GUI test
  objects on the main thread before starting fake synthesis workers; preserve
  the synchronization assertions and the application's runtime behavior.

Final full desktop suite after all corrections: **562 passed / 6 skipped**
(131.28 s), with no warnings in that run. Final journal suite: **20 passed**.
Launcher/scripts:
**189 passed**. Opt-in native Piper checks: **4 passed** (English/Hindi, both voice
genders). Desktop Ruff, formatting (108 files) and mypy (30 source files) passed.
The six normal-suite skips are two opt-in resident-Qwen and four installed-voice
checks. The native combined runs and separate opt-in voice run are reported
independently; physical microphone/acoustic verification remains open.

Unchanged API compatibility checks: **546 passed / 388 skipped**, with no
disposable PostgreSQL DSN configured. Database tests were skipped explicitly;
no application database was used. API Ruff, formatting and prescribed mypy passed.
No cloud calls, hosted deployment or Raspberry Pi verification was performed.
