# Pi-test final review, 2026-10-11

Scope: Pi service/control shutdown, bounded commands, hardware adapters, configuration
and deployment. Preserve previous work; keep application services stopped. Physical
Pi and native Linux execution are unavailable on this Windows host.

- [x] Inspect Pi-specific service, control, capture, configuration and deployment.
- [x] Reproduce and fix confirmed lifecycle/input issues.
- [x] Run affected regressions, static checks and inspect final fixes again.
- [x] Refresh release evidence and record remaining qualification boundaries.

## Findings and fixes

1. **Pending control requests delayed shutdown.** `Server.wait_closed()` was awaited
   before cancelling connected handlers, so a slow command held shutdown open until
   its timeout. Handlers are now cancelled and joined first. Response draining and
   socket closure have deadlines; handlers remain tracked until cleanup finishes.
2. **Commands could start during shutdown.** Setting the stop event did not reject
   queued or new mutations, and the control socket stayed open while its runtime
   dependencies closed. Admission now checks stopping state after acquiring the
   command lock. The service closes control before runtime dependencies; status
   reports stopping/unready immediately.
3. **Unicode questions exceeded the command limit unnecessarily.** JSON ASCII
   escaping expanded an otherwise valid 8,000-character question beyond 32 KiB.
   Requests/responses now use UTF-8; oversized commands are rejected before opening
   a connection. The existing server byte limit and private authentication remain.
4. **Oversized stdin could become a silently truncated question.** The CLI read
   8,001 characters and stripped whitespace before length validation. An overflowing
   question whose cutoff was whitespace could submit its prefix. Input is now
   checked before trimming, allowing only an optional terminal LF/CRLF.
5. **Upgrade ignored service-stop failure.** Installation could switch the active
   release after failing to stop the old service. Existing installations must now
   stop successfully before the unit or release link is replaced. A dangling release
   symlink is also rejected. Pi deployment shell/unit files have explicit Git LF
   rules so Windows checkout does not introduce Linux script parsing failures.

The first four regressions were demonstrated failing against the previous code;
all passed after the fixes. Additional boundary cases verify full-length stdin
with no newline, LF or CRLF. A second inspection checked cancellation ordering,
handler cleanup, shutdown admission, input framing, deployment guards and the
final packaged sources. No confirmed finding remains unresolved in this scope.

## Verification

- Pi/shared: **91 passed**, including seven new regression/boundary cases, existing
  socket authentication, private state, idle boot, hardware mocks, capture failure,
  finish barriers, reconnect behavior and cloud/remote transport contracts.
- Pi Ruff lint/format: **24 files**; mypy: **10 source files**, all passed.
- API broad regression: **620 passed, 411 skipped** without a database DSN. Skips
  include database-dependent checks; no database tests were executed in this pass.
  API Ruff/format (244 files) and mypy (88 source files) passed. Existing dependency
  warnings remain. Prior database-backed journey evidence is linked below.
- All three Pi shell scripts passed individual `bash -n` checks. Deployment shell
  and unit files contain LF endings; Git attributes confirm they remain LF. The
  installer guards were reviewed in source, not exercised against real systemd.
- Built **24 hash-pinned CPython 3.13 ARM64 wheels**. Offline, hash-checked pip
  installation dry-run passed. All **69 Python source files** across the four
  application wheels match the checkout; no private connection/config files are
  bundled. Native ARM code was not executed.
- Application process/listener inspection found API, Human-test, Pi-test and
  local-models stopped; the disposable PostgreSQL server remained stopped. No
  application database changes, commit, publication or hosted deployment occurred.

Current bundle: `.test_artifacts/pi-final-review/wheelhouse-arm64/`, with
`release-requirements.txt`; installation-resolution report:
`.test_artifacts/pi-final-review/arm64-install-report.json`. This supersedes the
earlier `client-e2e-review` Pi bundle. Use the current `pi-test/deployment` scripts
with it. The software version remains the unpublished 0.2.0 release.

Physical Pi/ALSA/CSI/USB, Linux/systemd execution, real GPU over LAN, live cloud and
reboot/power-loss/thermal endurance remain unverified. See the
[hardware acceptance checklist](compatibility.md) and the preceding
[cross-client/database review](../../docs/client-e2e-review-20261011.md).
