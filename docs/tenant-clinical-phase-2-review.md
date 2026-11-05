# Tenant clinical ownership Phase 2 review

Date: 2026-10-01. Scope: local API, migration, runtime grants, authorization tests and documentation. The application database and Ubuntu VM were not migrated or deployed.

## Implemented

- Forward migration `0030_clinical_capabilities` adds `organization_member_capabilities` with a composite tenant/membership foreign key, allowlisted codes, a unique membership/capability pair, and grant/revocation provenance. It fixes the Phase 1 catalog update trigger using a forward function replacement; no frozen baseline or previous migration was edited.
- Tenant administrators grant and revoke capabilities through member routes. The API checks the active accepted tenant membership, eligible role and department scope for every request. Catalog authors and reviewers require organization-wide staff membership; instructors require eligible staff membership; clinical readers may hold an eligible read-only membership. Tenant admins receive no author/reviewer permission automatically. The browser context resolves effective permissions from current assignments.
- Tenant administrators may assign a capability to themselves, with the same audit path. The separate-reviewer publication rule remains a Phase 3 implementation and product decision; Phase 2 does not publish scenarios.
- The tenant catalog API provides specialties, fictional patient profiles and case drafts at `/api/v1/organizations/{organization_id}/clinical-catalog`. Tenant ID is bound in record, parent, options, list, import and copy queries. A reader receives summaries without case documents or profile backgrounds; only an author/reviewer sees full draft content. Writes use expected row versions, serialized tenant quota checks and same-transaction audit. Archived parents cannot acquire active cases.
- Explicit starter listing/import is limited to fixed seed IDs at unmodified seed revisions. Imported and copied records start inactive. Imports are idempotent within one tenant. The old `/platform/patient-catalog` API routes are absent, and the deployment grant bundle revokes writes to the shared global tables from the API role.

## Review and corrections

The first disposable PostgreSQL run found that the initial Alembic revision string exceeded the 32-character version column; it was shortened before a passing migration rerun. A scoped specialty update then exposed a Phase 1 trigger branch that referenced case-only columns even on other tables. The Phase 2 forward migration corrects the trigger without editing migration 0029. Final access review added an active target-user check for grants and rechecked organization lifecycle after acquiring the catalog write lock. Import review restricted global sources to the reviewed fixed seed identities and their original revisions, preventing a tenant author from importing arbitrary historical global content. Reimport of an existing tenant copy remains idempotent if the global source later changes.

Focused disposable PostgreSQL tests cover two-tenant list/ID/body denial, platform-only denial, capability revocation on the next request, reviewer read versus write, reader-safe projections, inactive membership and target identity, stale and concurrent edits, import/copy, and rollback when audit insertion fails. Migration and runtime-grant tests cover the new head and frozen global writes. Full-suite and final static-check counts are recorded below after the final run.

## Verification

- Disposable PostgreSQL 17 ran the migration/backfill, catalog and grant-focused set: 25 passed. A later affected set covering final import/listing/browser-session additions, legacy grant assertions and schema synchronization passed 22 tests. The schema check matched all 37 tables and 639 ORM columns, including the new capability table.
- The full API run completed with 652 passed, 11 skipped and three failures in tests that still expected API INSERT/UPDATE access to the legacy global catalog. Those three assertions were updated to the new read-only grant contract and all three passed in the affected rerun. The full suite was not rerun after the final corrections; the affected rerun covered the final code changes. Disposable database tests were enabled through `PMS_TEST_ADMIN_DSN`; the 11 skips were opt-in or environment-dependent checks.
- Final `uv run ruff check .`, `uv run ruff format --check .` (184 files), `uv run mypy src/pms_api` (76 source files), and CRLF-aware diff whitespace check passed. The final review found no further confirmed Phase 2 authorization, data-integrity, or audit gaps.

## Deployment boundary

The local API is intentionally incompatible with the current web catalog screens: those screens still call the removed platform routes. Phase 3 must still bind rehearsal, scenario approval, instructor controls and training to these tenant capabilities; existing scenario/training routes retain their previous grants until then. Deploy this API only as a coordinated release with Phases 3 and 4, after the Phase 0 product and target-VM inventory review, verified backup, controlled legacy write pause/backfill, runtime grants, and confirmation that no old API replica can write global catalog records. Hardware, cloud, target-VM deployment and live browser verification were not part of Phase 2.
