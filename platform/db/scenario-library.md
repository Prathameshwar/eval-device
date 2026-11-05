# Patient Scenario Library: database storage

Migration: `0008_scenario_drafts`, after `0007_training_pilot`.

This document describes database storage and deployment/verification scripts. The subsequent [authoring API](../api/deploy/scenario-library.md) implements clinical contracts and the draft/publication workflow on this unchanged schema. UI and version-2 dialogue/device behavior remain deferred. See the [phase plan](../../docs/patient-scenario-implementation-plan.md) and [TODO](../../docs/pms-api-todo.md).

## Storage decisions

Use the existing `training_scenarios` for immutable patient-case snapshots and `training_sessions` for assigned sessions. Add one `training_scenario_drafts` table for editable, incomplete authoring content. Do not create a separate database or one table per symptom/vital. Patient identity, history, initial vitals, approved answers, disclosure rules, and instructor content fit inside the bounded JSONB document; complete nested clinical validation and response projections are enforced by the shared contracts and authoring API.

The database validates the draft envelope: an object of at most 65,536 UTF-8 bytes in PostgreSQL JSONB text representation, with numeric `version` equal to `schema_version` and string `code` equal to the row's code. Schema versions 1 and 2 can be stored. Missing, null, contradictory, or unsupported envelope values fail. Version 2 storage support does not mean the current version-1 runtime can execute it. Drafts are never executable session assignments.

## Draft fields

| Field | Type | Rule |
|---|---|---|
| id | uuid | Primary key; immutable |
| organization_id | uuid | Required organization FK; immutable tenant |
| request_key | uuid | Unique per organization; original creation request; immutable |
| request_fingerprint | text | 64 lowercase hexadecimal characters; fingerprint of the original create request, not the edited document; immutable |
| code | text | 1-40 lowercase letters/digits/underscores, starting with a letter; unique per organization; immutable |
| schema_version | smallint | 1 or 2; must match document.version |
| document | jsonb | Required bounded object; incomplete clinical content is permitted in a draft |
| revision | integer | Starts at 1; database increments exactly once on every update |
| source_scenario_id | uuid, nullable | Original version copied to create this draft; same-organization composite FK; immutable; may have a different code for a copied case |
| created_by | uuid | Required user FK; immutable |
| updated_by | uuid | Required user FK; initially equals created_by; later set by the authenticated service |
| created_at | timestamptz | Set by database on insert; immutable |
| updated_at | timestamptz | Set by database on insert/update; cannot move backwards |
| is_archived | boolean | False by default; archived drafts cannot be published or have their document edited |

One draft per organization/case code is reused across edits and publications. The limit is 100 drafts per organization, including archived drafts. Archiving does not free a slot; it is not permission to accumulate unlimited documents. Existing published-scenario capacity remains 100 versions per organization. Both are explicit pilot bounds, not subscription billing limits.

The organization lock serializes draft capacity checks. Draft creation and draft-backed publication require READ COMMITTED; stale-snapshot isolation is rejected. Copying from another organization's scenario is rejected. Database grants allow no runtime draft deletion or truncation; publication/history references also use restrictive foreign keys.

## Editing transaction contract

Authenticate the user and resolve organization permissions in the future API before any read or mutation. Use parameterized SQL and an explicit expected revision:

```sql
UPDATE device_platform.training_scenario_drafts
SET document = :document,
    schema_version = :schema_version,
    updated_by = :authenticated_user_id,
    revision = :expected_revision
WHERE organization_id = :authorized_organization_id
  AND id = :draft_id
  AND revision = :expected_revision
RETURNING revision, updated_at;
```

A missing result means missing/out-of-scope/conflicting data and must not be treated as a successful save. The trigger advances the revision; do not set expected_revision + 1 yourself. A stale explicit revision also fails if a caller omits the WHERE revision predicate. A plain SQL UPDATE that omits the expected revision cannot establish the caller's intent; the future API must require the complete compare-and-set contract above.

Set updated_by from authenticated identity, not request content. Save the redacted audit event in the same transaction. Do not include patient text or answers in audit details. Database user references are consistency checks, not authentication. An archived draft must be restored in a separate revision before changing its document.

For create retries, read by organization/request_key and compare the ORIGINAL request_fingerprint. Do not compare against the current edited document. Return the existing identity only for an equivalent create request; conflicting key reuse must fail. UUID/unique constraints prevent duplicate storage, but HTTP reconciliation is deferred to the API.

## Publication provenance

Two nullable fields extend training_scenarios:

| Field | Type | Rule |
|---|---|---|
| source_draft_id | uuid | Same-organization draft FK; absent for existing/legacy cases |
| source_draft_revision | integer | Positive revision copied at publication; present exactly when source_draft_id is present |

Existing rows receive NULL provenance; their documents, fingerprints, approvals, and assigned sessions are unchanged. The existing immutability guard protects both new fields after insert.

A draft-backed snapshot must exactly match the current draft's code, revision, and document, must reference an unarchived draft, and must contain explicit approval fields. A unique key allows at most one published version for each organization/draft/revision. Advancing the draft later does not alter the older snapshot. Legacy creation/approval without a source draft remains supported.

The future publishing service must use this transaction order:

1. Authorize the caller and resolve the intended organization.
2. Lock the organization, then the draft. All authoring/publication paths must use this order if taking both locks.
3. Reconcile the publication request key BEFORE allocating another revision. Recheck expected draft revision, lifecycle, clinical completeness, translations, permitted answer modes, and educator approval.
4. Allocate the next scenario version under the organization lock and insert the approved immutable snapshot, including provenance and its canonical fingerprint.
5. Insert the redacted audit event and commit together. On failure, all changes roll back.

The database enforces snapshot identity, uniqueness, references, and atomic transaction behavior. It cannot establish clinical accuracy, an authenticated educator's approval, or the correctness of an application-supplied fingerprint. It does not invent an audit actor or automatically add audit events. Those existing service responsibilities remain mandatory in the API phase. Never seed an approved version-2 case into a live version-1 runtime.

## Database privileges

The API backend role receives SELECT/INSERT/UPDATE on drafts. The worker and retention roles receive no draft privileges, including after the grant bundle's broad existing SELECT grants. PUBLIC receives no draft privileges or execution rights on the new guard functions. The API has no DELETE/TRUNCATE permission. These are trusted backend roles, not human/tenant roles; no row-level security is introduced. Every future endpoint must enforce organization and role scope, and device/session/media access retains department restrictions. Platform administrators have no implicit tenant-content authorization.

The existing published snapshots and sessions retain their grant model. Full clinical documents must remain private to authorized instructor/runtime paths; a generic database serializer must not become a learner detail endpoint.

## Installation and verification

Back up an application database before a reviewed deployment. Use the existing schema owner/migration role and three unprivileged backend roles; never run the application as owner. From platform/api:

```powershell
uv run pms-admin migrate
psql -X -h <host> -p <port> -U <schema-owner> -d <database> -v db_name=<database> -v api_role=<api-role> -v worker_role=<worker-role> -v maintenance_role=<retention-role> -f deploy/grant-runtime-access.sql
psql -X -h <host> -p <port> -U <schema-owner> -d <database> -f deploy/verify-scenario-library.sql
```

Use the configured migration DSN for migrate. The grant bundle is atomic and must be reapplied after migration. The read-only verifier checks the current migration head, draft columns, publication constraints, enabled guards, and PUBLIC function execution. It is a structural check, not a replacement for application-role or clinical acceptance tests. API readiness now expects migration 0008; deploy the matching package and schema together.

The frozen SQL baseline and prior migrations are unchanged. Fresh installations upgrade through all Alembic revisions. Existing baseline-only installations require verified adoption before migration. Downgrade intentionally refuses destructive removal; recovery requires a reviewed forward fix or backup restore.

## Verification scope

Automated database tests cover envelope rejection, immutable identity, editing revisions, archived drafts, tenant references, publication snapshots/approval presence, original request uniqueness, backend grants, actual lock contention at the quota boundary, concurrent editors/publications, rollback of publication/audit, upgrades with retained version-1 cases/sessions, and populated backup/restore. Run only against a dedicated disposable PostgreSQL server. Actual execution evidence and review findings are recorded in [reviews](../../docs/pms-api-reviews.md); API authorization and the authoring workflow are verified separately by the API tests linked above.