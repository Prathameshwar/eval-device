# Pi framework implementation

Authorized 2026-10-10. Implement all software phases without requiring Pi hardware.
Preserve Human-test and use training-client for the conversation/session engine.
Hardware and paid cloud acceptance remain separately identified evidence.

## Phase plan and acceptance

- [x] 1. Architecture: record component ownership, lifecycle, trust boundaries, supported OS/Python, commands, recovery and acceptance contracts.
- [x] 2. Headless framework: typed configuration, one asyncio runtime, private command socket, enrollment/diagnostics, systemd lifecycle and fixture adapters. Verify boot without capture, command serialization, shutdown and dependency recovery.
- [x] 3. Remote inference: explicit HTTPS endpoint and shared client, device/host binding, short-lived scoped platform grants, independent GPU gateway, replay/admission limits and negative authorization tests. Preserve loopback management.
- [x] 4. Conversation integration: published scenarios, assigned sessions, local/cloud routing, text/listening/playback and existing durable history/media. Verify two complete scenarios without Tk.
- [x] 5. Hardware: ALSA-compatible audio selection, USB/CSI recorder adapters, no-preview camera subprocess, bounded queues/storage and failure tests. Record ARM/hardware checks as unverified.
- [x] 6. Media: independent bounded audio/video streaming contracts and clients, cloud output through existing platform processing, interruption/status handling and no inference replay.
- [x] 7. Unattended recovery: signal/watchdog handling, retryable readiness, authorization expiry, storage pressure, interrupted-session recovery, GPU startup integration and redacted diagnostics.
- [x] 8. Distribution: reproducible wheel/service installation, upgrade/rollback, compatibility and operations documentation; Linux/ARM dependency checks where the environment supports them.
- [x] Review 1: correctness, security, lifecycle and integration; reproduce/fix findings and run affected verification.
- [x] Review 2: inspect the final implementation independently by concern; fix findings, rerun regressions and record evidence/limitations.

No publication or deployment is authorized by this task. Never use the application
database as a destructive test target. Use mocks for paid provider execution.

## Completion and deferred acceptance

All eight software phases and both review/fix passes are complete. See
[review evidence](review.md) for test totals, fixes and qualification boundaries.
The final CPython 3.13 ARM64 wheelhouse is under
`.test_artifacts/pi-framework/wheelhouse-arm64-final/` at the repository root.

- [ ] Physical Raspberry Pi acceptance: ALSA/USB/CSI devices, Linux/systemd
  installation and reboot, WiFi interruptions, power/storage/thermal endurance.
- [ ] Live cloud/provider and real GPU over LAN acceptance with the intended Pi.
  Local fixture tests and ARM wheel resolution do not substitute for these checks.

This is the historical first-framework milestone. The later 0.2.0 implementation,
including live audio transport and bounded video processing, is tracked in
[completion phases](completion-todo.md) and [completion review](completion-review.md).
Use that release's artifacts for installation. Partial ASR remains unsupported.
