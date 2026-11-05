# Shared client runtime extraction

Started 2026-10-10. Human-test and the future Raspberry Pi service must use one
implementation of the client workflow. This phase changes the common package and
Human-test; Pi hardware/service deployment and a network inference gateway remain
the next phase. Existing platform authorization, model assignments, request
idempotency, private bounded media and unknown-outcome handling remain intact.

## Implementation

- [x] Create `shared/training-client` with explicit application paths and packaged defaults; reuse `training-contracts` and `local-model-client`.
- [x] Move pairing, platform communication, turn execution, audio orchestration, filtering, history, performance, recording and synchronization into the package; remove duplicate Human-test implementations.
- [x] Extract a headless runtime that owns listening, playback, cancellation and camera archive completion independently of UI event consumption.
- [x] Separate assigned-session lease/lifecycle management from Tk controls and timers.
- [x] Make inference connections/capabilities belong to each client instance rather than process-global configuration.
- [x] Preserve injectable hardware boundaries and explicit startup/shutdown; keep GUI dependencies outside the core.
- [x] Correct camera options field mapping and interrupted/overloaded utterance handling with regression coverage.
- [x] Migrate Human-test, its scripts, tests and portable packaging to the shared implementation.
- [x] Run headless lifecycle/failure regressions, existing desktop/client tests, lint, formatting, type and packaging checks; review twice and resolve findings.
- [x] Document supported interfaces, storage/credential ownership, migration and remaining Pi prerequisites.

## Next phase (not implemented here)

- [ ] Raspberry Pi daemon, boot/service integration, hardware selection and physical/remote session controls.
- [ ] Authenticated remote GPU inference endpoint and device-scoped server authorization; retain loopback management isolation.
- [ ] Cloud TTS integration, live network ASR/TTS/video streaming and video inference where required.
- [ ] Explicit unattended capture/upload scheduling and restart/session-resumption policy.
- [ ] Linux/ARM package and hardware verification; live cloud and remote GPU integration.

## Follow-up review - 2026-10-10

- [x] Recheck common runtime and desktop behavior; reproduce and fix confirmed lifecycle, media and packaging findings.
- [x] Run regressions, broad affected suites and protected-package checks; record final results and remaining limits.

Review evidence: [shared-client-review.md](shared-client-review.md).

## Live desktop verification after extraction - 2026-10-10

- [x] Start the existing Local Models services, local API and Human-test in order.
- [x] Exercise two published scenarios through the desktop and real local inference, including speech input/output and history synchronization.
- [x] Fix confirmed integration findings, rerun affected checks and record actual results without changing API implementation unless needed.

Live evidence: [shared-client-live-review-20261010.md](shared-client-live-review-20261010.md).
