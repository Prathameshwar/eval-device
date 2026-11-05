# Human-test, Pi-test and shared runtime end-to-end review

Scope: client startup/enrollment, assigned and standalone practice, text/audio/model
routing, output, camera processing/archives, cancellation/recovery, private state,
host boundaries and packaging. Application services stay stopped. Verification uses
isolated fixtures and a disposable PostgreSQL server; physical Pi/live cloud remain
unverified. Preserve all pre-existing workspace changes.

## Work list

- [x] Inspect both hosts and trace their shared runtime and API contracts.
- [x] Reproduce and fix processing submission status handling and session-stop races.
- [x] Review media URL/output identity and asynchronous lifecycle boundaries.
- [x] Exercise both hosts/shared code with regressions and database-backed journeys.
- [x] Re-review fixes, check packaging, record final evidence and stop test resources.

## Confirmed findings

1. The shared JSON client only accepted HTTP 200, but creating a video processing run
   returns 202. The existing video unit test mocked the JSON client itself, so it
   missed this integration failure. Add actual transport/API-boundary coverage.
2. Pi video jobs were cancelled after an assigned session's finish acknowledgement.
   Cloud processing could continue while that acknowledgement was unavailable.
   Cancel on the stopping event and reject new session work during the finish barrier.

3. Cloud synthesis used a separate authorization header but shared the platform
   client's cookie jar when following signed media addresses. It also accepted
   embedded URL credentials and a different loopback HTTP port. Centralized media
   validation and a separate storage client now enforce the same rules as video.
   Tests cover same-host and separate-host storage with an actual platform cookie.
4. Playback cached its PortAudio output using sample rate alone. Changing the
   selected speaker at the same rate could retain the old stream. The shared engine
   now reopens it on device change; the regression uses two fake devices.

## Second review and fixes

The second pass traced acknowledgement failures, output configuration, packaging
and actual HTTP/API status boundaries after the first fixes. Standalone Pi finish
had the same uncertain-acknowledgement problem as assigned finish: a later pause
could re-enable input while conversation closure was unknown. A persistent finish
barrier now survives pause and clears only after the idempotent close succeeds.
Both assigned and standalone failure/recovery cases have regression coverage.
The Pi playback adapter now also reapplies the configured voice preference when
GPU voice metadata arrives after startup or reconnection. A regression verifies
the preference becomes active after the catalogue is populated.

No platform API implementation change was needed in this review. The new API test
uses the actual shared HTTP client, processing routes, grants and isolated PostgreSQL;
only camera input and GPU inference are fixtures. It verifies a single accepted
submission, signed run-bound authorization, result persistence and completion.

The database run also exposed stale desktop integration fixtures: retired model
configuration routes, direct access to the old model worker, and a hard-coded v4
scenario expectation. The tests now use enrolled device assignments, the manager
inference API and the published document's schema version. Both hosts' scripted
model fixtures select the name fact explicitly instead of an arbitrary first fact.
Actual answers, saved history and rejected operations are still asserted.

## Verification

- Human-test/shared broad run: **638 passed, 2 opt-in local-model tests skipped**.
  The native Tk camera-view check initially failed to read its installed Tcl file
  under the sandbox. Its isolated rerun outside the sandbox passed (**1 passed**),
  using synthetic camera frames. No application services or real camera were used.
  The additional same-host storage-cookie case passed in the subsequent shared run.
- Final Pi/shared suite: **84 passed**. This includes transport/status handling,
  both finish barriers, capture normalization, camera failure, persistent request
  inspection, output-device changes, voice preference and cookie isolation.
- Local manager/inference-client and desktop packaging regressions:
  **90 passed, 2 subtests passed**.
- GPU gateway suite: **18 passed**, including real loopback TLS/WSS with fixture
  grants/model execution. This does not verify a real GPU over the intended LAN.
- API broad suite without a database DSN: **620 passed, 411 skipped**. The skipped
  database-dependent tests are not claimed as passed.
- Dedicated PostgreSQL at **127.0.0.1:55459**: **23 distinct selected tests passed
  across targeted runs**. Initial run: 19 passed, 2 failures and 2 setup errors;
  these four failures came from the stale desktop fixtures above. After updating
  them, desktop compatibility passed all 4 combinations; the final journey rerun
  passed both desktop cases plus Pi's two-scenario text/ASR journey (3 tests).
  Coverage includes actual shared-client video creation/result handling, concurrent
  grants, ownership/lifecycle, archive recovery and permissions, local/cloud route
  compatibility, scenario changes, saved history, revocation and shutdown.
  Each DB fixture creates/drops its own database and roles and runs migrations and
  runtime grants. No application database was used.
- Ruff lint/format passed for API (244 files), Human-test (59 files) and
  Pi/shared/inference-client (63 files). Mypy passed for API (88 source files),
  Human-test (13) and Pi/shared/inference-client (44), with its existing untyped
  function limits. Existing dependency deprecation warnings remain.
- Built **24 hash-locked CPython 3.13 ARM64 wheels**; offline hash-checked pip
  installation dry-run passed. All 69 Python sources across the four application
  wheels match the final checkout. No desktop/private configuration is bundled.
  This resolves dependencies; it does not execute ARM native binaries.
- Final whitespace review passed. The disposable PostgreSQL server was stopped.
  Process/listener inspection found no running API, Human-test, Pi-test or
  local-models application service on their configured ports. No commit or
  publication was performed.

Current Pi bundle: `.test_artifacts/client-e2e-review/wheelhouse-arm64/`, with
`release-requirements.txt`; resolution evidence:
`.test_artifacts/client-e2e-review/arm64-install-report.json`. Earlier Pi bundles
under `pi-framework` and `pi-completion` predate these fixes and are superseded.
The existing Human-test portable executable was not rebuilt; rebuild it before
distributing the updated shared client. Its packaging regressions passed.

## Remaining qualification

No confirmed finding remains unresolved in the reviewed client paths. Physical Pi
hardware, Linux/systemd execution, real GPU inference over LAN, live cloud models,
reboot/power-loss and thermal endurance remain unverified. Those checks require
the target environments; mocks and Windows checks are not substitutes. Both review
passes and the final inspection of the fixes are complete.

## Follow-up client and deployment fixes - 2026-10-11

A deeper pass found five remaining lifecycle and deployment gaps. Human-test could
discard committed setup and final-answer notifications when the Tk display queue
filled. The queue now drops replaceable status/stream updates first and reserves
bounded space for completion events. Shared session shutdown now waits longer for
the disk writer and reports an unfinished flush through the controller and desktop.
Pi installation restores the previous release, unit, active state and boot
enablement if switching fails. Installed qualification requires a ready, idle
service. On Linux, the CSI camera child receives a parent-death signal so an
abnormally killed recorder worker cannot leave the camera process running.

Final review also tightened installer checks for unexpected service-unit symlinks
and a non-symlink current release marker, and made the desktop warn if shutdown
itself exceeds its deadline. The broad Human-test rerun passed **585 tests with 2
skipped**. Shared passed **58**; Pi passed **35**. Targeted regressions for the final
queue and shutdown edits passed. Ruff lint/format and mypy passed in all three
packages; `bash -n` and `git diff --check` passed. A synthetic Tk preview test
failed once under the first broad run's load, passed alone, and passed in the final
broad rerun. Shared pytest emitted a cache-write warning, without a test failure.

No physical Pi, native systemd rollback, live camera, or hosted deployment was run
for this follow-up. The existing portable Human-test executable and Pi wheelhouse
were not rebuilt from these source changes.
