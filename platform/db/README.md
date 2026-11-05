# PostgreSQL database scripts

For the current PMS API, use `platform/db/init.bat` or `pms-admin init-database`,
then apply `platform/api/deploy/grant-runtime-access.sql`. Current Alembic head is `0048_refined_starters`. Historical table counts below refer
to their named revisions, excluding role views and `public.alembic_version`. The SQL installer described below is the
frozen baseline; it is not a replacement for the current migration chain.

Migration `0046_patient_background` permits bounded version 5 background alongside
version 4 documents. Existing cases, publications and revisions are preserved.
Reapply runtime grants: only the API role needs the new background validator.
Session details use the existing private conversation snapshot JSON; no new media
or credential storage is introduced.

Migration `0033_tenant_training_starters` labels automatically published training
versions separately from clinician-approved versions and adds one tenant-wide Patient
setup template per new tenant. The template references a case and its parents through
a same-tenant foreign key; staff adopt it into their own private selection. Existing
tenant data remains unchanged. Reapply runtime grants after upgrading.

Migration `0034_platform_model_connections` adds platform-owned encrypted cloud model configurations, a managed tenant LLM binding marker, Anthropic endpoint constraints, and supported local model catalog entries. It removes tenant administrator connection/profile management grants from the current role view. Existing tenant connections, profiles and device assignments remain intact. Reapply the current runtime grant bundle after migration; only the API role may read or write the new credential table. See [Platform model setup](../../docs/platform-models.md).

Migration `0035_unified_scenarios` adds tenant-scoped specialty and submission metadata to scenario drafts, specialty references to published versions, a versioned tenant Practice default, and published-scenario references on private practice selections and conversations. Existing catalog, draft, published, conversation, and practice rows remain intact. New version-3 drafts use submit and independent clinical review; existing version-1/2 drafts retain their legacy lifecycle. Reapply `platform/api/deploy/grant-runtime-access.sql` so only the API runtime can update tenant scenario defaults.

Schema v1 for the device platform: **12 tables, 223 fields, and six fixed application roles**. Targets PostgreSQL 17; no extensions or Python packages are required. The SQL lives in the `device_platform` schema. This package creates database objects; it does not implement the API, device agent, or cloud adapters.

## Files

| File | Purpose |
|---|---|
| `create-database.sql` | Optional new database creation, UTC default, restricted public access. |
| `install.sql` | Atomic fresh installation; includes the six ordered files under `sql/`. |
| `sql/001_validation.sql` | Policy, processing-settings, and telemetry row validators. |
| `sql/002_tables.sql` | All columns, checks, tenant foreign keys, and database comments. |
| `sql/003_indexes.sql` | Identity/name uniqueness, queue, history, and retention indexes. |
| `sql/004_triggers.sql` | Timestamps, versioning, immutable context/history, retention, administrator guards. |
| `sql/005_seed.sql` | One platform-settings record with explicit limits; no demo identities or secrets. |
| `sql/006_role_catalog.sql` | Read-only `default_roles` and `default_role_permissions` views, matching the JSON catalog. |
| `bootstrap-admin.sql` | One-time provisioning against a verified OIDC identity, with an audit event. |
| `grant-access.sql` | Optional grants for separately provisioned API, worker, and retention database roles. |
| `tests/verify.py` | Disposable-database integration checks, including concurrent administrator changes. |
| `tests/constraints.sql` | Transactional constraint and lifecycle assertions used by the verifier. |
| `tests/runtime.sql` | Real API/worker/retention writes and a complete relational fixture for backup testing. |

The design remains in [table-fields.md](table-fields.md), [default-roles.json](default-roles.json), and the [platform plan](../../docs/platform-service-plan.md).

## Install

Run from the repository root with `psql` on PATH. Authenticate using your PostgreSQL password prompt, protected password file, or deployment identity. No shared/default password is provided. Substitute your host and deployment owner. The owner needs CREATE on the target database; optional database creation additionally needs CREATEDB. The installation sets privileges on its own schema and does not require PostgreSQL superuser privileges.

```powershell
# Optional: skip if the deployment already provides an empty database.
psql -X -h localhost -U deployment_owner -d postgres -v db_name=device_platform -f platform/db/create-database.sql

# All schema changes and initial settings commit together.
psql -X -h localhost -U deployment_owner -d device_platform -f platform/db/install.sql
```

Check each command succeeds before continuing. Missing parameters or invalid grant targets cause a nonzero psql exit status; setup scripts do not silently report success on rejected inputs. The installer intentionally rejects an existing `device_platform` schema without changing it. Use a reviewed migration for upgrades; do not drop an existing schema to reinstall. Configure service connections for UTC and either qualify names with `device_platform.` or set their search path explicitly. UUIDs and policy-based expiration times are supplied by the service.

The deployment operator must verify the first administrator's issuer, subject, and contact details against the configured identity provider. Then run:

```powershell
$adminId = [guid]::NewGuid().ToString()
psql -X -h localhost -U deployment_owner -d device_platform -v "admin_id=$adminId" -v "issuer=https://your-identity-provider.example" -v "subject=verified-subject-id" -v "email=admin@example.com" -v "display_name=Platform Administrator" -f platform/db/bootstrap-admin.sql
```

Bootstrap fails once any platform administrator exists. It grants no organization membership or tenant media permission. An existing matching OIDC account is promoted without replacing its identity/contact details. Public signup must never invoke this script or accept `platform_role` from request input.

For deployment, provision three distinct unprivileged PostgreSQL roles through your normal identity/secret tooling, then apply grants as schema owner:

```powershell
psql -X -h localhost -U deployment_owner -d device_platform -v db_name=device_platform -v api_role=device_api -v worker_role=device_worker -v maintenance_role=device_retention -f platform/db/grant-access.sql
```

These are trusted backend database roles, separate from the six application roles. Start with roles that have no broader inherited privileges; the grant script also rejects membership among API, worker, and retention roles. It adds privileges and does not clean up existing ones. Runtime roles must not own the schema. Retention can redact run request/result/error content and delete eligible history; it cannot rewrite audit events. Workers handle provider/media cleanup and its status before retention deletes a run.

## Seeded settings

Cloud providers start disabled (`enabled_providers = {}`), all new profile sections start disabled, registration mode is `self_service`, and maintenance mode is off. Enable providers only after their adapters and connection validation work.

| Policy | New-organization default | Platform ceiling |
|---|---:|---:|
| Offline local authorization | 24 hours | 24 hours |
| Temporary media retention | 24 hours | 72 hours |
| Results / telemetry / operational / audit retention | 30 / 7 / 30 / 90 days | 90 / 30 / 90 / 365 days |
| Audio recording / video clip | 60 / 15 seconds | 300 / 60 seconds |
| Video size / frame rate | 1280 ÃƒÆ’Ã¢â‚¬â€ 720 / 15 fps | 1920 ÃƒÆ’Ã¢â‚¬â€ 1080 / 30 fps |
| One upload | 25 MiB | 100 MiB |
| Concurrent jobs per organization | 2 | 4 |
| Daily audio / video / synthesis | 1,800 seconds / 600 seconds / 10,000 characters | 7,200 seconds / 1,800 seconds / 50,000 characters |

Heartbeat is 60 seconds, offline timeout 180 seconds, active polling 5 seconds, and telemetry sampling 300 seconds. These are explicit starting deployment limits, not provider quotas or performance promises. Review them before production. Exact JSON keys appear in `005_seed.sql`; omitted required limits fail validation. Copy the current default policy on organization creation. At configuration resolution and dispatch, take the stricter platform, organization, and profile limits.

## Database guarantees and service responsibilities

SQL enforces role-code subsets, required fields, bounded text/JSON shapes, positive policy values, supported connection/auth combinations, conditional connection bindings, idempotency uniqueness, same-organization references, and queue/retention row invariants. Provider-specific settings, operation/engine compatibility, supported languages/formats, complete media schemas, and all credential redaction still require API validation. References never authorize a caller. To fit PostgreSQL B-tree index entries, issuer plus subject is limited to 2,048 bytes combined; indexed names, normalized emails and token hashes are limited to 1,024 bytes each. Ordinary CHECK violations report oversize input before an index insertion fails.

The API must resolve the current user/device, organization and department; enforce `default-roles.json`; check active ancestors and maintenance rules; and authorize every query/download. **Row-level security is not installed.** Trusted backend roles can query across tenants, so tenant and historical-department filters must be applied by the service. Humans and devices never connect directly to PostgreSQL. Trainees get only scoped device summaries/status/results/media; platform administrators have no implicit tenant-content access.

Administrative changes and their redacted audit event must be written in the same service transaction. Database triggers do not invent an authenticated actor. The `updated_by` check on platform settings is a consistency check; the API must establish that actor's identity. Do not trust user-supplied actor or role fields.

The following transaction contracts are required during API/worker implementation:

- **Administrator coverage:** use READ COMMITTED, PostgreSQL's default. Administrator-affecting statements lock the settings singleton; deferred checks preserve the last active platform administrator and an accepted active administrator for each active organization. Create an active organization and its first accepted admin in one transaction, or create it inactive. Replace administrators or suspend affected organizations atomically. Acquire the singleton before any organization locks, then organization locks in UUID order; retry deadlocks. Other isolation levels are rejected for these administrative mutations.
- **Versioning:** triggers maintain `updated_at`, active-status timestamps, credential versions on issuance/rotation/revocation, connection versions on settings/auth changes, and the platform configuration version on every update. Connection changes clear old validation results. Use `WHERE configuration_version = :expected` for optimistic updates; do not increment these versions twice. Rotating an external secret in place also requires changing its versioned `secret_ref` to invalidate connection validation. Preserve the first `enrolled_at`; clear redeemed enrollment/invitation hashes atomically.
- **Publishing:** lock the profile row, validate settings/connections/limits, allocate `max(version)+1`, insert a revision and update its published pointer in the same transaction. An all-disabled revision is valid. Rollback creates another immutable revision. Resolve effective policy changes through the device configuration hash as well as revision ID.
- **Processing:** reserve usage under the organization lock and insert the run using its unique request key. Reject conflicting reuse of that key. Claim due work with `FOR UPDATE SKIP LOCKED`, assign a fresh lease token/expiry, and update only with the matching token. Apply active-state/capability/usage checks before dispatch. Reconcile `submitting`/`unknown` provider submissions before retrying; an expired lease is not proof a provider call failed. Historical department fields stay unchanged if a device is reassigned.
- **Retention:** derive timestamps from server receipt, not device clocks. Schedule every private media/provider copy for cleanup by its deadline. Redact expired request/result/error content even if cleanup needs retry; delete only after terminal processing, resolved submission/playback, cleanup completion, and expiration. The database checks the recorded states; the worker must verify actual provider/object deletion. History has no update path, and deletion requires expiration. Runtime roles have no TRUNCATE privilege.

No provider connection, user, organization, or device is created by database installation. Create the first password administrator in the [first-run web setup wizard](../api/README.md#first-run-web-setup-recommended-for-password-accounts); its account, Argon2id credential and audit event use the existing tables and runtime grants. AWS and Azure are the allowed initial provider codes; implementing Google later requires a reviewed schema/catalog change.

## Verify

Run against a local test PostgreSQL server using an operator with database/role creation and administration rights. The verifier creates a uniquely named disposable database and NOLOGIN roles, executes the real scripts, compares all fields/types/nullability and role grants to the design, checks preflight failures, permissions and concurrency, and performs a full `pg_dump`/`pg_restore` round trip with data in all twelve tables. Installation and restore also run as an unprivileged schema owner. It removes its own databases/roles in `finally`. It never installs into an existing application database.

```powershell
python platform/db/tests/verify.py --host 127.0.0.1 --port 5432 --user postgres
```

Python uses only the standard library and the installed PostgreSQL client tools (`--psql`, `--pg-dump`, and `--pg-restore` can supply their paths). Authentication follows PostgreSQL's normal PG* environment/password-file configuration. Reviewed and validated locally on PostgreSQL 17.10; cloud adapters, API authorization, and device behavior require their own implementation tests later.


## PMS API migrations

The SQL scripts remain the reviewed 223-column baseline. For the implemented API use `platform/api` Alembic migrations: encrypted credentials, device languages and organization subscriptions bring the schema to 241 columns across 13 domain tables; training migration 0007 adds two tables and 36 columns (277 total). Run `pms-admin adopt-baseline` for an existing SQL-installed database, then `pms-admin migrate`. For fresh or already managed databases, `pms-admin init-database` creates the configured database if missing and upgrades it to the current head; [init.bat](init.bat) is the Windows wrapper. Do not blindly stamp an existing database. Apply `platform/api/deploy/grant-runtime-access.sql` after migration. See [API setup](../api/README.md) and [updated field details](table-fields.md).

Current API head: `0037_direct_device_models` (see the current migration and grant instructions above). Migration `0025` adds six manual subscription fields and a database-managed version trigger; status and dates are tracking only, with no new runtime grants. See [manual subscription terms](subscriptions.md#manual-subscription-terms-0025). Migration `0022` adds an opaque browser-session token hash and credential-version binding for account actions, after the platform-audit index migration `0021`. It preserves existing credentials/bearer sessions and consumes pre-upgrade email-change actions. Migration `0020_management_api` adds explicit local/OIDC identity state, local credential/session/action storage, encrypted account-email delivery state, shared authentication counters, management archive/version fields, invitation method binding, and the provider/model catalog. Existing OIDC identities, memberships, encrypted connections, profile revisions, and processing history are preserved. Reapply runtime grants after upgrading; downgrade intentionally refuses destructive identity/session removal. Every organization must select Standard or Advanced; see [subscription fields, limits and deployment](subscriptions.md). Connection activation/deactivation advances `configuration_version` and clears validation at the database level, including changes made outside the API. PUBLIC has no execution grant on application functions; runtime grants remain explicit. The subscription migration adds one plan table and two organization fields, bringing the pre-training field count to 241. The API grant bundle is self-contained and runs atomically; apply it after migration.


Migration 0007 adds `training_scenarios` (13 fields) and `training_sessions` (23 fields), scoped through organization/device/department composite foreign keys. A partial unique index permits one active session per device. Database guards preserve scenario versions, approval records, session context, terminal state and result receipts; only the first late receipt may be attached to an already terminal row. Unexpired sessions cannot be deleted. Runtime grants and the retention worker cover these tables. Scenario capacity is bounded to 100 versions per organization for the pilot. See the API/pilot documentation for authorization, reservations, signing keys and manual feedback.


Migration 0008 adds `training_scenario_drafts` (14 fields) and two nullable provenance fields to `training_scenarios`: **16 domain tables, 293 columns**. Existing immutable cases and sessions remain unchanged. See [scenario authoring storage](scenario-library.md) for fields, bounded drafts, revision/publication guarantees, grants, the read-only verifier, and mandatory future API transaction responsibilities. The [authoring API](../api/deploy/scenario-library.md) now adds versioned clinical contracts and the draft/publication workflow on this storage. UI and version-2 runtime changes remain deferred.


Migration 0009 adds `llm_connections` (14 fields) and `llm_requests` (18 fields): **18 domain tables, 325 columns**. Existing baseline/scenario records are preserved. See [local LLM storage](local-llm.md) for credentials, retention, quotas, grants and request transitions.

Migration 0010 extends LLM connections with provider, token parameter, streamed-usage and instruction-role settings: **18 domain tables, 329 columns**. Existing connection ciphertext, revisions and request/lease records are preserved. No new runtime privileges are added. See [LLM storage](local-llm.md) and [provider setup](../api/deploy/llm-providers.md).

Migration 0011 adds the shared `scenario_categories` catalog and three defaults: Cardiology, Nephrology and Respiratory Medicine (**19 domain tables, 338 columns** at that revision). Seeds and their audit records are committed together. Initialization is repeatable and preserves existing records; API access to categories is read-only. See [category fields, defaults and initialization](scenario-categories.md).

Migration 0012 adds `patient_identities` with one fictional Alex default and an atomic seed audit event. Schema at migration 0012: **20 domain tables, 356 columns**. Existing categories and scenarios are preserved; runtime identity access is read-only. The same initializer applies this migration for both fresh databases and upgrades. See [Alex and identity field contracts](patient-identities.md).
# Patient practice increment

Migration 0013 adds nine case templates sharing Alex, private revisioned staff setups, and LLM request provenance. Schema at that revision: **22 domain tables, 383 columns**. Apply the current runtime grants after initialization. See [patient practice storage and API](patient-practice.md).


## Cloud model extension

Forward migration `0015_cloud_models` extends LLM provider options and profile bindings, raises the two-call token reservation ceiling to 8,192, and adds fenced speech request metadata. Audio stays in private object storage. Apply the current runtime grant bundle after upgrading; existing migrations and the SQL baseline are unchanged. See [cloud model configuration](../../docs/cloud-models.md).


## Locally executed turns

Forward migration `0016_local_turns` adds `local_turns` (26 fields): **26 tables, 446 columns**. A
profile that publishes a local model is executed on the caller's own laptop, so this service is not
on that turn's data path and the table deliberately holds no prompt, transcript, answer or request
key â€” only counts, timings, the authored routing outcome and the identity of the route, connection
and practice snapshot. Rows are append-only: a trigger rejects every `UPDATE` and allows `DELETE`
only after `expires_at`, which retention uses. The API role receives `SELECT, INSERT` and the
retention role `SELECT, DELETE`; apply the current runtime grant bundle after upgrading. Earlier
migrations and the SQL baseline are unchanged. See
[local execution boundary](../../docs/local-execution-boundary.md).

## Organization online token accounting

Forward migration `0017_llm_total_quota` adds immutable `reserved_total_tokens` and terminal `charged_total_tokens` to `llm_requests`: **26 tables, 448 columns**. Valid successful historical provider usage is backfilled; unknown cloud usage retains a conservative prompt/output bound, while known local rows are exempt. Existing columns and old migrations remain unchanged. Runtime table grants already cover these fields; readiness requires the new head. See [quota policy](../api/deploy/llm-providers.md).

Migration `0018_local_conversation_history` adds append-only `local_conversation_turns`, with scoped configuration references, unique turn/sequence keys, bounded paired text and expiry. API runtime receives SELECT/INSERT, retention receives SELECT/DELETE; unexpired deletion and all updates are rejected. Reapply the runtime grants after upgrading. See [archive contract](../../docs/local-conversation-history.md).


### Device transfers

Device `organization_id` remains immutable. The platform transfer API retires and
revokes the original registration, inserts a fresh destination device and appends
source/destination audits in one transaction under the administration/device
locks. Existing active-device quota constraints cover the destination; failure
rolls back the whole transfer. Historical rows retain their source device and
tenant IDs. Removal also means terminal retirement, not SQL deletion. These
operations use existing runtime grants and need no new migration or baseline edit.

Migration `0026_member_imports` adds bounded tenant `member_imports` records and an encrypted `invitation_email_outbox`. It preserves all existing accounts/memberships and grants access only to the API role. Reapply runtime grants after upgrading. See [member import contract](../api/deploy/member-imports.md).

Migration `0027_catalog_management` adds management versions to existing shared categories and fictional patient identities; case templates keep their existing revision counter. No new tables are added. Reapply runtime grants for API-only catalog INSERT/UPDATE. [Management contract](../../docs/web-content-management.md).


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

## Tenant clinical expansion (migration 0029)

Forward migration `0029_tenant_clinical_content` creates `organization_clinical_specialties`, `organization_patient_profiles`, and `organization_case_templates`. Each row has one organization, a stable code, a revision and lifecycle state; imported global records retain provenance. Composite organization foreign keys prevent a case or staff selection from pointing at another tenant's specialty, profile or case. Per-tenant catalog limits are serialized on the parent organization row. Existing global catalog tables and historic selection columns remain for the coordinated API cutover; no frozen baseline SQL or older migration is changed.

Existing practice selections receive nullable tenant reference columns and retain their original document and revision. The owner-only, dry-run-first `pms-admin tenant-catalog-backfill` copies only global records referenced by current legacy selections, into inactive tenant records. Apply needs a verified backup and stopped old writers; see [API instructions](../api/README.md#tenant-clinical-catalog-expansion-migration-0029). Reapply the API runtime grant bundle after migration. Do not treat this schema expansion as the final security cutover: the existing platform catalog endpoints remain available until the later API/UI release closes them.

## Clinical capability assignments (migration 0030)

Forward migration `0030_clinical_capabilities` adds `organization_member_capabilities` with a composite membership/organization foreign key, one assignment per capability, and grant/revocation provenance. Only the API runtime role receives read/write grants. It also corrects the tenant catalog update trigger so specialty and profile updates do not access case-only columns. The refreshed runtime grants remove API writes to the legacy global catalog tables; the tenant catalog API and a coordinated web release must replace old writers before deployment. Existing tenant clinical rows and historical practice selections are retained.

The frozen `default_role_permissions` view and matching baseline JSON describe the original role set. Current API policy additionally grants `org.clinical.author` to active tenant administrators by role; it is resolved from the membership on each request and requires no stored capability row or schema change.

## Tenant case draft provenance (migration 0031)

Forward migration `0031_case_draft_provenance` adds `source_case_id`, `source_case_revision`, and `content_updated_by` to scenario drafts. A composite foreign key binds the source case to the draft's organization; the draft may refer to a source case or a published scenario, never both. Existing drafts retain their documents and authors, and their current editor is backfilled as the last content editor. The database guard keeps provenance immutable across ordinary edits and allows an explicit revision refresh. Published scenario versions and sessions are not changed.

## Tenant provisioning and import passwords (migration 0032)

Forward migration `0032_tenant_import_passwords` permits new `manikin` device registrations while preserving existing `laptop`, `raspberry_pi`, and `other` records. It adds two nullable, paired import password ciphertext/key-ID columns to `member_imports`. Passwords are AES-GCM encrypted by the API using an external key, scoped to tenant and batch, and removed when the 30-day import record expires. Runtime grants remain table-scoped; reapply the grant bundle after migration. No frozen baseline or old migration is changed.


Migration `0036_media_model_configs` adds tenant-owned reusable media configuration defaults with a same-tenant provider-connection foreign key, bounded JSON defaults, operation/engine constraints, and optimistic versions. Credentials remain in `provider_connections`. Existing records and profile revisions are unchanged. Only the API runtime receives SELECT/INSERT/UPDATE; workers and retention receive no access. Apply the forward migration and reapply the runtime grant bundle before starting this API version.


## Direct models and device selections (0037)

Migration `0037_direct_device_models` supersedes the model connection/preset workflow described above. `runtime_models` owns typed local/cloud settings and encrypted credentials; `device_model_selections` stores the four device choices in one versioned save. New saves create immutable device execution snapshots without editable processing profiles or tenant connection clones. Existing effective assignments, credentials, tenant scope and historical revisions are preserved. The physical `platform_model_connections` and `media_model_configs` tables become read-only compatibility views; historical connection/profile storage remains. Reapply the runtime grant bundle after migration. Workers receive media-model access only; retention receives no model access. See [Models and device configuration](../../docs/platform-models.md) for current UI/API behavior, limitations and rollout instructions.


## Retired configuration management (0038)

Migration `0038_retire_model_setup` removes `devices.profile_id` and `organizations.default_profile_id`; their old references are recorded in immutable history before removal. Direct device selections are the sole assignment store. Legacy connection/profile management routes and tenant model pickers are removed. Old connection/profile rows remain read-only for historical foreign keys; database triggers and runtime grants prevent further edits. Existing execution snapshot wire identifiers remain compatible. Only Platform Admin creates/edits/deletes models and assigns them to devices. The desktop reads assigned models. Apply migration head and reapply the runtime grant bundle before starting this version.


## Verify or synchronize an existing database

Run `platform\db\sync.bat` from the repository root for a read-only check of the configured database against the migration head, ORM table/view mappings, column types/nullability, primary keys and runtime grants. Queue/archive access must remain API-only, and their lifecycle/immutability triggers must be enabled. Run `platform\db\sync.bat --apply` with database-using services stopped to create a private backup under `.local/db-backups/`, apply Alembic head, reapply the current grant bundle and verify the result. The script refuses connected services and mismatched runtime database targets. PostgreSQL client tools and the API virtual environment are required. Credentials come from the API environment, never command-line arguments. Keep backups private; archive inspection is not a restore drill. Fresh database creation remains `pms-admin init-database` followed by runtime grants.

2026-10-04 scenario simplification: current authoring uses version 4 with Presentation & symptoms, History and eight Vitals only. Q&A, Instructor content and fact-disclosure fields are removed from API inputs, stored cases and historical scenario contexts by migration `0041_simple_clinical_cases`. Earlier version/lifecycle descriptions below are historical. See [scenario cleanup](../../docs/scenario-simplification.md).


## Immutable device unique IDs

Migration 0040 adds a required, immutable 1-50 character device unique ID with case-insensitive platform-wide uniqueness. Existing registrations receive their current UUIDs. Transfers keep the physical ID while preserving separate tenant registration/history UUIDs. Apply the updated runtime grants. See [Device unique IDs](../../docs/device-unique-id.md) for API fields, migration and transfer behavior.


Migration `0043_device_practice` adds nullable device ownership to five Practice/turn tables, makes user ownership nullable with an exclusive user/device check, and records device credential versions on cloud requests. Composite foreign keys keep device records within their tenant and private selection/conversation. Ownership is immutable. Existing user-owned records and device registrations are preserved. No new users or tables are provisioned; reapply the standard runtime grants during deployment.

## Device session queues (0044)

Migration `0044_session_queue` adds `device_session_queues` and `practice_sessions`, plus the immutable `patient_conversations.assigned_session_id` link. Organization/device foreign keys, a partial unique active-device index and lifecycle/deadline triggers preserve attribution and serialize device use. Existing data is retained. Reapply runtime grants; only the API role can access the new tables. See [device session queue](../../docs/device-session-queue.md).

Migration `0045_session_archives` adds immutable session identities, final manifests and checksum-backed recording receipts. Media expires independently of result history, and removing expired blobs preserves upload receipts until result retention ends. Reapply runtime grants; worker and maintenance roles receive no access to the new tables.

2026-10-08: migration `0047_compact_starters` corrects unchanged Chest discomfort and Wheeze starters, publishes new versions for existing tenants, and updates fresh provisioning. Customized content and historical sessions are preserved. See [compact starter scenarios](../../docs/compact-starter-scenarios.md).
