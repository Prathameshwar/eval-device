# Tenant-owned clinical content and training: implementation plan

Date: 2026-10-01. Status: Phases 0-5 are implemented and reviewed locally; Phase 6 verification and Phase 7 release preparation are recorded in the [combined review](tenant-clinical-phases-3-7-review.md). The [Ubuntu rollout checklist](tenant-clinical-rollout.md) covers the operator-run VM cutover. The application and VM databases have not been migrated, and physical device identity, clinical approval, and VM evidence remain external gates. See also the [Phase 0 review](tenant-clinical-phase-0-review.md), [Phase 1 review](tenant-clinical-phase-1-review.md), and [Phase 2 review](tenant-clinical-phase-2-review.md).

## Product contract

Each hospital or institute (organization/tenant) controls its own devices, staff access, clinical specialties, fictional patient profiles, cases, approved Q&A, and training policy. A device registration belongs to one tenant at a time. Training joins a device, instructor, learner, and approved scenario version from that same tenant. A person with memberships in several tenants must select one context; permissions and data stay separate. Platform administration covers tenant onboarding, subscriptions, global accounts, service settings, aggregate health, and platform audit. It grants no clinical-content, session, or media access in a tenant context.

Clinical content is tenant-wide for the first release. Existing department scope still limits device use, sessions, results, and media. A later department-specific library needs its own explicit contract. All patient profiles remain fictional simulation material.

The tenant workflow is: select specialties -> author patient profiles and case drafts with approved answers, disclosure rules, learning objectives, and rubric -> review and publish an immutable scenario version -> select same-tenant device, instructor, and learner -> verify readiness and start -> retain the pinned version, results, feedback, and bounded media. The scenario controls patient facts, language, answers, and assessment; a tenant processing profile controls model/voice/media behavior within platform and device limits. Published versions and completed sessions never change when a catalog entry is edited.

## Baseline at plan start

- `scenario_categories`, `patient_identities`, and `patient_case_templates` are global tables without `organization_id` in `platform/api/src/pms_api/database/models.py`. The platform routes in `platform/api/src/pms_api/modules/patient_catalog.py` use `platform.settings.read/manage`; `platform/ui/apps/web/src/lib/navigation.ts` places them under Platform Admin.
- `patient_case_templates` currently supply **staff rehearsal** through `platform/api/src/pms_api/modules/patient_practice.py`, `llm.py`, and `patient_conversations.py`. They are distinct from educator-approved learner training scenarios. The saved rehearsal document is a snapshot.
- `training_scenario_drafts`, `training_scenarios`, and `training_sessions` already have `organization_id`. `platform/api/src/pms_api/modules/scenarios.py` gates authoring on `org.profiles.manage`; `training.py` gates session start on `org.processing.execute` and `org.playback.execute`. Those permissions combine duties that this plan separates.
- Device registrations and historical training already carry tenant ownership. The existing physical-device transfer retires the old registration and requires fresh enrollment; it must continue to carry no clinical content or media between tenants.
- Device registration has a single `organization_id`, but optional physical serial information is stored in JSON without a global uniqueness constraint. A one-registration-per-physical-unit rule needs an enforceable device identity policy.
- The structured case editor supports version 3 documents, while the current device training runtime accepts version 1 scenarios. Phase 3 must validate a conversion or add explicit runtime support before a tenant-authored case can run on a device.
- `platform/api/src/pms_api/security/default-roles.json` and `security/access.py` define fixed role grants. `platform/ui/apps/web/src/lib/session-user.ts` folds read-only and trainee into the Tenant User navigation shape, then filters by grants. New responsibilities require the API identity response and UI navigation to use the same effective permissions.

## Access policy to implement

Use the current tenant membership as the authority anchor. A tenant administrator now receives clinical authoring by role, so they can manage specialties, patient profiles and case Q&A immediately. A small, allowlisted, audited membership-capability assignment lets eligible staff hold more than one clinical responsibility without multiplying mutually exclusive base roles. The tenant administrator assigns and revokes staff capabilities and separate reviewer/instructor/reader capabilities; reviewer access remains separate from the author role.

| Capability | Allowed operations | Scope |
| --- | --- | --- |
| Clinical author | Read private draft content; create/edit/archive specialties, fictional profiles, case drafts, Q&A, and learning objectives | Active, accepted, organization-wide staff membership |
| Clinical reviewer | Read private draft and rubric; record review and publish/retire scenario versions | Active, accepted, organization-wide staff membership |
| Instructor | Read approved instructor material; assign/start/stop training and submit permitted feedback | Active, accepted `org_admin` or `org_user` membership; retain processing/playback grants and honor department/device scope |
| Clinical reader | Read permitted catalog summaries without draft answers or hidden rubric | Active, accepted membership and its department policy |

The `org_trainee` role retains learner-safe, own-session access; `org_read_only` does not acquire clinical draft access by default. Device credentials retain only device operations. Platform admins may receive a separate tenant membership through the existing audited process, with no permission inherited from their platform role. Re-evaluate active membership and capability on each request and after taking mutation locks; never rely on a browser menu or token role claim as the access check.

**Phase 0 implementation decision:** require a reviewer different from the author of the published draft revision, with no single-person exception in this release. A Tenant Admin may assign clinical capabilities to themselves with an audit event, but a second person must still review and publish their authored content.

## Phase 0 - Freeze the contract and inventory existing data

**Files:** this plan; `docs/platform-service-plan.md`; `docs/web-content-management.md`; `docs/patient-scenario-library.md`; `platform/api/README.md`; `platform/db/README.md`; `platform/api/src/pms_api/security/default-roles.json`.

1. Record the final permission matrix, approval rule, tenant-wide content policy, starter-content policy, and exact instructor versus trainee views. Define what an archived specialty/profile/case does to future selection while preserving old snapshots.
2. Inventory global categories, profiles, cases, modified seed rows, practice selections per tenant, published scenario versions, active sessions, and existing ID/FK dependencies. Check organizations with no content, multiple staff selections, and repeated case codes across tenants.
3. Define a migration report and invariants: every active new reference has exactly one tenant; parent references share that tenant; all old published hashes and session IDs remain unchanged; the old-to-new mapping is complete for currently used records.
4. Review current platform device-registration and user-association operations with the tenant ownership rule. Retain limited platform onboarding and aggregate fleet status; make tenant administrators responsible for normal enrollment, configuration, and staff membership.

**Exit/review:** product owner approves the access and publication matrix. A read-only inventory and migration rehearsal plan is reviewed before schema changes. Record decisions in the TODO and review evidence.

## Phase 1 - Expand the schema and backfill safely

**Files:** a **new forward** `platform/api/migrations/versions/<next>_tenant_clinical_content.py`; `platform/api/src/pms_api/database/models.py`; `platform/api/deploy/grant-runtime-access.sql`; `platform/api/src/pms_api/cli.py` for a bounded dry-run/apply backfill command; `platform/api/tests/test_catalog_migration.py`; new migration/constraint tests; `platform/db/README.md`. Do not edit frozen `platform/db/sql/*.sql` or old migrations.

1. Add proposed `organization_clinical_specialties`, `organization_patient_profiles`, and `organization_case_templates` tables. Include `organization_id`, immutable stable ID/code, `(organization_id, code)` uniqueness, lifecycle/revision fields, creator/editor identity, and `source_global_id` provenance. Use `(organization_id, id)` keys and composite foreign keys so cases cannot point at another tenant's specialty or profile, and selections cannot point at another tenant's case. Index tenant listing/filter paths; enforce per-tenant caps under platform hard limits with a locking strategy for concurrent writes.
2. Treat the existing global tables as legacy/seed records and make them read-only at the coordinated API cutover in Phase 2. Until then, the old API can still write them; stop those writers for the backfill and do not restart them before cutover. Provide no shared live clinical template whose later edit changes tenant content. New tenants start with an empty clinical catalog; importing starter examples is an explicit tenant action that creates inactive/pending-review copies.
3. Add new tenant-content references to `patient_practice_selections` in stages. The existing global-reference columns are `NOT NULL`, so the expansion must permit a validated legacy-or-tenant reference shape before new tenant writes. Backfill tenant references, then require them for every new selection. Preserve the saved `document`, revision, identity, and existing `llm_requests` references. Keep old FK columns only as long as legacy selections need them; a later forward migration removes obsolete constraints/columns after verified conversion.
4. Backfill **only** global records referenced by a tenant's current selection, cloning them per tenant and storing old/new ID mappings. Report orphans, duplicates, and any content whose intended tenant cannot be established. Require tenant review before a copied case is enabled for new work. Do not rewrite immutable published scenarios, historical sessions, or their hashes.
5. Make the backfill idempotent and resumable under a controlled write pause. Produce pre/post counts and per-tenant mapping checks. Test upgrade from the actual previous Alembic head and from a restored application-like database; verify least-privilege API/worker/retention grants.

**Exit/review:** disposable PostgreSQL tests prove cross-tenant FK rejection, unique codes per tenant, concurrent caps, exact snapshot preservation, idempotent backfill, and backup/restore. Review data-loss and lock-time risks before API cutover.

## Phase 2 - Implement tenant permissions and catalog API

**Files:** `platform/api/src/pms_api/security/default-roles.json`, `security/access.py`, `modules/auth.py`, `modules/management.py`, `modules/patient_catalog.py`, `modules/patient_catalog_schemas.py`, `main.py`, `database/models.py`, a forward migration for capability assignments and any changed default-role view, and `deploy/grant-runtime-access.sql`; `platform/api/tests/test_patient_catalog_management.py`, `test_people_management.py`, `test_management_api.py`, and new authorization tests. Keep the frozen SQL baseline unchanged.

1. Add proposed `organization_member_capabilities` with a constrained capability code, membership/organization foreign key, grant/revocation provenance, and one active assignment per membership/capability. Add administrative grant/revoke routes. Introduce explicit catalog-author, scenario-reviewer, and training-instructor permission keys; keep `org.profiles.manage` for processing profiles instead of using it as clinical authoring authority. Only an active tenant administrator can change assignments; write the assignment and audit event atomically. Revocation takes effect on the next request, including a reused browser session. Update the current-context API to return only effective permissions for that verified membership.
2. Move catalog endpoints to `/api/v1/organizations/{organization_id}/clinical-catalog/{specialties|patients|cases}`. Lists, details, options, validation, edits, archive/restore, and copy/import all require current membership plus the exact capability. Every lookup binds `organization_id`; IDs in request bodies are rechecked against the same tenant. Return 404 for foreign-tenant objects without exposing their existence.
3. Keep credentials, audit metadata, logs, and error responses free of case text and media URLs. Save content and its audit event in one transaction; use expected revision for edits and lifecycle changes; serialize quota checks. Return safe conflicts for stale writes and uncertain responses.
4. Close the old `/platform/patient-catalog` read and write routes at cutover. Platform Admin's `platform.settings.manage` must no longer authorize clinical edits. Coordinate API replicas and old web clients so no old replica can keep writing global records after backfill.

**Exit/review:** a two-tenant API matrix proves read/write/ID-guess denial, platform-role denial, inactive/archived membership denial, instant capability revocation, and atomic audit/rollback under concurrent writes.

## Phase 3 - Connect authoring, rehearsal, approval, and runtime snapshots

**Files:** `platform/api/src/pms_api/modules/patient_practice.py`, `patient_conversations.py`, `llm.py`, `scenarios.py`, `training.py`, `patient_catalog_schemas.py`; shared contracts only if payload changes; `platform/api/tests/test_patient_practice.py`, `test_scenario_drafts.py`, `test_scenario_library.py`, `test_scenario_review.py`, `test_training.py`.

1. Resolve staff rehearsal cases from tenant-owned records. Only a clinical author with organization-wide staff membership can save a rehearsal selection; execution also retains the existing processing permission. A selection must match the caller's tenant and retain its private document snapshot. Legacy selections remain readable as history only for their owning tenant while conversion completes; new rehearsal starts require a tenant-approved migrated case and new writes use tenant IDs. The preflight report names tenants that need approval before cutover.
2. Let an author copy a tenant case into the existing `TrainingScenarioDraft` flow, recording source ID/revision. Q&A, patient-known facts, disclosure rules, hidden diagnosis, and instructor rubric remain in the bounded document with separate safe projections. Editing a profile or case never silently mutates a draft or a published version; the author explicitly refreshes and reviews a new revision. Resolve the version 3 editor versus version 1 device runtime gap with a validated conversion or supported runtime version; refuse assignment when no compatible runtime exists.
3. Require reviewer capability and the agreed author/reviewer rule at publication. Recheck after locking; validate active same-tenant parents, language completeness, approved answers, rubric separation, and lifecycle. Publication creates one immutable tenant scenario version and one audit event atomically; repeat requests keep existing idempotency behavior.
4. Creating, accessing instructor controls/rubrics, starting, stopping, and assessing training require instructor capability plus existing processing/playback eligibility, an active same-tenant device and learner, department compatibility, an approved active scenario version, current subscription/lease limits, and a matching runtime hash. Audit each control action. Results, feedback, and media remain scoped to the session's recorded tenant and department. Preserve device lease fencing and uncertain playback/submission rules.

**Exit/review:** staff rehearsal, publication, and training tests pass with two tenants and multiple departments. Old approved versions and existing sessions remain readable without changing fingerprints.

## Phase 4 - Rework the web console

**Files:** `platform/ui/apps/web/src/lib/navigation.ts`, `roles.ts`, `session-user.ts`, `catalog-access.ts`, `catalog-actions.ts`, `patient-catalog.ts`, `practice-actions.ts`, `scenario-actions.ts`; `components/ConsoleShell.tsx`, `CatalogDirectory.tsx`, `CatalogEditor.tsx`, `PatientSetup.tsx`, `ScenarioLibrary.tsx`; `src/app/(console)/catalog/**`, `scenarios/page.tsx`, tenant member/capability screens; tests `navigation.test.ts`, `catalog-actions.test.ts`, `catalog-editor.test.tsx`, `settings-pages.test.tsx`, and browser catalog journey.

1. Remove Clinical specialties, Patient profiles, and Cases & Q&A from Platform Admin navigation and direct-route access. Add a tenant **Clinical content** section: Specialties, Patient profiles, Case drafts & Q&A, and Published scenarios. Reuse the existing `/scenarios` library for published versions. Show author, reviewer, and instructor controls from the API's effective permissions, including multi-tenant context switching.
2. Make the content journey explicit: create/copy -> edit -> preview patient-safe and instructor views -> submit for review -> approve/publish -> select for rehearsal or training. Show inactive/stale-parent status, validation paths, concurrent-save conflicts, and who approved each version. Keep Q&A within the case/scenario document; avoid a second independent answer store.
3. Keep Platform Admin pages to platform operations. Tenant Admin handles members, capability assignments, departments, devices, and tenant configuration. Direct Next page requests and server actions use the same tenant/permission checks as the API; hiding a link is presentation only.

**Exit/review:** unit and real browser journeys show correct menus and direct-route denial for all roles; Tenant A never sees Tenant B in lists, search, copied IDs, previews, or errors. Mobile, keyboard, and failed-save behavior are reviewed.

## Phase 5 - Verify device execution and session isolation

**Files:** `platform/api/src/pms_api/modules/training.py`, `modules/devices.py`, `modules/scenarios.py`; `device/training/src/device_training/coordinator.py` and its tests **if** the signed scenario/assignment contract changes; `platform/api/tests/test_training.py`, `test_device_management.py`, and relevant integration tests.

1. Confirm one enrolled device registration has one current tenant. Define an attestable physical identity and enforce at most one current registration for that identity, including how serial-less devices are handled. Physical reassignment retires/revokes the old registration, clears local credentials and patient state, then enrolls a new tenant registration; historical records stay with the original tenant.
2. At assignment and Start, bind device ID, tenant, learner, instructor, approved scenario ID/revision/hash, language, and lease. Recheck tenant membership, department, device status, scenario status, runtime capability, and quota when work actually starts. An edited or retired case cannot replace the pinned session document.
3. Run two fictional cases in sequence on one device fixture and verify that answer facts, dialogue memory, patient state, and media labels do not cross sessions. Keep instructor-only rubric out of patient/trainee responses. Validate idempotent retries and uncertain external/playback outcomes with mocks.

**Exit/review:** API and companion fixtures demonstrate correct tenant/device/version binding. Hardware and hosted checks are reported separately from local software results.

## Phase 6 - Integrated verification and first review

**Files:** affected test files above; `platform/api/tests/test_catalog_web.py`, `test_catalog_migration.py`; `docs/pms-api-todo.md`; `docs/pms-api-reviews.md`.

1. Test upgrade, grants, backup/restore, auth, tenant/department isolation, lifecycle, concurrency, quota, audit, and old-client behavior on a dedicated disposable PostgreSQL server. Never point `PMS_TEST_ADMIN_DSN` at the application database. Mock cloud calls.
2. From `platform/api`, run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/pms_api`. From `platform/ui`, run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build`. Run the affected `device/training` suite if its contract changes. Report skipped database tests explicitly.
3. Review authorization on every route/server action, database tenant FKs, history preservation, stale writes, error paths, safe learner projections, subscription/device behavior, worker permissions, and migration compatibility. Fix confirmed findings and rerun affected checks.

**Exit:** the first review has recorded findings, fixes, test evidence, and remaining limitations. A clinical educator separately reviews sample patient facts, answers, translations, and rubric; passing software tests does not certify clinical content.

## Phase 7 - Fresh review and Ubuntu rollout

**Files:** `platform/api/README.md`, `platform/db/README.md`, `docs/web-content-management.md`, `docs/platform-service-plan.md`, `docs/patient-scenario-library.md`, `docs/pms-api-todo.md`, `docs/pms-api-reviews.md`, `start/README.md`; review the in-progress `start/deploy-platform.sh` when it becomes part of the release.

1. Re-review the final code **after** Phase 6 fixes, including two-tenant negative paths, migration maps, runtime grants, backup restoration, stale Next UI, and source/packaged artifact parity. Re-run only checks needed for changed code or unresolved risk. Record this as Review 2, separate from Review 1.
2. Rehearse deployment on a restored staging database with the exact artifact intended for Ubuntu. Quiesce catalog writes and new sessions, take a verified backup, apply forward migrations and grants once, run backfill, deploy API/worker/retention and rebuilt Next UI, then check `/health/ready` and HTTPS/Nginx routing. Confirm old API replicas are gone before reopening writes. Test a tenant author/reviewer/instructor journey and a second tenant's denied access.
3. Record post-cutover counts, unresolved legacy selections, role assignments, and a rollback drill. A schema-changing rollback needs a matching database restore or reviewed forward repair; switching code alone is insufficient. Keep the existing hosted/cloud/Pi verification limits explicit until those checks actually run.

**Exit:** both software reviews and all required checks are recorded; a tenant representative approves the clinical workflow and starter content; the target VM's migration, readiness, two-tenant smoke test, and recovery drill have actual evidence.

## Acceptance checklist

- Platform Admin cannot list, open, edit, or publish tenant clinical content through API or UI solely by platform role.
- Each tenant can choose and edit its own specialties, profiles, cases, answers, approvals, and training settings without changing another tenant's records.
- Foreign IDs, inactive memberships, missing capabilities, wrong departments, retired devices, and stale scenario versions fail safely on direct API calls as well as in the browser.
- An instructor can start only a valid same-tenant session with an approved immutable version; a trainee sees only permitted learner-safe content and own results.
- Existing rehearsal snapshots, approved scenario hashes, sessions, media ownership, and audit history survive the upgrade.
- Migration, permission, concurrency, UI, runtime, two reviews, staging, and target-VM evidence are recorded with skipped or deferred checks named honestly.

External design references: [OWASP multi-tenant security](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html), [OWASP authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), and [PostgreSQL 17 constraints](https://www.postgresql.org/docs/17/ddl-constraints.html).
