# Pi implementation completion

Authorized 2026-10-11. Extend the existing framework, preserve desktop behavior,
and leave the user's application services stopped. Use isolated fixture services.

## Behavior and ownership

Boot is idle; sessions and capture require explicit local commands. An optional
`listen_on_begin` setting starts listening only after an explicit successful begin.
Interrupted capture requires an explicit resume. Readiness recovery never replays
a question or starts capture. No model executes on the Pi.

Reuse the platform's supported visual tasks: `video.motion` / `opencv_motion` on
the remote host and `video.labels` through its cloud processing runs. These are
bounded observations, not patient facts or commands to change a clinical scenario.
The private control channel retrieves results; operational status excludes media
and result text. Unsupported partial ASR is reported explicitly.

## Phases

- [x] 1. Record behavior, scope, acceptance matrix and ownership.
- [x] 2. Commissioning, binding validation, capability/readiness diagnostics and control results.
- [x] 3. Strict audio identity, normalization, failure recovery and transmission during capture.
- [x] 4. USB/CSI identity, bounded video processing on remote local/cloud routes and results.
- [x] 5. Route/configuration reconciliation, provider adapters, durable request status and mixed routes.
- [x] 6. Unattended recovery, cancellation, storage and outage regression coverage.
- [x] 7. Linux/ARM qualification automation and deployment fixes; record actual execution limits.
- [x] 8. Two-scenario integration, desktop regression, final release bundle and operations guide.
- [x] Review 1: authorization, lifecycle, privacy, bounds; fix findings and repeat affected checks.
- [x] Review 2: inspect final behavior, concurrency, recovery, packaging; fix findings and verify.
- [ ] 9. Physical Pi acceptance (requires the user's hardware; cannot be certified by mocks).

Linux/ARM execution requires an available runner. This Windows host currently has
no installed WSL distribution or Docker runtime. Native Pi I/O, real cloud calls,
reboot/power endurance and deployment remain separate acceptance evidence.

## Acceptance by phase

| Phase | Software acceptance | Evidence boundary |
| --- | --- | --- |
| 1 | Headless ownership, idle boot and explicit capture/resume documented | No hardware claims |
| 2 | Config validation, pairing, exact binding, diagnostics, bounded private results | Probe does not capture/play |
| 3 | Native rate conversion, exact device identity, capture loss, clean-end ASR | Synthetic PCM and real loopback TLS |
| 4 | USB/CSI adapters; reserved remote motion and cloud video runs | Real image codecs, mocked cloud/GPU |
| 5 | Published routes, optional GPU failure, private journals and owner-scoped status | Real API/PostgreSQL authorization |
| 6 | Independent media cancellation, no automatic resume/replay, private bounded queues | Service and shared regressions |
| 7 | Native ARM qualification runner, offline release, upgrade/rollback safeguards | ARM wheels resolved; native runner still required |
| 8 | Two scenarios through text/ASR, desktop regression, two review/fix passes | No paid provider or production services |
| 9 | ALSA, USB/CSI, reboot, WiFi/GPU loss, power/storage/thermal endurance | Pending physical Pi |

Release: `.test_artifacts/pi-completion/wheelhouse-arm64/` (Pi-test 0.2.0,
CPython 3.13 ARM64). See completion-review.md for final verification.
