# Manage Local Models controls

The default desktop uses the authenticated per-operator manager. `--preview`
shows an explicit sample-data layout and never connects to the backend.

| Control | Implemented operation |
|---|---|
| Overview / Models / Services / Logs / Settings | Navigate without loading models. |
| Category and Installed tabs, search | Filter the verified local inventory. |
| View details | Show capability, format, publisher terms, size and verification state. |
| Download model / Prepare runtime | Select explicit CPU/GPU, install an isolated runtime, download approved assets, verify and publish them atomically. Progress survives desktop closure. |
| Provision service / Configure service | Select a verified installed model, device, port and bounded runtime options. Configure preserves the saved values. Save a stopped worker configuration with revision checks. |
| Start Service | Verify files, probe resources/ports, launch an owned resident worker and require warmup/readiness on the selected device. |
| Stop Service | Confirm, close admission, drain active inference, then stop only the owned worker. On drain timeout, restore admission and report the failure. |
| View status / Refresh status | Update the open dialog with actual health, configured/actual execution device, model, active requests and load time. Show the connected manager port; enable configuration/removal only for stopped or failed workers. |
| View Logs | Open the selected capability's bounded operational events. |
| Log service/level/search filters, Follow latest | Filter events and control scrolling without changing retained logs. |
| Export Logs | Export the current filtered events to an explicitly chosen JSON file outside managed state/model/runtime storage. Linked destinations are rejected. |
| Save settings / Reload saved settings | Validate defaults and reject stale saves. Existing worker configurations retain their options. |
| Refresh / diagnose | Rescan hashes and GPU availability; this does not claim inference verification. |
| Reconnect | Attach to the existing manager, or start it if unavailable. Never replay an inference or mutation. |
| Remove configuration | Remove a stopped worker configuration while preserving model files. |
| Close window | Disconnect the UI; leave the manager and workers running. |
| Start when the machine boots | Disabled: Windows SCM installation and reboot auto-start are queued next. |
| Download video model | Disabled: video inference requires a specified analysis task and adapter. Recording itself needs no model. |

Long operations have durable UUIDs. Duplicate submissions with the same request
are idempotent. A reused UUID with a different request fails. Interrupted work
is labelled interrupted on manager restart and never silently reissued.
Invalid or disconnected submissions keep entered form values available.

The manager binds only to `127.0.0.1:8790`. Its key and worker configuration are
private to the operator and SYSTEM in ignored `.manager/`. Prompts, audio,
transcripts, generated output and native process logs are never persisted.
Only approved IDs and typed options are accepted; the desktop cannot supply
arbitrary commands, model URLs or provider credentials.

One worker per capability is supported. Preparation of a capability's shared
runtime requires its manager-owned worker to be stopped. Existing asset folders
are verified and reused without moving them. New assets use `.library/`; an
unverified legacy model can be downloaded into this separate managed library.
Corrupt managed assets are preserved for explicit operator inspection.

This is a detached Windows operator process, not an installed Windows service.
It survives desktop closure but currently does not restart after a reboot.
Human-test consumes inference through its shared client with platform-authorized
clinical context; TLS/LAN pairing and Pi code remain planned phases. Native workers provide model inference;
they do not duplicate tenant/session authorization or the conversation engine.


## Loading and initial preferences

The desktop displays Loading local models and an animated progress bar while
connecting or verifying model inventory, hardware and service configuration.
Action forms are unavailable until data is ready. Failed inventory/connection
checks show Try again; retry reconnects or rescans and never restarts inference.

New GPU-capable model/runtime selections default to GPU. CPU-only adapters remain
CPU. New LLM provisioning prefers installed Qwen 3.5 4B when available; an explicit
model-card selection and saved service configuration take precedence. The factory
GPU layer count is 20. Untouched legacy factory preferences upgrade from 16 to 20;
explicit operator preferences and existing service options are retained.

Native regression: `python local-models/tests/desktop_loading_smoke.py` exercises
delayed connection/inventory, failures and retry, all five loading pages, initial
model/device/layer values and preservation of explicit choices using fixture data.


## Provisioning runtime options by capability

Runtime controls update immediately when capability, model or execution changes.

| Capability | Visible runtime options |
|---|---|
| Language model | CPU threads, context size, maximum output tokens; GPU device index and GPU layers in GPU mode |
| Speech recognition | CPU threads for Whisper/Nemotron; GPU device index in GPU mode. Vosk does not expose thread tuning. |
| Speech synthesis | Service startup and drain timeouts; the current Piper adapter has no provisionable thread/GPU controls |

Startup and drain timeouts are available for every capability. Draft runtime values
are kept separately for each capability; switching CPU/GPU also retains draft
values without parsing hidden inputs. Saved legacy worker configurations keep
their complete options and unchanged hidden values for compatibility. Only visible
inputs override that configuration during provisioning. Global default settings
remain available on Settings.

Native check: `python local-models/tests/desktop_provision_options_smoke.py` verifies
all capability/device combinations, Vosk/Piper controls, draft isolation, hidden
invalid inputs, language token-budget validation and legacy configuration saving.
