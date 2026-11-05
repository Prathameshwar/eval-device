# Pi framework review evidence

Implementation and qualification: 2026-10-10/11. Physical Raspberry Pi, paid cloud
calls and hosted deployment are not part of this evidence. Nothing was published.

## Implementation checks

Early tests caught private-directory creation on first boot and a shared camera
worker argument regression. Both were fixed. The affected Human-test camera and
shared runtime suite subsequently passed (53 tests).

The real Pi service, shared Controller/Runtime, device-authenticated API, signed
gateway and disposable PostgreSQL completed two published scenarios. Only the
GPU model response was substituted. Conversations closed on the platform and
credentials remained separated at each transport boundary. This is protocol and
lifecycle integration, not live GPU/physical microphone qualification.

## Review 1 — authorization, state ownership, shutdown and bounds

Reviewed the API grant policy, gateway trust/replay boundary, Pi command lifecycle,
shared transport, audio/camera adapters, cloud processing, journals and deployment.

Findings fixed:

- Added a service state-directory lock and finally-protected shutdown cleanup.
- Preserved the assigned-session finishing barrier while local pause cancels work.
- Bound tokenizer caches to the selected remote host, and persisted request IDs
  before submission so uncertain outcomes remain inspectable after restart.
- Enforced the platform token/audio-duration limits at the gateway, in addition to
  model, host, scope and body-hash checks.
- Bounded grant-response reads before allocation; revalidated active conversation
  access during service supervision and before camera start.
- Allowed existing synthesis requests to finish when the journal reaches capacity.
- Rejected dot-directory release names and bounded the stale-socket startup probe.

Review 1 checks passed: Pi/shared tests 42; gateway tests 13; real PostgreSQL
inference/two-scenario integration 8. The bounded-grant reader initially exposed a
bytearray/httpx response conversion error; corrected to immutable bytes and repeated
the full integration check successfully. Type checks passed for 41 client/Pi and
88 API source files. Shell and PowerShell deployment syntax checks passed.

## Review 2 — recovery, concurrent control and distribution

Re-read the resulting source, test outcomes, deployment scripts, service settings
and ARM64 wheel bundle, checking behavior independently of the phase checklist.

Findings fixed:

- A slow serialized control mutation could block status/shutdown; those commands
  now bypass the mutation lock, and every socket command has a response deadline.
- Ending an assigned listening session could leave an idle host labelled paused;
  listening cleanup now follows actual session ownership.
- Unexpected upstream stream errors could escape into service logs; they now keep
  an unknown receipt and close the stream without exposing exception details.
- Added atomic, durable per-device gateway admission limits, including concurrent
  requests, independently of host concurrency and request-size bounds.
- Corrected architecture documentation to match actual states/control semantics.
- Rejected malformed grant response shapes before any GPU request; preserved
  cancellation propagation and unknown receipts at the gateway.
- Applied cancellation/deadline checks during cloud response reads and decoding.
- Detected asynchronous GPU model startup failures and exited the supervised
  manager so OS restart policy can act; model selection/download remains explicit.

## Final verification

- Broad Human-test/shared regression: **623 passed, 2 opt-in native tests skipped**.
- Final Pi/shared/local-manager/inference-client regression: **126 passed,
  2 subtests passed**, including the last cloud cancellation and startup fixes.
- Gateway security/receipt/WSS suite: **14 passed**. A separate real loopback TLS
  check passed for the HTTPS client, framed audio and independent video client:
  certificate verification enabled, signed grants, durable completion receipts,
  fixture issuer/model only. No physical devices or live cloud were used.
- Full API suite without a database DSN: **620 passed, 408 skipped**. Skips include
  database-dependent and opt-in tests; they are not counted as database evidence.
- Dedicated disposable PostgreSQL at loopback port **55459**: **20 passed** across
  inference grants, both Pi scenarios, assigned sessions, device management,
  authorization, lifecycle and concurrency. Each test used an isolated database
  with forward migrations and runtime grants. The application DB was untouched.
  The disposable test server was stopped after verification.
  An earlier Windows Alembic child-process startup error did not recur in the
  isolated concurrency rerun or final full selected database run.
- API Ruff lint/format passed (243 files); mypy passed (88 source files).
  Pi/shared/client lint/format and mypy passed (41 source files); gateway lint,
  format and mypy passed (5 source files). Mypy retains its configured untyped
  function limits. Existing Starlette/test-client deprecation warnings remain.
- All three deployment shell scripts passed individual `bash -n` checks; the
  Windows task-registration script passed PowerShell AST parsing. This checks
  syntax, not Linux service installation or Windows reboot behavior.
- Final ARM64 CPython 3.13 wheelhouse: **24 hash-pinned wheels**, including PyAV,
  OpenCV, NumPy, PortAudio's Python adapter, Pydantic core and WebSockets.
  Offline, hash-checked cross-platform pip install **dry-run** resolved the whole
  bundle. It does not execute ARM binaries. Gateway wheel also built successfully.
  All four Pi application wheels matched final source byte-for-byte and contained
  no desktop imports or private configuration.
- `git diff --check` passed. No publication, hosted deployment or application
  service restart was performed.

Artifacts (ignored, relative to repository root):
`.test_artifacts/pi-framework/wheelhouse-arm64-final/` contains the final Pi
bundle and `release-requirements.txt`; `.test_artifacts/pi-framework/gateway-wheel/`
contains the gateway wheel. An earlier wheelhouse in the same parent directory
predates review fixes and must not be used as the final release.

## Remaining qualification boundaries

Physical Pi hardware, ALSA/CSI/USB behavior, Linux/systemd execution, reboot and
power-loss endurance, real GPU inference over the intended LAN, paid cloud output
and hosted deployment remain unverified. A Pi was not available. The hardware
acceptance checklist is in [compatibility](compatibility.md).

The complete software framework is implemented. WSS audio carries completed
utterances; partial live ASR is not implemented. Video ingress validates bounded
frames and reports inference unsupported; it does not run a vision model. Full
recordings retain the shared private archive path. These limitations are explicit
in the operator documentation. No confirmed review finding remains unresolved.
