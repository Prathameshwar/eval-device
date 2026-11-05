# Pi completion review evidence

Work started 2026-10-11. The earlier framework review is in review.md; this record
covers the additional implementation requested after it. Application services stay
stopped. Fixture APIs, disposable databases and loopback test servers are isolated.

## Findings during implementation

- Existing cloud-output detection used `mode`, while actual platform processing
  sections use `execution_mode`; align detection and grant policy with that contract.
- Configured microphone names could silently fall back to another device; the Pi
  needs exact identity checks and an explicit unavailable state.
- Module presence and a wheel dry-run do not prove Linux/systemd or ARM execution.

## Review 1: authorization, lifecycle, privacy and input bounds

- Fixed remote speech preflight incorrectly requiring the desktop manager credential.
  Extended the real API/PostgreSQL two-scenario journey to include ASR, conversation
  turns and service reconciliation using authenticated fixture inference.
- Shared heartbeat identity/sequence across output, video and service checks;
  concurrent media no longer impersonates successive device boots.
- Fixed coarse-clock duplicate WSS timestamps found by real loopback TLS testing.
  Partial audio still cannot trigger inference and remains an uncertain receipt.
- Centralized JPEG header bounds before decoder allocation, including CSI and cloud
  clip encoding. Duplicate size headers are rejected before decode.
- Device processing grants require an owned, current, reserved local video run.
  PostgreSQL concurrency tests prove only one grant can authorize that run.
- Cancellation now records the platform's observed status, avoiding a false cancelled
  report when processing had already completed. Session completion and camera-stop
  cancel video jobs; premature camera loss rejects the partial clip.

## Review 2: recovery, compatibility and packaging

- An unavailable optional GPU could block cloud conversation readiness. Metadata
  checks now have a five-second bound, avoid a duplicate boot probe, and report
  gateway availability separately; an assigned local LLM still blocks when unavailable.
- Probe sample-rate selection differed from capture. Both now use the same checked
  16/44.1/48 kHz selection. Explicit non-16 kHz input is normalized even outside Pi
  strict mode; failed PortAudio startup closes its stream.
- Disabled platform speech output now disables Pi playback. Processing inspection
  includes both durable video and cloud output journals after service restart.
- Upgrade/rollback reject redirected release paths and stale switch markers before
  stopping the service. Rollback validates imports and restores the prior executable
  if service startup fails. Shell syntax passed; native systemd execution is pending.
- Updated old architecture/operations claims to describe streaming during capture
  and the actual supported visual operations. Partial ASR stays explicitly unsupported.

## Verification

- Pi/shared suite: **73 passed**, including media codecs, native-rate normalization,
  identity, concurrency, uncertain creation, cancellation and outage recovery.
- Gateway suite: **18 passed**, including real verified loopback TLS/WSS, frames
  acknowledged before capture ends, interrupted input without ASR, motion analysis,
  replay, size/sequence limits and pre-decode malformed/oversized JPEG rejection.
- Human-test/shared suite: **632 passed, 2 skipped**; the skips require GUI/display.
  After the remote preflight fix, the affected desktop readiness/local-execution/
  listening selection also passed **136 tests**. Additional final capture checks
  are recorded with the final release audit below.
- API full suite: **620 passed, 410 skipped** without an admin DSN. Skips require
  disposable PostgreSQL; they are not claimed as verified by that run.
- Dedicated PostgreSQL `127.0.0.1:55459`, data directory
  `.test_artifacts/pi-framework/pgdata`: **11 passed** in the targeted final run.
  These include two published scenarios through Pi/shared text and ASR, inference
  ownership/lifecycle, video grant concurrency, device cancellation and existing
  local-processing role/idempotency checks. Each test creates/drops its own DB/roles.
- API Ruff, format and mypy passed (88 source files). Pi/shared/client Ruff, format
  and mypy passed (43 source files); gateway mypy passed (6 files).
- Built **24 hash-locked CPython 3.13 ARM64 wheels**, including Pi-test **0.2.0**;
  offline `pip --dry-run --require-hashes` resolved the complete bundle successfully.
  Gateway **0.2.0** wheel built separately. Native imports/execution on ARM are unverified.
- `qualify.py` correctly rejected this Windows/AMD64 host as a native ARM runner.
  Its JSON records `passed=false`, `native_arm64=false`, `hardware_verified=false`.

Release artifacts: `.test_artifacts/pi-completion/wheelhouse-arm64/`,
`.test_artifacts/pi-completion/gateway/`, `arm64-install-report.json` and
`native-runner-check.json` under `.test_artifacts/pi-completion/`.

Physical Pi/ALSA/CSI/USB, Linux/systemd execution, real GPU over LAN, paid cloud,
reboot/power/thermal endurance and hosted deployment remain unverified. The software
implementation and both review/fix passes are complete; physical acceptance remains
open. API, Human-test and local-models application services remain stopped. No
commit, publication, application DB mutation or production deployment was performed.

## Final release audit

- Re-ran the two-scenario PostgreSQL journey after the final readiness changes:
  **1 passed** (two published scenarios, text plus ASR in each).
- Manager/inference-client regressions: **76 passed, 2 subtests passed**.
  Desktop capture/listening regressions after the sample-rate cleanup: **66 passed**.
- Compared every Python source file in all four application wheels against the final
  checkout: exact matches. CLI config-check/doctor passed without capture or enrollment.
- Final Ruff/format and whitespace checks passed. Existing dependency deprecation
  warnings remain; no test failure was left unresolved.
- Stopped the dedicated test PostgreSQL server. Verified no API, Human-test,
  local-models/gateway application processes or listeners on 3000, 8000, 8790, 8791,
  8795, 8797 or 8798. The application database service was untouched.
