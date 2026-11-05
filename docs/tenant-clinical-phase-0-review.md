# Tenant clinical ownership: Phase 0 contract and inventory

Date: 2026-10-01. Scope: source review and read-only inventory of the local application database at Alembic `0028_language_validator_acl`. The target Ubuntu VM database has not been inspected. This report contains no clinical document or media content.

## Contract used for implementation

| Responsibility | Eligibility and access |
| --- | --- |
| Platform administrator | Onboard tenants, global accounts, plans, service configuration, aggregate fleet health and platform audit. No tenant clinical drafts, Q&A, training sessions or media by platform role alone. An explicit tenant membership is required for tenant work. |
| Tenant administrator | Manage members, capability assignments, departments, devices, provider/processing settings and tenant audit. Clinical author/reviewer/instructor access requires a separately assigned capability. A tenant admin may assign a clinical capability to themselves, with an audit event. |
| Clinical author | Active, accepted, organization-wide `org_admin` or `org_user` membership with `clinical.author`. Create/edit/archive tenant specialties, fictional profiles, case drafts and Q&A; create and edit training scenario drafts. Cannot publish the revision they last authored. |
| Clinical reviewer | Active, accepted, organization-wide staff membership with `clinical.reviewer`. Review and publish an approved, immutable scenario version. The reviewer must differ from the author of the draft revision being published. |
| Instructor | Active, accepted `org_admin` or `org_user` membership with `training.instructor` plus the existing processing/playback eligibility. View instructor material and manage training only within the membership's department/device scope. |
| Clinical reader | Active, accepted membership with `clinical.reader`. Read approved summaries in their permitted scope; no private draft answers or hidden rubric. |
| Trainee/device | A trainee gets learner-safe own-session information only. A device gets only its credential-bound assignment and runtime operations. Neither gets draft Q&A or instructor rubric. |

These are implementation defaults from the agreed phase plan. A later product correction can change the policy before cutover. New tenants start with an empty catalog. Starter examples are copied only on explicit tenant action, start inactive, and require tenant review. Clinical records are tenant-wide initially; department scope applies to device operation, sessions, results and media. Codes and IDs are immutable. Archive blocks future catalog selection and new publication from that record; it does not change existing saved rehearsal documents or published scenario versions. Retiring a published version blocks new sessions while preserving historical sessions. Editing or archiving a source case does not silently retire a previously approved immutable scenario version.

## Source and dependency inventory

| Current path | Finding and migration consequence |
| --- | --- |
| `platform/api/src/pms_api/database/models.py`; migrations `0011`, `0012`, `0013`, `0027` | `scenario_categories`, `patient_identities`, and `patient_case_templates` are global. They lack tenant IDs. Their codes are globally unique. `patient_practice_selections` has a tenant ID but three non-null global FKs and a saved document. A forward migration needs a valid legacy-or-tenant reference shape. |
| `modules/patient_catalog.py`; `security/default-roles.json` | Platform settings authority currently lists and edits the global clinical catalog. It must be closed at API cutover, including old API replicas. |
| `modules/patient_practice.py`, `llm.py`, `patient_conversations.py` | Staff rehearsal reads global case/profile/category records and saves one selection per staff member and tenant. New rehearsal must use tenant-approved content; old snapshots and conversation links stay with their recorded tenant. |
| `modules/scenarios.py`, `modules/training.py` | Drafts, published scenarios and sessions already carry tenant IDs. Scenario authoring currently uses `org.profiles.manage`; session creation uses processing and playback grants. The new capability checks must recheck membership after locks. |
| `platform/ui/apps/web/src/lib/navigation.ts`; catalog pages/actions | Platform Admin currently sees Clinical specialties, Patient profiles and Cases & Q&A. Tenant Admin sees Patient setup and Scenario library. Navigation and direct server actions both need the new effective capabilities. |
| `modules/devices.py`; `database/models.py` | Each registration has one immutable organization ID and tenant-scoped enrollment. The optional physical serial is in `details` JSON, without a global uniqueness constraint. Phase 5 must decide how to enforce one current registration per physical unit, including units without a trustworthy serial. |
| `docs/web-content-management.md`; `modules/scenarios.py` | The structured case editor supports version 3 content, while the current device training runtime accepts version 1 scenario documents. Phase 3 needs an explicit validated conversion or a supported runtime contract before claiming that an edited case can run on a device. |

`llm_requests` and `patient_conversations` reference `patient_practice_selections`; `training_sessions` reference `training_scenarios`. Preserve these historical links. A new tenant catalog must use composite `(organization_id, id)` references throughout. Reusing a global case code in two tenants is valid; using two copies of the same code inside one tenant is not.

## Read-only local database inventory

The query file is [`platform/api/deploy/tenant-clinical-inventory.sql`](../platform/api/deploy/tenant-clinical-inventory.sql). It opens a repeatable-read, read-only transaction and rolls it back. It prints tenant UUIDs and counts, not case text, patient names, credentials or media. Copy the file to the target VM, then run this command from the directory containing `platform/api/deploy` before any migration:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d device_platform < platform/api/deploy/tenant-clinical-inventory.sql
```

Do not put a password in the command. Use the VM's existing secure PostgreSQL authentication. Save the output privately as migration evidence.

Local application database observation on 2026-10-01:

| Measure | Count |
| --- | ---: |
| Global specialties / active | 3 / 3 |
| Global fictional profiles / active | 1 / 1 |
| Global cases / active | 9 / 9 |
| Tenants / current practice selections | 1 / 1 |
| Distinct global cases referenced by that tenant | 1 |
| Drafts / approved scenarios / awaiting approval / training sessions | 0 / 0 / 0 / 0 |
| Unusable practice selections / unexpired active sessions | 0 / 0 |
| Enrolled registrations / enrolled with unrevoked credentials | 0 / 0 |
| Missing/mismatched selection parents; cross-tenant session device/scenario references | 0 |
| Global cases selected by more than one tenant | 0 |

The category/profile management-version indicator is zero. All nine cases have revision above one because an earlier language migration revised them; this is not evidence of nine manual edits. The query cannot prove whether pre-versioning seed rows were customized or which tenant should inherit an unused shared record. The target VM may contain different data and must be inventoried separately. Historical missing-membership counts are informational: a member may have been removed after a session. They do not test whether a current membership is active.

## Phase 1 rehearsal and review gates

1. Before migration, record the VM query output, `public.alembic_version`, a verified backup, counts by tenant, and hashes of saved practice documents, published scenario documents/fingerprints, and session IDs. The hash report must not print documents. Pause old catalog writes and new sessions for the final backfill/cutover window.
2. Expand schema with tenant specialties, profiles and cases, composite tenant FKs, per-tenant codes, lifecycle and provenance. Permit old global-reference selections during transition. Keep global tables and old snapshots intact.
3. Copy only global records actually selected by each tenant into inactive tenant records. Persist an unambiguous old/new mapping. Rerunning the backfill must not create another copy. Require a tenant reviewer to activate copied content for future work.
4. Compare all pre/post counts and hashes and assert no missing mapping, no foreign-tenant FK, unchanged `llm_requests`/conversations, unchanged published fingerprints and unchanged session IDs. Test on a restored, disposable database before using the VM.
5. Cut over all API replicas and UI together. No old replica may continue global writes after the last backfill. A schema rollback uses a reviewed forward repair or database restore; switching only application code is insufficient.

Review 0 findings: the global catalog route and Platform Admin menu violate the desired ownership model today; scenario authoring and training grants are too broad; physical device identity is not database-unique; version 3 case content is not yet executable by the version 1 device training runtime. These are planned Phase 2-5 changes, not claims of current protection. The local query completed without integrity anomalies. VM inventory, tenant clinical review, hardware and hosted behavior are unverified.
