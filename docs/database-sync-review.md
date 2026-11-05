# Database, models and scripts synchronization - 2026-10-04

## Completed

- Upgraded the configured local PostgreSQL database at `127.0.0.1:5432/device_platform` from `0035_unified_scenarios` through `0038_retire_model_setup` and reapplied runtime grants.
- Created a pre-upgrade custom-format backup at `.local/db-backups/20261004T025824236932Z.dump`; verified that PostgreSQL can read its archive index. This was not a restore drill.
- Verified physical tables, column types/nullability, compatibility views, migration head, ORM mappings, historical write restrictions, worker model access and retention restrictions. The API readiness handler returned **200 ready** against this database using its configured API role.
- Confirmed existing users, organizations, device registrations, processing runs and historical configuration/revision record counts were preserved. Canonical storage now contains 14 models. Device selections remain unassigned; this synchronization did not invent model choices.
- Added `platform/db/sync.bat` / `sync.py`: default read-only verification; `--apply` backs up, upgrades, reapplies grants and verifies. Apply refuses connected services and mismatched runtime database targets. The script uses an advisory lock and does not print credentials or put passwords on command lines.
- Included initialization/sync scripts in the transfer archive source allowlist; private backups remain excluded.
- Updated startup scripts to read device assignments, removed the old launcher mutation endpoint, retired the tenant-default helper, updated the model-status URL and aligned examples/documentation.
- Corrected schema contract tests to distinguish the two compatibility views from physical tables.

## Verification

Evidence is under `.test_artifacts/direct-models-20261003/`.

- Initial disposable schema/migration/access run: **10 passed** (`sync-db-tests.log`).
- Expanded sync contract suite: **9 passed** (`sync-contract-final.log`); final strengthened worker/RLS checks rerun in `sync-contract-reviewed.log`. Includes refusal before backup when other database sessions exist and detection of forbidden historical writes.
- Full API suite without database fixtures: **379 passed, 336 skipped** (`sync-api-unit.log`). The broader legacy database suites were not rerun; retired-API fixtures still need porting as noted in the direct-model review.
- Full launcher script suite: **174 passed** (`sync-launcher-final.log`), with the API source added to PYTHONPATH for its cross-project readiness-budget assertion.
- Platform startup/deployment unit checks: **30 passed, 13 subtests passed** (`sync-start-tests.log`).
- API Ruff lint/format and mypy (81 files) passed; changed launcher scripts and the sync script passed Ruff. Transfer inclusion and backup exclusion checks passed. Windows-aware Git whitespace check passed.
- Local database read-only sync command and API readiness passed after upgrade. An initial ad-hoc readiness probe used the wrong Windows event loop; corrected verification used the same selector loop as the API launcher, with no background delivery/retention services started.

Disposable database checks used only port 55453; that server was stopped afterward. The application database at port 5432 remains running. No hosted deployment, live cloud inference, physical-device execution, commit or publication was performed.
