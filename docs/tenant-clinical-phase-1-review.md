# Tenant clinical ownership: Phase 1 review

Date: 2026-10-01. Scope: local schema expansion, runtime grants, and owner-only backfill tooling. The application and Ubuntu VM databases were not migrated.

## Implemented

Forward Alembic migration `0029_tenant_clinical_content` adds tenant-owned clinical specialties, fictional patient profiles, and case templates. Stable IDs/codes, same-tenant composite foreign keys, inactive imported copies, immutable provenance, revision checks, size bounds, and per-tenant caps are enforced in PostgreSQL. Existing global catalog data and the saved rehearsal document/revision remain in place. The current selection table accepts a complete legacy reference group, a complete tenant reference group, or both during cutover.

The owner-only `pms-admin tenant-catalog-backfill` defaults to a read-only, count-only dry run. Apply needs backup and write-pause confirmation flags, processes bounded organization batches, copies only records referenced by legacy selections, and records a count-only audit event in the same transaction as each mapping. It rejects changed global source revisions and inconsistent prior mappings. The old platform catalog routes still write global records, so an actual backfill requires a real old-writer pause maintained through the Phase 2 cutover.

## Review findings and fixes

- The existing selection trigger advances revision on any update. The backfill now locks the selection table, temporarily disables that one trigger as schema owner, fills only the tenant references, re-enables it before commit, and verifies every saved document hash, revision, and legacy reference. A failed transaction restores trigger state and data.
- A worker inheriting the API database role could read private tenant cases despite table revokes. Both grant scripts now reject membership among the three runtime roles; a PostgreSQL regression proves the preflight fails and worker access remains absent.
- The original seeded-global-catalog forward-upgrade regression was restored after the new migration tests were added. A separate previous-head upgrade test preserves an existing rehearsal selection. A custom-format PostgreSQL backup/restore test compares restored selection hashes and tenant mappings.
- Full-suite review exposed stale tests for self-disable status, conversation start, local-turn idempotency/evidence-review rules, and the current 512 KiB draft cap. Their assertions now follow the existing API contract. The migration adoption test now pins its owner URL to the disposable target instead of allowing a local `.env` URL. The Hindi latency case explicitly skips until a Hindi conversation pack is bundled.
- A concurrent VM deployment edit had mixed line endings in `management.py`; only those line endings were normalized. Its logic and 10-line diff were preserved.

## Verification

- `PMS_TEST_ADMIN_DSN` pointed only to a dedicated disposable PostgreSQL 17 cluster on `127.0.0.1:55823`. The full `uv run pytest -q --tb=short` run passed: **654 passed, 11 skipped, 0 failed** in 29m 16s. The skips were eight opt-in browser tests, two native audio/model checks, and the absent Hindi conversation pack. No database tests were skipped.
- Disposable PostgreSQL tests covered fresh and previous-head upgrades, seeded global data and saved snapshot preservation, cross-tenant FK rejection, same-tenant code uniqueness, concurrent tenant capacity, worker/retention grants, inherited-role rejection, inactive copies, source-drift rollback, idempotent/resumable batches, and backup/restore. Cloud calls were mocked.
- `uv run ruff check .`, `uv run ruff format --check .` (183 files), `uv run mypy src/pms_api` (76 files), and a CRLF-aware Git diff whitespace check passed. The final code and documentation were reviewed again after the fixes.

## Final review

Rechecked the final migration and backfill for same-tenant references, historical snapshot preservation, stale source handling, transactional audit, quota races, worker access, bounded locks, and old-client compatibility. The reviewed Phase 1 code has no remaining confirmed blocker. Its tenant authorization release is still gated on the later API cutover; running the backfill while old global writers remain active would invalidate the mapping.

## Remaining gates

Phase 1 is a preparatory expansion. Platform Admin still has the existing global catalog routes; tenant author/reviewer permissions, tenant catalog API, Q&A approval, UI menus, and device execution are later phases. Before a production cutover, review the target VM inventory and product policy defaults, take and verify a backup, pause old writers and new sessions, apply the forward migration and grants, run/reconcile the backfill, and keep old writers stopped until the tenant API replaces them. There is no target-VM, hosted cloud, or Raspberry Pi verification in this review.
