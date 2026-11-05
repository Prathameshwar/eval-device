# Cloud/local switching and local service cleanup — 2026-09-20

The reported cloud-to-local failure occurred before model loading: an independently
started llama-server held the LLM port, while the launcher waited for an unowned
process to disappear. A second issue would have affected the first local question:
the cloud startup path did not hand the installed laptop model key to the desktop.

The launcher now checks unregistered listeners before stopping any service, reuses
an authenticated compatible service, and gives an actionable cleanup message for
an incompatible listener. The desktop receives the installed laptop key even when
starting with a cloud profile. Local inference remains entirely in the desktop's
loopback model client. No API inference route or schema changed.

The Models popup now offers **Stop & clean local services**. The authenticated
loopback mailbox queues cleanup on the same supervision thread as activation.
Both operations share the concurrency fence and request-ID reconciliation;
cleanup accepts no caller-supplied PID, command, path or port. The launcher checks
PMS organization-administrator access and audio activity, and the UI blocks cleanup
while listening, processing, switching, or recording/saving camera video. It stops
owned process groups and current TCP listeners on ports 8787, 8769 and 8766. External
listeners are terminated through a captured Windows process handle after checking
that they still own the port. PMS, PostgreSQL, models and recordings are preserved.
Windows access failures are reported without claiming success. Stopped registered
services remain disabled until local activation restarts them, including the video
receiver when that service was part of the stack.

Review covered authorization, bounded inputs, concurrent operations, lost-response
reconciliation, rollback with reused services, port identity checks, secret-free
errors, and the hosted-PMS/local-inference boundary. The user explicitly authorized
stopping processes occupying these service ports and requested this cleanup button.

Verification:

- Launcher suite: **135 passed**, including native Windows termination of a child
  listening on an ephemeral test port and successful rebinding afterward.
- Desktop suite: **283 passed, 6 skipped** (two opt-in resident-model and four
  installed-voice checks). The native Tk popup test exercises the cleanup button,
  recording guard, busy/permission states and subsequent model selection.
- API boundary/provider tests: **84 passed**, including local/cloud prompt parity
  and transport restrictions. API Ruff, format and mypy checks passed; no database
  integration tests were needed or run because API/database code is unchanged.
- Desktop/launcher lint, formatting and desktop type checks passed.
- Repeated cloud → local → cloud → local turns against mocked services show that
  local prompts/answers go only to the loopback server, while remote PMS receives
  metadata. The laptop key never appears in PMS request headers or bodies.
- The operator-authorized real blocking listener was stopped: one LLM listener
  removed, port 8787 free. Application cloud selection was preserved.

- Native installed-model check: **Qwen3 4B + Whisper large-v3 started successfully**
  with CUDA audio and 16 GPU layers for Qwen. One synthetic direct local LLM request
  succeeded; repeat activation reused both resident processes. Startup, inference
  and repeat activation took **42.81 seconds** in total, then both owned ports were
  released. PMS publication was simulated for this check so the running app's saved
  cloud profile was preserved. This verifies actual local loading/inference, not a
  live cloud inference or production PMS-publication round trip.

No cloud inference, hosted deployment or Raspberry Pi hardware verification is
claimed. Existing running Python processes must be relaunched once to load this
code and the updated desktop environment.

Evidence: `.test_artifacts/model-switch-cleanup/` contains JUnit reports, source
snapshots/diffs and the native cleanup/startup JSON results.
