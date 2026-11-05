# Human-test and the central API

Central inference extraction, implemented 2026-10-09: [shared local model service](local-model-service-plan.md)
records the independently managed laptop service now consumed by Human-test.
See [migration and client contract](local-model-client-migration.md). Pi LAN transport
and Windows SCM/reboot startup remain queued.

Human-test is a client of the same platform API used by the web UI. Its runtime and launch scripts contain no platform API application, SQL client, database provisioning, migration, identity minting or database retention service.

The client workflow now lives in [`training-client`](../shared/training-client/README.md).
Human-test supplies Tk views and desktop startup/configuration. The shared runtime
owns playback, listening, assigned-session leases and recording completion even
when no frontend consumes its notifications. A future Raspberry Pi host will use
this package; the current local-model transport still accepts loopback only.

| Responsibility | Owner |
| --- | --- |
| Sign-in, permissions, tenant/department scope, lifecycle checks | Central platform API |
| Users, devices, subscriptions, published scenarios/private Practice setup and device model assignments | Central platform API and its PostgreSQL database |
| Cloud provider credentials and processing | Central platform API; encrypted credentials remain on the backend |
| Local LLM inference | Central local-models manager and owned resident worker |
| Local recognition / synthesis | Central local-models workers through manager port 8790 |
| Capture/playback and bounded recording lifecycle | Shared training-client runtime and optional hardware adapters |
| Desktop controls, preview and presentation | Human-test Tk frontend |
| Durable conversation history | Central platform API; optional bounded local outbox retries uploads |
| Model downloads/provision/start/stop/diagnostics | Manage Local Models |

Platform Admin manages model definitions and assigns them to devices. The desktop reads those assignments and never publishes profiles or creates provider connections. The obsolete activation/cleanup mailbox has been removed. Stopping Human-test leaves the local manager, platform API and database running.

## Startup and routing

1. Start the central API and web UI using `start/start-platform.bat` (or use an existing API). Database configuration lives only in the backend.
2. Open Human-test and enter the platform address, device unique ID (or registration UUID) and enrollment token. The API returns the tenant/device identity and a device credential. No user login is required. Existing manual `.env` user sessions remain a compatibility path when no saved pairing exists.
3. Assign a conversation model through Devices > Configure model. Human-test refuses a missing assignment instead of provisioning demo data. Speech recognition is optional for typing; microphone input requires local Whisper or Azure OpenAI Whisper.
4. Start `start/start-human-test.bat`. Readiness/profile checks use the configured central origin, including a custom API port. Assigned local services must already be running in Manage Local Models; Human-test only connects.
5. Practice selection, conversation authorization/revalidation, cloud speech/answers and history upload use the same authenticated tenant API. Launcher readiness uses `/api/v1/health/ready` through the public HTTPS proxy and checks published scenario access. The desktop restores the device's private selection and saves all eight observations before starting a fresh conversation. Local inference uses the API's immutable published scenario/context and the inference-client credential. An API outage never starts a private backend.

Migration `0043_device_practice` adds exclusive user/device ownership to Practice selections, conversations and turn records. Device execution is limited to its tenant, department and assigned models. It grants no tenant administration or clinical authoring rights. Devices cannot read another device's conversations. Revocation, retirement, inactive scope and credential changes stop further access. Transfers retain the physical ID but use a new registration and credential; old conversations stay in their original scope. Existing human-owned records retain their ownership.

Pairing runs off the UI thread with progress, bounded network calls, cancellation and actionable errors. An uncertain enrollment response is never automatically retried. Successful enrollment is privately saved before connecting to local model services, so retries resume the connection without consuming another enrollment token.

Local LLMs use caller execution. The client connects to its configured manager port; published native ports cannot redirect it. The platform API and central manager must use different ports. Existing launchers must match the configured API, tenant, login, department and current profile/revision/hash before reuse; cloud assignment changes require reloading Models; local service changes are made in Manage Local Models, followed by reloading the assignment. A login renewal/change or department change requires restarting the desktop because an existing window retains its original credentials. Only a one-way login/scope binding is saved in launcher status.

## Local files and credentials

`human-test/.local/platform-connection/connection.json` stores the device credential and discovered identity with private filesystem permissions and atomic replacement. It never stores the enrollment token. `human-test/.local/platform-client/` stores private desktop handover configuration, status/logs, recordings and optional conversation outbox files. These are not application databases. `HUMAN_HISTORY_ENABLED=false` in `.env` disables transcript/answer archival. Metadata reporting remains separate. History records are partitioned by API origin, tenant, department and authenticated identity (device history uses `urn:pms:device` plus its registration UUID); upload verifies identity again through the central API.

Local inference processes and GPU probes do not inherit platform/desktop/provider/database credentials. The desktop receives only its selected platform token and the inference-only manager credential. API calls use bounded response parsing, safe errors, no redirects and no environment HTTP proxy.

The old `.local/demo/` data and private `start/cloud-models.json` are left untouched and unused. Cloud connection provisioning and API enablement now belong to the platform web UI/API and backend environment. Use `start/start-human-test.bat` as the desktop batch entry point. `--external-api` and `--processing-mode` remain compatibility options, not alternate backend modes; the old batch shortcuts under `human-test/` have been removed.

Verification uses local tests and mocked model/provider transports. It does not establish real cloud account readiness, microphone/camera quality or Raspberry Pi hardware behavior.


## Desktop connection management (2026-10-09)

The header gear exits Practice through normal conversation/audio/camera cleanup and reopens the device connection page. Clearing the connection removes only the saved desktop/device credential and handover settings. A cleared marker blocks legacy `.env` fallback. History, recordings, model assets and platform registration remain intact; fresh enrollment requires a new platform-issued token.

Human-test has no Offline Models tab, installers, engine launchers or model cleanup. Downloads, verified assets, native runtimes, CPU/GPU settings, provisioning, start/stop and logs belong to Manage Local Models. The connection screen directs users to `start/start-local-models.bat`. Client startup and reconnection perform read-only readiness checks; closing the desktop leaves central inference running.
