# Platform database field specification

Updated: 2026-09-17 | Revision: 6  
Status: Frozen baseline contract for twelve tables and six default roles, with subsequent API migrations documented below. The current schema has **41 domain tables and 709 columns** at `0035_unified_scenarios`, excluding role views and Alembic history. The older field listings below describe their named migration revisions; current physical columns are checked against the ORM by `platform/api/tests/test_schema_sync.py`. PostgreSQL schema v1 scripts are available in [install.sql](install.sql); see [README.md](README.md) for the required migration chain, deployment and validation. Script generation does not deploy a production database.

Companion plan: [Platform service plan](../../docs/platform-service-plan.md).

Default role/permission catalog: [default-roles.json](default-roles.json). This is a fixed application catalog, not an editable permission table.

## Conventions

- Every table below lists all its physical columns, including repeated metadata. **Required** means SQL `NOT NULL`; conditional requirements are explained below each table.
- Use application-generated UUID primary keys, except the platform_settings singleton key, and `timestamptz` for instants. Configure database connections to UTC. `now()` defaults are database defaults.
- `Required` and `Set from policy` mean the server supplies the value. Named objects describe their documented shape: schema v1 supplies the disabled profile draft as a SQL default and seeds platform settings; the service copies/resolves policy values for organizations and history.
- Keep registration simple: `users.created_at` and `devices.created_at` are exposed as `registered_at` in the API/UI. Do not store duplicate timestamps. Device `enrolled_at` remains separate.
- Use `text` plus check constraints for small status vocabularies. Validate nonblank names and bounded text/JSON sizes. Optional text is NULL rather than an empty string.
- Indexed text also has byte limits for PostgreSQL B-tree compatibility: the OIDC issuer and subject together must fit 2,048 bytes; indexed names, normalized emails, and token hashes must each fit 1,024 bytes. Character bounds still apply.
- Never store plaintext invitation/device tokens or provider credentials. Hash high-entropy tokens; provider credentials are encrypted in PostgreSQL; encryption keys stay in deployment secrets outside the database. Do not log hashes as identifiers.
- Administrative records have active flags and mutable timestamps. Revisions and history are immutable to normal callers; processing runs have execution states.
- Tenant ownership, role permission, and active-state checks apply to every write/read. A valid UUID or foreign key alone does not authorize access.

## 1. `organizations`

Tenant boundary, organization contacts, processing defaults, and policy limits.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `name` | `text` | Yes | Required | Nonblank display name. |
| `description` | `text` | No | NULL | Optional short description. |
| `contact_name` | `text` | No | NULL | Primary contact person's name. |
| `contact_email` | `text` | No | NULL | Primary contact email; does not grant access. |
| `contact_phone` | `text` | No | NULL | Primary contact phone number. |
| `default_profile_id` | `uuid` | No | NULL | Default processing profile; must belong to this organization. |
| `policy_settings` | `jsonb` | Yes | Policy defaults | Validated retention, usage, capture, and offline limits; see JSON contracts. |
| `suspension_source` | `text` | No | NULL | organization or platform when inactive; NULL when active. |
| `last_activity_at` | `timestamptz` | No | NULL | Latest meaningful tenant activity; excludes heartbeats and backfills. |

Rules and relationships:

- Names need not be globally unique; id is the tenant identifier.
- default_profile_id uses a same-organization FK to processing_profiles. Create the organization before its default profile.
- When inactive, suspension_source is required. Org admins cannot remove a platform suspension; platform_admin manages organization status through platform routes.
- An active organization requires an accepted active org_admin whose user is active. Create both transactionally, or leave a new organization inactive pending first-admin invitation acceptance.
- Lock the organization row when changing administrator coverage or reserving usage. Global user deactivation must replace affected last org admins or inactivate those organizations atomically.

## 2. `departments`

Flat organizational units for device grouping and scoped access.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `name` | `text` | Yes | Required | Nonblank display name. |
| `description` | `text` | No | NULL | Optional short description. |

Rules and relationships:

- Unique (organization_id, lower(name)), including inactive departments; reactivate an existing department rather than create a duplicate.
- Inactivation blocks assigned-device processing and new assignments; it does not rewrite child is_active flags.

## 3. `users`

Global application users mapped to the login identity provider.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `identity_issuer` | `text` | Yes | Required | Trusted OIDC issuer identifier. |
| `identity_subject` | `text` | Yes | Required | Opaque subject from the verified identity token. |
| `display_name` | `text` | Yes | Required | User's display name. |
| `email` | `text` | Yes | Required | Contact/login email received from the identity service. |
| `email_verified` | `boolean` | Yes | false | Updated only from trusted identity verification. |
| `phone` | `text` | No | NULL | Optional contact number. |
| `platform_role` | `text` | No | NULL | NULL or platform_admin; independent of organization memberships. |
| `last_login_at` | `timestamptz` | No | NULL | Last successful interactive login. |
| `last_activity_at` | `timestamptz` | No | NULL | Last meaningful authenticated application action. |

Rules and relationships:

- Unique (identity_issuer, identity_subject). Do not merge identities solely because emails match.
- Index normalized email for invitations; it is not the identity primary key and is not globally unique.
- created_at is exposed as registered_at; no second physical registration timestamp.
- CHECK platform_role is NULL or platform_admin. Signup always sets NULL; only an active platform_admin or trusted bootstrap operation can grant/revoke this role.
- Org admins manage their memberships, not global user activation/platform_role. Platform role grants do not confer tenant-data permissions. No passwords are stored here.
- Preserve an active platform_admin using a platform_settings row lock during grant/revoke/global-user-status changes. Check organization admin coverage in the same transaction before global deactivation.

## 4. `organization_memberships`

Organization roles, optional department scope, and invitation acceptance.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | false | Pending invitations start inactive; accepted membership can be active. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `user_id` | `uuid` | No | NULL | FK users.id; required after acceptance. |
| `role` | `text` | Yes | Required | org_admin, org_user, org_read_only, or org_trainee. |
| `department_id` | `uuid` | No | NULL | Same-organization department scope; NULL means organization-wide. |
| `invitation_status` | `text` | Yes | pending | pending, accepted, expired, or revoked. |
| `invited_email` | `text` | No | NULL | Required for invitation flow; optional for directly created first-admin membership. |
| `invitation_token_hash` | `text` | No | NULL | Unique hash of the pending invitation token; never the plaintext token. |
| `invitation_expires_at` | `timestamptz` | No | NULL | Required while pending. |
| `joined_at` | `timestamptz` | No | NULL | Acceptance/join time; required for accepted memberships. |

Rules and relationships:

- Unique (organization_id, user_id) where user_id is not NULL, even for inactive memberships.
- Only one pending invitation per organization and normalized invited_email. Reissue/expire the existing invitation explicitly.
- Accepted requires user_id and joined_at. Pending requires invited_email, token hash, expiry, and is_active=false. Non-accepted memberships grant no access.
- Clear invitation_token_hash on acceptance/expiry/revocation; retain invited_email and dates for history.
- org_admin requires department_id=NULL. Other human org roles may have organization-wide or one-department scope. platform_admin and org_device are forbidden in this column.
- Preserve accepted active org_admin coverage for active organizations. Org admins may assign the four human organization roles; platform admins may assign/recover org admins across organizations. Neither route grants a platform role implicitly.
- org_trainee can read assigned device summaries/basic status and processing results/media; no processing execution, configuration, detailed telemetry, or administration.
- Acceptance verifies the identity's email and atomically consumes the invitation. Direct first-admin creation uses accepted status without a token; signup cannot choose a privileged role from request input.

## 5. `devices`

Registered laptop/Pi identities, assignments, configuration, enrollment, and current health.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `department_id` | `uuid` | No | NULL | Current department; same-organization FK. |
| `name` | `text` | Yes | Required | Nonblank display name. |
| `device_type` | `text` | Yes | Required | laptop, raspberry_pi, or other. |
| `role` | `text` | Yes | org_device | Fixed non-human role; CHECK role = org_device. |
| `details` | `jsonb` | Yes | {} | Optional model, serial number, OS, agent version, and hardware notes. |
| `location` | `text` | No | NULL | Simple location label. |
| `contact_name` | `text` | No | NULL | Responsible contact person's name. |
| `contact_email` | `text` | No | NULL | Contact email. |
| `contact_phone` | `text` | No | NULL | Contact phone. |
| `profile_id` | `uuid` | No | NULL | Explicit same-organization profile assignment; NULL uses organization default. |
| `applied_profile_revision_id` | `uuid` | No | NULL | Last acknowledged, same-organization revision. |
| `applied_configuration_hash` | `text` | No | NULL | SHA-256 hex of acknowledged resolved configuration, including relevant platform/org policy. |
| `config_error` | `jsonb` | No | NULL | Rejected revision ID, error code, and bounded diagnostic message. |
| `capabilities` | `jsonb` | Yes | {} | Available capture/output devices and installed local engines. |
| `enrollment_state` | `text` | Yes | pending | pending, enrolled, or retired; independent of is_active. |
| `enrollment_token_hash` | `text` | No | NULL | Unique hashed one-time enrollment code. |
| `enrollment_expires_at` | `timestamptz` | No | NULL | Expiry of the currently issued enrollment code. |
| `enrollment_attempt_count` | `integer` | Yes | 0 | Nonnegative redemption attempts for the current code. |
| `credential_hash` | `text` | No | NULL | Unique hash of this device's current high-entropy credential. |
| `credential_version` | `integer` | Yes | 0 | Trigger-incremented on credential issuance/rotation/revocation. |
| `credential_issued_at` | `timestamptz` | No | NULL | Current credential issuance time. |
| `credential_revoked_at` | `timestamptz` | No | NULL | Revocation time; inactive alone does not revoke. |
| `enrolled_at` | `timestamptz` | No | NULL | First successful enrollment of this registration. |
| `last_seen_at` | `timestamptz` | No | NULL | Last authenticated contact, measured by the server. |
| `last_activity_at` | `timestamptz` | No | NULL | Latest meaningful current capture/control/processing event. |
| `offline_authorized_until` | `timestamptz` | No | NULL | Last issued offline authorization expiry. |
| `last_telemetry_at` | `timestamptz` | No | NULL | Server receipt time for latest health snapshot. |
| `latest_health` | `jsonb` | Yes | {} | Latest validated measurements and component status. |

Rules and relationships:

- created_at is the registered_at API/UI value. enrolled_at is a separate event.
- Token hash and expiry must be both present or both absent. Consume enrollment atomically and clear its token fields.
- Enrolled requires enrolled_at and credential issuance metadata. Retired devices have no usable credential. Revocation clears the hash, records the date, and increments the version.
- Do not store an online boolean: derive never_seen/online/offline from last_seen_at and configured timeout. Missing health is unknown.
- Desired revision derives from the assigned/default profile; the applied revision/hash change only on acknowledgment. CHECK a non-null hash is 64 lowercase hexadecimal characters.
- Hash canonical resolved configuration, including platform configuration version and organization policy, but excluding volatile heartbeat/lease timestamps. This propagates policy-only changes without fabricating profile revisions.
- Device credentials resolve only to role=org_device and their own organization/device context; never create a users or organization_memberships row for a device.
- Inactive devices may authenticate only for restricted health/status traffic. Re-enrollment and rotation are atomic; credential history is recorded as redacted activity.
- A transfer creates a fresh device registration in the new organization and retires the old one, preserving historical tenant references.

## 6. `provider_connections`

Reusable organization-owned cloud configuration and secret references.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `name` | `text` | Yes | Required | Nonblank display name. |
| `description` | `text` | No | NULL | Optional short description. |
| `provider` | `text` | Yes | Required | aws or azure initially. |
| `connection_type` | `text` | Yes | Required | aws_processing, azure_speech, or azure_video_indexer. |
| `auth_mode` | `text` | Yes | Required | workload_identity, assume_role, access_key, api_key, or service_principal as supported. |
| `settings` | `jsonb` | Yes | {} | Non-secret region/resource/storage settings; see contracts. |
| `secret_ref` | `text` | No | NULL | Reference to a secret-manager object; required for secret-based auth. |
| `configuration_version` | `integer` | Yes | 1 | Positive version; trigger-incremented when settings/authentication change. |
| `validation_results` | `jsonb` | Yes | {} | Per-service check status/error/time and checked configuration version. |
| `last_validated_at` | `timestamptz` | No | NULL | Most recent current-configuration validation. |
| `last_used_at` | `timestamptz` | No | NULL | Most recent authorized provider operation. |

Rules and relationships:

- Unique (organization_id, lower(name)); validate the provider/type/auth-mode combination.
- Settings and auth changes invalidate previous validation results. A service must pass checks for the current configuration version.
- secret_ref stores no secret value. Workload/role authentication may have no tenant secret but requires a configured platform identity.
- Inactivation blocks dispatch, not authorized cleanup. Keep referenced records and secret access until outstanding cleanup finishes.

## 7. `processing_profiles`

Editable draft and pointer to the current immutable published revision.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `created_at` | `timestamptz` | Yes | now() | Server creation time; registration date for users/devices. |
| `updated_at` | `timestamptz` | Yes | now() | Set by a database trigger on every update. |
| `created_by` | `uuid` | No | NULL | User who created the record; FK users.id; NULL for bootstrap/system. |
| `is_active` | `boolean` | Yes | true | Administrative flag; parent status and lifecycle still apply. |
| `status_changed_at` | `timestamptz` | Yes | now() | Time the active flag last changed. |
| `status_changed_by` | `uuid` | No | NULL | User who changed status; FK users.id; NULL for system. |
| `status_reason` | `text` | No | NULL | Short explanation of the current status. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `name` | `text` | Yes | Required | Nonblank display name. |
| `description` | `text` | No | NULL | Optional short description. |
| `draft_settings` | `jsonb` | Yes | Disabled draft object | Audio/video/output and capture policy settings; schema_version=1. |
| `draft_audio_input_connection_id` | `uuid` | No | NULL | Cloud audio input connection; same-organization FK. |
| `draft_video_connection_id` | `uuid` | No | NULL | Cloud video connection; same-organization FK. |
| `draft_audio_output_connection_id` | `uuid` | No | NULL | Cloud synthesis connection; same-organization FK. |
| `published_revision_id` | `uuid` | No | NULL | Current immutable revision of this exact profile. |

Rules and relationships:

- Unique (organization_id, lower(name)). Connection IDs are explicit relational columns, not duplicated inside JSON.
- Published pointer must match both this organization and this profile.
- Publishing validates the draft, allocates the next revision under a profile-row lock, inserts the revision, and changes the pointer atomically.
- Rollback publishes a new revision from older settings; it never edits an old revision. Inactive profiles retain their drafts/history.

## 8. `processing_profile_revisions`

Immutable settings and provider bindings sent to devices.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `profile_id` | `uuid` | Yes | Required | Same-organization parent profile. |
| `version` | `integer` | Yes | Assigned on publish | Positive sequence within this profile. |
| `settings` | `jsonb` | Yes | Required | Validated complete settings snapshot, including schema_version. |
| `audio_input_connection_id` | `uuid` | No | NULL | Same-organization audio input connection. |
| `video_connection_id` | `uuid` | No | NULL | Same-organization video connection. |
| `audio_output_connection_id` | `uuid` | No | NULL | Same-organization audio output connection. |
| `published_at` | `timestamptz` | Yes | now() | Publication time. |
| `published_by` | `uuid` | Yes | Required | Publishing user; FK users.id. |
| `change_note` | `text` | No | NULL | Optional brief publication/rollback explanation. |

Rules and relationships:

- Unique (organization_id, profile_id, version). Prevent normal UPDATE/DELETE of revisions.
- Cloud sections require the matching connection ID; local/disabled sections have NULL connection IDs.
- Validate operation/engine/connection compatibility and platform/organization caps at publication and execution.
- Connection rows may rotate credentials; immutable revisions freeze routing/configuration choices, not secret values. Runs snapshot relevant connection settings/version.
- No is_active or updated_at: lifecycle is controlled by the parent profile and published pointer.

## 9. `processing_runs`

One local/cloud operation, queue lifecycle, results, media cleanup, and optional playback.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key and output playback deduplication ID. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `device_id` | `uuid` | Yes | Required | Same-organization device. |
| `department_id` | `uuid` | No | NULL | Authorized department snapshot at capture/request time. |
| `profile_revision_id` | `uuid` | Yes | Required | Same-organization executed/authorized revision. |
| `requested_by` | `uuid` | No | NULL | Requesting user; NULL for permitted device/system work. |
| `capture_id` | `uuid` | No | NULL | Correlation ID linking related audio and video; not a separate table. |
| `request_key` | `uuid` | Yes | Required | Client-generated idempotency key for this device request. |
| `operation` | `text` | Yes | Required | Registry operation, e.g. audio.transcribe, video.labels, audio.synthesize, audio.playback. |
| `execution_mode` | `text` | Yes | Required | local or cloud. |
| `engine` | `text` | Yes | Required | Registry engine, e.g. aws_transcribe, azure_speech, opencv_motion. |
| `connection_id` | `uuid` | No | NULL | Required for cloud execution; NULL for local. |
| `effective_settings` | `jsonb` | Yes | Required | Resolved non-secret configuration, provider settings/version, and policy snapshot. |
| `request` | `jsonb` | Yes | {} | Bounded operation input/options; may contain synthesis text, never credentials. |
| `status` | `text` | Yes | Required | awaiting_device, awaiting_upload, queued, running, succeeded, failed, cancelled, or expired. |
| `created_at` | `timestamptz` | Yes | now() | Server acceptance/creation time. |
| `updated_at` | `timestamptz` | Yes | now() | Trigger-maintained last modification. |
| `captured_at` | `timestamptz` | No | NULL | Device-reported capture start; not used to prove liveness. |
| `started_at` | `timestamptz` | No | NULL | Processing start time. |
| `completed_at` | `timestamptz` | No | NULL | Terminal processing time, including cancellation/expiry. |
| `deadline_at` | `timestamptz` | Yes | Set from policy | Latest allowed processing completion; bounded by media lifetime. |
| `attempt_count` | `integer` | Yes | 0 | Nonnegative processing dispatch count. |
| `next_attempt_at` | `timestamptz` | No | NULL | Next dispatch/poll retry time; required for scheduled queued work. |
| `lease_token` | `uuid` | No | NULL | Random worker-claim token; required when claimed. |
| `lease_expires_at` | `timestamptz` | No | NULL | Claim expiry for recovery; changed with lease_token. |
| `provider_submission_status` | `text` | Yes | not_submitted | not_submitted, submitting, submitted, or unknown; supports reconciliation. |
| `provider_job_id` | `text` | No | NULL | External asynchronous job identifier, where one exists. |
| `result` | `jsonb` | No | NULL | Normalized transcript, labels, local event, or audio metadata. |
| `error` | `jsonb` | No | NULL | Bounded code/message/retryable details without secrets. |
| `usage` | `jsonb` | Yes | {} | Reserved/actual usage by unit and accounting date, independent of retry count. |
| `media_manifest` | `jsonb` | Yes | [] | Private object/provider-copy references and per-copy cleanup state. |
| `media_expires_at` | `timestamptz` | No | NULL | Earliest required media-cleanup deadline. |
| `cleanup_status` | `text` | Yes | not_required | not_required, pending, running, succeeded, or failed. |
| `cleanup_next_attempt_at` | `timestamptz` | No | NULL | Due time for pending/retried cleanup. |
| `playback_status` | `text` | Yes | not_requested | not_requested, pending, playing, succeeded, failed, unknown, expired, or cancelled. |
| `playback_expires_at` | `timestamptz` | No | NULL | Deadline after which audio must not play. |
| `playback_acknowledged_at` | `timestamptz` | No | NULL | Receipt time of the device's final playback acknowledgment. |
| `expires_at` | `timestamptz` | Yes | Set from policy | Result/request retention deadline; normally creation plus 30 days. |

Rules and relationships:

- Unique (organization_id, device_id, request_key). A repeat returns the original run; conflicting request content is rejected.
- One logical cloud call per run. Audio/video correlate through capture_id but complete independently. Operation/provider IDs are server-validated, not client-authorized.
- Cloud requires connection_id; local forbids it. All context references must match the organization. Department is a historical snapshot, not a FK to the device's mutable current department.
- Terminal processing requires completed_at. Lease token/expiry are both NULL or both present. Queue/cleanup claims compare tokens so stale workers cannot overwrite newer work.
- Worker checks active ancestors, permitted revision, connection, and reserved usage before dispatch. Usage reservation is transactional under the organization lock.
- Stateful async providers need provider_job_id after successful submission; synchronous providers need not produce one. Unknown submission blocks blind retry.
- Audio synthesis success does not imply playback success. Playback uses run id for deduplication and has its own expiry/status.
- Deletion waits for media/provider-copy cleanup. At expires_at redact request/result content even if a minimal cleanup tombstone must remain for retries.

## 10. `device_telemetry_samples`

Sampled device-health history; latest health remains on devices.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `organization_id` | `uuid` | Yes | Required | Owning organization; FK organizations.id. |
| `device_id` | `uuid` | Yes | Required | Same-organization device. |
| `department_id` | `uuid` | No | NULL | Server-authorized department context when sampled. |
| `boot_id` | `uuid` | Yes | Required | Agent-generated ID for this runtime/boot. |
| `sequence_number` | `bigint` | Yes | Required | Nonnegative, increasing within boot_id. |
| `observed_at` | `timestamptz` | No | NULL | Reported measurement time; NULL if unavailable/unreliable. |
| `received_at` | `timestamptz` | Yes | now() | Server receipt time. |
| `metrics` | `jsonb` | Yes | Required | Validated CPU/memory/disk/temperature/capture measurements. |
| `expires_at` | `timestamptz` | Yes | Set from policy | Usually received_at plus 7 days. |

Rules and relationships:

- Unique (organization_id, device_id, boot_id, sequence_number) prevents duplicate samples.
- Latest health can update every heartbeat; historical samples are persisted approximately every five minutes.
- Unavailable metrics are NULL/absent, never fabricated zero. Reject invalid ranges, oversized payloads, and out-of-order replacement of latest health.
- No active flag or updated_at. Normal writes are append-only; a retention task deletes expired samples.

## 11. `activity_events`

Administrative audit and operational device events with scoped visibility.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `uuid` | Yes | Generated UUID | Primary key. |
| `organization_id` | `uuid` | No | NULL | Tenant context; NULL only for global identity/platform events. |
| `department_id` | `uuid` | No | NULL | Historical scope for operational entries. |
| `device_id` | `uuid` | No | NULL | Device context, including when a user/system acted on it. |
| `actor_type` | `text` | Yes | Required | user, device, or system. |
| `actor_user_id` | `uuid` | No | NULL | FK users.id; required when actor_type=user. |
| `category` | `text` | Yes | Required | audit or operational. |
| `event_type` | `text` | Yes | Required | Registry action, e.g. device.enrolled or profile.published. |
| `severity` | `text` | Yes | info | info, warning, or error. |
| `entity_type` | `text` | No | NULL | Kind of affected record. |
| `entity_id` | `uuid` | No | NULL | Stable historical record identifier; validated at event creation. |
| `run_id` | `uuid` | No | NULL | Correlation to a run; may outlive run retention. |
| `source_event_id` | `uuid` | No | NULL | Device-generated event deduplication ID; required for device-originated events. |
| `occurred_at` | `timestamptz` | Yes | Set by server/validated input | Event occurrence time; device time is informational. |
| `received_at` | `timestamptz` | Yes | now() | Server ingestion time. |
| `details` | `jsonb` | Yes | {} | Bounded redacted metadata, optional boot/sequence, and historical flag. |
| `expires_at` | `timestamptz` | Yes | Set from policy | Typically receipt plus 90 days for audit, 30 days for operational. |

Rules and relationships:

- Unique (organization_id, device_id, source_event_id) for device-originated events; those fields are all required in that case.
- Actor device requires device_id and operational category. Only the server writes audit entries; actor_type is never trusted from device input.
- Department/device contexts require organization_id and same-organization FKs. Global events are platform-scoped, not visible to arbitrary tenants.
- entity_id and run_id are immutable correlation IDs rather than deletion-blocking FKs; validate tenant ownership at ingestion. History can outlive its target.
- Administrative changes and their audit entries commit together. Include actor role and authorization scope in redacted details. Global platform settings/role events have organization_id=NULL; platform actions on an organization retain its ID.
- Platform admins can read global/cross-org administrative audit, not operational content without membership. Org admins read their own administrative audit. Trainees read results/media through run permissions, not this audit endpoint.
- Normal roles cannot edit/delete events; retention uses a restricted maintenance role.
- No transcript, raw media, passwords, tokens, or provider secrets in details. Historical backfills do not refresh current last_activity_at.

## 12. `platform_settings`

One platform-wide configuration record, managed only by platform_admin. It has no organization_id and is not a tenant-owned table.

| Field | PostgreSQL type | Required | Default/source | Description |
|---|---|---|---|---|
| `id` | `smallint` | Yes | 1 | Singleton primary key; CHECK id = 1. |
| `display_name` | `text` | Yes | Device Platform | Platform name shown in the application. |
| `registration_mode` | `text` | Yes | self_service | self_service or invite_only; controls organization creation/onboarding. |
| `enabled_providers` | `text[]` | Yes | Empty array | Global provider allowlist; enable aws/azure after their adapters and configuration are ready. |
| `default_organization_policy` | `jsonb` | Yes | Initial policy defaults | Policy copied when an organization is created. |
| `policy_limits` | `jsonb` | Yes | Required | Validated hard ceilings for tenant retention, usage, capture, and offline authorization. |
| `device_defaults` | `jsonb` | Yes | Initial device defaults | Heartbeat/control/history intervals and offline timeout. |
| `maintenance_mode` | `boolean` | Yes | false | Pause new enrollment/processing while preserving recovery, reads, health/status, and cleanup. |
| `configuration_version` | `integer` | Yes | 1 | Positive version, trigger-incremented on every configuration update. |
| `created_at` | `timestamptz` | Yes | now() | Seed-row creation time. |
| `updated_at` | `timestamptz` | Yes | now() | Trigger-maintained last modification. |
| `updated_by` | `uuid` | No | NULL | FK users.id; NULL only for bootstrap/system initialization. |

Rules and relationships:

- Seed exactly one row. Deny normal INSERT/DELETE after initialization; CHECK id=1 prevents a second configuration record. No is_active flag: maintenance_mode is the explicit operational switch.
- Only an active platform_admin may update it. Use configuration_version for optimistic concurrency, increment it atomically, and commit an audit event with the update.
- Validate the entire candidate settings object before committing. A provider cannot be enabled before its adapter exists; disabling a provider blocks only affected new work and retains cleanup access.
- Defaults seed new organizations only. Platform hard limits apply to existing organizations on new dispatch and configuration sync; resolve stricter organization/profile values rather than rewriting historical revisions.
- Keep database credentials, provider secrets, identity trust configuration, and arbitrary role grants outside this JSON. Changing signup mode must not permit self-assignment of platform_admin.
- The same singleton row provides a serialization lock for last-platform-admin checks. Seed the first administrator against a verified OIDC issuer/subject through a trusted one-time deployment command; never seed a shared/default password.

## Default roles and assignment rules

| Code | Assignment storage | Identity/scope | Default grants |
|---|---|---|---|
| platform_admin | users.platform_role | Human/platform | Platform settings, organization directory/status, global users/admins, org-admin recovery, administrative audit, aggregate health. |
| org_admin | organization_memberships.role | Human/whole organization | Org settings, human membership roles, departments, devices, connections, profiles, processing, results, telemetry, activity/audit. |
| org_user | organization_memberships.role | Human/org or department | Device/configuration views, approved processing/playback, results/media, telemetry, operational activity. |
| org_read_only | organization_memberships.role | Human/org or department | Same scoped read views as org_user, without processing or mutation. |
| org_trainee | organization_memberships.role | Human/org or department | Device summaries/basic status and processing results/media; no execution, configuration, detailed telemetry, or administration. |
| org_device | devices.role | Non-human/one device | Its own configuration/work/results/status, processing submission, telemetry/events, and playback acknowledgment. |

All unmatched actions deny access. An unassigned user has no organization role. Active humans may read their own identity/memberships and update permitted contact fields; verified invitation acceptance and self-service organization creation follow explicit onboarding rules. These routes cannot change platform roles. Platform-admin grants are not wildcard organization permissions; tenant processing/data requires explicit org membership, and any assignment is audited.

Keep the six grants in default-roles.json and enforce their role-code subsets with CHECK constraints on each assignment column. There are no roles, permissions, or role_permissions tables in this initial fixed-role design. Custom-role editing is deferred; platform settings cannot edit the catalog.

## JSON contracts

JSONB keeps the model small; it does not mean arbitrary unvalidated data. The API uses versioned schemas, rejects unknown credential fields, and enforces object/array shape and size limits. Relationship IDs listed as columns stay outside JSON.

### Organization policy

`policy_settings` contains these initial keys:

| Key | Value/type | Meaning |
|---|---|---|
| `offline_authorization_hours` | Integer; 24 initially | Maximum duration of cached local authorization. |
| `media_retention_hours` | Integer; 24 initially | Maximum temporary media lifetime. |
| `result_retention_days` | Integer; 30 initially | Request/result retention. |
| `telemetry_retention_days` | Integer; 7 initially | Sampled measurement retention. |
| `operational_retention_days` | Integer; 30 initially | Operational activity retention. |
| `audit_retention_days` | Integer; 90 initially | Administrative audit retention. |
| `capture_limits` | Object | Required positive integers: max_audio_seconds, max_video_seconds, max_width, max_height, max_fps, max_upload_bytes. |
| `usage_limits` | Object | Required positive integers: max_concurrent_jobs, daily_audio_seconds, daily_video_seconds, daily_tts_characters. |

Copy retention defaults from platform_settings.default_organization_policy when creating an organization; explicitly configure capture/usage limits before enabling affected cloud work. Resolve platform hard limits, then organization policy, then profile restrictions. Use positive values; zero is allowed only for documented disable/immediate-expiry behavior.

### Platform configuration objects

- default_organization_policy uses the organization-policy keys above. Updating defaults does not silently replace existing organization policies.
- policy_limits uses the same numeric limit keys as hard ceilings; nested capture_limits/usage_limits are validated key by key. The seed must include explicit deployed limits; omitted/malformed required limits cannot imply unlimited access. Disabled providers and maintenance_mode are additional global dispatch gates.
- device_defaults contains heartbeat_seconds=60, offline_after_seconds=180, active_poll_seconds=5, and telemetry_sample_seconds=300 initially. Validate positive intervals and offline_after_seconds greater than heartbeat_seconds.
- Effective configuration contains platform configuration version and resolved restrictions. Propagate it through the device's applied_configuration_hash acknowledgment; a profile revision alone cannot identify changes to global policy.

### Provider settings and secrets

`settings` contains non-secret configuration, with conditional keys based on `connection_type` and `auth_mode`:

| Connection | Settings keys |
|---|---|
| `aws_processing` | `region`, `enabled_services`; `staging_bucket` and `staging_prefix` for batch audio/video; `role_arn` and server-generated `external_id` for assume-role access. |
| `azure_speech` | `region`, `endpoint`; `resource_id` where required by identity authentication; `tenant_id`/`client_id` for a service principal. |
| `azure_video_indexer` | `subscription_id`, `resource_group`, `account_name`, `account_id`, `location`; `tenant_id`/`client_id` for a service principal. |

The object referenced by `secret_ref` holds only the selected authentication material: an AWS access-key pair if used, an Azure Speech resource key, or service-principal secret/certificate. Temporary provider tokens are refreshed by the server, not copied into configuration as permanent credentials.

`validation_results` is keyed by service/operation. Each entry records `status` (not_tested/valid/invalid), `configuration_version`, `checked_at`, `test_kind` (access/sample), and optional redacted `error_code`/`message`. Validate storage and processing separately. No single successful check validates every service in a connection.

### Processing settings

`draft_settings` and revision `settings` share this shape:

| Key | Contents |
|---|---|
| `schema_version` | Integer, initially 1. |
| `audio_input` | enabled, operation, execution_mode, engine, language, format, sample_rate, channels, max_duration_seconds. |
| `video` | enabled, operation, execution_mode, engine, width, height, fps, clip_seconds, event_cooldown_seconds. |
| `audio_output` | enabled, operation, execution_mode, engine, language, voice, format, volume_limit, pause_input_during_playback. |
| `capture` | Activation mode and maximum session duration; no automatic capture just because the agent boots. |
| `response` | Optional fixed event-to-alert mapping with an approved asset reference and cooldown. |
| `limits` | Optional restrictions tighter than organization policy and platform ceilings. |

The default draft sets `schema_version=1` and all three enabled flags to false. Enabling a section requires its operation/engine settings and, for cloud mode, its corresponding relational connection column. An all-disabled profile is valid.

A revision binds each modality to its own connection. Its settings never contain duplicate connection IDs. Each run's `effective_settings` records resolved settings and relevant non-secret connection configuration/version for traceability, without copying secret references/values.

### Device details, capabilities, and health

`details` may contain model, serial_number, os_name, os_version, agent_version, and notes. The server restricts which reported hardware keys the agent may update; it cannot overwrite administrative contact/assignment fields.

`capabilities` lists available cameras/microphones/speakers, supported formats, and installed local engines/version. Hardware IDs are selectors, not authentication credentials.

`latest_health` contains observation time, boot ID, sequence number, component status, and the latest `metrics`. Initially supported measurement keys:

| Group | Keys |
|---|---|
| Resources | `cpu_percent`, `memory_percent`, `disk_free_bytes`, `temperature_c`, `uptime_seconds`. |
| Capture/processing | `capture_fps`, `dropped_video_frames`, `audio_overflows`, `audio_underflows`, `processing_latency_ms`, `upload_failures`, `pending_runs`. |
| Components | `camera_status`, `microphone_status`, `speaker_status`, `last_error_code`. |

Normalize percentages to 0-100; durations/counts/bytes must be nonnegative. Temperature may be negative. Component status is ready/busy/absent/error/unknown. Missing measurements remain NULL/absent. Counters reset with boot_id; do not interpret resets as negative usage.

### Run media, usage, and activity payloads

- `media_manifest` is an array of private references: storage/provider, container/bucket, object key or provider asset ID, media role, format, byte size, expiry, cleanup state/error. Never persist temporary signed URLs; generate them after authorization.
- `usage` records reservation state, accounting date, and reserved/actual quantities with explicit units. Reserve under the organization lock; do not count the same logical request again on retry.
- `result` follows the operation schema: transcript segments, labels with time offsets/confidence, local event details, or generated-audio metadata. Provider-specific optional fields remain bounded.
- `details` in activity events contains redacted before/after values, correlation/context, and optional boot/sequence/historical metadata. Identity/global events have no fabricated organization.
- Retention is calculated from server creation/receipt time. Device-reported timestamps cannot extend retention or make a device appear online. Media expiry remains independent of result expiry.

## Constraints, indexes, and transaction rules for the SQL phase

### Tenant-safe relationships

Add `UNIQUE (organization_id, id)` to tenant-owned parent tables used in composite references. Child references use `(organization_id, referenced_id)` rather than just an ID. Nullable scoped references also require organization_id whenever the child ID is present.

Profile publication has two circular references, added after table creation:

- `organizations.(id, default_profile_id)` references `processing_profiles.(organization_id, id)`.
- `processing_profiles.(organization_id, id, published_revision_id)` references `processing_profile_revisions.(organization_id, profile_id, id)`, backed by a matching unique key.

A device's applied revision can legitimately lag its current profile assignment while configuration synchronizes. Enforce same-tenant linkage in SQL and validate the authorized assignment/revision in the service.

Historical department snapshots must refer to a department in the organization, not be constrained to the device's current department. Resolve historical context from a server-authorized capture/request context, never an untrusted department ID.

Use restrictive deletes for referenced administrative rows; inactive/archive is the normal lifecycle. Retention deletes telemetry, results after cleanup, and expired activities. Device organization transfers create a new registration so historical references remain stable.

Schema v1 also rejects reassignment of record identity/tenant context, protects immutable revisions and append-only history with triggers, and defers administrator coverage checks to transaction commit. Administrator-affecting mutations use READ COMMITTED and the singleton serialization lock. Exact DDL and backend-role grants are described in [README.md](README.md); API permissions are not PostgreSQL login roles and require service enforcement.

### Initial indexes

| Table | Additional access paths beyond PK/uniqueness |
|---|---|
| organizations | Active flag plus name for administration. |
| departments | organization_id, is_active. |
| users | Normalized email; platform_role, is_active for administrator checks; last_login_at where needed. |
| organization_memberships | user_id; organization_id, role, is_active; department scope; pending expiry. |
| devices | organization_id, department_id, is_active; organization_id, last_seen_at; profile_id. |
| provider_connections | organization_id, provider, is_active. |
| processing_profiles | organization_id, is_active. |
| processing_profile_revisions | Unique profile/version key supplies history lookup. |
| processing_runs | organization_id, device_id, created_at; due-work status/next_attempt_at; lease_expires_at; cleanup_status/cleanup_next_attempt_at; expires_at. |
| device_telemetry_samples | organization_id, device_id, received_at; expires_at. |
| activity_events | organization_id, device_id, received_at; organization_id, category, received_at; expires_at. |
| platform_settings | Singleton primary key only. |

Do not add broad JSON indexes until an actual query requires them. The first worker queue uses explicit run fields, not scans through JSON payloads.

### Enforcement responsibilities

- SQL handles nullability, allowed status values, uniqueness, tenant foreign keys, nonnegative counters, valid row-level timestamp relationships, and update timestamps.
- Transactions/locked operations preserve platform/org administrators, consume invitations/enrollment, publish revisions, check active-state permissions, reserve quotas, and claim worker work. Ordinary CHECK constraints cannot enforce changing conditions in other rows.
- All global administrator checks lock platform_settings first, then affected organization rows in deterministic ID order. Role grant/demotion and global deactivation use the same locking order to prevent concurrent last-admin removal.
- Enforce exact role subsets per assignment column, deny mass-assignment of role/identity fields on ordinary profile endpoints, and recheck current roles rather than trusting stale token claims. Org trainees can read scoped results/media but cannot invoke processing or administrative routes.
- Maintenance/inactivity exceptions are explicit route policies, never general authorization bypasses. Preserve authorized admin recovery, device status/health, and worker cleanup only as specified in the platform plan.
- Profile revisions and administrative audit payloads are immutable to normal application roles. Only restricted retention/maintenance paths can delete eligible history.
- Device ingestion may update its permitted health/operational fields only. It cannot change tenant assignments, audit category, actor privileges, connection settings, or active flags.
- Keep processing deadlines at or before media expiry, persist all staged copies, and complete cleanup before deleting the run tombstone. Retention must still redact expired transcript/request content during cleanup failures.

PostgreSQL references: [constraints and foreign keys](https://www.postgresql.org/docs/current/ddl-constraints.html), [JSONB](https://www.postgresql.org/docs/current/datatype-json.html), and [date/time types](https://www.postgresql.org/docs/current/datatype-datetime.html).


## API migrations after the reviewed SQL baseline

The frozen baseline above has 223 columns. `platform/api` owns subsequent Alembic migrations; apply them after a fresh baseline installation or verified adoption. The schema had 13 domain tables and 241 columns at migration `0006_confirmed_plan_limits` (capacity data update after `0005_subscriptions`).

| Table | Added field | PostgreSQL type | Meaning |
|---|---|---|---|
| provider_connections | encrypted_credentials | bytea, nullable | AES-256-GCM nonce/ciphertext/tag; bound to organization and connection IDs |
| provider_connections | credential_key_id | text, nullable | ID of deployment-managed key; present exactly when ciphertext is present |
| devices | preferred_language | text, nullable | Active catalog code chosen for this device; null resolves to English |
| platform_settings | languages | jsonb, required | Up to 100 language entries (`code`, `name`, `speech_locale`, `is_active`); starts with English and Hindi |

English must remain active. Selected catalog codes cannot be removed; deactivation makes affected devices fall back to English. Profile speech-language overrides take precedence. Migration `0002_credentials` invalidates per-operation validation on encrypted credential rotation; migration `0003_languages` enforces catalog/selection integrity. No credential plaintext or encryption key is stored in ordinary settings JSON.

Migration `0004_runtime_guards` changes no fields. It versions connection activation/deactivation and invalidates operation validation in the database, and removes PUBLIC execution on the language trigger function. Published baseline SQL and its 223-field contract remain frozen for verified adoption; that migration head had 227 fields.

Migration `0005_subscriptions` adds required `organizations.subscription_plan_id` (uuid FK) and `organizations.subscription_assigned_at` (timestamptz), plus the twelve-field `subscription_plans` table. The complete field table, seed prices, confirmed default caps, counting rules and upgrade procedure are in [subscriptions.md](subscriptions.md). The API now uses 241 physical fields across thirteen tables.


### Training and scenario authoring migrations

Migration 0007 added `training_scenarios` (13 fields) and `training_sessions` (23 fields), bringing the schema to 15 domain tables and 277 fields. Migration 0008 adds `training_scenario_drafts` (14 fields) and `training_scenarios.source_draft_id` (nullable uuid) / `source_draft_revision` (nullable integer), for **16 tables and 293 fields**. The complete authoring field table, provenance relationships, concurrency rules, privacy boundaries, and future API responsibilities are in [scenario-library.md](scenario-library.md). Document schema version, mutable draft revision, and immutable clinical case version are separate values.


Migration 0009 adds the 32 [LLM storage fields](local-llm.md), bringing the domain schema to **18 tables and 325 fields**.

Migration 0010 adds four provider settings to `llm_connections`: `provider`, `token_parameter`, `stream_usage`, `instruction_role`, bringing the domain schema to **18 tables and 329 fields**. Provider-specific constraints and token limits are detailed in [LLM storage](local-llm.md).

Migration 0011 adds nine `scenario_categories` fields: `id`, `code`, `name`, `name_hi`, `description`, `sort_order`, `is_active`, `created_at`, `updated_at`, bringing the domain schema to **19 tables and 338 fields**. See [category field contracts, three defaults and initialization](scenario-categories.md).

Migration 0012 adds 18 `patient_identities` fields: `id`, `code`, `name`, `name_hi`, `age_years`, `sex`, `occupation_en`, `occupation_hi`, `height_cm`, `weight_kg`, `preferred_language`, `languages`, `background_en`, `background_hi`, `is_fictional`, `is_active`, `created_at`, `updated_at`. Schema at migration 0012: **20 tables and 356 fields**. See [Alex default and field contracts](patient-identities.md).
# Patient practice fields (migration 0013)

Adds `patient_case_templates` (12 fields), `patient_practice_selections` (12 fields), and three nullable provenance fields on `llm_requests`. Domain schema at this revision: **22 tables and 383 fields**. Field lists, ownership, permissions and revision rules are documented in [patient practice](patient-practice.md).

## Current management storage (migration 0020)

Migrations 0014-0019 add patient dialogue, cloud speech/profile routing, token
accounting, local-turn metrics and private conversation history. Their contracts
are described in [LLM storage](local-llm.md), [cloud models](../../docs/cloud-models.md)
and [local history](../../docs/local-conversation-history.md).

Migration 0020 preserves those records and adds six tables:

| Table | Stored contract |
|---|---|
| `local_credentials` | User primary/foreign key, normalized unique login email, optional Argon2id hash, credential version and setup/password timestamps |
| `local_sessions` | User and refresh-family references, unique hashed refresh token, credential version, activity/expiry and revocation |
| `account_action_tokens` | User, purpose, hashed single-use token, optional target email, creation/expiry and consumption |
| `auth_rate_limits` | Composite key of hashed identity and category, window start, bounded request count and expiry |
| `account_email_outbox` | User, recipient/purpose, encrypted delivery payload/key ID, delivery state, fenced lease, retries and expiry |
| `model_definitions` | Unique provider/model key, display metadata, categories/operations/capabilities, adapter availability, lifecycle and version/audit fields |

Users explicitly distinguish local from OIDC identity; issuer/subject are nullable
only for local accounts. Organizations, departments, users, memberships, provider
connections, profiles and LLM connections gain archive fields. Management versions
are added to users, organizations, departments, memberships and profiles.
Membership invitations bind an optional authentication method; LLM connections
may reference a catalog model definition. Runtime grants restrict local identity
and delivery tables to the API. Passwords are one-way hashes, delivery payloads
and provider credentials are encrypted, and encryption keys stay outside PostgreSQL.

The authoritative column mappings are `platform/api/src/pms_api/database/models.py`
and `database/speech.py`; constraints, indexes, functions and triggers are owned
by the forward Alembic migration chain. The upgrade test compares every mapped
column name, PostgreSQL type and nullability with the migrated schema.

## Browser authentication storage (migration 0022)

Migration 0021 adds the partial `events_platform_audit_idx` index only through
the forward migration chain. The twelve-table baseline and its recorded
structural signature remain unchanged.

Migration 0022 adds two columns, bringing the current schema to **31 domain
tables and 545 columns**:

| Table | Field | PostgreSQL type | Meaning |
|---|---|---|---|
| `local_sessions` | `browser_token_hash` | text, nullable, unique | Peppered SHA-256 hash of the opaque browser credential; null for existing bearer sessions |
| `account_action_tokens` | `credential_version` | integer, required, positive | Credential version that authorized the action; verified at consumption |

The rate-limit category constraint includes account-wide login/recovery and
password/email-change limits. Existing reset/setup actions are backfilled;
pre-upgrade email-change actions are consumed because their authorization version
is unknown. Existing credentials and bearer sessions are preserved. API grants
cover both columns; processing and retention roles retain no access to these
authentication tables. Apply `grant-runtime-access.sql` after migration.
