# Platform device model profile assignment review (2026-10-02)

## Decision and implementation

Platform Admin selects an existing active, published processing profile from the
device's tenant. A profile already fixes the model route for each enabled
operation, including Local, Cloud, and mixed routes. The platform device create
and edit APIs now accept its ID, and the device list exposes the same edit form
through **Configure models**. A null assignment continues to use the tenant
default profile. No device model override or second credential store was added.

The new platform model-options endpoint returns only profile name/ID, published
revision ID, and enabled operation mode, engine, model and voice labels. It
excludes tenant drafts, system prompts, provider endpoints and credentials.
Tenant membership still guards the full profile and connection APIs. The
platform API rechecks same-tenant ownership, publication and lifecycle before
assigning a profile. Cross-tenant and unavailable
profiles fail. Device transfer still creates an unconfigured fresh registration.

The existing device configuration resolver applies the selected profile and
changes the configuration hash when selection changes. Device-submitted work
still requires the current configuration acknowledgement, engine capabilities,
connection validity, and normal processing authorization. Selecting a Local
profile does not establish that GPU hardware is present or that the local model
has been installed; the UI calls this out before training.

No schema migration or runtime database grant change was needed. The hosted VM
was not changed, and no deployment build was created.

## Device picker and human-test follow-up

The platform device create/edit form now groups published profiles by Local,
Cloud, or mixed operation mode. It shows LLM, transcription, synthesis, video,
and other enabled operation model labels from the paged API response. An
operation choice selects its complete published profile, so the screen shows
all resulting routes before save. The tenant default is shown without storing
an explicit device assignment. Incomplete profiles are flagged when they lack
the LLM or transcription route required by human-test.

The human-test launcher discovers installed local speech and LLM files on its
own laptop. PMS publishes declared route names; the central API cannot inspect
a remote laptop's installed models or GPU. `HUMAN_DEVICE_ID` is optional: when
set, tenant-authenticated model reads follow that active, enrolled device's
assigned profile (or the tenant default). The API checks tenant/department
scope and rejects another profile ID. Device-bound options contain only the
assigned profile and related connections and are read-only. The launcher and
desktop pass the device ID; the desktop refreshes its route on each preflight
instead of using the normal 15-second cache. Profile assignment continues to
be enforced by device credentials for `/device/config`; human-test uses its
human token and refreshes the assignment through the bound model reads.

## Verification

On a dedicated disposable PostgreSQL 17 test cluster, all 9 device management
integration tests passed. The changed profile assignment test covers Local,
Cloud and mixed operation routes, effective device configuration, pagination,
tenant scope, stale ETags, inactive profiles, disabled connections and
reactivation with a profile change. The broader device console and cloud model
tests passed after the platform summary expectation was updated (43 tests, plus
the focused summary regression rerun).

The full web test suite passed 500 tests across 72 files before the final
asynchronous mode selection regression was added; its focused file then passed
all 7 tests. API Ruff lint/format and mypy checks, web TypeScript typecheck,
and `git diff --check` passed. No deployment build or hosted VM verification
was run, as requested.

### Follow-up checks and local database synchronization

The updated device assignment flow passed 9 integration tests against the
dedicated disposable PostgreSQL server, including the human-test device-bound
profile route, cross-tenant refusal, wrong-profile refusal, inactive device,
and tenant-default fallback. The human-test configuration, launcher and
client tests passed 76 focused cases. The complete web test suite passed 512
tests across 73 files. The complete API run without the opt-in test DSN passed
374 tests and skipped 309 database/native tests; the changed database flow
was tested separately above. API Ruff lint/format, mypy, workspace TypeScript,
and whitespace checks passed. The web suite emitted existing React `act()`
warnings in unrelated model/settings tests but no failures.

For local startup, the application database at `127.0.0.1:5432/device_platform`
was backed up in the ignored `platform/api/.local/db-backups` directory, then
advanced from revision 0028 to 0032. Runtime grants were reapplied. The
documented tenant clinical catalog backfill copied one legacy practice
selection into one inactive tenant specialty, patient profile, and case;
educator review/activation remains a tenant action. The local published
default profile declares Whisper `large-v3` and Qwen `qwen3.5-4b-local`;
human-test discovery found both installed on this machine. The launcher
`start-platform.bat --check` reported API/database and web readiness, then
stopped only its temporary services. No deployment build or VM update was run.
