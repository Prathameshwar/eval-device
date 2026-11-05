# Human-test implementation and review

Current camera addition (2026-09-20): explicit laptop preview/recording, private year/month/day/time folders, low-priority worker and bounded recording/preview rates. See [camera review and measured overhead](../docs/desktop-video-review.md). Earlier camera-deferred statements below describe their original delivery; Pi-to-desktop transport and physical hardware acceptance remain deferred.

Date: 2026-09-19. Both review passes were performed by the same agent. This implementation connects the existing audio service to a reusable PMS LLM client and the resident local Qwen server. The test desktop and launchers are in `human-test/`.

## Planned versus implemented

| Phase | Delivered |
| --- | --- |
| 1. Storage/security | Forward migration 0009; encrypted tenant LLM connections, scoped requests, atomic audit, idempotency, UTC quotas, per-endpoint capacity, leases, expiry, runtime grants and readiness |
| 2. LLM client | Pooled async llama.cpp adapter; JSON/SSE, Hindi UTF-8 parsing, deadlines, bounded messages/output, provider error normalization, cancellation and no uncertain POST retry |
| 3. PMS API | Connection create/update/list/status; completions and request status; role/tenant/department/lifecycle enforcement and live rechecks |
| 4. Screen | Tkinter microphone/language controls, transcript and streamed/final answer panes, finalized multi-chunk turn assembly, memory-only history, pause/send/cancel/reset/status/exit |
| 5. Launch/measurement | Locked dependencies and batches; isolated local demo with PostgreSQL/PMS/CPU ASR/GPU Qwen/retention worker; authenticated Qwen reuse, process ownership, native audio fixtures, actual microphone capture and batch verification |
| 6. Review/fixes | Security, persistence, concurrency, streaming, UI, Windows permissions and deployment compatibility review; confirmed fixes and regressions |
| 7. Final review | Corrected source, native cancellation/UI behavior, package privacy, full platform and compatibility checks, runbooks and remaining limits |

Practical adjustments: the first adapter has a fixed llama.cpp implementation instead of a general provider registry. The optional demo uses its own signed fixture identity, verified by the existing PMS authentication flow, and a separate database; it is clearly identified as a demo. It does not manufacture a production identity or alter the application database. The normal launcher uses operator-configured authenticated services. Demo audio/PMS ports must be free; only a matching Qwen server is reused automatically. No inference or cloud fallback is hidden from the operator.

## Review 1: findings and fixes

- Provider async-generator deadlines were initially crossed through per-chunk tasks. One producer now owns the full provider iterator, with a bounded queue to the API response.
- A user's newly narrowed department could have widened access to a historical organization-wide request. Reads and live checks now preserve the recorded scope; a PostgreSQL-backed regression verifies denial and newly scoped requests.
- Windows sandbox-owned private state could block the interactive launcher. Private files were restored to the actual launching account/SYSTEM, and native/batch tests ran under that account. No private directory was made public.
- UI cancellation initially exposed completion before coroutine cleanup. Actual asyncio task completion now controls admission of the next turn; reset/exit wait for cleanup.
- ASR completion now checks session and final chunk count. Missing completion, mismatched/conflicting chunks, overflow and silence cannot submit a question.
- Expired running requests have a background recovery path even when the caller never returns. Expired terminal results are removed by the restricted retention worker.
- Launcher cleanup tracks ownership, protects against unlocking an unowned lock, stops API/ASR before PostgreSQL, and uses Windows job objects for descendants.
- The existing deployment verifier and schema/grant expectation checks were updated for the additive migration. The database adoption test preserves pre-existing data and verifies all 325 mapped fields.

## Review 2: native findings and final corrections

A real HTTP disconnect exposed a streaming cleanup issue that mocked HTTP tests did not show: middleware can hide transport send failures, and AnyIO cancellation repeats at await points. The LLM response now explicitly observes disconnects, closes suspended generators and shields bounded cleanup. A regression exercises ASGI 2.4 disconnect behavior. In the final desktop native check, cancellation reached a durable cancelled state in 157 ms and the next inference succeeded.

Hindi answer completion initially triggered a full text-widget rewrite, causing a roughly five-second UI pause. Consecutive deltas are now grouped and an unchanged final answer is not rewritten. The repeated native GUI check observed a 141 ms maximum timer gap; there were no gaps above 200 ms. The answer stayed visible through a following silent turn, Reset cleared it, and Exit stopped the background event loop.

Final filesystem inspection found that the disposable test database inherited broad workspace permissions. After stopping it, its directory and inherited WAL/file permissions were restricted to the launching Windows account and SYSTEM; an actual WAL-file ACL was checked. Demo keys and model keys already had those private permissions.

Existing frozen baseline/earlier migrations, audio/video model selection and transport, training behavior and standalone local-llm launchers were preserved. No confirmed unresolved authorization, integrity or replay finding remains from these reviews. This is bounded pilot validation, not a clinical or production-scale certification.

## Verification

Raw evidence is under `.test_artifacts/human-test/`: `backend-native-tests.txt`, `backend-native-metrics.json`, `review-regressions.txt`, `end-to-end.json`, `direct-versus-pms.json`, `gui-native.json`, `resources.json`, `batch-smoke.json`, `package-check.json` and `checks.json`.

The PostgreSQL integration tests use only a dedicated disposable cluster on port 55443 with random per-test databases/roles. The optional runnable demo uses its separate cluster on 55444. Neither is the application database. Cloud calls are mocked or absent.

## Final suite and timing results

**436 tests passed:** PMS 141 (including real Qwen), human-test 12, audio 152, video 85, training 21 and local-llm 25. The final PMS run had **zero skips**, including all disposable PostgreSQL integration checks. Required Ruff/check/format/mypy passed. Human-test and PMS packages built and exclude private state; the PMS wheel includes migration 0009. Setup and actual demo batch from a different working directory passed. Existing dependency deprecation warnings remain.

Final real-fixture matrix, milliseconds (Whisper small CPU, Qwen3 4B Q4_K_M GPU):

| Audio | Response | ASR after audio ends | Model first token | PMS request to final answer | Finish |
| --- | --- | ---: | ---: | ---: | --- |
| en | JSON | 1625 | N/A | 1969 | stop |
| en | SSE | 1750 | 297 | 2000 | stop |
| hi | JSON | 3078 | N/A | 4187 | stop |
| hi | SSE | 3219 | 375 | 6531 | length |
| en (multi-chunk) | SSE | 2203 | 359 | 734 | stop |

The multi-chunk case produced 4 finalized transcript events and exactly one answer; a following silent capture produced no PMS request. The WAV tests are paced like input audio but do not include a user's additional silence-detection wait. The screen's default end-of-question silence is 800 ms. Model-first-token timing starts at the provider call, not at microphone start; JSON has no first-token measurement.

Three identical short arithmetic comparisons had median direct-model latency **110 ms** and median PMS latency **172 ms**. The median difference between each PMS round trip and its own provider duration was **77 ms**. These are a few warmed local samples; prompt caching, ordering and background load affect the comparison. Native JSON disconnect also released capacity: `failed` / `client_disconnected` in **1016 ms** (no resubmission).

Final demo readiness took **25.2 seconds** including service startup and database checks, separate from warm-turn latency. Models remained resident across the matrix. Sampled device-wide GPU memory peaked at **2,769 MiB**; the sum of Python/llama process working sets peaked at **3.64 GiB** (shared pages can be counted twice; excludes PostgreSQL/OS overhead). Peak sampled CPU across those processes was approximately **3.8 logical-core equivalents**. Sampling is coarse and includes test tooling, so these are observations, not capacity guarantees. Native full-suite model diagnostics confirmed 37/37 layers on GPU and one model load.

The final GUI check separately verified Hindi display, answer preservation after silence, reset, background-loop shutdown and 141 ms maximum UI timer gap. Microphone capture was real but the chosen spoken-question/answer acceptance check still belongs to the user. All owned demo/test services were stopped after verification; the batch restarts them when needed.

## Acceptance limits

- Real English/Hindi WAV fixtures passed through ASR -> PMS -> Qwen. The Hindi fixture demonstrated ASR spelling errors and occasional weak generation; one initial 192-token answer was truncated and correctly labelled. This is pipeline evidence, not an accuracy benchmark or a clinically grounded patient response.
- The real laptop microphone opened at mono 16 kHz PCM16 and captured half a second, discarded without saving. Native GUI tests injected WAV fixtures. A human speaking a chosen question and judging the answer remains a separate user acceptance check.
- Question detection uses an adjustable energy/silence threshold and the existing ASR VAD. It is not a turn-taking or interruption model. Quiet voices/noisy rooms need threshold selection.
- Hardware unplugging was not physically tested; buffer overflow, invalid format and interrupted transport have controlled paths/tests. Native streaming cancellation was tested; every possible USB-driver failure was not.
- Default Qwen output is 192 tokens and context is bounded. Hindi can consume more tokens; an authorized operator can increase output to 512 at the cost of latency. Patient persona/context, clinical rules, TTS, camera, Pi/Wi-Fi and live cloud integration remain future work.
- The independent normal-service launcher requires a real current PMS token and configured connection. The demo's local signing identity is intentionally confined to its own issuer/database and is not a deployment authentication strategy.


## Provider/token follow-up (2026-09-19)

PMS now supports local Qwen, OpenAI and configured OpenAI-compatible Chat Completions endpoints in JSON/SSE mode. The desktop remains a PMS client and receives no provider secret. Its read timeout honors the configured overall deadline; empty final answers cannot enter history. The demo remains local, while existing-service mode selects the configured connection ID. Follow-up verification: 207 PMS tests (zero skips, including native Qwen and disposable PostgreSQL), 14 desktop tests, static checks and package builds passed. Cloud calls were mocked. Both reviews/fixes are in the [review log](../docs/pms-api-reviews.md); setup is in the [provider guide](../platform/api/deploy/llm-providers.md). Test services were stopped.

## Speaker output (2026-09-19)

Local, offline, CPU-only speech for the patient's answer, with a **Speaker out** checkbox that defaults to checked. Text still appears exactly as before; audio is additive.

**Engine choice.** Piper (`piper-tts` 1.8.0, ONNX) was selected after checking what the repository already had:

| Candidate | Outcome |
|---|---|
| PMS `audio.synthesize` (Polly / Azure Speech) | Fully implemented, but it is the asynchronous worker + media-download path and needs cloud credentials. Wrong latency shape for an interactive turn. |
| `espeak_ng` | Appears once, in the PMS engine catalogue (`configuration.py`), with no implementation. eSpeak NG is not installed on this laptop and is formant synthesis: intelligible but robotic. |
| Windows SAPI | Only `Microsoft David/Zira Desktop`, both `en-US`, are installed. No Hindi voice, so it cannot meet the bilingual requirement. |
| Piper (selected) | Installs cleanly on Windows/Python 3.12, bundles espeak-ng phonemization for `en-us` **and** `hi`, 16 kHz output matching the capture rate, one chunk per sentence for pipelined playback. |

**Measured on this laptop (CPU):** voice load 4.51 s cold and 2.12 s warm, so the voice is loaded when the setup is saved rather than at the first answer. Synthesis real-time factor **0.102** (5.68 s of audio in 0.58 s). **First sentence ready in 0.16 s**, which is when the patient starts speaking. A 4.2 s answer completed playback 5.52 s after the request, including device start and tail. `stop()` took under 10 ms mid-answer.

**Echo fix.** `turn_complete` previously reopened the microphone after 400 ms, while the answer expression was still running. With audio that would have let Whisper transcribe the patient's own voice as the next question. The microphone now waits for playback to finish, bounded by 30 seconds so playback cannot strand input. A regression test asserts capture does not reopen while speech is playing.

**Checks (2026-09-20 update):** **124 desktop tests passed with zero skips** using `HUMAN_TEST_SPEECH=1` against the installed voices; 120 passed with 4 skipped when the opt-in voice checks are off. Desktop Ruff check and format passed, and mypy passes for `src/human_test` (13 files) after adopting the `ignore_missing_imports` setting already used by `device/audio-process` — previously `capture.py` failed that check. Playback, decline-without-a-voice, stop and preview paths were exercised against the real Realtek output device; all other tests use a fake engine and need neither model nor device. Real-window coverage of the checkbox and voice picker runs as a subprocess (`tests/speaker_smoke.py`) so the pytest process keeps a single Tcl interpreter.

An earlier note in this file claimed 43 tests over eight consecutive runs; that count predated the voice-catalogue and picker work and is superseded by the figures above.

A first version of the window tests created a second `tk.Tk()` root and made the suite fail intermittently with `TclError: Can't find a usable tk.tcl` — Tcl cannot reliably initialize another interpreter in the same process on this platform. Measured: six consecutive clean runs without those tests, against four failures in six runs with them. The speaker window behaviour is therefore verified by calling the real `Window.drain`, `Window.resume_after_speech` and `Window.apply_speaker_output` against a minimal stand-in object, so `tests/test_patient_workflow.py` keeps the single real root.

**Limitations.** Hindi speech is **not delivered**: only an English voice is pinned because Hugging Face is unreachable from this environment (HTTP 403 on every path), and Piper's GitHub release assets contain no Hindi voice. A Hindi answer is displayed as text with a status note. Add a pinned `hi` entry to `voices.lock.json` and rerun the installer where Hugging Face is reachable. Audio quality was **not** assessed — integrity and latency were verified, but voice suitability needs a listening check, as with the earlier Whisper Hindi evaluation. No Pi speaker, no cloud synthesis and no PMS `audio.synthesize` call is involved.

## Larger manikin layout (2026-09-19)

The patient stage now takes approximately two-thirds of the conversation width.
Microphone controls, question, typed input and response share the right panel.
At the default 1180×860 window, the canvas increased from 437×438 to 720×537
pixels; the rendered figure is approximately 30% taller. The existing window
dimensions, setup workflow, callbacks and manikin animation code are preserved.

| Review | Evidence |
|---|---|
| Layout and reachability | Fixture previews at 1080×800, 1180×860 and 1440×941; all 13 existing inputs/buttons/text widgets remain visible. Feet, status and observations fit. |
| First review and fixes | Long case titles wrap; explicit vertical scrollbars make longer transcripts and replies accessible in the compact panel. |
| Final review | Hindi text and long response scrolling checked; source comparison limits runtime edits to window style and conversation layout construction. |
| Regression checks | Full desktop suite: 67 passed, zero skips, with `HUMAN_TEST_SPEECH=1`; Ruff lint and formatting passed. |

[Current preview](../docs/images/human-test-manikin-focus.png). Local visual
fixtures and measurements are in `.test_artifacts/manikin-focus/`. These checks
do not claim new live cloud, microphone, Raspberry Pi or database verification.

### Setup input readability (2026-09-19)

Step-one inputs, dropdown selections, popup lists and field labels now use
11-point Segoe UI. Smaller vertical gaps keep the default setup within its
existing height. Visual checks at 1180×860 and 1080×800 confirmed horizontal fit
and access to Save & continue through the existing scrollbar. Popup font checks
covered all three setup dropdowns. Only `build_setup` changed; conversation and
event handlers were preserved. All 67 desktop tests passed, with Ruff lint,
formatting and mypy checks also passing. Preview evidence is in
`.test_artifacts/setup-fonts/`.

## Patient voice selection (2026-09-19)

Output voice now follows `document.patient.sex` from the saved PMS selection:
male uses the installed Alan English voice, female retains Lessac, and unknown
values default to male. Missing female files fall back to male within the same
language. Voices warm on the background worker and share a cache capped at two
instances. Hindi was text-only in that review; the installation below resolves it.

## Hindi speaker installation (2026-09-19)

Installed Rohan (male) and Priyamvada (female) through pinned official Sherpa-ONNX
Piper archives, resolving the earlier Hugging Face download limitation. Existing
language/gender selection and cache behavior required no runtime changes. All
120 desktop tests passed with native English/Hindi synthesis enabled; lint,
format, types, offline build and installed-file verification passed. A short
Hindi sentence completed through the real laptop output stream. See the
[audit, timings, samples and voice-specific terms](../docs/hindi-voice-review.md).

Two reviews covered setup propagation, fallback, resident voice reuse, playback
interruption and silent answer recovery. An installer file-handle leak on failed
downloads was fixed, with five-attempt cleanup regression coverage. Full desktop
suite: **114 passed, zero skips**, including native synthesis of both voices.
Ruff lint/format, mypy, package build and installed-voice verification passed.
No live speaker audition, cloud call, Pi test or database test was performed for
this desktop-only change. Details and measured samples are in the
[patient voice audit](../docs/patient-voice-review.md).

## Natural-voice upgrade and voice picker (2026-09-20)

Reported symptom: English speech sounded mechanical while Hindi did not. Cause: the English male voice was `en-gb-alan-low` — Piper's **`low`** tier at **16 kHz** — while the Hindi voices were already `medium` at 22 kHz. This was a voice-catalogue problem, not a code defect.

Quality tiers measured on this CPU with the same sentence (median of three, through the thread-capped `voice_runtime` session):

| Voice | Rate | Real-time factor | First sentence |
| --- | --- | ---: | ---: |
| `en-gb-alan-low` (previous) | 16 kHz | 0.198 | 0.38 s |
| `en_US-ryan-medium` | 22 kHz | 0.241 | 0.55 s |
| `en_US-ryan-high` | 22 kHz | **1.580** | 2.89 s |

`high` synthesizes **slower than real time**, so streamed playback would starve and stutter; `medium` costs almost nothing over `low`. Medium is therefore the deliberate ceiling. After the catalogue change, all six installed voices measured **RTF 0.082–0.122** with first-sentence latency **0.19–0.38 s**.

Installed catalogue: English defaults **Ryan** (male) and **Lessac** (female); English alternatives **Alan** (British male) and **Jenny** (British female); Hindi defaults **Rohan** (male) and **Priyamvada** (female). All are 22 kHz medium tier, pinned by archive size and SHA-256 plus per-member size and SHA-256, and sourced from the reachable Sherpa-ONNX distribution. Optional per-voice prosody (`length_scale` 1.05, `noise_w_scale` 0.9) is applied through Piper's `SynthesisConfig`.

Selection order is explicit choice, then the voice marked `default` for the patient's sex, then any installed same-language voice, then the male fallback. **A preference never changes the language of an answer** — choosing an English voice cannot make a Hindi answer speak English. The window offers the list plus a **Hear** button that speaks one fixed sample, refused while the microphone is open.

Also fixed in this pass, from the previous review: the microphone gate now waits on audio actually reaching the device instead of a 30-second timeout — speech measured at 12.8–15.8 characters per second, so answers beyond about 480 characters were previously cut into while still playing; the voice installer now holds an `msvcrt` byte-range lock that Windows releases if the installer is killed, replacing an `O_EXCL` file that had to be deleted by hand; and a failed size or SHA-256 check now stops with a clear message instead of a raw `ValueError` traceback.

**Not verified:** audio quality itself. Integrity, latency, tier and sample rate were measured; how natural each voice sounds is a listening judgement, which is why the picker and **Hear** exist.

## Seated patient drawing (2026-09-20)

The conversation manikin now sits upright on a chair, with bent knees, feet on
the floor and hands on the thighs. The existing Tk canvas draws the backrest,
seat, chair legs and patient in depth order. Animation timing and application
callbacks are unchanged; no assets or dependencies are loaded at runtime.

Native Tk previews passed containment checks and visual inspection at 1080x800,
1180x860 and 1440x900. Ready, open-mouth and blinking frames were inspected.
The existing patient-workflow suite passed **3 tests**, including animation
completion, cancellation and repeated setup/conversation navigation. Ruff lint,
format and mypy passed for `src/human_test/manikin.py`.

The preview used fictional text and isolated initialization, with microphone,
speaker and camera off. No cloud, hardware or database tests were run for this
drawing-only change. [Conversation preview](../docs/images/human-test-seated-patient.png).
Local capture script and additional frames: `.test_artifacts/seated-manikin/`.

## OPD room background (2026-09-20)

The seated patient now faces the viewer against a light two-tone wall, skirting
and floor, with a framed OPD sign and a small decorative clock. A shared scale
and origin keep the room, chair and patient aligned on resize. The floor seams
recede toward the wall and a contact shadow grounds the chair and feet. The
two wall details stay clear of the patient. The clock is a static illustration.

Native previews passed containment checks and visual inspection at 1080x800,
1180x860 and 1440x900, including ready, speaking and blinking frames. All **3
patient-workflow tests** passed again, with Ruff lint/format and mypy passing for
the changed drawing module. Animation timing and conversation behavior remain
unchanged. No dependencies were added.

Verification used fictional text and isolated initialization with microphone,
speaker and camera off; no cloud, hardware or database tests were run.
[OPD room preview](../docs/images/human-test-opd-room.png).
Additional captures: `.test_artifacts/seated-manikin/opd-room/`.

Follow-up: a compact split AC now replaces the clock high on the right wall.
The OPD sign is smaller with softer contrast. The patient retains the same size
and central position, with just two background details outside the silhouette.
Native containment and visual checks passed again at all three sizes, including
the blink frame. All 3 patient-workflow tests and the drawing module's Ruff
lint/format and mypy checks passed. This remains an isolated visual check;
no live services or devices were exercised.
[Updated preview](../docs/images/human-test-opd-ac.png); local captures are in
`.test_artifacts/seated-manikin/opd-ac/`.

## Human appearance and clothing (2026-09-20)

The seated figure is now a clothed human illustration. A shaped jaw, ears, hair,
eyebrows, eyes and nose replace the round manikin face. Continuous arm and leg
contours, relaxed hands, fabric folds and shoes replace the exposed joint circles
and molded body segments. The T-shirt is light sky blue with short sleeves; the
trousers are light gray. The chest light and waveform are removed, while the
existing status label remains below the patient. The OPD room, chair alignment
and scene scale are preserved.

Native containment checks and visual inspection passed at 1080x800, 1180x860 and
1440x900. Ready, speaking and blinking frames were inspected. The mouth and eyes
use the existing animation lifecycle with redrawn facial features. All **3
patient-workflow tests** passed, including animation completion, cancellation
and repeated navigation. Ruff lint, format and mypy passed for the drawing module.

The preview used fictional text and isolated initialization with microphone,
speaker and camera off. No live cloud, hardware or database tests were run.
[Clothed patient preview](../docs/images/human-test-clothed-patient.png).
Local captures: `.test_artifacts/seated-manikin/human-patient/`.

Hand refinement: both hands now have four separately drawn rounded fingers of
different lengths, an inward-facing thumb, a shaped palm and a tapered wrist.
The fingers have visible gaps and subtle creases, with their roots blended into
the palm. Mirrored placement keeps both hands resting on their respective thighs.
Native containment checks and visual inspection passed at all three window sizes,
including the blink frame. All 3 patient-workflow tests, drawing-module Ruff
lint/format and mypy passed again. No live devices or services were used.
[Updated hands](../docs/images/human-test-patient-hands.png); local captures:
`.test_artifacts/seated-manikin/human-hands/`.

## Occasional speech gestures (2026-09-20)

Spoken patient replies now have a small randomized chance of one wrist movement
or one index-finger flex. The following spoken reply always stays still. Actual
speaker progress gates motion; synthesis waits, silent replies and voice samples
cannot start it. Audio completion/stalls and conversation stop paths restore rest.
The mouth and blink sequence, 120 ms animation timer and 111 canvas items remain
unchanged; there are no additional threads, audio operations or model calls.

Full desktop suite: **197 passed, 6 skipped** (the existing opt-in voice/model
checks). Ruff lint/format and mypy passed. Deterministic playback tests cover
frequency, cooldown, cancellation and stalls; a native Tk subprocess verifies
both sides, finger-only isolation, unchanged face geometry and timer cleanup.
These checks use simulated playback; no new live audio, cloud, database or Pi
verification is claimed. [Review and performance evidence](../docs/patient-gesture-review.md).

## Tenant clinical catalog compatibility (2026-10-01)

The desktop now shows the active tenant clinical specialty, patient profile and case
choices returned by PMS. It filters cases by both parents, shows the current profile
identity in the preview, and explains when the tenant has no active case. Historical
global selections are identified and cannot be used to start another interview;
staff choose and save a tenant case. Changed or inactive saved cases also require a
current choice. Patient setup requires explicitly assigned organization-wide
clinical author and processing permissions.

Review found the old global catalog/administrator wording, missing profile choice,
stale identity preview after profile edits, and duplicate profile names dropping a
choice from the desktop list. Duplicate names now include the unique profile code.
Focused regression coverage checks
profile filtering and save identifiers, restored/changed/legacy selections, empty
catalogs and rejection before conversation submission. The full desktop suite passed
with 473 tests and 6 opt-in checks skipped. The focused workflow passed after the
final preview correction; Ruff check/format and mypy passed. The target VM and live
tenant-authored case remain to be verified by the operator.

### End-to-end follow-up (2026-10-01)

A published tenant case can use Hindi as its source language, omit optional onset
text and leave initial observations for staff to enter. The setup preview now uses
available case text and leaves missing observations blank for entry, instead of
failing while the case loads. A clinical profile can also change its supported
languages after a case is activated. PMS now returns a structured
`patient_language_unavailable` error without changing the selection or writing a
save audit when the chosen language is incomplete.

The local Human-test suite passed with 473 tests and 6 optional voice/model checks
skipped. The real desktop client to FastAPI to disposable PostgreSQL journey and
related tenant catalog/practice tests passed 34 checks. API and desktop Ruff and
mypy checks passed. The target Ubuntu VM and live audio/cloud services were not
exercised by these checks.
