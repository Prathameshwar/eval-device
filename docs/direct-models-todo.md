# Direct model architecture

The requested product has two concepts: a model (type plus local/cloud execution), and a device's selected models. No profile publication, reusable connection, or binding wizard is exposed.

## Plan

- [x] Consolidate executable model settings and encrypted credentials into a typed model record.
- [x] Store the device's conversation, speech recognition, speech output and video selections directly, with one atomic versioned save.
- [x] Migrate existing model settings and assignments without losing credentials, immutable execution history or tenant scope.
- [x] Resolve runtime configuration from direct selections, including LLM, interactive speech, media workers and local reporting.
- [x] Replace model creation/editing with relevant type/mode fields; remove profile/connection links and unused UI components.
- [x] Replace Configure model with Local/Cloud selection and four model dropdowns; no profile or connection fields.
- [x] Remove obsolete editable storage where safe; preserve records required by historical/in-flight execution and compatibility.
- [x] Verify migrations, permissions, credentials, concurrency, runtime behavior, UI and responsive browser workflows.
- [x] Review/fix, rerun affected checks and publish a planned-versus-implemented reconciliation.

No hosted deployment, live provider calls or hardware checks are included. Migration testing uses a dedicated disposable PostgreSQL instance.

Final verification and the planned/implemented mapping are recorded in [Direct models review](direct-models-review.md). The migration is implemented and tested. The configured local database was upgraded on 2026-10-04; see [synchronization evidence](database-sync-review.md).

## Final simplification requested by user

- [x] Remove legacy connection/profile management APIs and unused web editors/actions.
- [x] Remove alternate profile assignment inputs and restrict model/device management to Platform Admin.
- [x] Remove historical configuration tables from active write grants; preserve execution history.
- [x] Verify direct model CRUD/assignment, retired entry points, permissions and UI; review/fix and update reconciliation.

The current verification section in the reconciliation distinguishes targeted database checks from the broader legacy suites whose retired-API fixtures still need porting.
