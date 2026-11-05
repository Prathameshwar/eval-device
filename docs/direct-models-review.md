# Direct models: reconciliation and review

Updated 2026-10-04. Source implementation is complete. The configured local database has now been backed up and upgraded through 0038; see [database synchronization evidence](database-sync-review.md). Hosted rollout remains separate.

## Planned versus implemented

| Requested outcome | Implemented result |
| --- | --- |
| Only create/manage models | Models has Add LLM, Add audio, Add video, row Edit/Delete, and search/type/location/status filters. No assignment, connection, profile or publication controls. |
| Relevant form fields only | Local models need a name and supported model choice. Cloud models carry their own provider settings and encrypted credentials. Audio distinguishes speech recognition and speech output. Optional preferences are collapsed. |
| Simple device assignment | Devices > kebab > Configure model opens a popup with Local/Cloud, four optional dropdowns and Save/Cancel. None disables an unused capability. Saves are atomic and versioned. |
| Platform Admin only | Both server actions and API authorization enforce platform management permissions. Tenant users and device credentials cannot create/edit/delete models or change assignments. The desktop only reloads assigned models. Platform Admin still receives no implicit tenant media/execution access. |
| Remove connections/profiles | Removed legacy management/list/publish/validation APIs, tenant model pickers, unused editors/actions and profile form/filter inputs. Old web URLs redirect to Models. No profile or connection must be created for the new flow. |
| Clean database structure | 0037 consolidates executable configuration into runtime_models and device_model_selections; two former metadata tables become compatibility views. 0038 removes device/organization profile assignment columns, disables legacy sync and freezes old configuration tables. Historical references are preserved before removal. |
| Preserve safety and data | Credentials remain encrypted/redacted with original encryption context. Tenant scope, device lifecycle, fresh local inventory, quotas, optimistic concurrency, atomic audit records and immutable execution snapshots are retained. |
| Review/fix and reconciliation | Completed this checklist, reviewed source and browser layouts, fixed confirmed issues and reran affected checks. |

Historical connection/profile rows remain immutable because existing execution history references them. They are not an editable configuration system. Internal execution revision and model wire identifiers remain compatible; no legacy configuration management API remains.

## Review findings fixed

- Removed remaining profile columns from devices and organizations, preserving assignment provenance before dropping them.
- Blocked writes to historical configuration through database triggers and reduced runtime grants; credential rotation now targets canonical models.
- Removed desktop configuration mutation and tenant model-choice routes. Only assigned device selections resolve at runtime.
- Removed leftover device profile filters, form properties, validation and display copy; the read-only device summary now shows Models.
- Corrected the all-None device summary to show Not assigned instead of treating any execution snapshot as an assigned model.
- Aligned access tests and retired URL redirects with platform-only Models management.
- Rechecked credential encryption, worker media-only access, scope/lifecycle restrictions, concurrent saves, stale revisions and fresh local inventory.

## Current verification

Evidence: `.test_artifacts/direct-models-20261003/`.

| Check | Actual result |
| --- | --- |
| Full web suite | 554 passed across 78 files (`cleanup-web-passed.log`). After final copy/summary/redirect fixes, all 47 affected tests passed, including two new all-None/assigned summary cases (`cleanup-web-review.log`). |
| Web TypeScript | Passed after final changes. |
| API suite without database fixture environment | 379 passed, 334 skipped (`cleanup-unit-passed.log`). Skips include database and opt-in tests. |
| PostgreSQL direct model, access and migration checks | 11 passed (`cleanup-db-final.log`): canonical CRUD, permissions, concurrency, mode/kind/tenant constraints, cloud/patient/local/worker paths, populated 0036-to-head upgrade and baseline/schema agreement. Strengthened access checks passed again: 2 tests (`cleanup-access-review.log`). Runs overlap and are not added together. |
| API static checks | Ruff lint, format check and mypy (81 source files) passed. |
| Desktop regressions | 59 passed for assigned-model reload, readiness, cloud/local execution and route checks. Changed-file Ruff checks passed. |
| Authenticated browser | 1 passed with 32 layout checks at 320/390/768/1440px, light/dark (`cleanup-browser.log`, `result.json`). Browser -> Next -> API -> disposable PostgreSQL exercised create/edit/delete, filters, secret redaction, popup save/reopen and retired URL redirects. No page errors. Representative desktop/mobile screenshots inspected. |
| Final review | Source reviewed for authorization, data integrity, credentials, runtime compatibility and error handling. Windows-aware Git whitespace check passed. |

PostgreSQL verification used only the dedicated disposable server on port 55453. Cloud calls were mocked. Broader legacy database suites were not rerun for this final cutover; some fixtures still create profiles/connections through the retired API and need porting before that entire historical suite can run against 0038. The passing checks above are not a claim of a full database-suite pass.

## Rollout and limitations

- Apply migrations through **0038_retire_model_setup**, then reapply `platform/api/deploy/grant-runtime-access.sql` before starting the new API/worker/web version. The configured local database was upgraded on 2026-10-04; other environments still require this rollout. Migrations are forward-only; rollback requires a backup.
- No live provider invocation, hosted deployment or physical device verification was performed.
- Local model definitions do not install models. Eligible LLM/Whisper choices require fresh device inventory; local speech output/video require advertised capability.
- Interactive desktop speech supports local Whisper and Azure OpenAI Whisper. Other cloud ASR services are media processing operations. Video supports analysis/motion detection, not video generation.
- Existing mixed assignments remain readable until Platform Admin saves one Local/Cloud mode.
- Temporary verification services were stopped and Next's temporary TypeScript include restored. Unrelated workspace work was preserved; nothing was committed or published.
