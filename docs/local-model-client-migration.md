# Central local inference clients — 2026-10-09

Human-test is now a consumer of the services managed by **Manage Local Models**.
Model downloads, verification, provisioning, CPU/GPU selection, resident engine
loading, service lifecycle and model diagnostics belong to `local-models/`.
Clinical/session authorization and case validation remain in the platform and
`training-contracts`; microphone, camera and physical speaker handling remain in Human-test.

## Start and use

1. Run `start/start-local-models.bat`. Download/verify the assigned model assets,
   provision the matching LLM and recognition services, and start them. Start
   synthesis as well when speaker output is needed.
2. Assign the matching conversation/recognition models in Platform Admin.
3. Run `start/start-human-test.bat`, enroll/reconnect, save Practice setup and train.
   Cloud assignments use the existing platform API. No local LLM/recognition
   service is required for those cloud stages.
4. After changing a local assignment, change the service in Manage Local Models
   and reload assigned models in Human-test. Reload also refreshes the central
   voice catalogue. Closing Human-test or the manager UI leaves inference running.

`human-test/setup.bat` installs only its locked client/capture dependencies.
There is no Offline Models tab, installer, engine launcher, port-kill helper,
GPU selector, model restart supervisor or native Piper implementation in Human-test.
Native qualification tools and voice installation tests have moved to local-models.
Existing local voice assets were moved intact from `human-test/.local/voices/`
to `local-models/.voices/`; the isolated TTS runtime is now central. Clinical
history, recordings, enrollment and older unused demo data are retained.

## Client contract and access

The reusable Python package lives at `local-models/client/`. Human-test installs
it as an editable dependency. Default endpoint: `http://127.0.0.1:8790`.
`HUMAN_LOCAL_MODELS_PORT` and `HUMAN_LOCAL_MODELS_STATE_DIR` support a separate
manager installation under the same Windows operator. The launcher reads
`client-key.txt` from that private state directory. It never gives the app the
operator or worker keys; keys remain excluded from session/history copies.

| Route | Consumer operation |
| --- | --- |
| GET `/v1/capabilities` | Verified installed IDs, aliases, voices and live readiness |
| POST `/v1/infer/llm` | One model-pinned, bounded completion; constrained fact decoding when applicable |
| POST `/v1/llm/inspect` | Whitelisted props/template/tokenize requests for exact prompt budgeting |
| POST `/v1/infer/asr` | Model-pinned mono 16 kHz PCM16 WAV, maximum 30 seconds |
| POST `/v1/infer/tts` | Approved voice, bounded text, validated bounded WAV |

The inference credential is rejected for downloads, settings, provisioning,
start/stop, operation journals, log/status inspection and shutdown. Requests
refuse redirects and environment proxies. Failed inference POSTs are never
replayed automatically. Explicit capacity rejections retain the existing bounded
busy policy. Metadata readiness checks may retry; model execution does not.
The published native `local_port` is declaration metadata: it cannot redirect
the client away from the configured central manager.

The manager executes no patient policy and receives no platform credential.
Human-test retains immutable context/revision/pack checks, evidence validation,
durable playback gates, private bounded journals and scoped metadata reporting.
Model readiness is probed live for clients; the desktop's monitoring cache is
used only for its UI. Neither client startup nor metadata refresh manages services.

## Delivery and remaining work

New Human-test builds contain one client/capture environment with the shared
inference client installed as an ordinary runtime dependency; engine binaries, weights, runtime installers and manager
credentials are excluded. GPU/model-bundling options and their legacy build/refresh tools are removed;
only Human-test modules are compiled/obfuscated. Local Models packaging is separate. Existing hosted downloads have not been republished.

Windows SCM installation and reboot auto-start remain the queued next phase.
The current manager is a detached per-operator process. Raspberry Pi code,
authenticated LAN/TLS pairing and remote transport remain future work; this
extraction supplies the shared inference contract and client, not verified Pi access.
Video model inference remains unimplemented in the current manager; Human-test's
camera continues bounded capture/recording. Live cloud, VM deployment and physical
microphone/camera/Pi checks were not part of this migration.

Verification evidence and the two review passes are recorded in
[pms-api-reviews.md](pms-api-reviews.md) and [manager-review.md](../local-models/manager-review.md).


## Verification and reconciliation

Two reviews and their fixes are complete. Human-test: 674 passed, 2 opt-in native
clinical tests skipped; final affected launcher checks: 112 passed. Central manager,
client permissions and packaging: 144 passed plus 41 subtests. Native Tk pairing,
Practice layout and Models checks passed. Separate real CPU and sequential CUDA
runs exercised the SDK with verified Qwen3 1.7B, Whisper large-v3 and Piper English;
inference continued after closing the manager UI. Ruff lint/format and whitespace
checks passed. No new weights, live cloud requests or deployment were used.

All requested ownership changes are implemented for LLM, recognition and synthesis.
Video AI, Pi access and genuine Windows SCM/reboot startup remain the documented
next phases. The detailed findings and evidence are linked above.
