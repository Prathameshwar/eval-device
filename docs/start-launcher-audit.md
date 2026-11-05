# Local stack launcher audit

Date: 2026-09-19. Entry point: [start/start-human-test.bat](../start/start-human-test.bat). The batch delegates to the shared Human-test demo supervisor instead of duplicating service configuration.

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| One batch in `start` | Quoted script-relative paths, UTF-8 output, exit-code propagation, dependency guidance | Actual batch invoked from `C:\Windows\Temp` and another directory containing spaces | Passed |
| Start required APIs/models | Private PostgreSQL, PMS, retention, resident Whisper large (now automatic CUDA/CPU), Qwen3 4B, video recording API, Human-test | Cold `--check` run reached readiness for every service; GPU correction evidence below | Passed |
| Clear progress and errors | Named START/WAIT/READY/REUSE/ERROR/STOP messages, bounded startup waits and child-exit detection | Native console output and unit tests | Passed |
| No duplicate services or screen | Shared owner file lock; concurrent invocations wait for readiness and validate the existing stack | Native concurrent launch and repeat launch; unchanged listener process IDs and exactly one owned desktop window | Passed |
| Reuse a compatible model | Authenticate Qwen and verify model alias; no reload | Separately started real Qwen reused by the batch and remained running after desktop close | Passed |
| Safe database reuse | Authenticate, verify exact private data directory and current migration head; no migration/stop of a reused DB | Focused database-reuse unit test; native duplicate checks authenticate the real demo DB | Passed within these checks |
| Confirm usable Human-test dependencies | Verify audio model/device/recording, video storage, PMS readiness, patient permissions and PMS-to-Qwen connection | Real patient name completion through authenticated PMS returned “My name is Alex.” | Passed |
| Preserve incompatible listeners | Fail on failed authentication, wrong model/configuration or invalid status; no port-based termination | Native HTTP 401 audio conflict returned exit code 1, cleaned up owned DB and preserved the conflicting listener and reused Qwen | Passed |
| Cleanup | Windows process ownership guards; close only children started by the active owner | Native GUI close cleaned up owned services and preserved reused Qwen | Passed |
| Review and compatibility | Existing model selectors, credentials, patient data, direct audio/PMS boundaries and local-only behavior preserved | Two review passes, focused tests and existing desktop suite | Complete |

## Review findings and fixes

Review 1: replaced unconditional occupied-port failures with authenticated readiness/model checks. Added video with independent credentials and private recording storage, child startup failure checks, a singleton retention worker and a shared launcher lock. PostgreSQL reuse validates its directory/schema and does not run migrations under another owner. The batch resolves paths from its own location and propagates failures; it does not reinstall packages or start every model variant.

Review 2: required recording storage readiness before marking audio ready; bounded status bodies and read time; detect a stopped first launcher rather than making the second wait for the whole startup timeout; align duplicate-launch waiting with the configured model startup allowance; verify patient permissions and the actual PMS-to-Qwen connection before opening the window. Existing non-owned services survive both normal cleanup and startup failure. Only safe error summaries are printed; credentials, transcripts and database exception detail are not logged by the launcher.

## Verification and boundaries

| Final check | Result |
|---|---|
| Launcher unit/regression tests | **15 passed**; run using `uv run pytest -q ../../human-test/scripts/tests/test_startup.py` from `platform/api` |
| Existing desktop suite | **20 passed** |
| Static checks | Human-test/start Ruff and format passed; API Ruff/format and mypy passed (49 source files) |
| Actual batch startup | Cold `--check` succeeded from another working directory; all required services reached readiness |
| Actual duplicate behavior | Concurrent and ready-stack invocations succeeded without another GUI or changed listener PIDs |
| Actual application | One native Human-test window opened; authenticated PMS/Qwen returned the expected Alex answer |
| Actual failure behavior | Conflicting audio listener rejected, nonzero batch exit code propagated, external listener and independently owned Qwen preserved |
| Actual shutdown | GUI close stopped owned services; independent Qwen remained alive until its separate test owner closed it; final demo ports all closed |
| Build/package review | Human-test wheel/sdist built; shared startup scripts present in sdist; private environments, credentials, media and model assets excluded |

Both reviews were by the same agent. No API business logic, database schema, model selection or audio/video processing algorithm was changed, so the full database/API regression suite was not repeated for this launcher-only change. No destructive database integration tests were run against the application database; the native checks used normal startup and authenticated application calls against the existing isolated demo.

Live cloud, Pi/Wi-Fi and hardware microphone/camera acceptance remain deferred. The launcher starts the video API, but the current Human-test screen does not capture video. The launcher does not change the known Whisper large CPU latency or Hindi recognition limitation. Verification stopped its owned processes; double-click the batch to start your own session.

Native evidence is under `.test_artifacts/start-launcher/`: `normal-start.txt`, `concurrent-reuse.txt`, `ready-reuse.txt`, `conflict.txt` and `native-results.json`.

## Robustness follow-up: retries, diagnostics and ongoing supervision

The reported abrupt startup retained launcher PID 16964 in `starting` state. That was the same PID stopped during the user's preceding request to kill Python processes. The absence of the supervisor's normal error/STOP/DONE output was consistent with force termination. A subsequent clean cold startup passed, including Whisper large. The batch now prints its exit code and explains abrupt interruption separately from detailed service failures; operator cancellation has a STOP message.

| Behavior | Implemented policy | Verification |
|---|---|---|
| Startup retries | Five starts per owned service/session; 1-/2-/4-/8-second retry delays; old process group confirmed stopped first | Fifth-attempt success, retry exhaustion, backoff, lifetime budget and failed-cleanup regressions |
| Concurrent startup wait | A second launch allows the first launch's complete five-attempt budget and still detects an exited owner | Default/extended model-timeout coverage and stopped-owner regression |
| Configuration failures | Missing packages/assets, permission/configuration/integrity errors, insufficient memory or incompatible listeners fail with guidance | Categorized diagnostics and no-retry tests; native incompatible-listener check |
| Runtime monitoring | Process exit detection and readiness checks every 15 seconds; three consecutive readiness failures trigger bounded owned-service recovery | Temporary-health-failure tests and real audio crash recovery |
| Model reuse | Resident models stay loaded during healthy operation; failed owned model process is stopped before replacement | Lifecycle tests; native healthy services kept the same PIDs during audio recovery |
| Ownership and integrity | Reused services and PostgreSQL are monitored but not automatically restarted; migrations and inference submissions are not replayed | External-service protection, cleanup and no-overlapping-restart regressions |
| Failure messages | Service name, attempt count, safe category, available numeric/hex exit code and repair hint | Process-creation error redaction and native exit-code tests |
| Operational evidence | Private `launcher.log`, 256 KiB plus two backups; current stage/state in `launcher.json` | Credential/content scan passed; Windows ACL limited to current account/SYSTEM |
| Cancellation and shutdown | GUI close cancels recovery; cleanup continues after individual errors; original failure survives cleanup errors | Cancellation, cleanup retry and desktop-crash-during-recovery tests; native GUI close |

Review 1 checked retry boundaries, lifetime attempt budgets, permanent versus transient failure handling, ownership and model cleanup before replacement. Review 2 fixed cleanup error masking/resource release, distinguished a desktop crash during recovery from a normal close, added a direct PostgreSQL health watch, bounded diagnostic reads, and preserved the first classified child failure. Raw child output is consumed and discarded; only allowlisted categories enter operational messages. No raw traceback, provider credential, transcript, question or model answer is retained in the operational log.

Final follow-up checks: **29 launcher/supervisor tests and 20 desktop tests passed**. Human-test/start Ruff and formatting, API Ruff/format/mypy (49 sources), and Human-test wheel/sdist build/private-asset checks passed. The full database/API business suite was not repeated because API business logic and schema were unchanged.

The native test launched the actual batch, repeated it during/after startup, and deliberately terminated only the audio listener owned by that test. **Audio recovered in 28.618 seconds** (including reloading Whisper large); PMS, video, PostgreSQL and independently started Qwen retained their PIDs. Human-test stayed open and the subsequent authenticated PMS/Qwen request returned Alex's expected name. GUI close cleaned up owned services; the independent Qwen and a deliberately conflicting HTTP listener were preserved until their test owners closed them. Final demo listener count was zero.

Evidence: `.test_artifacts/start-launcher-recovery/{normal-start.txt,concurrent-reuse.txt,ready-reuse.txt,conflict.txt,native-results.json,final-checks.json}`. This is a verified local recovery exercise, not a long-duration soak test or a promise to survive termination of the supervisor itself. An active request interrupted by a crash may fail or have an uncertain outcome; it is never replayed automatically. Whisper large reload/CPU transcription latency, live hardware and cloud limitations remain unchanged.

## Five-attempt policy follow-up

The requested minimum startup allowance is now five total attempts for each owned audio/video/PMS/Qwen/retention service. This is the initial start plus four retries; readiness success ends retries immediately. Startup retries and later runtime restarts share this session budget. Review also extended the duplicate-launch wait to cover all five attempts. Permanent configuration errors and unconfirmed cleanup still stop immediately; database initialization/migrations and inference calls are not replayed.

| Check | Result |
|---|---|
| Launcher regressions | 32 passed, including fifth-attempt success, five failures with no sixth start, exact 1/2/4/8-second backoff and duplicate-launch allowance |
| Desktop regressions | 20 passed |
| Static checks | Human-test/start and API Ruff/format passed; PMS mypy passed for 49 sources |
| Review | Attempt limits, messages, cleanup ordering, permanent-error behavior and documentation checked; duplicate wait finding fixed |
| Verification boundary | Local unit tests for this policy change; native crash-recovery evidence above predates the increase from three to five attempts. Full database integration and native five-failure model startup were not repeated. |

## Automatic GPU selection correction

The CPU-only default in the combined launcher was contrary to the requested GPU-first behavior. Default audio selection is now automatic: probe from the audio environment, use compatible CUDA when available, otherwise announce CPU selection. Explicit `--audio-device cpu` / `--audio-device cuda` are supported. A CUDA selection remains fixed for that running service; inference/startup failures do not silently move a question to another device.

| Requirement / review item | Implementation and evidence | Result |
|---|---|---|
| GPU when available, CPU otherwise | Audio probe checks CTranslate2 support and Windows CUDA libraries; reports safe reason/device/index metadata | Native RTX 500 Ada CUDA selection passed; unavailable/runtime-error CPU branches mocked |
| Consistent device choice | Generated audio and desktop settings, status checks, launcher state and duplicate reuse share the same selection | Native CUDA preflight and duplicate reuse passed; wrong-device regression rejects reuse |
| Share limited GPU memory | New Qwen uses at most 16 GPU layers on a shared GPU of 6 GiB or less/unknown size; remaining layers use CPU | Both models ran together on the 4 GiB GPU; native Qwen readiness validates requested offload |
| Preserve explicit configuration | Lower Qwen limits/CPU setting and separate GPU choices retained; per-launch flag changes no config file | Unit coverage; explicit standalone audio flags preserved |
| Safe fallback and retries | Probe failures are redacted; explicit CUDA fails if unavailable; owned-service five-start policy retained; no inference replay | Launcher/device regressions passed |
| Actual entry point | `start/start-human-test.bat --check` used automatic CUDA and reached readiness for all services | Exit 0; owned stack cleaned up |
| Unit/regression suites | 47 launcher, 163 audio, 20 desktop, 33 local-LLM | 263 passed |
| Static/package checks | Human-test/start, audio, changed local-LLM files and API Ruff/format; audio/PMS mypy; audio/Human-test wheel/sdist | Passed; new helper packaged and private runtime assets excluded |

Native full-stack test used the same prerecorded synthetic English onset question as the earlier CPU audit. Both requests produced the exact expected transcript and scripted duration answer while preserving the saved patient selection:

| Mode | ASR finalization after input | PMS round trip | Whole turn including paced audio |
|---|---:|---:|---:|
| JSON | 1.047 s | 1.860 s | 5.235 s |
| SSE | 0.890 s | 0.688 s | 3.891 s |

The prior CPU result for that fixture was 16.390 s ASR finalization. These timings are individual recorded-input runs, not a guarantee for arbitrary questions, live microphone input or background load. GPU memory sampled after inference was 3,103 MiB used / 790 MiB free; peak usage was not sampled. Evidence: `.test_artifacts/start-gpu-auto/{verify.py,native-results.json}`. The native test also verified duplicate CUDA reuse and owned-service cleanup. Automatic CPU fallback is unit-tested, not a native no-GPU-machine test.

Final review covered device selection, CUDA remapping, small-GPU sharing, model residency, authentication, package dependencies and process ownership. Fixed inherited CUDA remapping inconsistency and stale CPU-default documentation. No platform schema/business logic changed, so destructive database integration and the full API business suite were not repeated. No new cloud, Pi, physical microphone, Hindi quality or long-duration acceptance is claimed. Earlier historical CPU and recovery evidence above remains valid for those recorded configurations.

## One startup path (2026-09-20)

`Demo.start()` used to choose between a PMS-profile startup (`model_startup.start`) and a
self-contained local startup that predated published profiles. `main()` always passes a
bootstrap `--processing-mode`, so the second path had been unreachable for some time while
still reading as the authoritative one — and a local-execution fix was applied to it instead
of to the live path, passing its own test while changing nothing at launch. The dead 190-line
body and its duplicated desktop-environment dict were removed; `start()` now delegates to the
PMS-profile path only, and `human-test/start-demo.bat` reaches the same code as
`start/start-human-test.bat` (it already did). `model_startup.local_model_key()` is the single
reader of `local-models/.state/api-key.txt`, used both to bootstrap the local PMS connection and
to hand the key to the screen for a published local model.

Checks after the removal: 103 launcher tests, 184 human-test tests with six opt-in skips,
Ruff/format and mypy on the launcher scripts and the desktop package. PMS sources were not
touched. A real local turn against the resident Qwen3 4B (eight routed questions, native
tokenizer budgets, no text in the reported record) is recorded in
[review evidence](pms-api-reviews.md). `start\start-human-test.bat --check` still needs a
non-elevated console: `postgres.exe` refuses to run under an administrator token.
