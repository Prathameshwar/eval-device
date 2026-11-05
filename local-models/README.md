# Local models

This directory contains **Manage Local Models**, its independent background
manager, resident LLM/recognition/synthesis workers and the existing console Qwen
runtime. The [shared service design](../docs/local-model-service-plan.md) records
clinical authorization and queued Raspberry Pi/Windows-service work.

A separate [Windows portable build](../docs/local-models-portable.md) bundles the
manager and verified download flow without model weights or saved credentials.

## Manage Local Models desktop interface

Double-click [start/start-local-models.bat](../start/start-local-models.bat) to open
**Manage Local Models**. The existing **manage-local-models.bat** in this folder
and `python local-models/manage_local_models.py` remain available. The UI uses
Python's standard Tk/ttk desktop widgets and locally drawn outline icons; it does
not require Human-test or additional UI packages. Python must include Tcl/Tk
(included in the standard Windows Python installer).

Overview, Models, Services, Logs and Settings show a loading panel with animated progress until model inventory and hardware checks finish. A failed check or connection shows Try again. Once loaded, these pages show real manager data.
Download approved models and isolated runtimes, provision stopped workers, start
and stop inference, inspect readiness/events, export filtered logs and save
bounded defaults. The [control reference](desktop/README.md) lists every action.
Long operations run outside Tk and retain durable request IDs and progress.

**Closing the desktop leaves inference running.** The manager is currently a
detached per-operator process. Genuine Windows service installation and automatic
startup after a machine restart are queued next; the boot checkbox stays disabled.
Video analysis also remains planned; recording requires no model. Human-test uses
the manager through its inference-only client; Raspberry Pi code remains planned.

The manager is authenticated and binds only to `127.0.0.1:8790`. Private state and
keys live in ignored `.manager/`; new verified assets use ignored `.library/`.
Existing model assets are verified and reused without moving them. Model loading
never downloads. CPU/GPU selection is explicit; incompatible GPU execution fails
instead of silently using CPU. Audio/voice installation requires `uv` and uses
frozen runtime projects without changing Human-test's environment.

Run `manage-local-models.bat --preview` for the original sample-data layout.
`python local-models/manage_service.py status` inspects the manager;
`connect` starts/attaches to it and `shutdown` requires stopped workers and no
pending operations. See [implementation and review evidence](manager-review.md).

UI verification: `python local-models/tests/desktop_layout_smoke.py` checks the
preview; add `--live` for real HTTP/control checks with fixture engines. The
separate `native_manager_smoke.py` opt-in uses existing native CPU models; add
`--gpu` to select CUDA for supported LLM/recognition workers. It checks actual
device execution, desktop closure and cleanup of its isolated manager/workers;
it never downloads. Sequential CPU and CUDA inference passed with installed
Qwen3 1.7B, Whisper large-v3 and CPU Piper. Concurrent GPU capacity, live publisher
downloads/conversions and Pi/cloud integration require separate qualification.

## Existing console inference

Double-click **start-llm.bat** in this folder. It verifies the local files, loads Qwen 3.5 4B once, starts an authenticated API on this laptop and opens a text conversation in the same console. Type in English or Hindi. `/reset` clears the client conversation; `/quit` exits and releases the model. The inference model remains resident across messages. No chat history is written to disk.

The first installation must finish before launching. Native inference verification and measurements are recorded in [validation.md](validation.md). The follow-up implementation review is in [review.md](review.md).

## Entry points

| File | Action |
|---|---|
| `start-llm.bat` | Start the model and chat in the console; stopping it releases the model. |
| `start-server.bat` | Keep the local inference API running; Ctrl+C stops it. |
| `chat.bat` | Chat with the already running instance without loading another model. |
| `setup.bat` | Install/verify the pinned CPU runtime, optional CUDA runtime and model. Downloads resume by completed chunks. |
| `setup.bat --cpu` | Install CPU runtime and model only; then use `start-llm.bat --cpu`. |
| `start-llm.bat --cpu` | Explicit CPU inference for this launch. |

All launchers work from other working directories and keep their assets/configuration in this folder. Python 3.12+ (64-bit) must be on PATH. Python scripts use only the standard library; `requirements.txt` documents this. No Python virtual environment, system CUDA toolkit or system-wide package installation is needed. NVIDIA GPU mode does require a compatible installed NVIDIA driver.

## Model and runtime

- Default model: **Qwen 3.5 4B Q4_K_M**, GGUF, 2,740,937,888 bytes. The installer verifies the pinned publisher SHA-256 in `assets.lock.json`. The older Qwen3 models remain explicitly selectable.
- Runtime: pinned llama.cpp **b11046**, Windows x64, MIT license; GPU package built for CUDA 12.4. CUDA libraries are installed within `.runtime/cuda`; vendor licensing applies to those libraries.
- Default artifact: Unsloth Qwen3.5-4B-GGUF, pinned ModelScope revision `167b4afc359863325cb4164418c715421b4e9118`, SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`.
- Runtime/CUDA archive digests are pinned from [GitHub release metadata](https://github.com/ggml-org/llama.cpp/releases/tag/b11046) in `assets.lock.json`.
- Serving is offline. Model files and native binaries are installed explicitly and reused; no cloud inference, PMS connection, audio integration or automatic model/device fallback is enabled.

The installer verifies complete archive/model sizes and SHA-256 before publication, extracts only selected native executable/DLL/license files into a new bounded staging directory and refuses corrupt installed assets. It retries transient GET failures at most three times; permanent HTTP failures/checksum errors stop installation. Requests use normal TLS verification and no account credentials. A setup lock rejects concurrent installers before downloads or extraction. Completed download parts are cached for restart; download caches are not source code and can be removed after successful installation if disk space is needed.

## Configuration

Defaults are in `config.json`. Put overrides in ignored `config.local.json`, for example:

```json
{
  "gpu_enabled": true,
  "gpu_device_index": 0,
  "gpu_layers": 20,
  "context_size": 2048,
  "max_tokens": 100,
  "cpu_threads": 6,
  "prompt_cache_mib": 256,
  "port": 8787
}
```

The default is `gpu_layers=20` for both Manage Local Models and the standalone LLM launcher. `gpu_layers=99` explicitly requests all available layers on GPU; other positive values select partial offloading. Existing service settings and explicit overrides are preserved. `gpu_enabled=false` selects the CPU runtime and passes zero GPU layers/device none. Install the required runtime before changing mode. Restart after configuration changes. Unknown settings and out-of-range values fail validation.

`prompt_cache_mib` defaults to 256 MiB of system RAM for reusing prompt computation
between routing and answer calls. It accepts 0 (disabled) through 1024. This is
temporary model state in memory, cleared when the server stops; no prompt cache
is written to disk and slot-management endpoints stay disabled. Existing config
files without this setting use the default. Restart Qwen once to apply changes.

`start-llm.bat --gpu-layers 16` overrides the layer count for that launch without editing config. Values must be 1–99; it cannot be combined with `--cpu` or `--connect`, and requires GPU enabled in config. Human-test no longer chooses GPU layers or starts native servers; provision compute and limits in Manage Local Models. The standalone LLM launcher keeps its explicit device policy.

The initial console profile uses one inference slot, a 2,048-token context, a 100-token output limit and thinking disabled. Direct authenticated API clients can override generation defaults; this standalone native API is intended for trusted local callers. The context includes instructions, previous messages and the new question. Long conversations can exceed it; use `/reset` instead of silently dropping patient facts. The console caps individual input sizes but has no limit on the number of conversation messages. Responses that hit the output cap are marked in the console.

Full GPU mode checks available VRAM. Readiness confirms the exact requested layer count for both full and partial GPU modes. It fails clearly if the GPU cannot be used; it does not silently switch to CPU. The combined launcher has now been tested on the 4 GiB RTX 500 Ada with Whisper large-v3 CUDA and 16 Qwen GPU layers together; see [the launcher GPU audit](../docs/start-launcher-audit.md#automatic-gpu-selection-correction). Running both models fully on GPU can exceed available VRAM. This sharing check does not cover additional GPU applications or future TTS workloads.

## Local API and privacy

The native server binds to **127.0.0.1 only**, port 8787 by default. Completion/model endpoints require a generated API key stored in `.state/api-key.txt`, readable by the installing/running Windows account and SYSTEM. The launchers read it internally; it is never printed or placed in command-line arguments. Use the same Windows account to install/run. Concurrent first launches serialize key creation and reuse the same complete key. Health is a public local readiness endpoint. This is a single-operator local service, not the tenant platform API.

The API supports `POST /v1/chat/completions` and streaming responses. Its default model alias is `qwen3.5-4b-local`. `scripts/client.py` provides the authenticated streaming client used by the console and the native checks. It uses direct loopback connections without system proxies, refuses redirects, bounds received events/output and never retries inference POSTs after an uncertain timeout/disconnect. `request_timeout_seconds` is a wall-clock network deadline, including slow response headers and incomplete streaming events. A failed or partial reply is not committed to console conversation history.

Native logs are consumed in memory; only numerical startup/device measurements are retained in the process. Prompts, replies and API keys are not logged. Console replies are visible on screen. Web UI, tools/agents, slot monitoring and persistent prompt-cache storage are disabled. The local server can retain its current model/context in RAM until stopped. No scenario rules, clinical validation, speech output or patient behavior engine is implemented by this standalone runner.

A process lock prevents a second launcher from loading another model. An occupied port is reported without terminating the existing service. The launcher owns its child process and uses a Windows job object to release the native server when the launcher exits, including abrupt closure. Ctrl+C and `/quit` also perform explicit cleanup. Cleanup still releases the job and instance lock after a process-termination error. `chat.bat --cpu` is rejected: choose CPU mode when starting the server.

## Checks

```powershell
python -m unittest discover -s local-models/tests -v
```

Run this from the repository root. The checks cover configuration/device selection, key reuse, unsafe credential paths, streaming boundaries, non-retry of uncertain inference, download integrity/ranges/retries, archive extraction and conditional CPU-only installation. Real inference evidence is separate in `validation.md` and `.test_artifacts/local-llm` at the repository root.

## Integrity errors

Setup deliberately refuses existing corrupt files. Repeating setup does not repair a checksum mismatch automatically. Stop the server, move the affected runtime directory, model file or download cache to a separate quarantine location, then run setup again. A final download checksum mismatch may require quarantining its matching `.parts` directory too. Keep the pinned `assets.lock.json` unchanged; never disable checksum verification to make installation pass.


## Optional smaller Qwen3

Qwen3 1.7B Q8_0 is available as `qwen3-1.7b`, with API alias
`qwen3-1.7b-local`. Run `setup-qwen3-1.7b.bat` to install its pinned, verified
1.83 GB GGUF, then `start-qwen3-1.7b.bat` for standalone chat. Add `--cpu` to
either batch for CPU installation/inference. The separate model and manifest
preserve the default Qwen 3.5 configuration. `config.local.json` can also
select `"model": "qwen3-1.7b"` for standalone launches.

For Human-test, assign the matching alias in Platform Admin, provision/start this
model in Manage Local Models and reload the device assignment. Human-test never
loads, replaces or restores a model process. Shared GPU capacity must be chosen
and qualified centrally.

## Optional QwenMedic

QwenMedic is available as the explicit `qwenmedic-v1` profile, with API alias `qwenmedic-v1-local`. Run `setup-qwenmedic.bat`, then `start-qwenmedic.bat` (or add `--cpu`). Qwen 3.5 4B stays the default. The setup downloads the publisher F16 asset, verifies it, and creates Q4_K_M using the pinned local quantizer. `config.local.json` also accepts `"model": "qwenmedic-v1"`. The same model/device selection applies to the console and API client.

**Current machine: model downloads are blocked by the corporate filter; QwenMedic inference is not yet verified.** See [medical setup, provenance and test status](../docs/medical-models.md).
# Patient prompts and PMS

`config.json.system_prompt` is the default for the standalone console chat. It now describes fictional patient interviews and requires supplied case facts. The native server does **not** prepend that prompt to API requests. Platform model assignments and immutable case contexts supply Human-test prompts; the desktop does not create or change model connections.

Selected-case practice uses the shared conversation compiler and exactly one generation. The prompt contains the complete permitted case, the selected language pack, recent complete conversation pairs, and the current question. Instructor-only and `never` facts are excluded before compilation. General questions use model knowledge; missing personal details remain unknown. There is no topic-router or automatic repair generation in this path. Completion-format validation is not a guarantee of factual correctness; semantic quality is measured separately.

English is the initial installed conversation pack. Auto is unavailable in patient conversations. A saved conversation pins its case, model configuration, pack version/hash and compiler version. Local patient output is capped at 256 tokens by default, with a 128-token safety margin. Complete old history pairs are pruned if necessary; required case facts and the current question are never silently discarded.

Run the live, fictional 45-question text evaluation from the repository root:

```powershell
human-test\.venv\Scripts\python.exe local-models\qualification\evaluate_patient_conversation.py --suite live --output .test_artifacts/english-live45.json
```

This starts and closes its own verified local model. It records actual answers, full prompt hashes, model artifact hash, call counts, tokens, and timings. It does not test microphone recognition or speaker playback. Review the saved answers before qualifying a model.

Platform assignments remain authoritative. Manage Local Models owns installation
and inference lifecycle; Human-test only consumes its inference gateway. See
[the shared client contract and migration](../docs/local-model-client-migration.md).
