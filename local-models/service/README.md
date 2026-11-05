# Operator inference manager

`daemon.py` acquires a per-root process lock before opening state. The desktop
attaches or launches it as a detached process. Closing a desktop never invokes
manager shutdown. A daemon exit releases its owned inference process trees using
Windows jobs. No arbitrary PID is discovered or terminated.

The management surface is native, authenticated loopback only. It rejects
browser Origin/Cookie requests, incorrect Host/authentication, ambiguous JSON,
oversized/truncated bodies and slow request headers/bodies. HTTP inference and
mutations are never automatically replayed after an uncertain response.

| Route | Contract |
|---|---|
| `GET /v1/status` | Catalog, verified inventory, hardware, service readiness, configuration revision, latest operations and bounded logs; no credentials. |
| `POST /v1/actions/download` | UUID, approved `model_id`, explicit `device` (`cpu` or `gpu`). |
| `POST /v1/actions/provision` | UUID, revision, `capability`, verified model ID, explicit device, port, `start_at_boot=false`, optional bounded runtime options. |
| `POST /v1/actions/start`, `stop`, `remove` | UUID, capability, configuration revision. Remove preserves assets and requires stopped/failed workers. |
| `POST /v1/actions/settings` | UUID, revision and complete bounded defaults. Existing service options stay unchanged. |
| `POST /v1/actions/refresh` | UUID; recheck file integrity and hardware. |
| `GET /v1/operations/{uuid}` | Original durable action status; inspect this after an unknown submission outcome. |
| `POST /v1/infer/llm` | `messages`: up to 32 bounded system/user/assistant messages. Returns native completion JSON. |
| `POST /v1/infer/asr` | `wav_base64`, `language`: at most 30 seconds of mono 16 kHz PCM16 WAV. Returns text/segments. |
| `POST /v1/infer/tts` | `text`: 1–2000 characters. Returns bounded `wav_base64` and sample rate; no physical playback. |
| `POST /v1/shutdown` | Empty JSON; requires no pending operations and stopped workers. |

Workers have separate private keys and loopback ports, defaulting to 8797 (LLM),
8795 (recognition) and 8798 (synthesis). The LLM native child uses worker port plus
100. One worker per capability and one active request per worker are supported;
extra requests fail with capacity rather than creating an unbounded queue.
Stops drain admission before shutdown and resume admission if active work exceeds
the drain deadline. Occupied ports and unrelated processes are preserved.
Provisioning reserves the actual manager port and the native LLM child port.
Status distinguishes saved `configured_device` (`cpu`/`gpu`) from the worker's
actual `device` (`cpu`/`cuda`). A repeated start requires current readiness and
matching model/device before it can be reported successful.

Defaults and UUID actions are saved atomically, with revision checks and bounded
logs. The journal retains up to 2000 UUIDs and rejects further operations when
full. A manager restart marks unfinished operations interrupted without replay.
A failed metadata write rolls back in-memory changes; if operation/event recording
fails, mutations become read only while resident inference remains available.
Resolve storage errors and inspect outcomes before explicitly restarting.

Known catalog assets use publisher hashes and immutable source revisions. New
assets are staged, verified and published independently of active models. Runtime
preparation requires the manager-owned capability to stop and shares the existing
LLM installer lock. Installers use owned process trees, bounded deadlines and a
minimal environment. Clinical inputs and outputs stay ephemeral; native output,
credentials, prompts, transcripts and media never become operational logs.
Source locks and managed manifests are replaced atomically. Completed or
partially published conversion staging can resume without reinstalling verified
assets. Reusing a verified model does not require duplicate model disk space.

These are privileged operator model APIs, not clinical tenant/device grants.
Scoped platform sessions, conversation compilation, client migration and the
authenticated TLS/LAN gateway remain separate phases. This version does not
register with Windows SCM or configure reboot auto-start. GPU preflight checks
availability; complete GPU memory/concurrency qualification remains necessary.
