# Shared client runtime review

Scope: extract common client behavior, migrate and clean up Human-test, and leave
Raspberry Pi-specific implementation for the next phase. No deployment or
publication is authorized by this task.

## Baseline analysis

Human-test has GUI-owned listening, playback dispatch, assigned-session timers
and camera archive finalization. Moving only its existing non-Tk modules would
not provide a working headless client. The local-model transport intentionally
accepts loopback only; this phase must preserve that security boundary.

Synthetic baseline probes reproduced three defects: positional camera settings
populate archive fields instead of configured limits; playback can terminate an
unfinished question as a normal endpoint; an overloaded listener can accept the
tail of a rejected sentence. A separate probe reproduced process-global model
configuration changing the endpoint used by newly created playback objects.

The prior read-only review passed 38 focused Human-test and 27 inference-client
tests. These are baseline results, not verification of the extraction.

## Implementation

`shared/training-client` now owns configuration validation, pairing, platform
HTTP calls, assigned model routing, ASR/LLM orchestration, filtering, listening,
speech playback, timing, conversation history/outboxes and bounded session media
archives. Existing clinical contracts and the inference-only client remain
separate dependencies. Human-test imports the shared implementation; the former
core modules and dictionary were removed from its source tree.

The new `Runtime`, `SessionSupervisor` and `CameraRecording` replace behavior
previously driven by Tk event consumption/timers. They enforce operation ownership,
session expiry/contact-loss shutdown, cancellation and archive finalization without
a frontend. Tk retains controls, presentation and desktop configuration/path adapters.
Hardware dependencies are optional, imported only when used; hosts may inject audio,
speaker and recorder implementations. Each runtime owns its inference connection
and capability cache. Shared settings require an explicit application directory;
desktop `HUMAN_` settings, pairing location and `.local` data paths are retained.

The portable builder installs the package inside its private runtime before
protecting 11 desktop/shared modules. Packaged defaults and spawned recorder imports
are included. No weights, inference engines, manager credentials or private media
are bundled. The ordinary shared wheel remains portable Python.

## Review passes and corrections

Both reviews were performed by the same agent.

1. Extraction/dependency and behavior review: corrected positional camera options;
   rejected playback-interrupted utterances before ASR submission; retained overload
   rejection until silence; removed production reliance on global inference
   configuration. Checked explicit storage roots, lazy hardware imports, bounded
   queues, observer failures, immutable context and existing unknown-outcome handling.
2. Lifecycle/packaging review: prevented late session setup after cancellation;
   retained uncertain Begin ownership until the exact claim's Finish is acknowledged;
   serialized concurrent finishes; ensured camera-monitor failures terminate workers
   and mark archives incomplete. Runtime shutdown closes other resources even when
   camera finalization fails. Moved protection after shared dependency installation
   and updated portable scope/publication validation. A final follow-up moved the
   desktop's mutual exclusion of session setup and runtime operations into the
   core, including refusal while another runtime owns the assigned session.
   No publication was performed.

Regression tests cover these findings. Final review found no further confirmed
blocking issue in the extraction. API authorization, private media boundaries,
idempotency and inference manager loopback restrictions were preserved; no platform
production code, database schema or migrations changed.

## Verification - 2026-10-10

- Human-test: `python -m pytest tests scripts/tests ../shared/training-client/tests
  -q --tb=short -p no:cacheprovider` with an isolated artifact directory:
  **703 passed, 2 skipped** in 329.38 seconds. Skips are opt-in resident Qwen checks;
  this run did not call live inference services. The shared package contributes
  13 new headless lifecycle/ownership regressions in this broad run. Earlier fixture failures were
  corrected and the full suite rerun.
- After the final ownership guards, the shared tests plus session queue, patient
  workflow, continuous listening and desktop scenarios passed again: **75 passed**,
  including three additional ownership cases (**16 shared tests** total).
- Portable/publication and inference-client tests: **55 passed**; additional
  `start/tests/test_human_test_package_scope.py`: **28 passed**.
- API: `uv run pytest -q`, with `PMS_TEST_ADMIN_DSN` empty: **614 passed,
  406 skipped**, three existing warnings. Database integration was skipped because
  no disposable server was configured; no application database was used for tests.
  `uv run ruff check .`, `uv run ruff format --check .` and
  `uv run mypy src/pms_api` passed (240 formatted files, 87 source modules).
- Human-test/shared/inference-client Ruff lint and formatting passed (111 files).
  Combined mypy passed for **40 source modules**, using the existing configuration
  that does not check bodies of unannotated functions. The seven changed packaging
  Python files also passed lint/format; `git diff --check` passed.
- Native Tk synthetic checks passed for setup at three viewport sizes, sequential
  assigned trainees/Previous/desktop completion/web stop, and camera preview,
  playable synthetic recordings, Back and Close at three viewport sizes. The
  native retry smoke also passed with actual 1/2/3/4/5-second waits: retained
  questions, microphone/playback interlocks, exhaustion without replay, typed
  cancellation, countdown and between-round cancellation. Its fixture now waits
  for UI notification of runtime-owned playback rather than assuming Tk starts it.
- `uv build --offline --wheel` succeeded. An extracted wheel was verified with
  editable Human-test imports disabled and imports of Tk, Human-test, sounddevice,
  OpenCV and PyAV explicitly blocked: all shared modules imported; the packaged
  dictionary and explicit paths resolved; a runtime was constructed and closed
  without hardware or network access.
- `python start/build_human_test.py --no-zip` succeeded. Self-test verified all
  **11 protected native modules**, application bytecode, private runtime imports,
  bundled Tcl 8.6.15 and spawned recording-process startup. Local output:
  `start/dist/Human-test-windows-x64-runtime-protected-20261010-124459-883677/`
  (rebuilt and self-tested after the final ownership guards).
  This is a local verified folder, not a published ZIP/download.

Ignored test/build logs and the wheel smoke script are under
`.test_artifacts/shared-client-extraction/`. No secrets or actual patient media
are included in the tracked review evidence.

## Remaining scope and limits

The Pi daemon, boot integration, hardware selection/controls and Linux/ARM
verification are deferred as requested. The current inference client accepts only
loopback; a Pi-to-GPU authenticated endpoint and device-scoped authorization are
still required. Cloud TTS, live network media streaming/video inference, unattended
capture/upload scheduling and restart/session-resumption policy remain follow-ups.
Local model selection still requires platform-authorized conversations; extraction
does not add disconnected practice or replay uncertain inference.

No live cloud, GPU, microphone/speaker/camera quality, Pi hardware, hosted deployment
or publication was performed. Historical cloud/audio simulation imports were moved
to the package; those older drivers were not used as current workflow verification.
The executable tests above are synthetic and do not claim physical-device quality.

## Follow-up review requested by the user - 2026-10-10

Rechecked the extraction, shared lifecycle, desktop integration, inference/config
isolation, audio boundaries, camera shutdown and portable validation. This review
was performed by the same agent, with a second inspection after the fixes.

Confirmed findings corrected:

- A cancelled poll could raise `CancelledError` out of the session supervisor and
  silently disable lease/expiry handling. Poll ownership is now detached before
  cancellation, and cancellation of a child poll does not cancel supervision.
- Headless text requests relied on Tk to stop prior playback. Both standalone and
  queued typed questions now interrupt playback in the common runtime.
- Duration/loss rejection could immediately accept the remaining audio fragment as
  another question. All rejected utterances now wait for a complete silence interval
  before rearming. The earlier test explicitly allowed the duration-limit fragment;
  its expectation was corrected and recovery after silence remains verified.
- An already-open Models dialog could reload models after an assigned session began.
  Model reload and conversation reset now use shared guarded operations. Closing the
  dialog cancels its pending reload. Preparation, selection, reload and reset await
  camera completion and stop playback before changing the conversation/archive.
- A closed runtime could initialize a new supervisor, and its exposed camera could
  restart recording. Both operations now refuse startup on a closed/stopping host.
- A camera worker that ignored termination was repeatedly terminated without being
  killed. Timeout handling now uses the bounded terminate/join/kill cleanup path.
- A protected-package manifest could map all module names to one native file. Build
  and publication validation now require the exact native path for each module.
  Publication remains unperformed; validation tests use synthetic private archives.
- Native camera verification exposed a pending Tk timer after window destruction.
  Desktop shutdown now cancels its Tcl callbacks before destroying the root; the
  camera smoke asserts that none remain and its final rerun has no callback warnings.

Before fixes, regression runs reproduced four lifecycle failures, two audio-fragment
failures and two camera/package validation failures. After fixes, the targeted
desktop/shared/media/package run passed **96 tests**. Combined client mypy passed
for 40 modules; API lint/format/mypy passed (87 source modules), and the API suite
passed **614 tests, 406 skipped**, with the same three warnings and database
integration explicitly disabled. Packaging/inference-client checks passed **84
tests**. The rebuilt shared wheel passed the isolated headless import/lifecycle
check. The broad Human-test/scripts/shared suite passed **720 tests, 2 skipped**
in 279.71 seconds (the skips are opt-in resident Qwen checks). Native Models,
assigned-session handoff, camera and retry flows passed;
the camera check was rerun after the timer cleanup. Client lint/format and mypy
were rerun after that final UI fix and passed. Direct comparison also confirmed
the moved cloud audio, platform client, history/outbox, filtering, route and timing
modules retain their original logic; pairing only changed explicit path ownership,
and synchronization changed its subprocess module path and lifecycle comment.

The final protected build, including the Tk cleanup, passed all 11 native module
imports, bytecode/scope validation, bundled Tcl and recorder process startup:
`start/dist/Human-test-windows-x64-runtime-protected-20261010-130023-167738/`.
Packaging lint/format and final whitespace checks also passed. No further confirmed
blocking issue remained in the reviewed scope after fixes and verification; the
skipped/live checks below remain limitations, not claims of verification.

Follow-up evidence is in `.test_artifacts/shared-client-review/`; the reusable wheel
smoke script remains in `.test_artifacts/shared-client-extraction/`. Live cloud,
physical devices, Linux/ARM, remote GPU transport and database integration remain
outside this verification. No deployment or publication was performed.

## Subsequent live verification

The requested real local integration run is recorded separately in
[shared-client-live-review-20261010.md](shared-client-live-review-20261010.md).
Both published scenarios passed through the shared runtime with Qwen, Whisper and
Piper, including ten completed history records and complete audio archives. A
misleading desktop warning on idle microphone pause was fixed and covered by
regressions; both scenarios were then repeated successfully. Physical microphone
probing still reports digital silence. API implementation remained unchanged.
