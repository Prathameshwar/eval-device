# Manage Local Models implementation reconciliation — 2026-10-09

The desktop controls now use an independent authenticated local manager. Model
installation, provisioned configuration, running processes and loaded/readied
models remain distinct states. The manager and workers survive desktop closure.

| Phase | Result |
|---|---|
| Contracts and state | Loopback/operator authentication, private atomic state, UUID operation journal, revisions, bounded events and approved inventory. |
| Assets and workers | Verified staged downloads, isolated audio/voice/conversion runtimes, compatible existing assets, owned resident LLM/ASR/TTS workers, explicit CPU/GPU choice and drain-before-stop. |
| Desktop actions | Live navigation/search/filtering, download/runtime preparation, provision/configure, start/stop/status, remove stopped configuration, filtered logs/follow/export, diagnostics/reconnect and saved defaults. |
| Reviews and fixes | Two manual implementation review passes, targeted regressions, native control checks and independent native CPU qualification. |
| Next queued phase | Genuine Windows service installation/removal, dedicated identity, startup before login and optional capability auto-start after reboot. Boot controls remain disabled. |

The [control reference](desktop/README.md) reconciles each button/menu/action and
the [API reference](service/README.md) documents its local contract. Launch with
[manage-local-models.bat](manage-local-models.bat). `--preview` retains the original
explicit sample layout; normal launch uses live data.

## Review 1 — foundations, security and engine compatibility

Inspected authentication/host/browser boundaries, bounded input, credential
privacy, safe paths and manifests, hashes/source revisions, idempotency,
concurrent actions, owned processes and compatibility with existing engines.

Fixed nested Vosk manifests/required files, QwenMedic's installer entry point,
cached source validation, private asset/cache permissions, isolated optional
medical conversion dependencies, duplicate-manager locking, guard failure
cleanup and slow input deadlines. Shared runtime preparation requires stopped
manager-owned workers; LLM preparation uses the existing installer lock.

The initial 26 new backend tests passed. Separate native qualification loaded
existing Qwen3 1.7B, Piper English and Whisper large-v3 on CPU; all inferred through
the manager and stopped without model downloads. Live HTTP/desktop control
checks passed with fixture engines; those fixtures are explicitly distinct from
native inference evidence.

## Review 2 — operations, failure states and desktop continuity

Inspected live click bindings, asynchronous Tk updates, revisions, reconnection,
real readiness, native process death, draining, shutdown admission, interrupted
operations and failed disk writes.

Fixed failed-start/native-child status and wrapper cleanup before reconfiguration,
shutdown races, recovery of active operation visibility, connection startup
deadlines, operator permission errors, state rollback on write failure and read
only mutations when metadata cannot be recorded. Active drain timeout resumes
admission instead of killing work. The native test's teardown now waits for its
owned manager process to exit, because closing the listening port can precede
release of the instance-lock file. The final successful run cleaned up its
isolated manager and workers.

An empty-body regression found the same status was used for empty and oversized
requests. Empty JSON requests now fail with 400, oversized bodies with 413.
Confirmed findings were fixed and affected checks rerun. No remaining confirmed
finding was identified in these reviewed paths.

## Verification

| Check | Actual result |
|---|---|
| Local-model unit/regression suite | 72 passed: existing 40 plus 32 manager/business/security/concurrency/failure regressions. |
| Native preview UI | 42 checks passed across all pages, three sizes, filters and dialogs. |
| Native live UI with real authenticated HTTP and fixture engines | 23 checks passed: page geometry, search, provisioning, start/stop, filtered export, settings and UI closure. |
| Separate native CPU workers | Qwen3 1.7B generation, Piper synthesis and Whisper large-v3 recognition passed; each was stopped. |
| Actual desktop closure | Closed Tk desktop while the LLM was resident; a new client successfully inferred through that same worker. |
| Existing runtime reuse | Verified Qwen model/CPU runtime reused under the shared installer lock, with fetch explicitly blocked. |
| Static verification | Ruff lint/format and Git whitespace checks passed. |

Representative commands, from the repository root:

```powershell
python -m unittest discover -s local-models/tests -p test*.py -q
python local-models/tests/desktop_layout_smoke.py
python local-models/tests/desktop_layout_smoke.py --live
python local-models/tests/native_manager_smoke.py
python local-models/tests/native_runtime_reuse.py
```

Native checks are opt-in Windows checks using already installed verified assets;
missing assets are reported, never downloaded. Test managers/ports are isolated.
Native GUI/protected-asset checks require access outside the restricted sandbox.
The operational phase changed no platform API/schema code, so no API/database
tests or migrations were applicable. Earlier rename evidence records its
separate API checks and database skips. Unrelated concurrent API/UI edits remain
untouched.

## Remaining scope

The manager is a **detached operator process, not a registered Windows service**.
It survives desktop closure and currently ends with OS shutdown. Windows SCM
install/remove, dedicated service identity, startup before desktop login, reboot
auto-start and crash recovery are explicitly queued next in
[the repository TODO](../docs/pms-api-todo.md).

Concurrent GPU memory/capacity and live publisher downloads/conversions still
need separate qualification. Sequential GPU evidence is recorded below. The
current model APIs are privileged local operator APIs; Human-test migration,
clinical tenant/session authorization,
conversation orchestration, TLS/LAN pairing and Raspberry Pi integration remain
separate phases. Video analysis still requires a defined task and adapter;
recording requires no model. No microphone/camera/Pi, live cloud integration,
Windows service registration, VM update, commit or publication occurred here.

## Final review follow-up — 2026-10-09

The requested final review inspected configuration round trips, desktop failure
states, native readiness, owned-process cleanup, installation recovery/integrity,
port reservations, export destinations and the final implementation again after
fixes. Confirmed findings were corrected and affected checks rerun:

- Configure retains the saved model, requested CPU/GPU, custom port and runtime
  options, including when the worker reports its actual device as CUDA.
- Invalid/offline forms retain their values. The service-status dialog refreshes
  in place, reflects current lifecycle restrictions, and displays the actual
  connected manager port. Removal does not close the dialog on a disconnected
  submission.
- Start cannot report success without explicit readiness; an existing worker
  must match the configured model and execution device.
- Reusing a verified model no longer requires space for a second model copy.
  Source locks/manifests are atomic; incomplete cached HF metadata fails before
  download; interrupted conversion publication can resume; voice-installer exits
  become a reported operation failure instead of terminating the operation thread.
- Installer process guards close even if termination fails. Legacy installer
  imports share a lock. Worker/native ports reserve the actual manager listener.
- Log exports reject managed metadata/model/runtime destinations and linked
  paths, preventing accidental overwrite of state, credentials or weights.

| Final check | Actual result |
|---|---|
| Unit/regression suite | 83 passed, including 11 additional backend regressions for the findings above. |
| Native live desktop with authenticated HTTP and fixture engines | 27 checks passed, including preserved configuration, disconnected forms, protected export and live status-dialog refresh. |
| Native preview layout | 42 checks passed after the shared field-widget change. |
| Native CPU workers | Qwen3 1.7B generation, Piper English synthesis and Whisper large-v3 recognition passed. |
| Native GPU/CPU workers | Qwen3 1.7B and Whisper large-v3 reported CUDA and inferred; Piper reported CPU and synthesized. Capabilities were tested sequentially. |
| UI closure | Both native runs closed the actual Tk UI, then a new client inferred using the same resident LLM. |
| Existing runtime reuse | Verified Qwen/CPU runtime reused under the installer lock with network fetch blocked. |
| Static checks | Ruff lint and formatting passed for 42 Python files; Git whitespace check passed. |

GPU qualification used this laptop's NVIDIA RTX 500 Ada Generation Laptop GPU
(4094 MiB), with 16 LLM layers requested for partial CUDA offloading. This is
functional device/inference evidence, not simultaneous-worker capacity or
performance qualification. Native checks reused installed verified models,
downloaded no weights and stopped their isolated workers/managers. Download and
failure-path regressions use fixtures/mocked publisher calls; live publisher
installation and conversion were not exercised.

No remaining confirmed finding was identified in the reviewed paths after the
fixes and second inspection. The documented 2000-entry operation-journal limit
remains a maintenance constraint. Windows SCM installation/removal, reboot
auto-start, shared clinical clients/LAN authorization, Pi/video adapters and
live cloud/hardware integration remain separate queued work. No platform
API/schema changes, application-database tests, VM update, commit or publication
were performed in this final review.


## Human-test centralized inference migration - 2026-10-09

Human-test is now a consumer of the local-models gateway. The scope covers desktop
routing/readiness, recognition and physical playback, setup/launch scripts,
portable packaging, central model credentials/voice ownership, and the relevant
qualification tools. Platform API/schema and unrelated concurrent work were not
changed by this migration.

| Requirement | Reconciliation |
| --- | --- |
| One implementation for local inference | Shared local-model-client package in local-models/client; manager owns LLM/ASR/TTS engines. |
| Models/access from the central manager | Verified inventory/aliases/voices and live service readiness; inference-only credential excludes management, logs and shutdown. |
| No model management in Human-test | Removed offline tab/installers, local catalog, native loaders, model launch/cleanup, GPU selection and restart supervisor. |
| Startup connects only | Prepared-child handover and read-only platform/manager readiness; cloud startup remains usable with the manager unavailable. |
| Central synthesis assets/runtime | Voice locks/installers and existing private weights moved intact to local-models; Piper removed from Human-test dependencies. |
| Physical devices stay in the client | Microphone, speaker, camera, bounded recording, UI/session handling and durable playback gates retained. |
| Model-free client builds | One desktop environment plus SDK; native engines, weights, runtime installers and manager keys excluded. |
| Future consumers | Shared inference contract prepared; Pi code and authenticated LAN/TLS pairing deferred. |

Both reviews were performed by the same agent. Review 1 checked the extraction,
model ownership, route/model pinning, clinical context/fact validation, credential
separation, private media/history preservation, client packaging and request replay.
Findings fixed included empty metadata breaking cloud UI startup, stale native
transport/test fixtures, a voice installer still called by setup, and central
runtime/model paths still rooted in Human-test. Affected regressions were rerun.

Review 2 checked the final startup/window lifetime, native engine calls, live
readiness, metadata refresh, playback caches, Windows HTTP rejection and source
imports. Fixes covered the prepared-child flag causing recursive launcher startup,
obsolete compute/process fields in launcher status/monitoring, stale monitor data
being used for synthesis readiness, cached audio losing its actual sample rate,
unread denied POST bodies aborting the Windows response, malformed metadata/error
codes, and simulation imports of removed Human-test modules. Explicit regressions
cover these findings. Final inspection found no remaining confirmed issue in the
reviewed paths.

Verification:

- Human-test full suite: 674 passed, 2 skipped. The two skipped tests opt into a separately
  running Qwen clinical fixture; this migration instead qualified isolated native
  CPU and GPU workers through the real shared client. Final affected launcher
  suite: 112 passed after the last status/monitoring/port-policy fixes.
- Central manager, shared-client security and portable-package suite: 144 passed,
  plus 41 subtests. This includes credential permissions, one-attempt inference,
  malformed inputs, model pinning, live readiness and model/private-data exclusions.
- Actual Tk checks: pairing/reconnect/reset/cancellation, read-only Models and
  Practice action layout passed. No real platform enrollment was performed.
- Native CPU: verified Qwen3 1.7B, Whisper large-v3 and Piper English inferred
  through the SDK. Native GPU: Qwen/Whisper reported CUDA and inferred; Piper
  remained on CPU. Runs were sequential on the existing installed weights, with
  16 LLM GPU layers; they do not qualify simultaneous GPU capacity or performance.
- Both native runs closed the actual manager desktop, then confirmed inference
  from a new client through the resident LLM. Client disconnection has no stop or
  shutdown request. Isolated managers/workers were stopped by their test owner.
- Frozen dependency sync and CLI help/import checks passed; Ruff lint/format passed
  for 165 Python files and Git whitespace checks passed. No weights were downloaded.

Private evidence is under .test_artifacts/human-central-models-20261009/:
human-final-pass.txt, launcher-final-pass.txt, central-complete.txt, native-cpu.txt,
native-gpu.txt, connection-window.txt, setup-layout.txt and CLI help output.

Windows SCM installation/removal and reboot auto-start remain queued. The manager
is currently detached under the Windows operator. Pi networking/hardware, video AI,
physical microphone/camera quality, live cloud and publisher downloads remain
unverified/deferred. No API/database tests or migrations were needed for this
client/manager-only change. No VM update, hosted-download replacement, commit or
publication was performed. Run instructions and remaining boundaries are in
[local-model-client-migration.md](../docs/local-model-client-migration.md).
