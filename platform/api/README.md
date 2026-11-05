# PMS API

Python 3.12, FastAPI, SQLAlchemy 2, psycopg and Alembic for PostgreSQL 17. See [architecture and phases](../../docs/pms-api-architecture.md), [TODO](../../docs/pms-api-todo.md) and [reviews](../../docs/pms-api-reviews.md).

## Local setup

From `platform/api`:

```powershell
uv sync --frozen
uv run pms-admin init-local
```

Edit the generated `.env` for your PostgreSQL database and optional OIDC configuration. Keep it private. `init-local` refuses to overwrite an existing file, enables password sign-in, and generates independent token/media secrets, a private installation key, an AES-256 credential key and a private Ed25519 training signing key. The training key is stored in `.local/training/training-private.pem` beside that environment file, and `PMS_TRAINING_KEY_FILE` is configured automatically. It does not create an administrator or store an administrator password. `.env.example` documents available settings. Install FFmpeg/ffprobe before accepting media uploads. The Docker image includes it.

Existing local installations are upgraded automatically by `start/start-platform.bat` or `pms-api`: if the key setting is absent, startup creates it once and updates `.env` without changing other settings. Repeated setup and restarts preserve the signing identity. An explicit environment override is validated, never replaced. If an API is already running with older settings, the launcher reports that it needs a restart; it does not stop an independently started service.

Current schema head is `0048_refined_starters`; apply it before starting this API/worker version. Provision the database owner plus three distinct, unprivileged PostgreSQL login roles: API, worker and retention. Set their URLs in `.env`; use the owner URL only as `PMS_MIGRATION_DATABASE_URL`. Provision role passwords outside source control. PostgreSQL URL connection options are preserved; runtime connections additionally enforce UTC, a 15-second statement timeout and a 5-second lock timeout. API and worker roles must not inherit ownership, superuser, role-creation or database-creation rights.

```powershell
uv run pms-admin init-database
psql -d device_platform -v db_name=device_platform -v api_role=pms_api -v worker_role=pms_worker -v maintenance_role=pms_retention -f deploy/grant-runtime-access.sql
```

`init-database` creates the configured application database if missing, then applies Alembic migrations. It requires an explicit deployment-owner `PMS_MIGRATION_DATABASE_URL`, access to the `postgres` maintenance database (or `--maintenance-database NAME`), and `CREATEDB` only when creation is needed. Existing data, database grants and category customizations are preserved; repeated runs do not duplicate seeds. On Windows, `platform/db/init.bat` runs the same command using this virtual environment and `.env`. PostgreSQL itself and login roles must already exist. For an existing managed database, `pms-admin migrate` remains supported.

Patient background: version 5 adds optional reviewed everyday background and bounded author-approved choices. Version 4 remains supported. Migration `0046_patient_background` preserves existing documents and adds database validation; reapply runtime grants. Conversations compile the selected background once into their immutable snapshot. Local defaults use 128 output tokens and two recent dialogue pairs, with exact native capacity checks. New English version 4/5 sessions use compiler 38: one generation selects literal fact IDs for personal/clinical answers, while clear general questions use a short knowledge prompt. Source IDs are validated against the fitted view and frozen snapshot before speaking stored text; missing evidence stays unknown. Admission reserves tokens for the actual selected prompt. Old snapshots retain their existing reply format. See [authoring and checks](../../docs/simulations/patient-background/README.md) and [starter refinements](../../docs/compact-starter-scenarios.md).

2026-10-04 scenario simplification introduced version 4 with Presentation & symptoms, History and eight Vitals. Q&A, Instructor content and fact-disclosure fields were removed by migration `0041_simple_clinical_cases`. Earlier version/lifecycle descriptions below are historical. See [scenario cleanup](../../docs/scenario-simplification.md).

Fresh initialization provides exactly three active Models page entries: **Whisper large-v3**, **qwen3.5-4b-local**, and **eSpeak NG**. Migration 0039 archives unused, unchanged extra starter entries with audit records; configured, tenant-owned, used or device-assigned models are preserved. Redeployment does not recreate deleted models or reset administrator edits. These are database defaults only; device installation and assignment remain separate. See [Models and device configuration](../../docs/platform-models.md).

Run `psql` as the database/schema owner with the correct host/port/user configuration. For an existing database created by the reviewed `platform/db/install.sql`, run `uv run pms-admin adopt-baseline` before initialization or migration. Adoption refuses structural drift; it does not modify or delete application data. Back up an existing database before deploying migrations. Downgrades intentionally refuse destructive removal; use a reviewed forward migration or restore the backup.

Migration 0011 adds the shared [scenario category catalog](../db/scenario-categories.md) with Cardiology, Nephrology and Respiratory Medicine defaults. It adds no patient scenarios and leaves existing specialty text unchanged. Reapply the runtime grant bundle: the API can read categories; category writes remain deployment-owner operations.

Migration 0012 adds [fictional patient identities](../db/patient-identities.md) with one Alex default (35-year-old male schoolteacher, 175 cm, 75 kg, English/Hindi). Initialization seeds it once and preserves later customizations. Migration 0027 adds platform-authorized catalog management; tenant practice selection keeps a private snapshot and does not rewrite historical cases.

### First-run web setup (recommended for password accounts)

After database initialization and runtime grants, start the API and web UI with
`start/start-platform.bat` from the repository root. Open `http://localhost:3000`.
An empty installation automatically opens `/setup`:

1. Paste the private `PMS_INITIAL_SETUP_KEY` from `platform/api/.env` (or your
   deployment secret configuration). It proves control of the installation and
   is never supplied by the public API or placed in a URL.
2. Choose the administrator's name, email and password (12–1024 characters),
   then confirm the password.
3. Review the details and create the administrator. Continue to sign in with
   that account. No email delivery or account-creation script is needed.

The password is stored only as an Argon2id hash. Account, credential and audit
record commit together using the least-privilege API database role. Setup checks
serialize on the administration lock, so concurrent requests create at most one
administrator. Any existing user, including an inactive/archived or external
identity, closes setup; this flow cannot replace or reset existing accounts.
Last-administrator database constraints keep setup closed after creation.

`GET /api/v1/auth/setup` returns only `required` and `available` and is never
cached. `POST /api/v1/auth/setup/verify` validates the installation key;
`POST /api/v1/auth/setup` revalidates it before creating the account. Both use
shared database rate limits. A missing key or disabled local authentication fails
closed. The key must be an independent random 32–512 character ASCII secret
without whitespace; `init-local` generates one. Existing deployments can leave it
unset. Remove it from deployment configuration after successful setup if desired.
Standard production mode requires HTTPS, SMTP and private storage settings for
email-based account administration. VM local mode uses HTTPS and private local
storage; authorized administrators share one-time setup and invitation links
manually because SMTP is disabled. Setup does not bypass those requirements.

### Optional trusted-operator CLI compatibility

For an external-identity installation, bootstrap the first administrator after
the operator verifies the OIDC issuer/subject:

```powershell
uv run pms-admin bootstrap-admin --issuer https://identity.example/ --subject verified-subject --email admin@example.com --name Administrator --verified-identity
```

This command is one-time and audited. Routine administrator changes use the platform API. External identities continue to use their provider for login and password management; there is no public administrator signup.

PMS local accounts use Argon2id password hashes, rotating server-owned refresh sessions, purpose-bound one-time actions, shared database rate limits, and an encrypted durable email outbox. They require an independent `PMS_LOCAL_TOKEN_SIGNING_KEY` and credential-encryption key ring. Configure SMTP and the action URL for invitations and recovery. Operators retaining the email-based CLI flow can bootstrap a first local administrator without placing a password on the command line:

```powershell
uv run pms-admin bootstrap-local-admin --email admin@example.com --name Administrator --verified-operator
```

The command queues a setup email and refuses to run after an administrator exists. Signing-key rotation invalidates outstanding local JWT access tokens; opaque browser sessions use the token pepper and must be revoked separately when rotating credentials after an incident; password or email changes revoke all local sessions. Expired sessions, actions, rate counters, and outbox rows are removed by the bounded API maintenance loop.

For a local development database without SMTP, `bootstrap-local-admin` also accepts
`--local-password-stdin`. Supply a private password of 12–1024 characters through
stdin, never as a command argument. This option requires `PMS_ENVIRONMENT=local`,
local authentication, the deployment-owner connection and `--verified-operator`.
It creates the first administrator with an Argon2id password, marks its local
setup complete and records an audit event; it does not queue email. It cannot
replace an existing administrator or run in test, staging or production.

Models are created and managed by Platform Admin under **Models**. Each model owns its local/cloud settings and any encrypted credentials. Platform Admin assigns models from **Devices > Configure model**, with one Local/Cloud choice and four optional model selections. There are no connection/profile management, validation, publication or binding APIs. Runtime metadata endpoints remain distinct from executable model configuration. See [the current model API and workflow](../../docs/platform-models.md).

Start the API and workers in separate terminals:

```powershell
uv run pms-api
uv run pms-worker
uv run pms-worker --retention
```

`pms-api` explicitly supplies a selector loop factory on Windows for psycopg compatibility. It binds to `127.0.0.1:8000` locally; `PMS_BIND_HOST` and `PMS_PORT` configure this. The start scripts provide the same commands on PowerShell and Unix. Database migrations are never run automatically by API replicas. Local API docs: `http://127.0.0.1:8000/docs`. `/health/live` checks the process; `/health/ready` checks PostgreSQL and the exact migration revision.

## Authentication and organization/device flow

1. Configure OIDC issuer/audience. Access tokens must have a trusted JWKS signature, issuer, audience, expiration, issued-at and subject. `POST /api/v1/identity/sync` registers or updates the verified identity. Test JWKS files are allowed only in local/test environments.
2. Read `GET /api/v1/subscription-plans` and create an organization with its required `subscription_plan_id`, then add departments and memberships. Invitations expire and require the invited verified email. When SMTP is unconfigured, the inviting administrator receives a one-time invitation token for manual delivery.
3. Create the Pi device (a laptop can substitute during development). The planned local transcription companion serves that Pi's logical device; it is not automatically another enrolled device. `preferred_language` is optional: null means English. `GET /api/v1/languages` lists active choices. Platform admins edit the catalog through versioned platform settings; English and Hindi are seeded.
4. Issue an enrollment token and exchange it at `POST /api/v1/device/enroll`. Store the returned device bearer credential securely on that device. Enrollment and device credentials are hashed in PostgreSQL.
5. As Platform Admin, create the required local/cloud models and select them in Devices > Configure model. Device `GET /api/v1/device/config` returns the effective language, policy, revision and configuration hash.
6. Apply settings on the device, then acknowledge revision/hash in a heartbeat. Report metrics/events through device endpoints. The included `scripts/device_probe.py` verifies configuration/heartbeat connectivity without falsely acknowledging installed engines.
7. Submit bounded processing requests with a client-generated UUID request key. Retries of the same body return the same run. A changed body with the same key returns 409. Local runs return normalized results from the device; cloud runs use the worker.

Registration timestamps, active flags, last-seen/activity and status information are available in their scoped management responses. Inactive device credentials can report basic health and receive restricted configuration; they cannot start work or fetch media/results. Retired/revoked credentials cannot authenticate. New processing also requires an enrolled device with a current credential when initiated by a human; pending work is cancelled after revocation. Re-enrollment restores processing eligibility. Platform administrator privileges do not grant tenant media access without an organization membership.

## Planned Pi and laptop execution modes

Raspberry Pi owns audio/video input and output: microphone/camera capture and speaker/display presentation. In **local mode**, it sends audio over local Wi-Fi to a connected laptop, where a selected installed OSS model produces transcript text and returns it to the Pi. The local target is a Windows CPU-based laptop with 16 GB RAM; Whisper `large-v3` INT8 and alternative multilingual models require Hindi/English accuracy and latency benchmarks before selection.

In **cloud mode**, the Pi contacts this platform API directly, without a laptop relay. The platform authorizes runs, grants bounded media access and dispatches provider calls through its worker. The Pi obtains results/generated media and performs physical output. Provider credentials are never distributed to the Pi or laptop.

A separate [standalone audio receiver](../../device/audio-process/README.md) now implements authenticated local audio streams and selectable multilingual Whisper models, loaded/warmed once at startup. It prints text to the laptop console, returns it on the stream, and saves audio/text through an independent bounded disk writer. Local recording defaults to 1 GB/1,000 sessions and seven-day retention, with client-scoped pending/saved/incomplete status. Safe transient local I/O has bounded retries and component-level storage fallback; explicit finalization flags prevent incomplete recordings being treated as saved. An optional receiver callback is disabled, with bounded retries prepared only for connection failures before submission. It has **no PMS API/server connection**. Pi hardware, platform device/run/configuration binding, model-selection/capability extensions and the video-display contract remain future work; no streaming endpoint was added to this PMS API release. Local results will remain associated with the Pi's authorized run; no implicit cloud fallback is allowed. See the [confirmed execution plan](../../docs/platform-service-plan.md#71-how-the-raspberry-pi-will-work) and [implementation backlog](../../docs/pms-api-todo.md#pi-inputoutput-and-laptop-transcription-follow-up).

## Encrypted connections

Create/update provider credentials in the connection API's `credentials` object. Use HTTPS in deployed environments. Accepted secret fields are `api_key`, `client_secret`, or `access_key_id`/`secret_access_key`/optional `session_token`, according to the selected authentication mode. Settings contain only resource/routing values. The server encrypts with a random nonce and authenticated organization/connection binding; normal responses expose only `has_credentials`.

The key ring is `PMS_CREDENTIAL_KEYS` (JSON map of key IDs to base64-encoded 32-byte keys); `PMS_ACTIVE_CREDENTIAL_KEY` selects the write key. Keep keys in deployment secrets, separately from PostgreSQL backups. To rotate: deploy a key ring containing old and new keys, select the new active key, run `uv run pms-admin rotate-credentials`, validate affected connections, then retire old keys only after all live ciphertext and required backups have a recovery path. Ciphertext rotation and activation/deactivation advance the database connection version and invalidate validation; stale validation responses are rejected.

Legacy baseline `secret_ref` values are retained for adoption but must be replaced with encrypted credentials through the API before those secret-based connections are used. They are not fetched from a secret manager.

## Processing and media

Profile section audio duration and video duration/dimensions/frame-rate limits tighten effective capture policy. Run admission, default quota reservations and actual upload inspection use these limits. Current organization/platform caps also clamp the configuration returned to devices; published revisions and existing run snapshots stay immutable.

Synthesis format, language/voice and request-length checks run before provider submission. Device polling includes cloud requests awaiting capture/upload and prioritizes actionable work/playback over completed history. Automatic expiry and cancellation produce operational activity events.

Uploads use short-lived access URLs issued only after authorization. Finalization checks actual container/streams, duration, resolution, frame rate and size; video-only processing rejects embedded microphone audio. The worker verifies the recorded SHA-256 before staging, detecting overwrites after upload completion. Keep storage private and configure a storage-level lifecycle as a secondary bound for orphaned uploads/provider staging.

Human media access rechecks tenant/department permissions when issuing URLs. Local URLs also recheck identity on use; cloud presigned URLs have a maximum 60-second revocation window. API logs omit URLs, tokens, request bodies and provider error payloads. Configure the reverse proxy to redact signed paths/query strings too.

Synthesis can request playback. `audio.playback` can select a successful generated-audio `source_run_id` for the same device, bounded by the source media expiration; arbitrary external media URLs are not accepted. Playback is acknowledged separately and uncertain playback is never automatically replayed.

Workers persist leases and submission intent, recover abandoned claims, poll known jobs and reconcile uncertain submissions. AWS processing clients make one transport attempt per call; durable workers decide whether retry or reconciliation is safe. Provider outages back off. An administrator's `resolve-submission` operation requires a recorded provider-verification statement and reason. Cancellation stops future work and prevents a delayed result from reopening the run; already accepted external work is polled to completion before cleanup.

The retention worker redacts expired results and deletes only expired, terminal, cleaned-up records with resolved submission/playback and no live lease. Cleanup failures/uncertainty remain visible for operations. Already-redacted unresolved rows do not block maintenance of later expired records. Keep both workers running. Monitor failed/unknown runs, overdue cleanup, queue age and worker heartbeat through your process supervisor and database metrics.

## Tests and delivery

```powershell
$env:PMS_TEST_ADMIN_DSN='postgresql://postgres@127.0.0.1:55441/postgres'
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/pms_api
uv build
```

Integration tests create uniquely named disposable databases/roles on the explicitly configured test server. They never reset an existing application database. Use a dedicated local PostgreSQL instance; the test login needs permission to create databases and roles. Unit tests run without this DSN; database tests are skipped when it is absent. Provider behavior is mocked, not contacted live.

From the repository root, build with `docker build -f platform/api/Dockerfile -t pms-api .`; run the API, processing worker and retention worker as separate instances of the image. The image runs as a non-root user. Disable the HTTP healthcheck on worker containers and use supervisor/process liveness. Supply configuration via deployment secrets; staging/production require HTTPS OIDC/public URLs and private S3/Azure storage. Apply migrations and runtime grants once before starting replicas. Restrict network access to PostgreSQL, approved provider endpoints and private storage; rate-limit authentication, enrollment and uploads at the ingress.

Live OIDC/AWS/Azure verification, cloud IAM/resource setup, hosted deployment and Raspberry Pi hardware/ARM verification remain deferred. Do not enable `PMS_EXTERNAL_CALLS_ENABLED` or provider settings until those resources are intentionally configured. Connection access checks are distinct from end-to-end sample runs and do not claim that real audio/video processing has already been verified.

The compose file runs the API and two workers after database provisioning. For a host database on Docker Desktop, use `host.docker.internal` in the container database URLs. Use a runtime environment file without the owner migration URL, and remove it from the runtime process environment after administrative setup. Docker/Compose execution was not verified on this workstation because Docker is unavailable.

## Verified delivery

The local suite covers PostgreSQL permissions/lifecycle, migrations, backup/restore, encrypted credentials, language selection, media inspection, worker fencing, playback and retention. Current test counts and review evidence are maintained in the review log and TODO. The planned and subsequent database/API review/fix passes are recorded in `docs/pms-api-reviews.md`. Lint, formatting, type checking, package build and real Windows API/worker startup checks passed. External and Docker deployment checks remain deferred as described above.

Database/API tests require PostgreSQL 17 client tools on PATH (or `PMS_TEST_PSQL` pointing to psql). They run the actual deployment grant bundle and verify migration adoption plus current-schema backup/restore.

## Organization subscriptions

Standard and Advanced are seeded at INR 350,000 and INR 500,000. Confirmed default caps are 200 users/1 device and 500 users/3 devices, respectively; the billing period is unspecified. Platform admins edit prices, INR/USD currency, period, caps and active status through versioned plan PATCH, and assign an organization's plan through the platform subscription endpoint. No payment, conversion or renewal operation is performed.

Active memberships plus unexpired invitations count as user seats; active device records count as device seats. Creator/admin and trainee memberships count. Revocation alone does not free a device seat; deactivate or retire it. Invitations, resends, acceptance, reactivation, administrator assignments, lower plan limits and downgrades enforce caps through serialized database guards. Existing organizations adopt Standard without losing records; summaries expose over-limit usage. Full [fields, counting rules and endpoints](../db/subscriptions.md).

Migration 0006 updates untouched provisional capacity pairs while preserving customized limits and existing records. Organizations above the new cap cannot add capacity until they free seats or upgrade. Migration 0006 adds no grants; deployments upgrading from before migration 0005 require reapplying `deploy/grant-runtime-access.sql` before restarting API/worker processes. New organization requests without a plan ID return 422. Quota conflicts return 409 with `subscription_user_limit` or `subscription_device_limit`.


## Standalone laptop companions

Local [audio transcription](../../device/audio-process/README.md) and [video recording](../../device/video-process/README.md) run as separate services. The video API receives and saves only; optional frame extraction is an offline CLI operation. Neither companion currently connects to PMS or its database. Pi/platform configuration binding and hardware integration remain deferred.


## Patient interview pilot

Migration 0007 adds organization-scoped approved scenario versions and device/learner sessions (15 domain tables, 277 columns total). Reapply `deploy/grant-runtime-access.sql`; API inserts/updates and retention deletes for these tables are explicit. Existing baseline SQL and migrations remain unchanged.

Local setup and the managed Ubuntu deployment automatically configure `PMS_TRAINING_KEY_FILE` with a persistent private Ed25519 PEM outside PostgreSQL. The VM stores it outside release folders, with read access limited to the API service. Deployments validate the key as the API account and check `/api/v1/training/verification-key` before reporting success. Keys are not rotated on deployment or restart. A missing, malformed, linked or unreadable previously configured key stops setup; restore that key rather than silently changing device trust.

For a separately managed installation, run `uv run pms-admin init-training --env-file /private/api.env` once with the API dependencies installed. Optional `--default-key`, `--runtime-directory` and Unix `--key-group` arguments support operator-managed locations; an existing setting takes precedence over the default. This command is idempotent and does not print private key material. Back up the key securely alongside deployment secrets. Container deployments must mount the persistent key read-only at the configured path; it is not embedded in the image or transfer archive.

Distribute only the public key through a trusted channel to the paired laptop/Pi; grants expire after `PMS_TRAINING_LEASE_SECONDS` (default 30, maximum 60). Automatic server provisioning does not change device trust or bypass enrollment. Custom deployments may still omit training for other platform operations, but creating/leasing a training session fails closed without its key.

Training routes are under `/api/v1/organizations/{organization_id}/training`: scenario create/list/approve/retire; session create/list/read/access/stop/rubric/feedback. Device routes provide `/device/training/next`, `/device/training/sessions/{id}/lease`, and idempotent `/result`. Session creation reserves concurrency, audio/video seconds and TTS characters against the same organization policy as processing runs. Device/profile revisions, instructor/learner scope and educator approval are rechecked on lease renewal. Late result receipts can attach once to closed sessions without reopening or changing terminal status. Feedback uses version checks and the immutable scenario rubric. No media bytes or transcripts are stored in these platform tables or audit records.

See [pilot setup and workflow](../../device/training/README.md), [design](../../docs/patient-interview-pilot.md), and the maintained TODO/review evidence. Native/fixture results are not Pi hardware, live OIDC deployment, cloud or clinical acceptance.


## Scenario authoring storage

Migration 0008 adds bounded private drafts and immutable publication provenance. Apply the migration and runtime grants, then run `psql -X -d <database> -f deploy/verify-scenario-library.sql` as the schema owner. See [storage fields and transaction contracts](../db/scenario-library.md). The authoring APIs below build on this storage. The existing version-1 pilot remains the executable contract; version-2 execution is deferred.


## Patient Scenario Library authoring API

The [authoring API runbook](deploy/scenario-library.md) documents draft creation/copying, revisioned edits, validation and patient preview, atomic educator-approved publication, safe/private retrieval, retirement, permissions, limits, and retry behavior. Fictional Hindi/English examples are packaged in `scripts/scenario-examples`. The original library uses migration `0008_scenario_drafts`; migration `0033_tenant_training_starters` added clearly labeled system starter provenance. Current migration `0035_unified_scenarios` adds tenant specialty/submission metadata, published-scenario Practice selections and tenant defaults. New version-3 drafts follow submit, independent language review and publication; published version-3 snapshots support the laptop conversation runtime. Version-2 cases can be authored and published, but execution is explicitly blocked until the later Pi/laptop runtime upgrade. Existing version-1 sessions remain supported. Generated patient dialogue, dynamic physiology and hardware verification remain deferred.

Scenario-library delivery verification: 105 platform tests passed with no skips, 12 companion regressions passed, and both implementation reviews/fixes are documented in the review log. Existing database migrations remain unchanged. The full suite includes the new authoring/security/concurrency checks and earlier database upgrade/permission/backup coverage.


## Local LLM and microphone test

Migration `0009_local_llm` adds encrypted local-model connections and bounded, scoped, idempotent inference requests. JSON and SSE use one resident model through a pooled async client, with no automatic inference replay. See the [LLM API runbook](deploy/local-llm.md) and [human-test desktop launcher](../../human-test/README.md). Enable `PMS_LLM_ENABLED` explicitly and apply the updated runtime grants; cloud calls remain separately disabled.

Migration `0010_llm_providers` preserves local connections and adds OpenAI and explicitly allowlisted OpenAI-compatible Chat Completions endpoints. JSON/SSE, encrypted keys, token reservations, cancellation and scoped access use the same PMS API. External calls remain off unless enabled by the operator. See [provider configuration and token handling](deploy/llm-providers.md); the desktop still receives only a PMS connection ID, never a provider key.
# Patient setup and rehearsal

The `patient-practice` organization routes list only the tenant's active clinical specialties, fictional patient profiles and cases, then save a private setup for the staff account. They require explicitly assigned organization-wide `org.clinical.author` and `org.processing.execute` permissions. Historical global selections remain readable but cannot start a new conversation; staff must save an active tenant case. Case and profile content must cover the selected conversation language, and staff must supply all eight initial observations. Selected-case completions attach server-built context, enforce snapshot revision/lifecycle, budget the 2,048-token local model and return scripted patient answers selected by Qwen. See [API and storage contract](../db/patient-practice.md). This staff preview does not activate version-2 Pi training sessions or bypass clinical approval.


## Published local/cloud model selection

See [cloud model setup and API contracts](../../docs/cloud-models.md) for Azure OpenAI Whisper, Azure/direct OpenAI LLMs, per-model parameters, complete patient-turn token accounting and the interactive speech API. Published profiles now bind the conversation LLM as well as speech. Provider keys remain encrypted in PMS. Cloud inference is not implicitly enabled by selecting a profile.

Migration `0017_llm_total_quota` enforces organization-wide online defaults of 5,000 requests and 5,000,000 combined input/output tokens per UTC day. Local execution is exempt. Atomic admission reservations settle to complete provider usage; unknown usage remains reserved. See [quota configuration and upgrade](deploy/llm-providers.md).

## Client-reported local conversation archive

Migration `0018_local_conversation_history` adds optional paired text history independently of local inference and the existing metrics endpoint. Enable `PMS_LOCAL_HISTORY_ENABLED` after migration and runtime grants. The authenticated `/organizations/{org}/llm/local-conversation-turns` routes enforce ownership/scope, exact idempotency, capacity and expiry. PMS never invokes a local model through these routes. See [contract and operational limits](../../docs/local-conversation-history.md).

## Browser sessions and account-action upgrade

Migration `0022_browser_sessions` follows `0021_events_platform_audit_idx`. It adds a unique peppered browser-token hash, binds account actions to credential versions, and expands shared rate-limit categories. Existing credentials and bearer sessions are preserved. Existing reset/setup actions adopt the current credential version; old pending email-change actions are consumed because their authorization version cannot be proven. Users with pending email changes must request a new confirmation. Reapply the runtime grant bundle as part of deployment; processing and retention roles do not gain access to authentication tables.

`POST /api/v1/auth/browser/login` accepts `email`, `password` and optional `remember`, and returns an opaque `session_token` plus `expires_in`. It uses the same locked credential check and auditing as bearer login. The web server holds this credential in an HttpOnly cookie and uses it as a bearer credential to the API. `GET /api/v1/auth/context` returns current identity and separate active platform/organization contexts. Browser sessions are stable across concurrent tabs and expire after `PMS_LOCAL_BROWSER_SESSION_HOURS` (24 hours by default), whether or not `remember` was selected. Remembering keeps the cookie across browser restarts until that deadline; an unremembered cookie ends when the browser closes. Account status, expiry, credential version and revocation are checked on every request. The web console checks an open session periodically and on tab focus, and sends expired sessions to sign-in. Existing `/auth/login` and rotating `/auth/refresh` remain available to bearer clients; browser credentials do not use bearer refresh tokens and cannot be renewed past their deadline.

Credential mutations serialize on user, credential, then session/action rows. Password rehashing cannot overwrite a password changed while login was verifying it; in-flight email/password changes reauthorize the session under those locks. Password/email changes consume old actions and revoke existing sessions. Setup/reset/email links now use fragments, keeping new tokens out of HTTP request URLs and referrers. Set `PMS_ACCOUNT_ACTION_BASE_URL` to the web application's `/account` base. Do not log request bodies, cookies, Authorization headers, or legacy token query strings at the proxy.

The original baseline seed has been restored without a default administrator. If an earlier altered seed was manually applied to an existing database, an operator must rotate that account's password and revoke its sessions; this change does not modify an application database automatically.

## Web user/member CRUD

The web user directory uses `/platform/users` for filtered cursor paging, local
creation, detail, profile/role/status edits, archive/restore and setup resend.
Responses expose only a `setup_pending` boolean, never credentials or setup tokens.
Local names/phones can be edited; external profile fields remain provider-owned.
`platform_role=none` selects ordinary accounts. Administrator creation and changes
require both user management and administrator management permission.

Tenant membership routes remain under `/organizations/{id}/members` and
`/invitations`. List/detail/edit responses consistently include the accepted user's
name, email, authentication method and availability. The directory supports
`archived` and effective pending/expired invitation filters. Joined-date cursors use
a fixed null sentinel. Invitation acceptance increments the membership version and
revalidates department availability. Resend rotates the token and increments the
version; closed invitations cannot be enabled or silently accepted.

User/member DELETE and invitation resend/revoke accept optional positive
`expected_version` query guards for existing client compatibility; the web always
sends them. User setup resend also accepts the guard and returns the updated user.
Restore requires a version and returns a disabled record. Membership activation
requires an accepted invitation, available account and active department. Existing
PostgreSQL uniqueness, seat quota, deferred last-administrator constraints and
atomic audit writes remain authoritative. No schema or runtime grant change is
needed for these routes.

Configure `PMS_INVITATION_BASE_URL` to the web `/invitations/accept` route. New links
use fragments, not token query parameters. SMTP failure returns a one-time token
only to the authorized inviter for private delivery; the directory never returns
tokens. Local account setup still uses the encrypted durable mail outbox. In VM
local mode, platform user creation and setup resend return a one-time setup token
only to the authorized administrator; a new local tenant invitation returns its
setup token to the authorized tenant inviter. These responses use `Cache-Control:
no-store`; list and detail responses never include the token. The web shows a
fragment-based setup link and, when applicable, a separate tenant invitation
link. Share both privately, with setup first. A platform administrator can
regenerate a lost setup link, invalidating the previous link. Self-service
password recovery and email change remain unavailable without SMTP. Invitation
acceptance still requires the matching signed-in identity and authentication method.

## Retained audit and activity logs

Read-only directories and direct details:

- `GET /platform/audit` and `GET /platform/audit/{event_id}` require
  `platform.audit.read`. They expose administrative audit across tenants, never
  operational events or tenant media.
- `GET /organizations/{organization_id}/activities` and
  `GET /organizations/{organization_id}/activities/{event_id}` require an active,
  accepted membership and available organization/department. Operational records
  require `org.activity.read`; audit records require `org.audit.read`. Historical
  department scope is checked against the event, not a device's current department.
  Platform administration alone grants no access to these tenant routes.

Lists support `category=audit|operational|all` (tenant default: operational;
platform: audit only), `q` (event type, entity type or event ID; literal
case-insensitive substring, maximum 128 characters), `severity=info|warning|error`,
`actor_type=user|device|system`, UUID filters `organization_id`, `department_id`,
`device_id`, `actor_user_id`, `entity_id`, `run_id`, and timezone-aware
`since` inclusive / `until` exclusive occurrence timestamps. Both categories
require both permissions. A query tenant/department ID can only narrow access.

Use `sort_by=id|occurred_at|received_at|event_type|severity`,
`sort_order=asc|desc`, `limit=1..100`, `cursor` and `include_total=true`.
Responses contain `items`, `next_cursor`, `has_more` and optional `total`.
Defaults retain ID-ascending legacy pagination; explicit sorts use filter/scope
bound signed keyset cursors with ID tie-breaking. Changed filters require a fresh
cursor. Expired events are excluded immediately, even before retention cleanup.

List and detail projections share a bounded metadata allowlist in
`modules/activity.py`. Unknown payload fields, credential-like strings and URLs
are omitted; `details_redacted` indicates omissions. This may hide historical or
custom fields until explicitly reviewed. Search never inspects hidden payloads.
The UI does not expose prompts, transcripts, media or raw provider responses.
Adding a producer must keep secrets/content out of activity metadata at write time.
No log mutation endpoint, new grant, migration or change to retention is introduced.


## Device association and lifecycle management

Platform administrators use limited fleet routes under `/api/v1/platform/devices`.
`platform.health.read` permits summary list/detail reads; mutations require
`platform.organizations.manage`. Only platform administrators register devices.
Tenant administrators use `/organizations/{organization_id}/devices` with
`org.devices.manage` for private fields, department, enrollment, and lifecycle
within an active, accepted membership. They cannot change the model profile. Platform access does not issue enrollment credentials or
expose private configuration, contact details, location, results or media.

| Route | Behavior |
| --- | --- |
| `POST /platform/devices` | Register with an active, unarchived tenant; accepts organization ID, name, `manikin` or `laptop` type, optional language, active status, and a published same-tenant processing profile. |
| `PATCH /platform/devices/{id}` | Change public name, active status, or the published same-tenant processing profile. |
| `GET /platform/organizations/{id}/device-model-options` | List active published profile names, revisions, and per-operation Local/Cloud model labels for device assignment; excludes drafts, credentials, prompts, and private media. |

Human-test can set `HUMAN_DEVICE_ID` to follow an active, enrolled device. A tenant-authenticated human may send `device_id` to `GET /organizations/{id}/model-options` and `GET /organizations/{id}/model-config`; the API verifies tenant and department scope, then returns only that device's assigned published profile (or its tenant default). Device-bound model options are read-only. The local launcher discovers installed speech and LLM files on its own machine; these platform endpoints report only declared published model names.
| `POST /platform/devices/{id}/revoke` | Revoke the credential and outstanding enrollment token. |
| `DELETE /platform/devices/{id}` or `POST /platform/devices/{id}/retire` | Remove the registration by terminal retirement; preserve historical ownership. |
| `POST /platform/devices/{id}/transfer` | Retire the source and atomically create a fresh registration in another active tenant. |

Platform mutations of existing devices require the summary's `management_etag`
as `expected_etag`: body for PATCH/transfer, query for revoke/retire/DELETE.
Every web mutation carries this guard and the selected context. Existing tenant
API guards remain optional for compatibility. Stale snapshots fail with 409;
heartbeats do not change the management version. Both list routes accept
`enrollment_state=current` to exclude retired records (the web default); omitted
filters retain the existing API behavior of including all states.

The optional `profile_id` on fleet create/update binds an existing published
profile in that device's tenant. A null assignment uses the tenant default.
The profile and media provider connections remain tenant-managed. LLM
connections and their credentials are tenant-scoped but platform-managed. The
device receives the profile's operation routing through its existing
configuration endpoint; changing the assignment changes its configuration hash
and requires a fresh device acknowledgement before device-submitted work.
Unavailable or cross-tenant profiles are rejected, including on reactivation.
The platform summary includes only the assigned profile ID/name. Local routing
does not itself attest GPU hardware; the device runtime must support the local
engine and GPU acceleration. No schema migration or new database grant is needed.
Migration `0032` adds `manikin` while retaining old `raspberry_pi`/`other` values
for historical registrations. New registrations use only **Manikin (Physical)**
or **Laptop (Software)**.

Transfer accepts `organization_id`, `name`, `expected_etag` and optional
`is_active` (default false). It returns `{source, device}` as public fleet
summaries. Only platform administrators can transfer between tenants. A move
creates a new UUID and copies the hardware type; all history, private fields,
assignments and credentials stay with the source. Language is unset and resolves
through the normal English fallback. The destination administrator must configure,
activate and freshly enroll the new registration. The old credential and pending
enrollment token cease working. There is no tenant-to-tenant transfer route or
in-place organization reassignment.

Deactivation is reversible and frees an active-device seat while allowing
restricted health/status checks. Processing authorization remains subject to
existing API, worker and offline authorization rules; already submitted external
work is not synchronously recalled. Removal and transfer retire permanently and
revoke authentication. Reactivation validates tenant availability, department,
profile and available quota. Unchanged unavailable assignments do not prevent
deactivation or unrelated edits. Database quotas and the administration/device
locks serialize concurrent changes. Failed transfers roll back source retirement,
destination creation and both audit events together. No schema migration, runtime
grant expansion or historical record rewrite is required.


## Manual tenant subscriptions

The web **Settings > Subscriptions** page uses the existing plan catalog and new
manual term/history APIs. Platform administrators manage plan assignment, dates,
renewal by date extension, suspension/resumption, cancellation, internal references
and notes. Tenant administrators can view their own plan, dates, usage and retained
changes. New tenants still select a plan on registration; subscriptions are never
physically deleted.

The confirmed behavior is **tracking only**: status/dates do not block processing,
sign-in or history. Existing user/device seat limits remain authoritative. Prices
are informational; no payment gateway, payment processing or auto-renewal is added.
Manual status differs from tenant activation status.

Manual subscription storage starts at `0025_manual_subscriptions`; upgrade through the current schema head in Local setup before starting this API version.
Existing assignments and data are preserved. The new
`PATCH /platform/organizations/{id}/subscription` requires the subscription's own
`expected_version`; legacy PUT assignment still uses organization management
version. Read-only directories and history use signed cursors. See the complete
[fields, routes, authorization and upgrade contract](../db/subscriptions.md).

## Administrator account management

Platform administrators can create a platform administrator or a tenant administrator from Settings > Users & administrators. `POST /platform/users` accepts either `platform_role: "platform_admin"` or `organization_id` for a tenant administrator, never both. Tenant creation requires `platform.organization_admins.manage`; it atomically creates the local account, password-setup delivery, pending tenant-wide administrator invitation, and audit records. Setup and explicit invitation acceptance are required before access. Pending invitations reserve subscription seats. A first administrator may accept for an inactive tenant; tenant activation remains a separate administrator action. Archived tenants cannot receive new administrators.

Account responses include `tenant_admin`; the platform user directory accepts `platform_role=tenant_admin` for filtering. Existing roleless account creation remains supported for API clients. The API rejects attempts to disable or archive the acting platform administrator's own account with `403 self_account_action`, even when another administrator exists. UI controls enforce the same restriction. Deleting a user retains the existing archive behavior.

## Tenant provisioning wizard

The **Create tenant** page uses `POST /platform/organizations/provision` to save
the tenant, one new or transferred device, an accepted first tenant
administrator, and the tenant-owned clinical starters in one transaction.
The standard `POST /organizations` and pending `POST /platform/organizations` paths
create the same tenant-owned clinical defaults. Each new tenant receives three
active specialties (Cardiology, Nephrology, Respiratory Medicine), an inactive
fictional Alex profile, and two inactive editable cases (Chest discomfort interview
and Wheeze interview). Tenant administrators review and activate the profile and
cases before catalog-based rehearsal.

The same transaction publishes two active bilingual scenario snapshots with
publication version 1 and document schema version 4. They contain presentation,
symptoms, history and eight vitals; no Q&A, Instructor or disclosure configuration
is provisioned. They are labelled `system_starter` without human reviewer
attribution. Published starters are selectable in the desktop app independently of
catalog-case activation. The tenant scenario default is chest discomfort in
English; users save their own private selection. A separate compatibility Patient
setup default points to the editable chest discomfort case and requires its
profile/case activation before adoption. No authoring draft or private selection
is created automatically.

Device training requires enrollment, supported agent capabilities and configured
models. Provisioning does not bind or install models. Revised scenarios follow
submission, independent clinical review and publication. See the
[starter reference](../../docs/default-tenant-case-drafts.md) for lifecycle details.
Existing tenants are unchanged by ordinary provisioning. Missing or modified
starter sources cause tenant creation to roll back atomically. The
wizard requires the platform organization,
administrator, and user management grants. A new administrator receives a
platform supplied initial password; an existing eligible, verified user can be
selected. A device transfer retires its old registration and creates a fresh
registration UUID while retaining the physical device's immutable unique ID,
leaving history and private configuration with the old tenant. Successful
provisioning activates the tenant; the new device awaits enrollment. Validation,
capacity, identity, device version, and audit failures roll back all changes.

The Administrator action on `/tenants` opens Tenant administration at Administrators, with Subscription and Devices also available. The Users tab and general user association controls are not exposed in this dialog. New device registration requires the immutable platform-wide device unique ID (1-50 characters). Platform membership routes are under `/platform/organizations/{organization_id}`: `GET /members` (bounded search, role/status filters and signed cursor pagination), `GET /member-candidates?q=...`, `POST /members`, `PATCH /members/{id}`, `DELETE /members/{id}?expected_version=...`, and `POST /members/{id}/restore`.

Reads require both `platform.organizations.read` and `platform.users.read`; writes require both management grants. Assigning, changing or removing an administrator additionally requires `platform.organization_admins.manage`. Existing active accounts with completed local password setup are associated directly, with an explicit UI confirmation and no invitation email. Duplicate memberships and pending invitations are rejected. New associations cover the whole tenant; a role change preserves an existing department restriction unless promoting to administrator, which explicitly clears it.

Membership edits/removal/restoration require the current management version and reuse the existing transactional quota, last-administrator, lifecycle and audit rules. Removal archives the membership only. Restoration keeps it disabled; restoring an account-linked closed invitation explicitly re-associates an eligible, setup-complete account without reopening its invitation token. Archived tenants are read-only; inactive tenants can receive their first administrator without automatically being activated. Tenant content/media access is not granted to the acting platform administrator.

The Devices tab reuses the fleet registration, lifecycle and transfer APIs. `/platform/devices` also supports `exclude_organization_id` for finding transfer sources outside the selected tenant. Registrations and transfers start inactive in this popup. Transfers permanently retire the source, revoke credentials and create a new registration requiring fresh enrollment while retaining the device unique ID; configuration and history stay with the source tenant. No database entity, migration or runtime grant was added.

## Bulk tenant member imports

Members now includes a four-step Excel import wizard with one role per batch, validation, partial success, saved history, and downloadable correction/results workbooks. See [workbook, API, delivery and deployment details](deploy/member-imports.md).
An optional password column supplies initial passwords for new local users; blank
cells generate passwords. Completed imports expose those initial passwords to
tenant-wide member managers in results and Import History for 30 days, with
encrypted database storage and audited views/downloads. Existing passwords are
never changed by import.

## Web content and configuration management

Shared catalog management began at migration `0027_catalog_management`. The Phase 2 API cutover removed shared catalog routes; the tenant web screens now call tenant catalog routes. Provider connections, processing profiles and history retain their API-backed management. See [the tenant ownership plan](../../docs/tenant-clinical-ownership-plan.md).

Migration `0034_platform_model_connections` adds platform-owned encrypted cloud model configurations, Anthropic Messages support, device-authenticated local model inventory, and Platform Admin device assignment. The unified [Platform model setup](../../docs/platform-models.md) covers the API, web and Human-test flow. Reapply runtime grants after the migration; existing tenant profiles and connections remain intact.

Migration `0035_unified_scenarios` supports web Scenarios and desktop Practice; the web Practice page has been removed. A new version-3 draft binds to one active tenant specialty, is submitted at a specific revision, receives localization review from a different tenant reviewer, and can then be published as an immutable version. A content edit clears its submission marker. Published versions appear in the desktop app; each user saves a private scenario/language/vitals choice, while a tenant administrator can set the tenant default. The desktop client reads its own published-scenario selection first. System starters are labeled as provisioned examples without tenant clinical approval. Both English and Hindi localization review are needed for the current device training runtime; a single reviewed language can be used in Practice. Historical catalog and practice APIs remain available for existing records and clients. Reapply runtime grants after upgrading and use only a disposable PostgreSQL server for migration tests.


Migration `0028_language_validator_acl` removes implicit PUBLIC execution of the two
localized-catalog validators. Reapply `platform/api/deploy/grant-runtime-access.sql`
(from the repository root) as the deployment owner after migration: only the API
role receives their EXECUTE permission. The migration does not change tables,
columns or application data. See the migration head and schema synchronization test for the current contract.

The synchronization checks in `platform/api/tests/test_schema_sync.py` compare the
single migration head with API/worker readiness, the packaged frozen baseline with
the SQL installer, and every fresh database column/type/nullability and primary key
with SQLAlchemy metadata using the runtime API role. Run them only with
PMS_TEST_ADMIN_DSN pointing at a dedicated disposable PostgreSQL server; the tests
create and remove their own databases. Existing migration tests additionally check
baseline adoption, preserved data, idempotent/concurrent initialization and grants.

## Tenant clinical catalog expansion (migration 0029)

Migration `0029_tenant_clinical_content` adds tenant-owned specialty, fictional patient profile and case tables, plus nullable same-tenant references on existing staff rehearsal selections. The global catalog is retained as read-only history and seed data after the coordinated API/UI cutover. New tenant copies start inactive; a tenant clinical author must review and activate them before future use. The migration leaves existing selection documents, revisions, LLM links, published scenario fingerprints and training sessions unchanged.

The owner-only backfill is a separate, count-only command. Run it only after a verified backup and a real write pause that stops old API catalog/practice writers and new sessions. The confirmation flags record the operator's checks; they cannot pause an API replica. The Ubuntu deployment script performs this backfill after stopping services and before starting the new API. For manual deployment from `platform/api`:

```powershell
uv run pms-admin tenant-catalog-backfill
uv run pms-admin tenant-catalog-backfill --apply --confirmed-backup --confirmed-write-pause --limit-organizations 25
```

The default is a read-only dry run. Output contains organization IDs and counts only. Apply processes at most 25 organizations per invocation by default, with one transaction per organization. If it prints `Resume with --after-organization UUID`, repeat the command with that option. A repeat invocation keeps existing copies and selection revisions unchanged; a changed legacy source or mismatched mapping stops the transaction for review. The backfill requires `PMS_MIGRATION_DATABASE_URL` for the schema owner. It temporarily disables only the selection revision trigger under an exclusive table lock while filling the three new reference columns, then re-enables it before commit. Normal API writes retain the trigger. Reapply `deploy/grant-runtime-access.sql` after migration: API owns tenant drafts; worker and retention roles have no tenant clinical-table access.

## Tenant clinical permissions and API (migration 0030)

Migration `0030_clinical_capabilities` adds audited capability assignments bound to one organization membership and fixes the tenant catalog update guard. Tenant administrators can assign/revoke `org.clinical.author`, `org.clinical.review`, `org.training.instruct`, and `org.clinical.read` through `/api/v1/organizations/{organization_id}/members/{membership_id}/capabilities`. Every active, accepted tenant administrator also receives `org.clinical.author` from the role, including existing administrators; revoking a redundant assignment cannot remove that role grant. Other authors and reviewers must be organization-wide active staff; an instructor must be active staff; a reader may be eligible read-only staff. `GET /api/v1/auth/context` resolves effective permissions from the current active membership on each request.

The catalog is at `/api/v1/organizations/{organization_id}/clinical-catalog/{specialties|patients|cases}`. Authors can create, edit, archive, restore, copy, validate cases, and explicitly import vetted starter examples listed at `/api/v1/organizations/{organization_id}/clinical-catalog/starters`. Reviewers may read private drafts; readers see summaries without case documents or profile backgrounds. Imported and copied content starts inactive. The import endpoint accepts only the fixed seed IDs at their unmodified seed revision; modified global records require separate review. Every parent and record lookup is tenant-bound, edits use `expected_version` against the row revision, and content/audit commit together.

The old `/api/v1/platform/patient-catalog` routes are removed. The runtime grant bundle revokes global catalog writes from the API role. Deploy the API and web as one release, stop all old API replicas before backfill, and do not enable new rehearsal from migrated cases until the tenant has activated them. No application or VM database was migrated by this repository change.

## Tenant case provenance, review and training (migration 0031)

Migration `0031_case_draft_provenance` records a tenant case ID/revision and the last content author on scenario drafts. Clinical authors may copy and explicitly refresh an active tenant case. Refresh replaces the draft document and increments its revision; case/profile edits never mutate an existing draft or published version. A different clinical reviewer records language review and publishes an immutable version. Both reviewed English and Hindi content are needed for version 3 device assignment; a validated conversion produces the signed version 1 runtime document while the published version 3 fingerprint stays unchanged.

New rehearsal selections use same-tenant case IDs and private snapshots. Existing global selections remain readable as history but cannot start a new rehearsal. Instructor session creation, controls, feedback and rubric access require the `org.training.instruct` capability with processing/playback eligibility. Start and device lease recheck current instructor/learner scope, device state, approved version and pinned source/runtime hashes. Published versions and historical sessions are never rewritten during case edits or backfill. Tenant clinical content and starter examples still require a separate educator review for factual and translation quality.


## Focused Models management

Historical 0036 implementation (superseded by 0037/0038 below): Settings > Models contained model/service configuration management: a type chooser for adding, focused editors, deletion, access/generation checks, and a filtered directory. Device assignments are reached from Devices; `/profiles` and `/connections` remain standalone. Existing `?tab=assign|profiles|media` links redirect there. Local LLM/Whisper rows are reported inventory, not editable installations.

Migration `0036_media_model_configs` adds reusable tenant media defaults referencing the existing encrypted provider connection. Reapply `deploy/grant-runtime-access.sql`; the API alone reads/writes the table. Profile drafts can copy these defaults and retain their configuration ID; published revisions remain immutable. Deletion archives configuration metadata and rejects active published dependencies. Cloud configurations can be added again after deletion, preserving identity/history and requiring a new successful test.

See [Models setup](../../docs/platform-models.md), [task checklist](../../docs/model-workspace-todo.md), and [review/reconciliation](../../docs/model-workspace-review.md).


## Direct models and device selections (0037)

Migration `0037_direct_device_models` supersedes the model connection/preset workflow described above. `runtime_models` owns typed local/cloud settings and encrypted credentials; `device_model_selections` stores the four device choices in one versioned save. New saves create immutable device execution snapshots without editable processing profiles or tenant connection clones. Existing effective assignments, credentials, tenant scope and historical revisions are preserved. The physical `platform_model_connections` and `media_model_configs` tables become read-only compatibility views; historical connection/profile storage remains. Reapply the runtime grant bundle after migration. Workers receive media-model access only; retention receives no model access. See [Models and device configuration](../../docs/platform-models.md) for current UI/API behavior, limitations and rollout instructions.


## Retired configuration management (0038)

Migration `0038_retire_model_setup` removes `devices.profile_id` and `organizations.default_profile_id`; their old references are recorded in immutable history before removal. Direct device selections are the sole assignment store. Legacy connection/profile management routes and tenant model pickers are removed. Old connection/profile rows remain read-only for historical foreign keys; database triggers and runtime grants prevent further edits. Existing execution snapshot wire identifiers remain compatible. Only Platform Admin creates/edits/deletes models and assigns them to devices. The desktop reads assigned models. Apply migration head and reapply the runtime grant bundle before starting this version.


## Verify or synchronize an existing database

Run `platform\db\sync.bat` from the repository root for a read-only check of the configured database against the migration head, ORM table/view mappings and runtime grants. Run `platform\db\sync.bat --apply` with database-using services stopped to create a private backup under `.local/db-backups/`, apply Alembic head, reapply the current grant bundle and verify the result. The script refuses connected services and mismatched runtime database targets. PostgreSQL client tools and the API virtual environment are required. Credentials come from the API environment, never command-line arguments. Keep backups private; archive inspection is not a restore drill. Fresh database creation remains `pms-admin init-database` followed by runtime grants.


## Immutable device unique IDs

Migration 0040 adds a required, immutable 1-50 character device unique ID with case-insensitive platform-wide uniqueness. Existing registrations receive their current UUIDs. Transfers keep the physical ID while preserving separate tenant registration/history UUIDs. Apply the updated runtime grants. See [Device unique IDs](../../docs/device-unique-id.md) for API fields, migration and transfer behavior.

## Cloud model management

Platform administrators create, edit, delete and test saved cloud models in Models. The revision-fenced `POST /api/v1/platform/runtime-models/{id}/test` checks provider access and returns `inference_verified: false`; it does not run inference. Provider fields, execution paths and deployment requirements are documented in [cloud model management](../../docs/cloud-model-management.md).


## Device-only desktop pairing (0043)

Enrollment requires only a one-time enrollment token, optionally matched against `device_identifier` (physical unique ID or registration UUID). No user account is created. The response includes tenant/device identity and the device credential; `GET /api/v1/device/identity` revalidates it. Public desktop readiness is available at `/api/v1/health/ready`.

Active enrolled devices can select published tenant scenarios, start their own fixed Practice conversations, use assigned cloud models and report local turns. Administration and authoring still require human permissions. Device-owned data has exclusive user/device ownership and same-tenant, same-owner foreign keys. Cloud requests retain the credential version for revocation checks. Inactive scope, retirement, revocation and model changes remain enforced. Transfers use a new registration and keep old conversations in the original tenant.

## Assigned desktop sessions

The web Sessions queue assigns trainees to Human-test devices, with atomic ordering, pause/resume, synchronized completion and a fixed 24-hour assignment deadline. See [device session queue](../../docs/device-session-queue.md) for the workflow, security model and upgrade requirements.

## Remote device inference

Pi-test reuses enrollment, scenarios, conversations, assigned-session leases and
cloud processing. `GET /api/v1/device/inference` returns the enrolled device's
validated GPU host binding; `POST /api/v1/device/inference/grants` authorizes a
single inference request against its assigned models and active conversation.
Grants bind device/tenant, host, method/path, payload hash, model/voice, budgets
and expiry using the configured training Ed25519 signing key. The API does not
connect to a device-supplied host or disclose provider/manager credentials.

The existing audited, tenant-scoped device PATCH accepts `details.inference`.
This optional binding uses the existing details column; no migration is required.
See [Pi setup](../../pi-test/README.md#inference-setup),
[gateway](../../local-models/gateway/README.md) and
[review evidence](../../pi-test/docs/review.md).

## Session archives

Migration `0045_session_archives` adds private, resumable session recording archives. Reapply the runtime grant bundle after upgrading; only the API role can access the archive tables. [Recording sync](../../docs/session-recording-sync.md) describes the protocol, capacity limits, expiry and verification.

## Desktop downloads

`GET /api/v1/downloads` lists operator-published protected desktop releases.
`GET` and `HEAD /api/v1/downloads/{artifact_id}` serve the CPU/GPU ZIPs with byte
ranges, download filenames and SHA-256 ETags. Active platform administrators and
active organization-wide tenant administrators can download them; device
credentials and regular members are denied. Every resumed request is authorized.
The web Downloads page proxies the stream using its private browser session.
It pins each link with `?sha256=HASH`; a replaced release returns 409 and requires
refreshing the page and starting a new download. API clients may use the same
optional parameter with GET/HEAD/range requests. No ZIP hashing is done per request.

Set `PMS_DOWNLOADS_ROOT` to private persistent storage outside public assets.
The managed VM deployment uses `/var/lib/pms-downloads` and preserves it across
releases. See [portable release publication](../../docs/human-test-portable.md#platform-downloads)
for the verified atomic publisher and file permissions. No migration is required.

2026-10-08: migration `0047_compact_starters` corrects unchanged Chest discomfort and Wheeze starters, publishes new versions for existing tenants, and updates fresh provisioning. Customized content and historical sessions are preserved. See [compact starter scenarios](../../docs/compact-starter-scenarios.md).
