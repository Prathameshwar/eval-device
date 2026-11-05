# Models management: reconciliation and review

Date: 2026-10-03. Source implementation and local verification complete. The latest request narrows Models to model management; it supersedes the earlier combined workspace layout.

## Planned versus implemented

| Requested outcome | Implemented result |
| --- | --- |
| A less crowded Models page | Header actions sit beside the title. Search, Type and collapsed secondary filters share one surface with the list. Edit is visible on configurable rows; other operations use Actions menus. |
| Type-specific Add buttons | The Add dialog presents four choices: LLM, speech recognition, speech output and video analysis. This preserves explicit choices without four permanent toolbar buttons. |
| Relevant Add/Edit inputs only | Provider-specific cloud credentials and endpoints; media service/authentication fields; speech defaults only where supported. Video does not show voice, audio-format or LLM fields. Optional settings and shared-connection editing are collapsed. |
| Local models need minimal input | Reported Qwen/Whisper inventory appears per laptop, with freshness and read-only details. No credentials form, fake installation button or local delete operation. Inventory refresh reads reports. |
| Useful filters and flags | Server-backed search, type, run location, status, provider, tenant, laptop and archived filtering; URL persistence and pagination. Rows distinguish verification, lifecycle, blocked calls and device usage. |
| Add, edit and delete safely | Encrypted stored credentials, blank-secret preservation, optimistic versions, atomic changes/audits and soft deletion. Active published dependencies prevent deletion. Deleted cloud configurations can be added again and require a new test. |
| Remove device assignments from Models | Configure models opens a device-specific popup on Devices. Old `/model-assignments` links redirect to that popup. |
| Remove audio/video connections and processing profiles from Models | Standalone `/connections` and `/profiles` pages. No tabs or navigation buttons for these tasks on Models. Legacy tab URLs redirect. |
| Reusable media configuration | Tenant-scoped media presets reference encrypted connections. Profile drafts copy selected defaults and provenance; later edits preserve published snapshots. |
| TODO, final review/fixes and reconciliation | [Completed TODO](model-workspace-todo.md), review findings below, automated checks and local browser evidence. |

Field rules are implemented in the focused editors and enforced by API validation; no new generic form-schema API is introduced. Existing connections appear as service entries until configured as media presets. Their **Configure defaults** action creates the typed preset; shared connection editing is explicit in the preset editor.

## Review and fixes

- Checked platform settings permissions, tenant ownership and lifecycle gates; no patient-media access is added. Reviewed parameterized directory queries, credential redaction/encryption, atomic audit records, and runtime grants.
- Fixed duplicate legacy service rows and prevented archived media presets from resurfacing as unconfigured connection rows.
- Corrected local device lifecycle filtering to use the existing retirement state; kept separate laptop inventory identities and the 24-hour freshness rule.
- Bound pagination cursors to filters and used the database sort value to avoid cursor mismatches under database collation.
- Added automatic matching catalog linkage, published-profile deletion safeguards and cloud re-add behavior while retaining history.
- Verified concurrent media edits produce one successful write and one version conflict. Profiles reject cross-tenant or mismatched preset references and copy defaults rather than mutating published history.
- Cleared credentials and irrelevant fields when changing provider/authentication choices. Kept stored keys on edits with blank replacements. Preserved action errors across directory refresh and handled transport failures in the focused editor.
- Updated route, stylesheet and runtime-grant regression expectations. Removed leftover assignment-page tabs/imports and inspected the final mobile and desktop browser layouts.

## Actual verification

| Check | Result |
| --- | --- |
| Full web Vitest suite | 81 files, 566 tests passed |
| Final affected UI regression run | 4 files, 32 tests passed |
| Full API `uv run pytest -q` without integration environment | 386 passed, **333 skipped** |
| Dedicated PostgreSQL model, assignment and migration tests | 21 passed; covers upgrades, grants, ownership, pagination, deletion/history, profile compatibility and concurrent editing |
| Real local Next/API/PostgreSQL browser scenario | 1 passed; authenticated cloud Add/Edit/Delete, speech creation, video field isolation, local filtering, desktop/mobile overflow and browser errors |
| API `uv run ruff check .` | Passed |
| API `uv run ruff format --check .` | Passed |
| API `uv run mypy src/pms_api` | Passed |
| Web TypeScript check | Passed |

The broad API run did not execute its 333 environment-dependent tests. The dedicated PostgreSQL and browser runs above supply targeted integration coverage; they are not a claim that every skipped test ran. Tests used only the disposable PostgreSQL instance on loopback port 55453, never an application database. Provider calls were disabled or mocked. Existing unrelated concurrent changes were preserved.

Local evidence: [API suite](../.test_artifacts/model-workspace-20261003/api-final.txt), [database suite](../.test_artifacts/model-workspace-20261003/integration-verified.txt), [web suite](../.test_artifacts/model-workspace-20261003/ui-final.txt), [affected UI rerun](../.test_artifacts/model-workspace-20261003/ui-review.txt), [browser run](../.test_artifacts/model-workspace-20261003/browser-final.txt), [desktop](../.test_artifacts/model-workspace-20261003/models-desktop.png), [mobile](../.test_artifacts/model-workspace-20261003/models-mobile.png), [video editor](../.test_artifacts/model-workspace-20261003/video-editor.png). These artifacts are local verification outputs, not release assets.

## Rollout and limits

This work does not deploy the application. Existing installations require forward migration `0036_media_model_configs`, updated `deploy/grant-runtime-access.sql`, and the updated API/web release. Source edits alone do not update a running database or server.

Local installation/removal remains on the laptop. The page reports the local Qwen/Whisper inventory supported by the existing contract; it does not claim automatic discovery of every local engine. Video configuration supports the existing video-label analysis operation, not arbitrary video generation. Provider access checks are labeled separately from LLM generation tests and do not claim end-to-end media verification. Live cloud, hosted deployment and physical hardware validation remain outside this work.

## UI clarity follow-up

The user's visual review found the first implementation confusing. The follow-up changes the layout and CSS rather than adding more controls:

| Problem reviewed | Implemented correction |
| --- | --- |
| Actions, filters, table and counts appeared as disconnected blocks | Header actions align with the title; a single bordered surface contains filters, rows and a compact count footer. Pagination appears only when needed. |
| Hidden filters could silently narrow results | Applied filters remain visible as removable labels, including filters restored from a URL. Removing a location/type filter also clears dependent provider filters. |
| Basic editing required finding a menu | A direct Edit button appears on configurable rows. Details, checks and deletion remain in the secondary menu. Local entries remain read-only. |
| Repeated badges and model names added noise | One primary status badge with supporting text; duplicate identity text is omitted. |
| Narrow drawers and compounded field spacing made forms long | Editors use the larger drawer, named details/connection/credential sections, consistent grid gaps and a separate footer. Two-column desktop fields become one column on phones. |
| A connection picker could offer only one choice | The reuse picker appears only while loading or when a compatible saved connection exists. |
| Type selection looked like another long form | A centered dialog offers four clear choices in a two-by-two layout, stacked on phones. |
| Mobile rows repeated labels and wasted space | Names lead each row at full width, row spacing is reduced, and phone gutters preserve usable input width. |

The CSS is scoped to Models and its editor; shared UI primitives, tenant screens, API contracts and database schema are unchanged by this follow-up. Keyboard focus trapping/return and responsive light/dark styles are checked in the actual local Next/API browser workflow using fixtures and a disposable database. See `.test_artifacts/models-style-20261003/` for screenshots and final test output. This remains local source work, not a hosted deployment.

Follow-up verification: **39 affected UI tests passed**, followed by **9 model-management tests passed** after the final test typing correction; **web TypeScript check passed**. The final authenticated browser run passed with **60 layout checks** (six states, five widths from 320 to 1440 pixels, light and dark), CRUD and keyboard focus assertions. Representative desktop/mobile, light/dark, chooser and editor screenshots were visually inspected. The review caught and fixed excessive stacked-row spacing and a shared CSS specificity conflict on mobile gutters. No API business changes were made in this follow-up; the broad API suite was not rerun.

Evidence: [final browser run](../.test_artifacts/models-style-20261003/browser-final.txt), [UI tests](../.test_artifacts/models-style-20261003/ui-tests.txt), [desktop list](../.test_artifacts/models-style-20261003/list-light-1440.png), [phone list](../.test_artifacts/models-style-20261003/list-light-320.png), [video editor](../.test_artifacts/models-style-20261003/add-video-light-1440.png), [Add choices](../.test_artifacts/models-style-20261003/add-choices-light-1440.png). Temporary browser server and disposable PostgreSQL were stopped after verification.

## Devices popup follow-up

The latest request replaces navigation from **Devices > Actions > Configure models** with a popup on Devices.

| Planned | Implemented |
| --- | --- |
| Configure in place | Centered, responsive modal; device and tenant are fixed, with the current setup shown above the model choice. |
| Relevant inputs only | Conversation model first, optional speech/video changes collapsed, local speech selection only for a local route. Current conversation choice is restored when it has a unique ready match. |
| Preserve list and drafts | Save refreshes the list without resetting search/filter/page state. Cancel/Escape protects changed inputs; declining discard keeps the draft. Focus returns to the device menu. |
| Safe assignment | Fresh device version loaded on open; existing published media retained by default. Tested cloud or freshly reported local choices only. Inactive devices, unavailable routes and missing local speech block Save. Concurrent-change errors retain the form. Duplicate saves and dismissal during submission are blocked. |
| Cleanup | Deleted the old assignment component, removed the all-device options loader and unused inventory action. Old assignment links open the popup on Devices after redirect. |
| Review and fixes | Fixed an initial-render hydration mismatch for old links, correct warning styling, and unnecessary warnings when no video/output settings exist. Added unchanged-save protection and current-model selection. |

The server action derives tenant scope from the freshly read device, not from a browser-supplied tenant. Existing API permissions, version guards and atomic publication/assignment remain in use. No provider credentials are entered or returned by this flow. The popup does not add installation or live cloud-check operations.

Verification: **33 focused UI tests passed**, **586 tests passed in the full web suite** (82 files), and the final affected dialog rerun passed **9 tests**. Web TypeScript passed. The existing isolated PostgreSQL assignment suite passed **8 tests**; the final local browser scenario passed with **20 light/dark layout checks**, actual local-model assignment through Next/API, draft preservation, retained search, reopened saved setup, focus return/trapping and legacy link checks. The initial browser run exposed the hydration mismatch; a subsequent test synchronization issue was fixed by waiting for filtered list results before opening its menu. The browser check uses a disposable database and fixture inventory; no live model inference or hardware verification is claimed. The broad API suite was not rerun because production Python and database contracts were unchanged; Ruff lint/format checks passed for the modified browser test harness.

Evidence: [web suite](../.test_artifacts/device-model-popup-20261003/ui-full.txt), [focused tests](../.test_artifacts/device-model-popup-20261003/ui-tests.txt), [browser](../.test_artifacts/device-model-popup-20261003/browser-final.txt), [desktop popup](../.test_artifacts/device-model-popup-20261003/configure-light-1440.png), [phone popup](../.test_artifacts/device-model-popup-20261003/configure-light-320.png). Local source implementation only; no hosted deployment or additional migration for this follow-up.
