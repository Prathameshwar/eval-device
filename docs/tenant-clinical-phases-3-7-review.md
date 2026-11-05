# Tenant clinical ownership: Phases 3–7 review

Date: 2026-10-01. Scope: local API, web, device fixture, disposable PostgreSQL and Ubuntu release preparation. The target VM, hosted services and Raspberry Pi hardware are outside the local workspace and have no execution evidence here.

## Implemented software

- New staff rehearsal selections resolve active cases, specialties and fictional profiles from the selected tenant. Saves keep a private snapshot and tenant IDs. Legacy selections remain readable to their owner, but cannot start a new rehearsal.
- Scenario authors can copy and explicitly refresh a tenant case. Migration 0031 stores source ID/revision and the last content editor, with same-tenant foreign keys and a database revision guard. A different clinical reviewer records source-language review and publishes immutable versions. Version 3 English/Hindi content is validated and compiled into the signed version 1 device format at assignment; the original published document and fingerprint remain intact. Sessions pin both source and runtime hashes.
- Session creation, instructor controls, feedback and rubric access require the current instructor capability plus processing/playback and the existing tenant, department, learner, device, profile, quota and lease checks. Device start rechecks current authorizations and hashes. A two-case device fixture verifies answer, memory, state and media-label isolation on one device.
- The web console removes clinical catalog links from Platform Admin, uses the tenant clinical catalog and effective permissions, shows copy/refresh/reviewer controls, and lets tenant administrators assign clinical capabilities. Server actions and direct pages check context and capability; readers cannot open the empty “new” editor pages.
- The Ubuntu deployment script now runs the owner-only legacy mapping after migration while services are stopped and before the new API starts, and checks that every legacy selection is mapped. The release checklist records preflight, backup, smoke and recovery steps.

## Review 1: findings and fixes

1. Published versions created from a draft attributed creation to the reviewer. The publication now records the draft's last content author in `created_by` and retains reviewer identity in approval and the audit event.
2. The owner-only backfill accepted migration 0030 but stopped at the new 0031 head. It now accepts 0031. Migration tests create genuine pre-cutover global selections directly because the platform catalog routes are retired.
3. The opt-in browser catalog fixture still called retired platform routes. It now prepares tenant content and exercises tenant editing, Q&A, rehearsal selection and case-to-draft navigation.
4. The Ubuntu release script applied migrations but omitted the clinical backfill. It now maps legacy selections in bounded batches before starting services, failing the release on an unmapped selection.
5. Clinical readers could open a blank “new” editor page directly, although saves were denied. All three direct pages now reject that route for nonauthors; six focused route checks pass.
6. Member responsibility controls appeared for pending/inactive members and ineligible role/scope combinations. They now appear only to a tenant member manager for an active accepted member and disable assignments outside the role/scope rules; the API remains authoritative.
7. Runtime readiness still referenced Alembic 0030 after adding migration 0031. The readiness constant and current-head documentation now name 0031.
8. The shipped scenario-library verifier assumed the old 14-column draft schema. It now accepts that historical shape and checks the three case-provenance constraints and nonnullable content editor when the new 17-column shape is present.
9. The Human-test journey and scenario audit fixtures still used global catalog or pre-reviewer publication assumptions. They now exercise three imported tenant cases and a separate reviewer, preserving conversation/history and overlapping retirement coverage.
10. The final security pass added foreign-tenant case-copy denial and immediate instructor-capability revocation tests. Both affected tests pass against disposable PostgreSQL.

## Review 2: final code and release pass

The fresh pass rechecked route and server-action authority, tenant-bound lookups and foreign keys, catalog lifecycle, draft authorship and publication replay, device lease checks, historical snapshots, runtime grants, the migration/backfill order, and source-to-archive parity. Three findings were fixed:

1. A second author could trigger the draft database guard by saving an unchanged document, and a case refresh with unchanged content had the same risk. Both paths now keep the previous content author unless the document actually changes. A disposable PostgreSQL regression proves the second-author save retains author attribution while updating the last editor.
2. The read-only inventory counted tenant-only selections as missing global cases after cutover. It now reports mapped and unmapped selection counts separately and limits the missing-global-case check to genuine legacy references. The disposable deployment rehearsal executed the revised query after migration.
3. The real browser journey stopped at an ambiguous test locator for the two visible “Create draft” buttons. The test now selects the dialog button and verifies that a draft with the tenant case source ID was stored. The completed run had no page exceptions.

No further confirmed software authorization, integrity, or packaging finding remained after these fixes. The physical identity and target-VM gates below remain open.

## Review 3: deployment readiness ownership

A fresh deployment review found that healthy HTTP responses alone could come from an old, unmanaged process on ports 8000 or 3000 while the new systemd services failed to bind. The Ubuntu script now checks that the API and web listeners have the MainPID of their respective active units, and separately requires the worker and retention units to be active before accepting readiness. It installs `iproute2` to provide the listener inspection tool. A regression simulates healthy HTTP endpoints with wrong listener PIDs and stopped worker/retention services; all are rejected. The seven deployment unit tests, Bash syntax, and CRLF-aware diff check pass. The release zip is unchanged because the script is transferred separately; its new SHA-256 is recorded in the rollout checklist. Actual systemd and Nginx behavior remains a target-VM check.

## Local verification

- Full API suite on dedicated disposable PostgreSQL 17: **660 passed, 11 skipped**. The skips were opt-in environment, browser, native or cloud checks; no selected database test was skipped. Two focused tests against the final draft code passed after the full run.
- API Ruff check and format check passed for 185 files; mypy passed for 76 source files. The device coordinator suite passed 8 tests, including two consecutive fictional cases on one device.
- Web package: **474 passed across 68 files** with two Vitest workers. The shared UI package passed 1,577 tests in the earlier workspace run. Workspace typecheck and the production Next.js build passed. The first broad web run had four timing failures under default worker contention; the complete web rerun passed.
- Real headless Edge → production Next 3124 → API 8137 → disposable PostgreSQL: sign-in/tenant scope, specialty and profile edit, case Q&A and rehearsal selection, and tenant case-to-draft copy all passed. The API fixture and production web server were stopped afterward.
- Ubuntu deployment tests: seven script/manifest/rollback/readiness unit tests passed; the opt-in isolated PostgreSQL bootstrap, migration, inventory, grants, dump and restore rehearsal passed. Bash and browser-script syntax passed. The exact archive has **737 entries**, all manifest hashes verified, and includes migration 0031 and the new tenant API/UI files. Archive SHA-256: `56c29b62f007bc53823ccf67e971ccf78bd40d700c5069a4413f5a08435ed735`.

## External gates

Physical device identity cannot be attested by the current optional user-entered serial number. The software transfer retires/revokes the original tenant registration and creates a fresh uncredentialed registration, but a VM/Pi operator must verify a physical identifier and wipe the old device's local credential/patient state before reassignment. A hardware-backed identity or documented serial-less attestation protocol remains open. A clinical educator must separately approve fictional facts, translations and rubrics. The target VM inventory, migration, HTTPS/Nginx, two-tenant smoke and rollback drill require actual VM access and evidence; they are not local passes.
