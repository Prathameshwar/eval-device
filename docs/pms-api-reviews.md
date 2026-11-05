# PMS API review record

## Device list required model action - 2026-10-09

Platform fleet rows with no selected conversation, recognition, output or video model now show Configure Model immediately after View, a subtle gray background, and Model required. The existing popup handles setup; saving refreshes the list and keyboard focus returns to the visible action or menu. Inactive/retired controls stay disabled and tenant/read-only users gain no management action. Configured devices retain their menu action.

The API adds only a models_configured boolean to platform device summaries, using one page-bounded selection query. Local and cloud selections both count; no selection record and all-null selections both count as unconfigured. This is assignment status, not an execution-readiness certification. No schema, grants, credentials, runtime policy or tenant media access changed.

Verification: 40 relevant UI tests passed across device-list, device-actions, device-model-actions, device-page and app-css suites; web TypeScript passed. API pytest without a test DSN passed 614 tests and skipped 406 database-dependent tests. A separate run of device-model-review, device-console and device-management passed all 25 tests on a newly initialized disposable PostgreSQL 17 server at 127.0.0.1:55589 (21 database cases and four validation cases). Ruff lint/format and mypy passed. The initial new database fixture hit the standard subscription limit; the comparison device was made inactive and the full targeted run passed.

Headless Edge inspected the actual component markup with application styles at 1440, 1024 and 390 pixels: action fit/no menu overlap and gray background assertions passed. Desktop and phone screenshots were visually inspected. This rendered fixture check is not an authenticated browser journey. Temporary capture test removed; screenshots and helper artifacts remain ignored under .test_artifacts/device-model-required-20261009/. Final diff review confirmed summary-only data, existing authorization/lifecycle guards, page-bounded queries and refresh behavior. No application database, live provider, hardware, hosted deployment or publication was used.

## Human-test menu, local-model validation and downloads - 2026-10-08

Reproduced the menu issue with the right drawer open, a wrapping case title and
200% display scaling. The camera preview was hosted over the entire stage and
overlapped the vertically centered menu. Top-aligning the menu and hosting the
preview inside the manikin clips it below the header. Native checks cover 240
combinations of five sizes (including a deliberately reduced 500-pixel height),
two title lengths, drawer, typed input and camera state, at three display scales.
The protected portable interpreter also passed all 80 combinations at 200%.
Generated-camera lifecycle checks passed; an existing non-fatal Tcl close callback
message remains outside this fix's scope. Hardware camera/microphone acceptance
on the user's other laptop has not been performed.

User-authorized read-only VM inspection found 41 checksum-verified synced turn
records: 30 completed and 11 failed. Failed turns store no model error code,
raw response or token timings, so those historical records alone cannot establish
the rejection stage. Local Qwen 3.5 4B reproduction from the retained case
snapshots, across different opening-question wordings and fresh/recent history,
consistently emitted four approved IDs despite the existing three-fact contract.
The model finished normally after 21 output tokens with prompts using 904-1110
of 2048 tokens. The validator correctly refused the fourth fact; this reproduced
failure was not a context overflow, timeout or truncated output.

The local client now supplies a bounded GBNF grammar for trusted source-ID
prompts, selecting up to three IDs from the fitted source view and an optional
unknown marker. Clarification/boundary replies remain separate. Case text does
not enter the grammar. User messages cannot install grammar. Plain-text cases,
greetings and general knowledge retain their response contract. Frozen-source,
duplicate, conflicting-special, completion and answer-size checks remain intact;
there is one inference call and no repair retry. The native protocol is supported
by the pinned llama.cpp b11046 grammar API. No context/output limits or clinical
source facts were changed.

Qualified the single rebuilt local_llm CPython 3.12 x64 extension with the existing
protection tool versions/directives. All 18 distinct reproduction runs passed
using that compiled module, with/without history. Eight further native boundary
checks confirmed a 1812-character question succeeds, 20712 characters of history
drop five complete pairs safely, an excessive question is rejected with
patient_context_too_long, and a 16-token truncated output yields llm_output_limit.
Greeting, general knowledge, absent clinical facts and blood-pressure questions
also passed. Portable executable self-test passed native imports, isolated
Python/Tcl runtimes, offline installer paths and spawned recording process checks.
These are actual local-model checks, not live cloud or new-laptop verification.

Downloads retain authenticated administrator access, tenant lifecycle checks,
private file permissions, checksum pinning and bounded streaming. The new
desktop-runtime option contains app/executable and CPU+NVIDIA runtimes, excluding
all model/voice weights. Both editions share Desktop-App-GPU extraction layout
for updating existing installations without replacing enrollment/history/models.
The legacy CPU ID remains supported for catalog/deployment compatibility. The
server derivation tool validates source/archive manifests and exact file hashes,
permits only the app bytecode/guide and optionally the one qualified local-model
native extension, writes immutable editions and rechecks all output members.
Source models/runtimes are reused on the VM; only small reviewed code was uploaded.

Verification: Human-test full suite 576 passed / 6 opt-in checks skipped; Ruff,
format and mypy passed. Archive/publisher/portable focused suite 28 passed.
Affected frontend tests 16 passed and workspace typecheck passed. API full suite
582 passed / 391 skipped; focused downloads tests 15 passed / 1 skipped. Database
tests were skipped because no dedicated disposable PMS_TEST_ADMIN_DSN was
configured; none ran against production. API Ruff, format and mypy passed.
Ubuntu production web build/deployment passed. Managed release
/opt/pms-platform/releases/20261008-114019-229207 retains the previous release
and private verified PostgreSQL backup. All twelve post-deploy checks passed:
five patched file hashes, unchanged other application files, configuration,
six retained table fingerprints, revision 0046_patient_background, service
health, public HTTPS routes and protected anonymous access. Backup restore
listing was checked; a restore was not exercised.

Final catalog publication passed. GPU bundle (models included):
Human-test-windows-x64-cuda-protected-20261008-113724.zip, 6,950,639,997 bytes,
SHA-256 6ebebf69c85f787cba5373e133cf23e5618861bee0aaea5efd2858a5064d48cb.
App/runtime without models:
Human-test-windows-x64-runtime-protected-20261008-113724.zip, 2,278,604,658 bytes,
SHA-256 7cc83400df2f527edabf645065db6d22b9fb70de20eb2f51d80b6ac04def2ba1.
Both contain the reviewed menu bytecode and qualified local-model extension.
Every output member and complete archive checksum was verified on the VM. Previous
live GPU/CPU ZIPs remain available for rollback; only unpublished task candidates
were removed. Model/runtime files were not uploaded again. The runtime-only ZIP
remains about 2.28 GB because it includes NVIDIA execution dependencies.

Live HTTPS verification passed anonymous login protection, platform/tenant admin
access, ordinary-member denial, both editions' HEAD/content lengths/friendly
filenames/private cache policy, pinned SHA-256, resumed byte ranges, invalid-range
416 responses and stale-release 409 responses. Temporary operator verification
sessions were revoked in finally. Sanitized production-rendered download markup
and actual CSS were inspected at 1440x900, 1080x680, 390x844 and 320x760 with
checksum details expanded; no horizontal overflow or missing download controls.
This fragment review applies the production root font/light theme and omits the
authenticated shell; the existing shell was not changed. Final source review and
diff whitespace checks passed. Only authorized task files are prepared for the
mapped git publish --dry-run / git publish workflow; private fixtures, models,
compiled binaries and archives remain ignored.

## AI Evaluator landing-page VM deployment - 2026-10-08

User explicitly authorized updating the existing VM. Connected using the pinned
SSH host key and an in-memory password prompt; credentials were not stored in
source or deployment archives. Used the existing managed deployment workflow,
without schema-upgrade or data-loss flags. The archive was built from the running
VM baseline plus the 17 reviewed public-web files, preserving the existing API,
database, shared-package sources, wheels and locked dependencies. Ubuntu rebuilt
the UI successfully before cutover. A private PostgreSQL custom-format backup
was taken and its pg_restore listing validated; a restore was not exercised.

Current release: /opt/pms-platform/releases/20261008-081101-222638.
Previous retained release: /opt/pms-platform/releases/20261007-144101-199603.
Release archive SHA-256:
d8524521c42d74f26ea63e36966d6db5821574aad05cf3cc8d99c00b782b6007.
Database revision remains 0046_patient_background. Backup retained privately at
/var/backups/pms-platform/pms-platform-20261008-081056-landing.dump (587,904 bytes).

Post-deployment verification passed all 12 checks: managed current/previous links,
all 17 landing-file hashes, unchanged remaining application sources/wheels,
unchanged /etc/pms-platform configuration hashes, exact pre/post fingerprints of
organizations, users, devices, model_definitions, runtime_models and
device_model_selections, unchanged database revision/downloads catalog, retained
private backup, five active services, HTTPS readiness/public routes, and protected
anonymous account access. /, /privacy, /terms and /login returned 200;
/home returned 307 and the anonymous auth-context API returned 401. Both API/web
readiness endpoints returned 200 through certificate-verified HTTPS.

Actual hosted Edge checks passed without mocked services or ignored TLS errors:
seven homepage sections, both Alex images, contact/operator identity, canonical
and social metadata, mobile navigation/focus, keyboard FAQ, policy documents,
existing sign-in and anonymous /home redirect. No failed assets or JavaScript
page errors. All 36 public-route/text-size/width reflow combinations and four
short-landscape menu combinations passed against the hosted origin. Inspected
hosted desktop/mobile screenshots; no further product fixes were needed.

Evidence: .test_artifacts/landing-vm-20261008/hosted-browser.json,
hosted-desktop.png, hosted-mobile.png, hosted-login.png and hosted-social.png;
private server-side package/backup/verification receipts are in the task staging
directory. GitHub publication was not requested or performed. Authenticated
learner sessions, live model-provider calls and hardware remain unverified.

## AI Evaluator rendered-page self-review - 2026-10-08

User requested another independent inspection of the rendered page, styling and
content, with fixes. Inspected actual production screenshots at 320, 390, 768,
820, 1024, 1280, 1440 and 1920px, including every section, images, expanded FAQs,
mobile/tablet menus, contact panel and footer. Normal layouts were clean. Enlarged
root text exposed horizontal overflow: 386px document width at 320px, 480px at
390px and 1238px at 1024px. This was a genuine layout defect missed by the earlier
single-width enlarged-text check.

Fixed intrinsic grid sizing, long-word wrapping and bounded links/buttons; allowed
the mobile header to wrap; added a font-relative container threshold for navigation.
Shared mobile-control styles avoid duplicated media/container declarations. A small
ResizeObserver measures the actual header for menu-height limits and anchor/focus
offsets. It is scoped to the landing tree and disconnected on unmount. Tuned the
mobile headline to avoid awkward enlarged-text word breaks. Clarified platform and
review copy without adding unsupported product/assessment claims. No image regen,
application theme, authentication, API or database change was needed.

Verification: 10 affected landing/document tests passed after the fixes; workspace
typecheck and final production build passed. Existing unrelated autoprefixer warning
remains in TenantProvisionWizard. Added a reusable read-only browser regression,
tests/browser-landing-reflow.mjs: all 36 route/text-size/width combinations passed,
with expanded menus, four short-landscape combinations, FAQ keyboard behavior and
sticky-header focus clearance. The full production browser review also passed:
images/metadata/links, saved themes, reduced motion, mocked account/outage, existing
login, policy pages and no browser errors. Re-inspected final screenshots after the
headline adjustment. Evidence: .test_artifacts/landing-render-review-20261008/.

Local Edge/browser verification only; account/setup endpoints in the full check
were mocked. No live hosted release, tenant data, provider call or hardware test.
Temporary production review server stopped after verification; source/docs remain
local and unpublished.

## AI Evaluator landing assets/content completion - 2026-10-08

Completed the subsequently authorized remaining local phases. Owner identity is
AI Evaluator Company, contact@aieval.com and the approved HTTPS origin. Validated
public environment overrides support external policies and intentional indexing;
the default remains noindex and private application routes retain noindex.
Contact is a real mailto destination, with no form database or external messaging.
Public privacy/data-use and terms pages describe existing product behavior and
institutional responsibilities without inventing retention, contracts or compliance.

Two Alex images were generated using the user-approved imagegen CLI/API fallback
(gpt-image-2, high quality). The second references the first portrait for identity.
The owner-provided local key stayed process-scoped, redacted and out of source.
TLS verification failures occurred before submission; a task-local bundle from the
Windows trust store corrected trust without disabling TLS. Actual generation and
editing then succeeded. The hero combines the portrait with a capture of the real
scenario workspace using only fictional data and read-only mocked endpoints.
Four responsive WebP exports total 180,756 bytes; largest is 77,528 bytes. Hero
fetch priority, lazy second image and explicit dimensions limit loading cost/shift.
Prompts and asset/release documentation are saved in docs/landing-page-assets/ and
docs/landing-page-release.md. Temporary evidence/originals remain ignored.

Review removed obsolete placeholder markup/styles and unused brand/label references;
checked copy against implemented scenario/session/companion behavior and retained
the ten SVG content positions and header/footer branding. The local social PNG
renders at 1200x630. Production review exposed missing inherited metadataBase;
the root now resolves social images using the approved public origin. Existing
authentication, private media, permissions and application styles are preserved.

Verification: 91 distinct affected web tests passed (23 landing/config/documents,
13 session, 4 setup, 3 auth layout, 10 login, 38 console shell). After final fixes,
all 23 new public-page tests passed again. Workspace typecheck and production build
passed; only the existing unrelated TenantProvisionWizard autoprefixer warning
remains. Headless Edge checked images, approved identity/links/canonical, social PNG,
noindex, seven sections, no overflow at 320/360/390/640/768/1024/1440, 200% text,
menu/FAQ keyboard behavior, anchors, reduced motion and stable light/dark/ledger
preferences. Measured initial layout shift was 0. Mocked verified account/outage and
existing login checks passed. Both policy pages pass 320px reflow/navigation checks.
Screenshots and forced-colors review found no remaining confirmed UI issue.
Repeated the browser review against the final production build: all checks passed,
including loaded local assets and inherited social metadata. Production account
checks injected a synthetic production-named Cookie header into the mocked GET;
loopback HTTP verification does not establish hosted HTTPS Secure-cookie behavior.
Stopped only the verified temporary review servers and restored the checked
Next-generated tsconfig addition. Final restored-config workspace typecheck passed.
Evidence: .test_artifacts/landing-final-20261008/.

Scope: frontend-only, with mocked account/scenario endpoints for local browser
checks. API/database suites and hardware tests were not run; no API/DB changes.
Actual image generation used the explicitly approved paid provider fallback.
Application cloud integration, hosted deployment and Git publishing were not done.

## AI Evaluator public landing layout - 2026-10-08

Implemented the authorized CSS/style/layout stage of the saved landing plan.
The root route now presents seven public sections instead of redirecting immediately.
Verified accounts receive My Account links to /home; visitors receive Login links
to /login. Existing login still redirects signed-in users into the console.
Known account-service outages fall back to public content with Login; unexpected errors
are not swallowed. No private identity details are passed into landing components.

The landing CSS module contains local colors, sizing, typography, grids, controls and
responsive rules. Shared styles and stored theme preferences are preserved. Existing
brand geometry is reused with local colors. A small client header handles mobile menu
dismissal and focus; the page body and native FAQ need no additional client state.
Ten content icons come from the existing SVG family. CSS-built Alex/scenario illustrations
reserve the two future image areas; these are explicitly fictional illustrations, not
screenshots or live data. Both visual regions have accessible image descriptions.

Review found transformed decorative rings causing narrow-screen horizontal overflow.
Scoped clipping on the hero corrected it without clipping the header. Navigation/footer
links also received 44px minimum targets. The locally scoped brand gradient endpoint was
darkened after contrast review (4.93:1 on the header, 4.73:1 on the footer). Source review
confirmed scoped CSS, actual link
destinations, continued protected-route authorization, and no external media requests,
credentials, database writes or backend changes. Documentation additions preserve the
pre-existing bytes and legacy encoding of these historical records.

Verification: workspace TypeScript checks passed; 75 relevant web tests passed (7 new
landing regressions, 13 session, 4 setup, 3 authentication layout, 10 login and 38 console
shell). Production build passed with an existing autoprefixer warning in the unrelated
TenantProvisionWizard stylesheet. After review fixes, the 7 landing tests and browser
checks passed again. Final palette verification passed for seven text/background pairs
(minimum 4.73:1); forced-colors FAQ rendering and disclosure were inspected. Final
production build and workspace typecheck passed after all fixes and config cleanup.
Local headless Edge verification used an isolated Next development instance and mocked
account/setup endpoints. It checked seven sections, account links, widths 320/360/390/
640/768/1024/1440 without overflow, mobile Escape focus restoration, anchor focus/header
clearance, resize dismissal, keyboard FAQs, 200% root text reflow at 640px, reduced motion,
stable landing colors under light/dark/ledger preferences, verified My Account display,
API-outage fallback and existing login rendering. No browser page errors occurred.
Screenshots and evidence: .test_artifacts/landing-layout-20261008/.

Remaining stages: two final Alex images, copy refinement, approved contact address and
legal pages. Contact currently explains institution account support and links to real
account access; no invented address or empty legal link is displayed. Existing noindex
settings remain. This is local UI verification, not hosted, live provider, database or
hardware acceptance. No API/database changes were made, so backend/database suites were
not run for this frontend-only stage. Nothing was published.

## Automatic training signing-key provisioning and Previous navigation - 2026-10-05

Permanent setup now shares `pms_api.security.training_keys`: local `init-local`, local API startup and the Windows launcher provision an absent Ed25519 signing identity and persist its path without changing unrelated settings. The explicit `pms-admin init-training` command supports managed environment files. An existing configured key is validated and reused; missing, malformed, linked or overly permissive keys fail closed without implicit rotation. Setup uses an OS file lock, private temporary files and atomic publication/replacement. Environment overrides remain operator-owned. Review corrected CRLF preservation, API-group traversal of newly created Unix key directories and exclusion of interrupted temporary secret files from source packaging.

Managed Ubuntu deployment provisions after API dependency installation and before runtime validation. The private key remains outside release folders; the master and API-only configuration receive the persistent path. Runtime validation loads the key as the API account, and deployment requires the verification-key endpoint after startup. Failed deployment restores master and role configurations while retaining the generated key for retry. Worker, retention and web services do not receive key access. The launcher detects an already-running API with stale training settings and reports the required restart instead of terminating another supervisor's process. The existing local API configuration was initialized with the new command and its generated signature verified; no database changes were made.

Verification: final API suite **430 passed, 371 skipped**; no disposable PostgreSQL DSN was configured, so database integration checks were skipped. Focused provisioning/deployment/launcher run **46 passed, 1 Unix-only skip**, with 13 subtests. Native isolated Linux checks using the previously authorized VM confirmed root/API-group 0640 ownership, private-directory traversal, real signing as `pmsapi`, denied reads as worker/retention/web accounts, stable identity on repeat and rejection of public-read permissions. Their temporary directory was removed; application configuration and services were not changed by these checks. API Ruff lint/format and mypy passed; launcher checks and Bash syntax passed. API wheel/source builds passed, and archive/source-selection inspection included the new module and excluded private keys. No full VM redeployment, new authenticated learner session, provider inference or hardware verification is claimed.

Human-test adds **Previous** with a left-arrow icon immediately before **Complete & Close**, calling the existing setup-navigation action and sharing its busy-state protection. The native layout check exercised the button with typed controls visible at minimum size, verified that it returns to setup and preserves the visible Save action. Desktop lint, formatting and type checks passed. Changes preserve the earlier setup-layout and connection-dialog work.

## Hosted training signing key repair - 2026-10-05

The user reported `training_not_configured` on the hosted Start session page and authorized VM access. Preflight confirmed neither `/etc/pms-platform/api.env` nor `/etc/pms-platform/api/.env` configured a training key and the default key did not exist. Using the existing pinned SSH host identity, generated an Ed25519 key on the VM at `/etc/pms-platform/api/training-private.pem` (root-owned, API group read access, mode 0640). Preserved private configuration backups and configured both master and API role files so redeployment retains the setting. Restarted only `pms-api.service`; the repair made no database or schema changes.

Verification: local repair checks covered key generation, unrelated-setting preservation, reuse without key rotation and refusal to replace a missing configured key. The live API verification-key response matched the generated public key; external HTTPS `/api/v1/training/verification-key` returned 200 with EdDSA and issuer `pms-training-v1`. Neither private key nor password was logged. The repair restores prior configuration on verification failure. No authenticated session creation, learner-device execution or hardware verification was performed; training agents still require the matching trusted public key. Operator scripts are in ignored `.test_artifacts/training-key-repair/`.

Live external testing remains deferred unless a section explicitly records user-authorized verification. Hosted deployment remains deferred. Historical local reviews are not live cloud certification.

## Database, ORM and deployment script synchronization - 2026-10-03

The configured local application database (127.0.0.1:5432/device_platform) was
at `0032_tenant_import_passwords` while this source requires
`0035_unified_scenarios`. No other application database connections were present.
Created a private custom-format backup and verified its archive catalog before
running the existing `pms-admin init-database` forward upgrade. Reapplied the
current grant bundle with the deployment owner and three distinct runtime roles.

Local verification after upgrade:

- Single Alembic head and asynchronous schema readiness: `0035_unified_scenarios`.
- All 41 domain tables / 709 column types and nullability match registered ORM
  metadata. Every API table read grant is present; model credentials and scenario
  defaults remain inaccessible to worker/retention roles.
- All prior table row counts were preserved. Only `model_definitions` increased
  (0 to 11 supported local catalog entries); no tenant data was reset or deleted.
- The read-only scenario storage verifier passed. Backup and verification
  manifest are retained under ignored/private
  `.test_artifacts/schema-sync-20261003/071039/` (`before.dump`, `before.json`,
  `verification.json`). Secrets were not printed or committed.

Source fixes: inventory SQL now counts published-scenario selections separately
from legacy/tenant-case selections, retaining compatibility through JSON row
projection on older schemas. Added a PostgreSQL regression checking that count
and default-table SELECT/INSERT/UPDATE permissions, with no runtime DELETE.
Updated Practice storage, scenario API runbook, schema field-count header, API
setup and model-configuration deployment notes to the current contracts. ORM and
migrations already agreed; no new migration or schema-model alteration was needed.
The frozen baseline and existing migrations were preserved.

Verification:

- Schema sync and catalog upgrade suites on dedicated disposable PostgreSQL
  (127.0.0.1:55467): **14 passed**. Tests create/drop their own databases; they do
  not use the local application database.
- Startup/deployment script suite: **29 passed, 13 subtests passed**. One existing
  archive-extraction test was deliberately deselected; no build was produced.
- Deployment bootstrap/migration/backfill/grants/dump/restore integration on a
  separate temporary PostgreSQL cluster: **1 passed**. The existing Ubuntu
  script's embedded database operations were executed locally, not on a VM.
- API full run without database DSN: **381 passed, 325 skipped**. Database tests
  in that run were skipped; the isolated database suites above were run with a
  dedicated test DSN. Ruff check, full formatting check and mypy passed.

No application API/web services, VM services or production deployment were
started or updated. No build, commit or GitHub publication was performed. This
records local database/script synchronization, not live cloud verification.

## Final Scenarios / Practice / human-test integration review - 2026-10-03

Reviewed web actions and role boundaries, published scenario selections and
conversation snapshots, desktop restore/save/reload, launcher readiness, model
assignment display, local history, and error recovery. Work stayed local; no
production build, VM change, deployment, commit or publication was performed.

Findings fixed:

- Launcher readiness still queried the author-only clinical catalog. It now
  checks published Practice options, allowing ordinary tenant users to launch
  while preserving authentication and scope rejection.
- Restoring a published scenario called Controller.use_selection on Tk's thread.
  With an existing conversation this could create an asyncio task without an
  event loop. Restore now only fills the form; explicit Save binds/reset the
  conversation on the worker, consistently with the existing case workflow.
- Optional null/missing patient measurements and occupation could break desktop
  rendering. Rendering now handles absent fields, and restored language choices
  respect the desktop's supported languages.
- Scenario retirement/language failures now explain recovery through web
  Practice. Permission errors no longer incorrectly require clinical-author
  access for ordinary users.
- The desktop Models dialog no longer offers editing/new-profile/cleanup
  controls when the API reports centrally managed configuration. It shows the
  published assignment and explains administrator changes and relaunching.
- Updated integration fixtures for platform-admin-only profile configuration,
  idempotent starter imports, device credential settings and the current
  launcher readiness endpoint. Documentation describes the same workflow.

Verification:

- Human-test full default suite: **478 passed, 6 skipped** (opt-in native-model
  and installed-voice checks). Affected desktop/model-dialog tests rerun after
  final edits. Real Tk widgets exercised restore, private observations, Save,
  reload, worker-thread binding and an explicitly idle microphone.
- Launcher suites: **84 passed**, including full cloud-only launcher lifecycle,
  central API boundaries, installed-model credentials, readiness retries,
  published Practice access and permission denial. Run with the API Python
  environment because one test compares the server's readiness timeout.
- Real FastAPI / disposable PostgreSQL with the actual human-test controller:
  **27 integration tests passed across the final runs** (journey and local-turn
  suites). Two initial fixture failures were corrected and affected tests rerun.
  Both published starters work as an ordinary org_user without catalog access;
  private vitals, immutable context, mocked local inference, central history,
  stale revision rejection, retired scenario rejection, expired authentication,
  API outage, tenant isolation and client shutdown are covered. Legacy tenant
  cases remain supported. Inference is deterministic/mocked, not live model
  verification. Only the dedicated test cluster at 127.0.0.1:55467 was used.
- API full non-database run: **381 passed, 324 skipped**. Database tests skipped
  in that run because its DSN was deliberately unset; the targeted integration
  runs above used disposable databases. API Ruff check/format and mypy passed.
- Web focused Scenarios/Practice/navigation/settings suite: **36 passed**;
  both UI workspaces' TypeScript checks passed. Existing settings test act()
  warnings remain. No web source changes were needed in this review; the prior
  local browser/layout review remains recorded below.
- Human-test Ruff check passed and formatting passed for affected runtime files,
  desktop tests and the new launcher test. Unrelated pre-existing formatting in
  the two older startup fixture files was preserved. Final whitespace review
  passed for the affected runtime/integration files.

Limits: no live cloud calls, real microphone/camera, installed-model inference,
Raspberry Pi hardware, hosted browser session, or full PostgreSQL suite rerun is
claimed. This review adds local end-to-end contract evidence, not a live service
certification.

## Scenarios and Practice usability follow-up - 2026-10-03

Reviewed the guided scenario editor, published read view, independent reviewer
screen, inline specialty creation, and private Practice selection. Scope was UI
and local verification; API contracts, permissions, and database storage were
unchanged in this follow-up.

Confirmed fixes:

- Published records without draft revision fields now open at Patient and
  specialty. Read views hide unusable specialty creation, show the saved
  specialty name, and use content-language and summary wording.
- Review language stays visible on the review step. Recording a review checks
  publication readiness for the returned revision, so the reviewer can proceed
  without discovering a separate validation action. Duplicate validation
  controls and the internal schema-format column were removed. Language labels
  use English and Hindi. Retirement controls require a published record.
- A sticky save bar shows saved/unsaved state on long drafts. Step changes focus
  their heading; pending operations disable editing controls. Creating a
  specialty updates both its ID and displayed name, closes the inline form, and
  reports success. Copying a published scenario clears stale case/specialty
  selections. Tenant changes remount the workspaces to isolate in-flight state.
- Practice has search, a bounded scenario list, an explicit selected marker,
  saved-choice feedback, and a separate explanation for the tenant default.
  Clicking the current scenario preserves edits. Switching scenarios or
  refreshing asks before discarding edited language/vitals. Edits clear stale
  success feedback, and unchanged saved selections cannot be resubmitted.
- Missing, non-finite, out-of-range, and reversed blood-pressure values are
  checked before submission. The vitals section opens and focuses the first
  invalid field after a failed save; typing does not move focus. Users can reset
  vitals to the scenario values.
- Local CSS constrains form width, preserves mobile button order, improves
  review spacing, and makes Practice stack when enlarged text needs more room.
  Browser review found and fixed overflow at 200 percent text size.

Verification: web TypeScript check passed. Five relevant test files passed 29
tests, including reviewer language/readiness, published read view, inline
specialty persistence, same-card reselection, discard confirmation, bounded
vitals/focus, search, saved feedback, back navigation, and list filtering.
Headless Edge exercised the real components through a local Vite fixture with
mocked API actions: 7 screen states at 320/390/768/1280 pixels in light/dark/ledger
themes, plus 200 percent text checks (91 layout checks total). No horizontal
overflow or browser runtime errors remained. Practice reselection, cancellation,
and invalid-field focus interactions passed. Screenshots were inspected locally.
Evidence: `.test_artifacts/scenario-usability-20261003/results.json` and adjacent
screenshots/fixture. This is UI verification with mocks, not a live API or hosted
deployment test. No production build, VM update, or GitHub publication was run.


## Unified tenant Scenarios and Practice - 2026-10-03

Stage 1 added forward migration `0035_unified_scenarios`: tenant specialty and
submission references on drafts, specialty references on published versions,
versioned tenant Practice defaults, and published-scenario references on private
Practice selections and conversations. Composite foreign keys, a default guard,
explicit API runtime grants, ORM models, and readiness checks agree. Existing
catalog, scenario, Practice, and conversation rows remain available for history
and older clients. Isolated PostgreSQL upgrade, backup/restore, and grant tests
passed. The frozen SQL baseline and earlier migrations were left intact.

Stage 2 introduced the submitted-revision lifecycle for version-3 scenarios.
An author binds an active tenant specialty and submits a complete draft; a
different tenant reviewer records language reviews before publication. Saving
changed content clears submission and review readiness. A no-op save advances
the submission marker with the revision so review cannot be bypassed by a
revision-only change. The API rechecks organization-wide permissions after
locking, enforces quotas and idempotency, prevents retirement of the current
tenant Practice default, and audits changes in the same transaction. Published
versions support a private per-user language and vital-sign selection; changing
vitals updates the selected language localization hash. Conversation and device
sessions keep their pinned snapshots. The desktop client reads the selected
published scenario first and retains legacy selection fallback.

Stage 3 reduced the tenant navigation to Scenarios and Practice. The scenario
editor uses a reusable three-step progress component, inline specialty creation,
published-first list, case source selection, and responsive CSS modules.
Historical catalog URLs remain reachable, and `/patient-setup` redirects to
`/practice`. Review fixed a hidden required specialty field in the new-draft
form, stale request keys when changing specialty, an unmarked copied specialty,
an unavailable saved Practice selection warning, and a copy action that could
create an uneditable legacy-format draft. UI and API tests were updated for the
active starter specialties and mandatory submit-before-review sequence.

Verification: isolated PostgreSQL suites passed 16 scenario, 10 provisioning,
12 conversation/schema, 19 Practice, 11 training, 8 catalog migration, 1 browser
migration, and 1 runtime-grant test. The API suite without a database DSN passed
381 tests and skipped 323 database-dependent tests. Ruff check, Ruff format
check, and mypy passed after the final test formatting. The web suite passed
547 tests serially; focused post-review scenario tests passed 7 tests, and web
and shared UI typechecks passed. Desktop patient-workflow tests passed 10 tests.
One broad PostgreSQL run stopped after 25 tests because a Windows Alembic child
process exited with `0xc000070a`; the relevant suites passed when run separately.
No hosted deployment, cloud provider, hardware, or production database was used.

## Manual tenant subscriptions - 2026-09-24

Implemented the confirmed **tracking-only** behavior. Platform administrators can
manage plan assignment, manual dates/renewal, suspension/resumption, cancellation,
private references/notes and the existing two-plan price/capacity catalog. Tenant
administrators can read their own summary and retained changes. Subscription
state never changes tenant activation, processing/configuration authorization,
offline access or historical data access. Existing plan seat quotas still apply.
Payment gateways, charging, invoices and automatic renewal remain deferred.

Migration `0025_manual_subscriptions` follows `0024`, adds six organization columns
and a version trigger, validates finite ordered dates and preserves old data.
Readiness and ORM models agree with the new head. Existing table-level runtime
grants cover these fields; the new trigger function has no PUBLIC execution grant.
Manual terms use subscription version; the legacy plan assignment and plan catalog
keep their distinct existing version contracts. Private fields are omitted from
generic organization responses, tenant summaries and audit values.

Review 1 checked role/context authorization, tenant/department boundaries,
constraint enforcement, locking, quota rollback, lifecycle and retained audit.
Database tests covered stale and competing edits, failed downgrade atomicity,
legacy-assignment version invalidation, archived tenants, cursor binding, literal
search and direct SQL constraints. Confirmed inactive catalog plans remain usable
for existing subscriptions, including manual date/reference maintenance. Added
invalid-text validation to catalog names. No processing permission or worker gate
was added. The migration fixture initially omitted the existing inactive-tenant
suspension source; corrected the fixture, without changing the constraint.

Review 2 checked UI/API integration, exact dates/prices, stale dialogs, history,
privacy, navigation and responsive layouts. Fixed UTC editor precision so changing
only notes/reference preserves original timestamp fractions. Corrected paginator
counts to represent the current page, and made older plan-assignment audit events
readable with actor identifiers rather than a raw event code. Catalog changes
require confirmation and explain their tenant-wide effect; save failures retain
forms and version conflicts. Cross-tenant deep links and server actions check the
selected context. Cancellation preserves records and dates, and resume explains
that expired dates still require renewal. Final inspection found no outstanding
blocking issue in this scope.

Verification:

- Full API baseline: **326 passed, 232 skipped**. Opt-in PostgreSQL/browser/live/
  native skips are reported separately, not counted as successes.
- Manual subscription and existing plan/capacity suite: **19 passed**. The one
  upgrade fixture failure was corrected; its isolated rerun passed.
- Forward `0024 -> 0025` upgrade preserved existing tenant/device/plan data and
  repeated upgrades were harmless. The existing full baseline-adoption upgrade
  check also passed. A final targeted rerun passed **2 tests**, including the
  expanded inactive-plan regression and baseline adoption.
- **Seven** real headless Edge -> Next server actions -> loopback API -> isolated
  PostgreSQL journeys passed: authentication/directory, plan catalog editing,
  expiry/private notes with processing still available, renewal/deep reload,
  suspend/resume/cancel/history, tenant read-only/privacy/context isolation, and
  filters/responsive layout. No browser runtime error or horizontal mobile overflow.
  Screenshots: `.test_artifacts/subscriptions-web/desktop.png` and `mobile.png`.
- Forward upgrade plus browser fixture passed together (**2 tests**). Across the
  targeted runs, **22 distinct API/test-fixture tests passed**, including **11**
  database-backed cases; unit cases overlap the full baseline.
- Full web suite: **377 passed in 53 files**. After final review fixes, the affected
  file passed **6 tests**, including two additional regressions (**379 distinct web
  tests passed** across these runs). Existing preview-route React act warnings
  remain non-failing.
- Ruff check/format (**154 files**), mypy (**68 source files**) and workspace
  TypeScript checks passed. The final Next production build passed after all
  review fixes.
- CRLF-aware diff whitespace validation passed. Owned Next/API/browser processes
  stopped, with no listeners on 3124/8137. The pre-existing disposable PostgreSQL
  server was left running.

The server on port 56362 was verified to use
`.test_artifacts/db-sync-20260922/pgdata`. Each database fixture applies migrations
and actual runtime grants and cleans its own database/roles; cloud calls and SMTP
were not used. No application database was changed. No `platform/api/.env` is present; application deployment was not performed.
Existing installations must apply `uv run pms-admin migrate` with their configured owner before this API starts.
Existing unrelated LLM, people, logs, device and concurrent human-test edits were
preserved. No commit/publication, hosted deployment, payment-service or hardware
verification was performed.

## Web device and tenant association management - 2026-09-24

Implemented the user's confirmed boundary: platform administrators control central
registration/lifecycle and cross-tenant association, and tenant administrators
manage devices within their tenant. Platform mutations use the existing
`platform.organizations.manage` permission and return public fleet summaries.
Tenant configuration, enrollment tokens and media still require explicit tenant
permissions. Transfers retire/revoke the old registration and create a fresh
inactive destination ID by default. Removal is terminal retirement; deactivation
is reversible. Source history and private settings never move between tenants.

Review 1 examined authorization, immutable ownership, database constraints,
credential lifecycle, atomic audit, quotas and concurrency. Platform payloads are
limited to registration/name/status; all new existing-device mutations require
an etag under row/administration locks. A failed target quota check rolls back the
source retirement and both audits. Same-source concurrent transfers create one
registration, and competing active transfers cannot overbook the destination.
Fixed assignment validation so unchanged inactive departments/profiles do not
prevent deactivation or unrelated edits; reactivation still revalidates them.
Reject invalid database text before writes. Confirmed that only the platform
route exposes cross-tenant transfer.

Review 2 examined selected-context fences, stale browser state, destructive
confirmation, enrollment-token display, responsive behavior and direct reloads.
Fixed duplicate React keys on the association/operations cards, hid a private
assignment shortcut in platform summaries, removed tenant-only client validation
from limited fleet saves, and kept revoke available for pending enrollment tokens
even when the prior credential was already revoked. Added regression coverage for
these UI boundaries. Server actions always reauthorize the selected context and
send etags; backend rules remain authoritative. Transfer failures remain visible
in the confirmation dialog. Retired records are available through explicit
filters and retain their detail/history links. Reviewed the final code and docs;
no further blocking implementation finding remains.

Verification completed:

- Full API baseline: **315 passed, 228 skipped**. PostgreSQL/browser/live/native
  checks are opt-in; skipped checks are not presented as passing.
- Device management, existing device console and subscription concurrency:
  **12 distinct targeted tests passed**, including **8** isolated PostgreSQL
  cases. The final batch initially had **10 passed, 2 setup errors**: Alembic
  subprocesses exited with Windows status `3221227274` before assertions. Both
  affected cases and the expanded transfer authorization case passed on isolated
  reruns (**3 passed**), without changing application behavior or relaxing tests.
- Real headless Edge -> Next server actions -> loopback API -> disposable
  PostgreSQL passed **seven journeys** in a separate browser fixture: platform
  registration/edit/lifecycle; tenant private edits and enrollment; platform
  transfer and credential revocation; fresh destination configuration/enrollment;
  direct reload; removal/current-retired filters; and desktop/mobile rendering.
  No browser runtime errors or horizontal mobile document overflow. Screenshots:
  `.test_artifacts/device-management-web/desktop.png` and `mobile.png`.
- The browser fixture brings the distinct targeted API/test-fixture count to
  **13**; unit cases overlap the baseline. SMTP was disabled and all accounts
  and registrations were synthetic.
- Full web suite: **368 passed in 51 files**. After the final review fix, the
  affected three files passed **16 tests**, including one additional regression
  (**369 distinct web tests passed** across these runs). Existing unrelated React
  `act` warnings remain non-failing.
- Ruff check and format check (**149 files**), mypy (**67 source files**),
  workspace TypeScript checks and the Next production build all passed.
- Final CRLF-aware diff whitespace validation passed. Temporary Next/API/browser
  processes were stopped; ports 3124/8137 have no listeners. The pre-existing
  disposable PostgreSQL server remains running.

The test server on port 56362 was verified to use
`.test_artifacts/db-sync-20260922/pgdata`. Fixtures apply forward migrations and
actual runtime grants, then remove their databases/roles. No application database,
frozen migration, permission catalogue or runtime grant bundle was changed.
Existing unrelated LLM/user/member/log work was preserved. No commit/publication,
hosted deployment, cloud, SMTP/OIDC or Raspberry Pi hardware verification was
performed. Previously recorded unrelated full-PostgreSQL findings remain outside
this task. Existing worker/offline authorization behavior is retained; central
deactivation does not synchronously recall already submitted external work.

## Web activity logs - 2026-09-24

Replaced the preview log directory and local sample lookups with persisted
platform audit and tenant activity list/detail APIs. Added metadata search,
category/severity/actor/date/ID filters, signed cursor pagination, totals, sorting,
manual refresh, direct detail reloads and recoverable errors. Tenant activity
readers now have a permission-filtered Logs navigation item. API records remain
immutable; retention and runtime grants are unchanged. Existing user/member and
LLM work was preserved, and no application database was modified.

Review 1 checked authorization, historical department scope, lifecycle, retention,
payload disclosure and the database contract. Removed the old web guard's
unrelated platform organization permission bypass. Server actions fence the
selected context; platform audit cannot read operational events and does not
grant tenant access. Approved metadata is projected identically in lists/details;
unknown fields, credential-like strings and URLs are omitted with an explicit
flag. Search only uses public event/entity types and event IDs, so omitted payloads
cannot be discovered through counts. The real browser fixture exposed the old
preview's unsupported `critical` severity. Fixed the filter, type and badge to the
persisted `info|warning|error` contract.

Review 2 checked direct links, late responses, filter resets, legacy pagination,
UTC boundaries, cursor ties/tampering, error retry, immutability and responsive
behavior. Existing ID-ascending clients remain compatible; the UI requests
occurrence-descending signed cursors. Through-day filters advance to the next UTC
midnight. Context-keyed providers/details prevent stale tenant state; refresh and
retry restart directory pagination. Rechecked query bounds, parameterized SQL,
expiry checks and department/category restrictions. No further blocking finding
remained. Metadata allowlisting deliberately hides unreviewed historical/custom
payload fields; this is documented rather than silently returning raw details.

Verification completed:

- Full API baseline: **311 passed, 223 skipped**. The skipped PostgreSQL/browser/
  live/native checks are opt-in, not claimed as passing.
- API Ruff check, Ruff format check (**146 files**) and mypy (**66 source files**)
  passed. Web TypeScript checking passed.
- Full web suite: **361 passed in 50 files**, with two workers. Existing React
  `act` warnings in unrelated preview route tests remain non-failing.
- Real headless Edge -> Next server actions -> loopback API -> disposable
  PostgreSQL passed **seven journeys**: anonymous/authenticated platform access;
  direct audit details/redaction/reload; operational denial in platform context;
  tenant cursor pagination/totals; filters/UTC dates/empty search/reset/refresh;
  tenant deep links/expiry/retry; and selected-tenant isolation/mobile layout.
  No browser runtime errors or mobile document overflow. Screenshot:
  `.test_artifacts/logs-web/mobile.png`.
- Browser fixtures disabled SMTP and used synthetic events/accounts. Early fixture
  failures were corrected (expired receipt chronology, awaited mail mock and waits
  for debounced search results). A migration subprocess also exited abnormally
  during verification, including outside the Windows sandbox; fixtures cleaned
  up their databases/roles. The affected checks passed on isolated reruns without
  application or test-rule changes. This was a subprocess setup failure, not a
  failing assertion in log behavior.
- The new log API suite passed **9 tests**, including **3** isolated runtime-role
  PostgreSQL cases. All **3** broader platform/tenant dashboard and lifecycle
  checks passed on reruns. Together with the browser fixture, **13 distinct
  targeted tests** passed (baseline unit tests overlap).
- The Next production build passed. Final CRLF-aware whitespace validation passed.

The disposable server on port 56362 was verified to use
`.test_artifacts/db-sync-20260922/pgdata`. Fixtures apply forward migrations and
actual runtime grants, then remove their databases and roles. Owned Next/API/
browser processes were stopped, and ports 3124/8137 are closed; the pre-existing
test PostgreSQL server remains running. No migration, hosted deployment, cloud,
SMTP/OIDC or hardware verification, commit or publication was performed.
Existing unrelated full-PostgreSQL findings recorded in the LLM review remain
outside this task. This screen shows retained business/device events, not terminal
output or every HTTP request.

## Web user and member management - 2026-09-24

Replaced the mock administrator/member screens and in-memory mutations with an
API-backed platform account directory and tenant membership directory. Both have
search/filter/sort/cursor paging, direct detail routes, error/retry feedback and
versioned lifecycle actions. Users support local creation, profile/platform-role
editing and setup resend. Members support identity-bound local/OIDC invitations,
department/role editing, resend/revoke and explicit recipient acceptance. Archive
preserves records and audit history; restoration returns disabled. Email changes
retain their verified account flow, and OIDC profile fields remain provider-owned.
No migration, frozen baseline edit, new runtime grant or application DB mutation
was needed. Earlier uncommitted LLM work was preserved.

Review 1 covered authorization, identity ownership, secrets, database integrity and
concurrent requests. Fixed the preview's platform-permission bypass, required the
selected tenant on every server action, removed invitation pre-acceptance, added
version guards to archive/revoke/resend/setup, and made acceptance increment the
version and revalidate its department. Duplicate invitations serialize under the
administration lock and retain database uniqueness/seat enforcement. Existing
deferred guards protect the last usable platform/tenant administrator. User list
setup projections are batched; list/detail member projections agree. No tokens or
password fields appear in directory responses.

Review 2 covered lifecycle edges, browser retries, account setup, stale forms and
usability. Fixed member activation against unavailable global accounts, invalid
Unicode/null text before persistence, moving joined-date cursor sentinels,
effective invitation expiry filters, and missing setup-resend version updates.
Removed unnecessary directory loads on direct details and false preview labels.
The recipient page clears fragment/legacy-query tokens, keeps them only in memory,
requires explicit acceptance, and supports local sign-in without losing the link.
Invitation email failure opens a temporary share drawer; queued setup is never
labelled delivered. Late responses, duplicate submits and dirty closes are guarded.

Verification completed:

- `uv run pytest -q --tb=short`: **305 passed, 219 skipped**. Database/browser/live
  gates are opt-in and were not silently treated as passing.
- Dedicated disposable PostgreSQL port 56362 was verified to use the test-only
  `.test_artifacts/db-sync-20260922/pgdata` directory. Management plus people tests
  passed **18**, session/subscription tests passed **18**, and the final browser plus
  people regressions passed **13** (overlapping tests; **45 distinct targeted tests**).
  Each fixture upgraded a fresh database and applied actual unprivileged runtime
  grants, then removed its database and roles. No application database was tested.
- Ruff check, Ruff format check (**143 files**) and mypy (**65 source files**) passed.
- Web suite: **345 passed** in 49 files with two workers. The initial fully parallel
  run timed out in two existing account-action tests under concurrent browser load;
  the bounded rerun passed without increasing test timeouts. TypeScript checking
  and the Next production build passed.
- Headless Edge -> real Next server actions -> loopback HTTP API -> PostgreSQL
  passed eight complete journeys: platform create/edit/setup, direct detail and
  persistence, lifecycle, tenant invitation/resend, recipient acceptance and scope,
  concurrent stale edit, member archive/restore/activation/revoke, and responsive
  layout. Two runner timing errors (reload before navigation; mutation before the
  editor finished loading) were corrected before the successful final run. No
  browser runtime errors or mobile document overflow were observed. Screenshots:
  `.test_artifacts/people-web/desktop.png` and `mobile.png`.
- Test-owned Next/API/browser processes were stopped and ports 3124/8137 closed.
  The pre-existing disposable PostgreSQL server was left running. Whitespace check
  passed with the repository's CRLF-aware Git setting. No commit or publication.

External SMTP/OIDC, hosted deployment and hardware were not contacted. Existing
unrelated full-PostgreSQL qualification findings in the LLM review below remain
outside this task; focused runtime-role PostgreSQL tests are not a claim that the
entire database suite passes.

## Web LLM connection management - 2026-09-24

Implemented tenant **Settings > LLM connections** with real server actions and API
CRUD, filtering/cursor paging, encrypted key replacement, enable/disable,
archive/restore, optional catalog linking and provider-specific response settings.
The existing active-only processing list remains compatible. No migration or new
runtime grants are required. An archive preserves history; restoring leaves a
connection disabled. Saving does not select a different published profile.

Review 1 checked authenticated tenant context, permission enforcement, encrypted
credentials/redaction, endpoint policy, lifecycle and revision checks. Added a
context guard to prevent a stale browser tab writing into a newly selected tenant.
Found a publication/archive race in the existing profile validator; publication now
locks the LLM row and rechecks its lifecycle. A PostgreSQL concurrency regression
holds publication at validation and verifies archive waits, then rejects the active
published dependency. Blank names/prompts and PostgreSQL-incompatible text are
rejected before database writes/searches.

Review 2 checked the rendered desktop/mobile screens, failure recovery, protocol
defaults and check-result wording. Fixed an undefined style reference, whole-token
formatting, mobile action wrapping, readable model-parameter details, specific
provider errors, and a stale-revision status-result guard. The local-status regression
still expected the previous Qwen3 ID; updated it to the configured Qwen3.5 default.
The final diff preserves earlier migrations, credential encryption, provider gates,
the local execution boundary and the existing profile-selection mechanism.

Verification: API Ruff lint/format and mypy (65 source files) pass; both UI workspaces
typecheck and the production Next.js build passes. The design system's 1,577 tests
pass; the web suite's 340 tests pass, with two additional list/status regressions
passing separately. The real headless browser flow passed twice against Next.js,
HTTP FastAPI and isolated PostgreSQL, covering login/access, creation and reload,
details/checks, key rotation, response edits, all lifecycle actions, stale edits,
all four supported provider forms, search/filter and mobile layout, with zero browser
runtime errors. Browser checks made no cloud calls. See the reproducible instructions
in [web README](../platform/ui/apps/web/README.md#llm-connection-management).

The focused API selection verified 30 passing cases and identified the obsolete
Qwen-name assertion above. After correction, the affected rerun passed all 12 tests
(the 11 management/input/concurrency cases plus the local-status regression), for
35 distinct affected cases verified across the runs. The final full API run without
a database DSN passed 297 tests and explicitly skipped 214 database/opt-in cases;
the separate PostgreSQL and browser runs supply the scoped database evidence.
Test-owned Next.js and HTTP API processes were stopped after verification. The
pre-existing disposable PostgreSQL server was left running.

The broader PostgreSQL run was interrupted after it exposed failures outside this
increment; it is **not** a passing full database qualification. Separate reproductions
confirmed `test_patient_conversation_uses_one_completion` still submits patient
completion without the required conversation setup (409 `conversation_required`),
and `test_connection_activation_fences_validation_and_database_acl` reports PUBLIC
execution grants on `valid_language_map` and `valid_language_list`. The interrupted
run also reported a teardown error that was not diagnosed. Those broader failures
remain follow-up work. Live cloud inference, hosted deployment and physical devices
were not verified.

## Empty speech recognition remains silent - 2026-09-24

The desktop previously emitted the language pack's canned clarification, answer
events and TTS when recognition returned no words. Removed that fallback and its
obsolete status badge mapping. Empty recognition and speech containing only
punctuation/invisible marks now use the existing ignored-input path before the
editable dictionary or answer dispatch. No answer, TTS, reply animation, accepted
history, archive entry or answer-usage record is produced. ASR admission and
recognition still occur; an active microphone session continues listening.

First review traced the local/cloud recognition paths and verified that the
reported reply came from the canned fallback, not the LLM. Second review checked
the shared response guard, preserved generation fencing/audio cleanup, dictionary
independence, valid short questions and UI continuation. The clarification phrase
remains available for meaningful ambiguous input; it is no longer emitted for
empty recognition.

Verification: **146 passed** across flow, continuous listening, editable filtering
and native patient workflow tests, with no skips. Coverage includes both speech
hosts and answer execution modes, blank/whitespace/punctuation/invisible Unicode,
unchanged prior history, zero answer calls, audio cleanup, a blank answer display,
no speech/animation and continued listening. Targeted Ruff lint/format and controller
mypy passed. Tests use mocked recognition and a native UI; live noisy microphone
verification was not performed. Restart an open Human-test window to load the fix.

## Development snapshot verification - 2026-09-24

Prepared all current workspace changes for the user-requested commit and publication:
conversation/language implementation, Qwen 3.5 defaults, input filtering, model UI,
and seated manikin gestures. Existing implementation and qualification gaps remain
open; publication does not mark the language phase plan or answer-quality work complete.

- Full desktop suite: **427 passed, 6 skipped** (opt-in model/voice checks).
- API suite without a disposable database configured: **291 passed, 208 skipped**.
  Database integration/migration qualification was not performed in this run.
- Changed model/settings UI tests: **45 passed**; web TypeScript checking passed.
  React `act` warnings remain in some passing UI tests.
- API Ruff lint/format and mypy passed; desktop Ruff lint/format passed. Fixed
  import ordering and formatting in the evaluation script and existing test changes.
- Reviewed staged paths and common credential patterns; private environment files,
  runtime state, media/models and ignored test artifacts are excluded. No credential
  pattern matches or files over 5 MiB were found among the 116 staged files.

The previous [gesture reviews](patient-gesture-review.md) record native previews
and focused regression evidence. Live model answer quality, comprehensive isolated
database checks and live microphone/cloud/hardware qualification remain outstanding.



## Editable input ignore dictionary - 2026-09-24

Implemented `human-test/src/human_test/input-ignore.json` and a bounded literal-phrase
matcher before the desktop's local/cloud generation dispatch. English filler-only,
acknowledgement-only and gratitude-only inputs are ignored, including combinations,
repetitions and elongated fillers. Questions and other content pass unchanged.
Typed and recognized speech inputs share the same check. Ignored input produces no
answer event, TTS request, reply animation, accepted-history entry, archive entry or
local usage record. Speech recognition and its existing admission checks still occur.

Review 1: checked whole-utterance matching, Unicode question punctuation, prefix
collisions, overlapping phrases, exact language isolation and safe reload behavior.
Fixed a Windows console encoding issue that initially altered non-ASCII punctuation;
question marks, operators and emoji now remain meaningful input. Malformed, oversized
or missing configuration fails before model dispatch instead of using stale rules.

Review 2: traced both controller entry paths through queued desktop input and the
UI. Added a dedicated non-reply event to clear the previous answer without calling
speech/animation handlers. Regression tests cover an ignored filler between two
meaningful turns, unmodified history and question text, both execution hosts, typed
and recognized input, invalid edits, and dictionary edits without restarting.
The installable wheel includes the exact default JSON. Filter-only measurement:
1,000 local checks, median 0.340 ms and p95 0.431 ms (no ASR/LLM/TTS timing claim).
Ruff, formatting and the typed matcher check passed. The full desktop suite passed
407 tests with 6 opt-in live/native checks skipped; the final focused filter rerun
passed all 78 tests. This change does not certify the broader pending model
quality/language-architecture work or live microphone/cloud behavior.

## Detailed conversation language phase plan - 2026-09-24

Expanded the architecture into a [phase-by-phase implementation plan](language-conversation-phased-implementation-plan.md)
at the user's request. Phases 0-8 cover baseline, pack contracts, localized case data,
conversation persistence, shared engine, host integration, English speech, measured
qualification, and final review/development activation. Phase 9 is the repeatable
later-language process. Each phase identifies dependencies, work, affected modules,
and an exit gate; existing unfinished code is not treated as a completed phase.

The plan specifies proposed conversation API operations, server-owned cloud history
versus client-reported local history, turn claims/idempotency, stale callback handling,
translation-review invalidation, bounded retention, and current offline authorization
limits. Acceptance separates 45 live questions, at least 216 broader English turns,
controlled repetitions, held-out coverage, recorded speech, and actual microphone/
speaker evidence. Targets and preliminary token allowances are not claimed results.

Reviewed the plan for dependency order, consistency with the architecture and repository
guides, token-budget arithmetic, and distinctions between planned and verified work.
Documentation links, Markdown fences, and scoped whitespace checks passed. No runtime,
database, cloud, deployment, or publishing action is part of this planning revision.

## Pluggable conversation language planning - 2026-09-24

The user requested an architecture and implementation plan before further runtime
changes, with English first and additional languages added independently. The
[language architecture plan](language-conversation-architecture-plan.md) supersedes
the earlier plan's language scope and sequence. Single-call runtime changes have
started in the workspace but remain unfinished; this entry does not certify them.

Inspection found repeated English/Hindi branches in case contracts, prompt rules,
desktop settings, startup, API schemas, and speech capabilities. The proposal
reuses the existing platform language catalog and provider interfaces, adds trusted
versioned packs and generic localized case text, and pins language/case/model
versions to an immutable scoped conversation. Model and speech readiness remain
operation-specific. English qualification precedes Hindi and further languages.

Design review covered missing/stale translations, no automatic language switching,
late asynchronous replies after reset, tenant/cache/history isolation, source edits,
permission revocation, one-call budgeting, and the distinction between typed model
latency and live speech latency. Language extensibility will be tested with a
synthetic second pack before claiming that additional languages require no core
branches. Planned targets and earlier draft token measurements are labelled as
such; no completed English quality gate is claimed.

This revision changes documentation only. Verification is document inspection,
local-link checks, and scoped whitespace/diff review; no runtime or database tests
are newly claimed for this planning revision. Earlier experimental implementation
and test artifacts remain separate. No cloud call, deployment, commit, or publishing
is part of this revision. Unrelated model UI changes are preserved.

## Patient conversation replacement planning - 2026-09-24

The user selected one generation with the complete permitted case and recent
conversation, then requested a detailed implementation plan. The installation is
not in production: the plan uses a coordinated replacement without a legacy
execution mode, mixed-client compatibility layer, staged rollout, or backup gate.
See the [implementation plan](patient-conversation-implementation-plan.md).
At the time of this initial planning entry, runtime changes, schema updates, and
answer-quality validation were outstanding. Implementation subsequently started;
the revised language planning entry above records the current paused state.

Evidence from this investigation: 26 retained exchanges across September 21, 22,
and 24 showed repeated intent, negation, and relevance failures for the same case.
Database inspection was scoped and read-only; historical simulation outputs were
considered separately from actual retained sessions. No private transcripts or
credentials are added by this documentation change.

A tokenizer-only diagnostic covered nine seeded cases using the installed local
Qwen3-4B model template. Draft English prompts used 826-858 input tokens without
history and 995-1,027 with six short pairs; corresponding six-pair Hindi prompts
used 1,261-1,293. These include the template and illustrative histories, not the
final compiler's complete field/disclosure representation. The diagnostic made
zero answer-generation calls and its temporary model server was stopped. Results
remain in the ignored `.test_artifacts/single-call-budget-20260924/` directory.
These measurements establish neither answer quality nor latency.

Verification for this change is documentation inspection, referenced-path checks,
and whitespace/diff review. No runtime tests, database changes, live cloud calls,
or deployments are claimed. Existing unrelated model UI work is preserved.

## Database, scripts and models synchronized after login — 2026-09-23

Completed the user's follow-up for the configured local `human_test_demo` database.
Verified the private data directory and stopped launcher, and confirmed zero active
application clients before maintenance. Windows currently excludes TCP ports
55430–55529, including its configured 55444; the same data directory was started
temporarily on loopback 56324. Application connection settings were unchanged.

Removed the duplicate `events_platform_audit_idx` additions from both frozen
baseline copies; migration 0021 remains the sole forward introduction of this
index. The original recorded baseline signature is unchanged and verified adoption
works again. Updated `deploy/verify-scenario-library.sql` to accept revisions 0021
and 0022, and added an executed-script regression after a real upgrade. Updated the
field contract to **31 tables / 545 columns** at `0022_browser_sessions`. The runtime
revision and Alembic's single head both match that revision.

Before modifying the application database, created a private custom-format backup
and restored it to the dedicated disposable server on port 56323. Verified its
original schema and all 1,765 rows, then rehearsed 0020→0022 and current runtime
grants. The upgraded restore matched a fresh migrated reference, every ORM
column/type/nullability/primary key, and the API/worker/retention privilege matrix.
PostgreSQL's dump/restore reparses two LLM CHECK expressions into equivalent
flattened AND expressions; this was validated by asking PostgreSQL to reparse the
reference definitions inside a rolled-back transaction, without weakening or
changing the application's constraints. Row fingerprints were compared in UTC.

Applied the same forward migrations and atomic grant script to the idle local
database under the launcher owner lock. Rechecked unchanged pre-upgrade row
fingerprints against the verified backup before migration. Afterward, **all 31
tables and 1,765 existing rows were preserved**, the full structural catalog and
runtime privilege matrix matched the reference, all **545 columns** matched the
ORM, all **31 model SELECTs** succeeded as `human_api`, and schema readiness plus
the read-only scenario-storage verifier passed. The successful backup is
`human-test/.local/demo/backups/before-browser-sessions-20260923T042032Z.dump`.

Verification: **2 migration/adoption tests passed**; the updated verifier, deployment
grants and API backup/restore subset passed **3 tests**; the standalone SQL
installer/constraint/role/concurrency/backup verifier passed **92 operations**.
Changed-test Ruff lint/format and owned-file whitespace checks passed. The normal
API suite remains **244 passed, 22 failed, 195 skipped** without a test DSN; those
22 pre-existing local-parity/patient-practice failures are unchanged. Repository
lint still reports three unrelated management/training findings, formatting flags
six unrelated files, and mypy flags the unrelated training float/int assignment.
No clean full-repository result is claimed.

Evidence is in `.test_artifacts/db-sync-20260923/`: `upgrade.json`,
`rehearsal.json`, fresh reference signatures/privileges, migration/grant/restore
results and standard-check logs. Both owned PostgreSQL servers were stopped after
verification. The application remains stopped as before; normal startup on 55444
is still blocked by the Windows port reservation. No database on port 5432, cloud
provider, SMTP service, or hardware was contacted.

## Login implementation and verification — 2026-09-23

Implemented the authorized follow-up to [the eight login findings](login-review-20260923.md#implementation-follow-up). The seed is restored to its original administrator-free content. Login rehash and account mutations now serialize through refreshed user/credential locks, and one-time actions bind to credential versions. Forward migration `0022_browser_sessions` preserves credentials and bearer sessions while consuming legacy email-change actions. Existing runtime grants cover the added columns without granting authentication-table access to processing workers.

The web app now uses real local-account API authentication, opaque revocable sessions, and current API identity/permissions. Platform and organization contexts remain separate. Setup, reset, email confirmation, recovery, password change, email change and logout are connected. Production cookies use HttpOnly/SameSite/Secure/host-prefix rules; deletion retains the prefix-required attributes. New email action links use fragments, which the form removes from both the address bar and Next router state. A second link opened on the same page resets the form safely. Rejected requests release pending state. Demo identities remain only in presentation-test fixtures.

Verification:

- Production Next build and TypeScript validation passed. The real Edge browser journey passed **12 checks** against the actual Next server actions, FastAPI and disposable PostgreSQL runtime role: forged-cookie rejection, setup/token removal, invalid credentials/retry, cookie flags/session lifetime, parallel tabs, foreign-Origin rejection, server-side logout revocation, remembered login, password change, one-time recovery, email confirmation/new login, and expiry.
- Focused PostgreSQL authentication/management run: **24 passed**. Its additional baseline-adoption test failed on pre-existing/concurrent index drift in `003_indexes.sql`; that unrelated change was preserved. A separate **0020→head upgrade regression passed**, checking credential and bearer-session preservation, action-version backfill and legacy email-action consumption. The twelve new API regressions include deterministic password/rehash and stale-email races, refresh replay/concurrency, account lifecycle, rate limits, purpose binding and revocation.
- Initial full web suite: **333 passed**. After the browser-discovered fixes and one added regression, the full suite returned **331 passed, 3 timed out** under host load; all **29 tests** in those three files passed when rerun serially. The final account/session subset passed **18 tests**. No failing UI assertion remains.
- Full API run without a database: **244 passed, 22 failed, 195 skipped**. The 22 failures match the pre-implementation local-parity/patient-practice failures. Database/live/native cases skipped in this run are not counted as verified. A broader run with the disposable database was stopped after repeated local connection timeouts and additional failures; it did not complete and is not a clean full-database result.
- Ruff lint and format checks pass for all **12 owned Python files**. Repository-wide lint still reports three errors in unrelated management/training changes; formatting flags six unrelated files; mypy reports the existing/concurrent float-to-int assignment in `modules/training.py:450`. Owned-file diff whitespace checks pass.
- The browser fixture initially exposed a Windows event-loop mismatch; its runner now uses a Selector loop, consistent with the existing production CLI. Synthetic expiry data was corrected to respect session timestamp constraints, and expiry control uses the fixture's runtime connection pool. The final browser run passed after these fixture corrections. Some checks were rerun outside the sandbox following local PostgreSQL connection stalls.

Evidence: `.test_artifacts/login-implementation-20260923/`, including `browser-result.json`, build/type logs, focused API results, upgrade results, web suite/rerun logs, repository checks and the explicitly incomplete database-suite log. Browser fixture routes are loopback-only test code with a random control secret; they are absent from the production app. Temporary browser/API services were stopped and the fixture secret removed. The dedicated PostgreSQL test cluster was stopped after testing.

The application database and live providers were not changed. Deployment needs migration 0022 plus runtime grants, the server-only web API URL, and API local-auth/SMTP/account-URL configuration. Any administrator previously provisioned by an altered shared seed requires operator password rotation and session revocation. Google/Microsoft browser SSO, live email delivery, hosted deployment, cloud and hardware remain unverified. Business dashboards/directories still show labelled preview data. Concurrent dashboard/index work and unrelated simulation files were preserved.

## Login and account lifecycle review — 2026-09-23

Review-only findings are in [Login and account lifecycle review](login-review-20260923.md), with source references, reproductions, impact and remediation. Application source, migrations and application data were unchanged. Web login remains a demo with no authentication API call. Local HTTP checks confirmed an unsigned demo cookie can select the admin preview and the three account-action completion routes return 404. A rejecting sign-in component probe reproduced the permanently pending button.

Fresh PostgreSQL migration failed because the packaged frozen seed references local-identity columns/tables introduced only in 0020. It also contains a shared administrator password. Seven focused database test setups failed for this reason. A child-process-only fixture overlay then used the original `platform/db/sql` baseline and all current forward migrations/runtime grants; only the administrator seed differs after newline normalization. Four supplemental probes passed, including deterministic reproductions of a login rehash overwriting a completed password change and an email-change action being created after password/session revocation. Normal refresh replay/family revocation, protected access rejection, reset purpose binding, one-time use and reset session invalidation also behaved as expected.

Existing authentication UI tests passed 22/22, the extra rejection probe passed, and web type checking passed. Focused API checks without a DSN passed 14 with 3 skipped. Full API pytest without a DSN returned 244 passed, 22 failed and 179 skipped; failures are outside login in local parity/patient practice. Ruff lint and mypy passed; formatting reports existing comment line-ending differences in `llm.py` and `local_turns.py` (125 files passed). Unrelated source was preserved. Two further probes passed for deactivation/reactivation/expiry/disabled authentication and simultaneous refresh, bringing supplemental coverage to six probes. The synthetic expiry timestamps were corrected after an initial fixture constraint violation. Temporary Next and PostgreSQL services were stopped; review artifacts and unrelated patient-routing work were retained. Documentation diff whitespace checking passed.

Local evidence: `.test_artifacts/login-review-20260923/`. The dedicated disposable PostgreSQL server uses loopback port 56323. No application database or external provider/email service was tested. No live end-to-end login is claimed; findings remain open in TODO.

## Configured database synchronization and tenant back navigation - 2026-09-22

The user limited database synchronization to the configured `human_test_demo` on
`127.0.0.1:55444`. Read-only inspection verified its private data directory, no
connected application clients, and revision `0019_patient_turn_recovery`. Its
complete structural catalog matched a fresh revision-19 reference. The separate
PostgreSQL installation on port 5432 was excluded; no configuration or data there
was changed.

A dedicated disposable PostgreSQL 17.10 cluster on port 55462 was used for fresh
migration, upgrade, runtime-role and API tests. Migration 0020 produced 31 domain
tables and 543 columns matching every ORM column, type, nullability and primary
key. All six packaged baseline SQL files match `platform/db/sql/`. Published SQL
and migrations were preserved. Updated the database documentation's stale current
field counts and the scenario-storage verifier's accepted revision list.

Database execution exposed a real local-account creation failure: the mappings
do not declare DDL foreign keys, so a combined flush could insert credentials
before the user. Platform user creation, local invitations and local-admin
bootstrap now flush the user first inside the same transaction. The HTTP account
flow, bootstrap, invitation creation and a forced audit-failure rollback are
covered by PostgreSQL regressions. No model or schema change was necessary.
Updated the upgrade assertion to check the new nullable fields before comparing
the old record, and made backup hashing support tables whose key is not `id`.
The cursor tamper test now changes signed bytes instead of sometimes changing
only unused base64 padding bits. Upgrade coverage also compares every column's
PostgreSQL type and nullability with the ORM.

After 13 focused database checks passed, took a private custom-format backup,
verified its archive listing, and applied the existing forward migration and
current grant bundle to the idle configured database under the launcher lock.
The backup is retained at
`human-test/.local/demo/backups/before-management-api-20260922T082039Z.dump`.
Post-upgrade catalog comparison matched all 523 constraints, 127 indexes,
33 functions, 58 triggers, both role views, table/column defaults and policy state.
Effective table, column and function privileges for all three runtime roles match
the fresh grant bundle; roles retain no owner or administrative inheritance.
All 1,866 existing records across 25 pre-upgrade tables have identical content
hashes when projected onto their original columns. The configured API role can
select all 31 mapped tables, the schema readiness check passes at
`0020_management_api`, and the read-only scenario-storage verifier passes.
The database and its private data were not used by destructive tests. No providers,
SMTP, hosted service or physical devices were contacted.

Tenant View now includes a visible top Back to tenants link with the shared
left-chevron icon in the breadcrumb navigation. The footer link is retained.
Eleven focused app tests and app type checking passed. Six local browser checks
verified top-link visibility/icon at mobile width, filter retention, exact 200px
table-scroll restoration, mobile navigation dismissal and no runtime errors.
Unrelated device UI work was preserved. No UI API integration was added.

Final regression results and cleanup are recorded below after completion.
Local evidence is under `.test_artifacts/db-sync-20260922/`; private database
backups and credentials remain excluded from Git.

## Tenant View page - 2026-09-22

Completed the dedicated `/tenants/[tenantId]` UI. View now uses a real Next link instead of a drawer. The page presents a named heading and breadcrumb, a status/plan/created summary, About this tenant and Primary contact cards, and record ID/creation/update/archive information. It reuses the existing page, card, badge, menu, icon and theme styles. Long values wrap, the detail columns stack on small screens, and no usage counts, subscription limits or audit events are invented.

Moved local records and list query/page/bookmark state into `TenantDirectoryProvider` under the guarded tenants layout. List/detail navigation retains newly created and edited records without storage or API calls. Back links and browser Back/Forward preserve the directory context; the returning row/table receives focus and the saved scroll position is restored. A reload resets the fixture. Missing local records (including a newly created record opened after reload or in another tab) show an unavailable-preview explanation and a directory link, not a fabricated server 404.

The tenant layout, directory page and detail page all require the existing tenant-read grant on the server. Client actions also honor the manage grant and archive state. Edit uses the existing form and refreshes the current view in place. Copy ID confirms success or focuses/selects the displayed identifier as a manual fallback. Delete requires confirmation and leaves the archived details visible while Edit is removed and repeated Delete is disabled. The shared local mutation handlers reject missing permissions, stale versions, archived mutations and invalid create plans. These remain demo presentation rules, not production authentication or API concurrency enforcement.

Review checked semantic heading order, email-link construction, plain-text descriptions, missing contact/description/plan states, direct-route denials, same-record editing, archive behavior and navigation focus. Fixed the browser's input-like outline on the programmatically focused page heading while keeping control focus styles intact; wrapped header actions now align to the trailing edge. Detail components are keyed by route ID so transient editor state cannot follow a different tenant. Final screenshots were inspected after the styling fixes.

Verification from `platform/ui`: `npm run test --workspace=@pms/web` passed **156 tests in 19 files**; app type checking and `npm run build` passed. New/updated cases cover route and layout guards, detail cards, in-place editing, delete confirmation, clipboard fallback, empty/unknown states, safe rendering, read-only access, stale writes and archived records. Existing Create/Edit, tenant directory, Settings and authentication tests passed. `git diff --check` passed.

Local Edge verification passed **40 checks in development and 40 against production**, plus **five additional production navigation checks**. The latter verified preserved status filtering, exact table scroll restoration (200px before and after the round trip), mobile-rail return/dismissal and heading focus styling. **15 direct HTTP requests** across visitors, unknown demo IDs and all three demo roles verified directory/detail/missing-preview access. Screenshots and measurements cover 1440x900, 1366x768, 760x900, 390x844 and 320x740, including a long tenant name, light/dark/ledger themes, archived details and missing records. No runtime/hydration errors, API requests, horizontal/document overflow or duplicate content scrollers were observed. Evidence is under `.test_artifacts/tenant-view-20260922/` locally. Development was stopped before building to avoid concurrent `.next` writes.

Final review found no further confirmed issues within this UI scope. Prior Settings, tenant forms and shared rendering fixes were preserved. No shared-package or API/database source changed in this phase; shared-package/backend/database/live-service suites were not rerun. API integration and persistent records remain deferred.

## Tenant Create/Edit preview - 2026-09-22

Implemented the four UI-only Create/Edit phases. Both entry points now open the existing shared large drawer, with grouped tenant details, primary contact and subscription/status fields, reused icons and theme styles, a scrolling body and fixed actions. View also offers Edit when permitted. The initial tenant-name field receives focus. Required name/plan controls, optional description/contact fields, email normalization, inline errors and first-invalid focus make the form usable without native browser error popups. Unchanged edits and duplicate submissions are prevented; local failures retain the draft and permit retry.

Inspected `OrganizationCreate`, `OrganizationPatch`, platform create/update routes and subscription assignment before implementation. New records start inactive, as the platform create route does, and require a sample plan. Edits preserve ID, creation time and subscription assignment; plan changes remain a separate operation. Existing tenant status is editable in the preview, optional fields can be cleared to null, timestamps/version update locally, and contact information does not create accounts or send invitations. Real activation prerequisites, server authorization, constraints and concurrent updates require the future API integration; the demo does not claim to enforce those services.

Saves update only the list's in-memory records and preserve its search, filters, sort and page (clamping if a row leaves the final page). A success notice offers View tenant even if the saved record is outside that view. Cancel, Escape, close and backdrop share a dirty-draft confirmation with Keep editing focused first. Dirty forms also register the browser's refresh/tab-close warning. Row/table focus is restored on return. Create/Edit remain gated by the existing manage permission, and archived records cannot be edited. The save handler rechecks permission, record lifecycle and version. There are no API calls, persistent browser records or simulated network delays.

Review found and fixed two presentation issues: development Strict Mode's focus cycle could show a required-name error before the user edited anything, and the shared adjacent-field margin could offset the second contact field. Blur validation now waits for a changed field (submission still checks every field), with a Strict Mode regression test. The grid override now has sufficient specificity in both development and production. Reviewed the final forms in light, dark and ledger themes, narrow/mobile widths and short windows; verified keyboard flow, nested confirmations, saved-record navigation and contact alignment.

Verification from `platform/ui`: `npm run test --workspace=@pms/web` passed **138 tests across 17 files**; `npm run typecheck --workspace=@pms/web` and `npm run build` passed. Tests cover field boundaries, unavailable plans, optional email, inactive creation, identity/version preservation, clearing contacts, dirty and unchanged drafts, save failure/retry, duplicate submissions, filtered-out saves, paging/focus restoration, permissions and archived controls. Existing Settings, tenant-list and authentication tests remain green.

Local Edge checks passed **46 in development and 46 against the production build**, plus **18 production checks** for saved-list scrolling/layout and dirty close/backdrop dismissal. Five direct `/tenants` requests verified visitors/unknown IDs redirect to Login, tenant roles redirect to Home and the platform demo account can enter. Viewports included 1440x900, 1366x768, 1366x600, 1366x500, 390x844 and 320x740. Form actions remained visible; there was no horizontal/document overflow, extra list scrollbar, runtime/hydration error or API request. Build/test logs, measurements and screenshots are under `.test_artifacts/tenant-editor-20260922/` locally. Development was stopped before building to avoid concurrent `.next` writes.

Final review found no further confirmed issues in this UI scope. Previous tenant, Settings and shared-shell changes were preserved. No shared package or API/database code was modified in this phase; shared-package/backend/database/live-service suites were not rerun. Demo changes reset on reload. API binding, subscription reassignment and administrator onboarding are separate work.

## Settings follow-up review - 2026-09-22

Re-reviewed the Settings catalogue, server route guards, navigation, card semantics, theme styling and shared shell behavior. Reproduced a mobile navigation issue in Edge: Home -> open navigation -> Settings updated the route, but the persistent shell left its drawer and scrim covering the cards. An app regression test failed with `data-drawer="open"` before the fix.

Added an optional, router-independent `AppShell.navigationKey` and passed the current pathname from `ConsoleShell`. A route change now dismisses an open drawer through its existing focus-restoration logic. Shell updates without navigation leave the drawer alone; desktop navigation does not move focus to the hidden mobile trigger. Focus already moved into the destination is preserved. Four shared-shell regression cases and one application regression cover these behaviors.

Verification from `platform/ui`: `npm test` passed **1,699 tests** (**1,577 shared package + 122 app**, 62 files); `npm run typecheck` passed for both workspaces; `npm run build` passed. `git diff --check` passed. Development was stopped before the production build to prevent concurrent `.next` writes.

The follow-up browser script passed **18 checks in development and 18 against production**, covering actual pointer and keyboard navigation, focus restoration, Back/Forward, the mobile Models card and return breadcrumb, collapsed desktop navigation and all three demo roles. The existing production sweep passed **59 checks** across responsive layouts, all four theme preferences, reduced motion, card links and tenant-directory preservation. All **20 direct HTTP access checks** passed again. No runtime/hydration errors, API requests, horizontal overflow or extra document scrollbar were observed. Screenshots and logs are under `.test_artifacts/settings-hub-20260922/`, including the before-fix mobile reproduction and failing regression log.

Final review of the fix and screenshots found no further confirmed issues in the approved Settings hub scope. Existing tenant and hydration changes were preserved. The linked management screens remain previews and identity remains the existing demo session; this work does not add API integration or production authentication. No API/database code changed or backend/database/live-service tests were run.

## Settings hub - 2026-09-22

Completed the four approved Settings phases. `/settings` now presents Models, Licenses and Administrators as equal cards for platform administrators, reusing the existing card surface, model/license/role icons and theme tokens. Each card has one named, keyboard-focusable Next link, a description and a bottom-aligned action. The grid adapts from three to two to one column; focus is visible and hover movement respects reduced-motion preferences.

Moved the three platform destinations out of the rail, leaving Home, Tenants, Devices and Logs with Settings and Sign out below. Tenant administrators also reach Models through Settings; tenant users retain their personal Settings preview. Existing destination URLs remain `/models`, `/licenses` and `/users`. Each destination has a Settings breadcrumb and keeps Settings highlighted, including descendant paths without matching unrelated prefixes.

The category catalogue in `src/lib/settings.ts` combines role scope and permission checks. The hub, rail visibility/highlighting and direct-route guards use that catalogue. Review specifically checked that category readers can still reach Settings without settings-manage, that settings-manage alone does not unlock other categories, that tenant roles cannot reach platform destinations, and that an empty grant set exposes no management links. Visitors redirect to Login and unauthorized direct requests redirect to Home. Demo identity remains a role preview rather than production authentication.

Verification from `platform/ui`: `npm run test --workspace=@pms/web` passed **121 tests across 16 files**, including the existing tenant suite; `npm run typecheck --workspace=@pms/web` passed; `npm run build` passed. New tests cover role/grant combinations, missing grants, direct-route access, breadcrumbs, current-section highlighting, similar route prefixes, card keyboard order and an account with no accessible categories.

Local Edge browser verification passed **59 checks in development and 59 against the production build**, plus **20 direct HTTP route checks** across visitors, an unknown demo identity and all three roles. Browser checks covered sidebar-to-hub navigation, all cards and return links, client navigation, four persisted theme preferences, focus visibility, reduced motion, tenant scope and preservation of the tenant directory. Screenshots and measurements cover 1440x900, 1366x768, 1024x768, 760x900, 390x844, 320x740 and 1366x500. There was no horizontal overflow, outer scrollbar, runtime/hydration error or API request. The main content used at most one scroller. Evidence is under `.test_artifacts/settings-hub-20260922/` locally.

Final code and visual review found no remaining confirmed issues within the approved hub scope. No API/database or shared UI package changes were needed in this phase, and prior tenant/hydration fixes were preserved. Backend/database suites and live services were not exercised. Models, Licenses and Administrators remain preview destinations; their management forms and API integration are separate work. The development server was stopped before building to avoid concurrent `.next` writes.

## Tenant list preview and console rendering fixes - 2026-09-22

Completed all five tenant-list phases. The existing Tenants rail link opens the directory with 68 fictional records (62 current, six archived). Search, active/archive filters, stable sorting and 25/50/100-row paging follow the existing organization API's field/query names without making API calls. Shared components provide the table, controls, icons, badges, drawer, confirmation and notices. The final desktop design places Search/Status/Records/Sort in one row, removes the duplicate filter chip, and puts the filtered count beside pagination below the table.

View shows read-only tenant details; Copy ID uses the clipboard with a manual-copy fallback; confirmed Delete archives the sample record, marks it inactive and keeps it available under Archived. Removing a page's last row returns to the preceding page and restores useful keyboard focus. Archived mutations are disabled. Create/Edit remain explicit demo notices, as agreed for the list-only scope. Reload restores the fixture. The server route checks the read permission before passing records to the client; mutation controls require the manage permission. Existing demo sign-in remains a role preview, not production authentication.

Review and user feedback exposed four rendering issues, all fixed:

- The theme provider read browser storage during its initial render, disagreeing with server HTML. It now starts with the same state on both sides, then adopts browser preferences after hydration while preserving the pre-paint palette.
- The notification portal existed on the first browser render but not on the server. It now mounts after hydration. Four real server-render/hydrate regression cases assert retained DOM, correct saved theme, functional toasts and no recoverable or console errors.
- Absolutely positioned accessibility text escaped the table/main scrollports and extended the document, producing a third scrollbar and a blank tail. Both containers now establish positioning contexts; the shell's content row can shrink. Desktop tenant scrolling stays in the table with the pager visible; narrow or short screens use the main page scroller. Short windows may independently scroll the navigation rail.
- The console's bottom gutter was excessive, and production stylesheet ordering could reapply the shared table height cap on short windows. The console gutter is now 16px and the scoped table override has sufficient specificity. The final production browser pass verified this correction.

Verification: `npm test` from `platform/ui` passed **1,573 shared UI tests and 91 web tests (1,664 total)**; `npm run typecheck` passed both workspaces; `npm run build` passed. The app CSS checks passed again after the final stylesheet adjustment. Local production-browser checks covered Tenants navigation, full-dataset search, empty results, filters/sorting, paging, View/focus, actual clipboard copy, archive confirmation/cancellation, archived restrictions, reload reset and all four persisted themes. Measurements and screenshots covered 1440x900, 1366x768, 760x900, 390x844, 320x740 and a 1366x500 short window, plus Home on desktop/mobile. The document stayed within the viewport without horizontal overflow; content had one vertical scroller and desktop pagination ended 16px above the bottom. No browser runtime/hydration errors or API requests were observed.

Direct HTTP checks confirmed visitors/unknown demo IDs redirect to Login and tenant roles redirect to Home before tenant fixtures are rendered. Tests also cover missing read/manage grants, combined filters, stable tie-breaking, unchanged input fixtures, clipboard failure, empty directories and last-row archive paging. Build/test logs, browser measurements, screenshots and route checks are stored locally under `.test_artifacts/tenant-list-20260922/`. Development was stopped before building to prevent concurrent writes to `.next`.

No API/database code changed; backend/database suites and live services were not exercised for this UI-only work. API integration and Create/Edit forms remain outside the approved scope. Final review found no further confirmed issues within this preview.

## API management planning review - 2026-09-22

Prepared the [API-only management completion plan](pms-api-management-plan.md) from current management, authentication, device, model-routing, connection/profile, schema, and pagination code plus API/database/service documentation. The user confirmed two account types: external OIDC accounts keep provider-owned passwords, while platform-created users receive local login and password management. The plan specifies salted one-way password hashes and separate local credentials/sessions without converting or merging existing external users.

Planning review checked explicit CRUD/archive semantics, list consistency, identity migration compatibility, same-email collision handling, password recovery/session revocation, tenant and department isolation, administrator coverage, concurrent quotas, immutable profiles, credential redaction, and deferred live verification. Added phase checkpoints to the TODO. Documentation-only inspection; no runtime/schema changes and no tests run. Existing staged and unrelated work is preserved.

Expanded the plan after the planning baseline was published: added ordered work packages, proposed endpoint and list-field matrices, compatible schema sequencing, local-admin bootstrap, delivery/rate-limit responsibilities, and per-phase completion evidence. Rechecked current routes, role grants, user identity constraints, serialization, authentication dispatch, and disposable-test fixtures. The existing rate limiter is per-process, so local authentication explicitly plans shared limits. This remains documentation-only; no API behavior, migrations, deployment, or runtime verification changed.

Expanded phase 6 into a [multiple model/provider contract](pms-api-model-management-plan.md): distinct providers/adapters/model definitions/tenant bindings/profiles; current LLM, ASR, TTS, and video scope; catalog-only future categories; operation-specific parameter and availability checks; mixed-provider profiles; compatible legacy mapping; and eight delivery steps. Checked current provider literals, model options, profile sections, endpoint policy, and speech/media adapters. Provider discovery/access and future protocols are not claimed as implemented or live-verified. Documentation-only; no runtime tests required.

Consolidated the main management plan into a single ordered seven-phase contract, removing repeated phase narratives and incorporating phase 6's categories/providers, tenant deployments, typed capabilities, lifecycle and eight delivery steps. Preserved shared list/mutation conventions, local/OIDC boundaries, per-phase acceptance, migration/grant sequencing, compatibility and deferred verification. Added stable phase anchors and checked documentation links/formatting. This is planning only; concurrent UI work was not modified and no backend tests, migrations, or publication were performed.

## AI Evaluator console shell and dashboards — 2026-09-22

Added the signed-in console to `platform/ui/apps/web`: a guarded `(console)` route group, a role-aware rail and top bar, three dashboards, a change-password dialog, and twelve placeholder pages so no menu item is a dead link. Presentation only, by request — no API call, no data fetch. Roles and permission keys are the real catalogue from [`platform/db/sql/006_role_catalog.sql`](../platform/db/sql/006_role_catalog.sql) (`platform_admin`, `org_admin`, `org_user`); `lib/roles.ts` is the single place the schema's *organization* becomes the product's *tenant*, and the schema was not renamed to match the label. Every dashboard figure lives in one module, `data/demo.ts`.

**Sign-in still authenticates nobody, and the code says so.** A server action compares against three hardcoded accounts, so the password never enters the browser bundle; a test fails if any client module imports the credential file. The cookie holds a **user id only** — role and permissions are looked up server-side on every request, so a hand-edited cookie can at most name another demo account, never mint a permission — and is `httpOnly`, `sameSite=lax`, `secure` outside development. The guard is a server-side redirect in the console layout, so an unauthenticated browser never receives the console's markup. Verified live: no cookie and a forged `ae-demo-session=root` both 307 to `/login`, a valid session renders the console, and an already-signed-in visit to `/login` 307s to `/home`. Every screen carries a "Demo — no live data" badge.

Two additions were made to `@pms/ui`, both generic and both tested in the package: an optional `email` on `UserMenu`, which draws the identity block (name, address, role) at the head of the open menu as `role="presentation"` so it adds no fourth arrow-key stop; and an optional `as` on `RailItem`, so a router's link component can be supplied — without it a console built on Next reloads the whole document on every menu click. The second exposed a latent bug: two conditions tested `Link === 'a'` as a proxy for "is this destination safe", which would have rendered a custom link component with no `href` and no `aria-current`; the question is now asked once, of the href, and an unsafe destination still degrades to a `<span>`. Nothing else in the package changed, and its suite went from 1,565 to 1,569 tests, all passing.

Review of the new code found and fixed six items. The rail drew **Home ungated** while every other destination was permission-filtered — an exemption that is exactly the judgement belonging to the permission set, so it is now filtered like the rest and an empty grant set yields an empty rail. Three controls did nothing when clicked: the notification bell, the tenant switcher, and the tenant user's "Choose a scenario" call to action, which was a `<button>` that navigated nowhere; the first two now state why in a toast, and the third is a link to `/sessions`. The greeting split the display name on a space and addressed the tenant administrator as "Dr". The brand lockup overflowed the 72px collapsed rail, spilling across the content — a compact horizontal variant was added, with the wordmark hidden at that width, which is also the second caller that justified reintroducing the variant removed in the previous task. An unreviewed session rendered a bare em-dash in the score column, which a screen reader announces as punctuation or skips; the figure is now absent and the meta line carries "awaiting review".

Verification: **1,569 package tests and 74 app tests passed**, both workspaces typecheck, and `next build` prerenders 20 routes. The full sign-in flow was driven through the DevTools protocol against the production build for all three roles in light and dark: each signed in with the real form, landed on its own dashboard with the expected rail, opened the account menu and the change-password dialog, navigated to a placeholder page, collapsed the rail, opened the drawer at 430px, and signed out back to `/login`. Screenshots: [platform admin](images/ai-evaluator-console-platform.png), [tenant admin, dark](images/ai-evaluator-console-tenant-admin-dark.png), [tenant user](images/ai-evaluator-console-tenant-user.png), [account menu](images/ai-evaluator-console-account-menu.png), [change password](images/ai-evaluator-console-change-password.png), [collapsed rail](images/ai-evaluator-console-collapsed.png), [narrow drawer](images/ai-evaluator-console-narrow.png). A navigation test asserts every menu item is gated on a permission its own role actually holds, so the table and the catalogue cannot drift; the stylesheet test now covers three app stylesheets and still forbids colour literals and `z-index`.

Limitations: there is no authentication, session integrity, CSRF protection or rate limiting to review, because there is nothing yet to protect — the demo cookie is a preference, not a credential. The rail's collapsed state resets on reload, deliberately: persisting it needs the pre-paint treatment the theme has, or the rail renders at 288px and snaps to 72px after hydration. The bell's count is static and opens nothing, the twelve management screens are placeholders, and no assistive technology, physical device or browser matrix was exercised — the keyboard paths asserted here are jsdom, not a screen reader. The `npm audit` position is unchanged from the previous task: eight build-time advisories in the development toolchain, none reaching the shipped bundle.

## AI Evaluator login page — 2026-09-21

Added `platform/ui/apps/web` (`@pms/web`, Next.js 15.5.25 App Router, React 19) as the second member of the existing `platform/ui` npm workspace, containing `/login`, `/forgot-password`, a `/` redirect and the favicon. The screens are built from `@pms/ui`: `EmailField`, `PasswordField`, `Checkbox`, `Button`, `Notice`, `Badge`, `ThemeSwitcher`, `ThemeProvider`, `themeScript`, `isEmailLike`, `currentYear`, the shared icons and every design token. Only two stylesheets are new — `brand.css` (the AI Evaluator identity) and `auth.css` (the split-screen) — because `packages/ui/src/styles/shell.css` states that the auth split-screen belongs to the consuming app. The package itself was not modified; its 1,565 tests are unchanged and still pass.

**Sign-in authenticates nobody, by request.** There is no HTTP call, token, cookie or storage write on either screen: validation is local through the field's own `isEmailLike`, the pending state is a 700 ms timer, and both screens end in a notice stating that no server was reached and, on the reset screen, that no mail was sent. That wording is deliberate — the API verifies OIDC bearer tokens (`pms_api/security/identity.py`) and exposes no password endpoint, so a success message here would describe a session that does not exist and an inbox that will never receive anything. No API, database, schema or worker code was touched.

Review of the new code found and fixed four items. Two disabled social buttons rendered as available because the design system has no `.pms-btn--social:disabled` rule, so they now state why they do nothing instead; `BrandMark`'s `label` prop and `BrandLockup`'s size variants had no caller and were removed rather than kept as speculative API; the brand glyph's spark overlapped the tick's stroke and merged into one shape at small sizes, so the geometry was separated and the favicon updated with it; and the sign-in screens carried no response headers, so `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, a camera/microphone/geolocation/payment `Permissions-Policy` and `same-origin` COOP were added with `poweredByHeader` off, verified live against the production server. "Keep me signed in" defaults to off. No `Content-Security-Policy` was added: a useful one must allow the pre-paint theme script through a per-request nonce, which belongs with the sign-in work rather than being faked with `'unsafe-inline'`.

Verification: **1,565 package tests and 24 app tests passed**, both workspaces typecheck, and `next build` prerenders all five routes. The dev and production servers answered `/login`, `/forgot-password`, `/` (307 → `/login`) and `/icon.svg` with 200, and the compiled stylesheet contains the app rules, the package rules and all three palettes. Screens were captured from the production build through the DevTools protocol at 1440, 760 and 390 px and in light, dark and ledger: [light](images/ai-evaluator-login-light.png), [dark](images/ai-evaluator-login-dark.png), [ledger](images/ai-evaluator-login-ledger.png), [narrow](images/ai-evaluator-login-narrow.png), [field errors](images/ai-evaluator-login-errors.png). A stylesheet test enforces that the app CSS states no colour literal and no `z-index`, and that no class the app emits is unstyled in either the app or the package; a second test pins the favicon's geometry to the component's, and a third pins the response headers.

Limitations: no real authentication, session, CSRF or rate limiting exists to review yet, and `/login` is currently a static prerender served with a long `s-maxage`, which must be revisited when the route becomes session-dependent. Screenshots came from headless Edge with an emulated `prefers-color-scheme`; no assistive technology, physical device, browser matrix or contrast instrument was run, and the palettes' own contrast guarantees come from the package's existing tests rather than a new measurement. Google and Microsoft are presentation only. `npm audit` reports 8 advisories in the workspace's development toolchain — six pre-existing in vite/vitest/esbuild, plus `postcss` reached through `next`; all are build-time, none reach the shipped bundle. An `overrides` entry deduping `next`'s pinned `postcss@8.4.31` to the fixed 8.5.28 already in the tree was tried in both the blanket and `next`-scoped form and npm applied neither — `npm explain postcss` still reports `postcss@"8.4.31" from next@15.5.25` — so it was reverted rather than forced; the fix is a Next upgrade. `npm audit fix --force` is not the answer either: it installs `next@16` and `vitest@5`, both breaking, to resolve build-time-only findings.

## Authorized 25-question live audio baseline - 2026-09-20

The user explicitly requested an uninterrupted live online audio interview and reusable scripts. Added [the simulation suite](simulations/alex-cardiology/README.md), with production desktop/PMS calls, generated spoken input, unchanged retry/limit rules, incremental results, offline grading and a new timestamped folder per run. The saved patient selection changes through normal authorization to Alex's English chest-discomfort case; only owned services stop afterward. Credentials are not exported.

Actual cloud evidence: **25 attempts, 24 audio inputs admitted, 18 exact normalized transcripts, 5 correct answers, 13 daily-limit rejections, 6 speech retry exhaustions and 1 preflight failure; 60 speech retries**. Start/end quota counters explain the LLM admission failures: 83,968 to 94,208 reserved tokens; the next 2,048 reservation would exceed 96,000. Full [findings and evidence](simulations/alex-cardiology/findings-2026-09-20.md) distinguish new errors from pre-existing database history and untested answer correctness.

Final review corrected the evidence classifier so an earlier recovered speech error cannot hide the final LLM quota failure. Five offline reviewer tests and Ruff lint/format pass. Batch help and a separate native screenshot self-test passed; the actual run's screenshots were unavailable, and its exact UI strings/events are retained. Physical microphone, acoustics/VAD, provider throttle details and the precise failed readiness provider remain unverified. Application business/API/database suites were not rerun because application code/schema are unchanged. No production fix, quota increase or second cloud run was performed.


## Desktop camera recording — 2026-09-20

Added an explicit laptop camera checkbox/preview with private, quota-bounded year/month/day/time recording folders. Capture/encoding runs at low priority outside Tk and conversation workers, with one encoding thread, at most 640×480/10 FPS recording and a latest-frame 5 FPS preview. Files are finalized in one-minute Matroska segments; uncheck, new conversation, setup and close stop capture. No PMS runtime/schema, provider or Pi transport behavior changed.

Two reviews covered storage ACLs, links, quota/concurrent writer bounds, file finalization, failure reporting, process shutdown and UI sizing. Fixed explicit Windows subfolder ACL inheritance, shutdown re-entry, a segment double-close path and preview/worker-exit races. Native generated-frame recordings decode correctly; window Back/Close and minimum-size layout pass. Short synthetic video + resident speech measurements showed no median TTS slowdown in the tested samples, with about 75 MiB worker memory and 5–12% of one CPU core. The final run measured 0.234 seconds median synthesis both before and during video; native saved-file ACLs contained only current-account/SYSTEM access. Physical camera capture, ASR/LLM concurrency, Pi/Wi-Fi and sustained hardware performance remain unverified. See [complete evidence and limits](desktop-video-review.md).

Final verification: **157 desktop tests passed, zero skips**, including 15 video regressions and four opt-in installed-voice checks. Native window lifecycle/layout, desktop and API lint/format/types, dependency-lock check and desktop wheel/source builds passed. API business/database tests were not run for this desktop-only change; no database or live cloud was contacted.

## One-click local stack launcher — 2026-09-19

Automatic GPU correction: the launcher had explicitly set Whisper CPU despite working CUDA. Removed the forced CPU choice and introduced an audio-environment probe for compatible CUDA hardware/runtime. Defaults now choose CUDA when usable, otherwise report CPU selection; explicit CPU/CUDA flags remain available. Generated audio config, Human-test config, authenticated readiness and duplicate-launch metadata use the same device/index. Probe and service environments consistently remove inherited CUDA remapping. Standalone audio flags retain their explicit behavior.

The 4 GiB shared GPU needs room for both models, so new Qwen starts on small shared GPUs use at most 16 GPU layers through a validated per-launch override; lower explicit limits and separate GPUs are preserved, and no config is rewritten. Models remain resident, owned-process cleanup still precedes retries, existing servers remain untouched and inference is never replayed. Review covered device mismatch rejection, failed probe redaction, CPU fallback, explicit-CUDA failure, duplicate reuse, GPU layer override validation and optional dependencies. A second pass fixed inherited CUDA environment inconsistency and updated stale CPU documentation. Both passes were by the same agent.

Verification: **47 launcher, 163 audio, 20 desktop and 33 local-LLM tests passed**; Ruff/format, audio/PMS mypy and audio/Human-test package builds passed. Native combined startup verified Whisper CUDA and Qwen partial GPU offload together; the existing synthetic English question produced the exact transcript and correct duration answer in JSON and SSE modes. ASR finalization after input was **1.047 s / 0.890 s**, versus the earlier **16.390 s** CPU run of that fixture. GPU memory after inference was **3,103 MiB used / 790 MiB free**, not a measured peak. An actual `start/start-human-test.bat --check` also passed and stopped its owned stack. Automatic no-GPU fallback is covered by mocks; this machine's native check exercised CUDA. No live microphone/Pi/Hindi quality/soak acceptance or full database business-suite rerun is claimed. Details: [GPU audit](start-launcher-audit.md#automatic-gpu-selection-correction).

Five-attempt follow-up: raised the owned audio/video/PMS/Qwen/retention start budget to five per service/session (initial start plus four retries), with 1/2/4/8-second delays and `1/5` through `5/5` messages. Review found that a second launch's wait allowance could expire before all retries finished; it now scales with the full attempt budget. Regressions verify success on attempt five, clean exhaustion without a sixth attempt, backoff, lifetime recovery limits and duplicate wait coverage for default/extended model startup. **32 launcher tests and 20 desktop tests passed**; Human-test/start and API Ruff/format plus PMS mypy passed. Permanent configuration failures still stop immediately, healthy services stop retrying, and failed cleanup blocks another process. This follow-up used local unit tests; native five-failure model startup and database integration were not rerun because no schema/API business behavior changed.

Robustness follow-up completed: the user's abrupt log corresponded to launcher PID 16964 being stopped during the preceding Python cleanup; a clean cold startup then passed. Added bounded startup/recovery budgets (initially three starts per owned service, now five as recorded above), readiness supervision, safe child-error classification, exit codes, named repair guidance, and private rotating operational logs. Retry/recovery never replays inference requests or migrations and never restarts an independently owned service. The old owned process group must be confirmed stopped before a replacement model loads.

Two follow-up review passes fixed cleanup error masking, shutdown resource release, health monitoring of the private database, cancellation while recovering, desktop-crash exit reporting, and failure-detail redaction. **29 launcher/supervisor tests and 20 desktop tests passed**; Ruff/format, PMS mypy and Human-test builds passed. In the actual batch, deliberately killing its audio listener triggered recovery in **28.618 seconds** while Qwen, PMS, video and database PIDs stayed unchanged; the desktop remained open and a subsequent PMS/Qwen patient answer succeeded. Repeated launch, conflict rejection and owned-only cleanup also passed. Logs passed a scan for configured secrets/sample question-answer content and an ACL check for current-account/SYSTEM access only. All test-owned listeners were closed. Both passes were by the same agent; no soak, cloud or hardware acceptance claim is made. Details: [launcher audit robustness section](start-launcher-audit.md#robustness-follow-up-retries-diagnostics-and-ongoing-supervision).

Added `start/start-human-test.bat`, a small entry point into the shared Human-test demo supervisor. It starts/reuses the private PostgreSQL instance, selected Qwen and Whisper models, audio/video/PMS APIs and retention worker, verifies patient access, then opens one desktop window. It preserves the existing model configuration and saved patient setup.

Review 1 covered Windows quoting and exit codes, startup order, authentication/model checks, private credentials, file locks and process ownership. Added independent video credentials/storage, verified database directory/schema on reuse, singleton retention, named readiness waits and early child-failure detection. No existing listener is killed to free a port, and reused databases are not migrated beneath another owner.

Review 2 covered simultaneous launches, incomplete startup, stale owner status, recording availability, bounded responses, shutdown and package contents. Fixed stopped-owner detection, required working audio recording storage, bounded health response size/time, and matched the duplicate wait allowance to configurable model startup. Both review passes were by the same agent.

Verification: **15 launcher regressions and 20 desktop tests passed**; Ruff/format and PMS mypy (49 sources) passed. Actual batch cold startup succeeded from `C:\Windows\Temp`. A separately started Qwen server was reused; concurrent and repeated batch launches kept listener PIDs unchanged and opened exactly one Human-test window. A real authenticated PMS request returned Alex's expected name. Closing the GUI stopped owned services while preserving independent Qwen. An incompatible audio HTTP listener caused exit code 1 and safe cleanup without stopping the conflicting listener or Qwen. All test-owned processes were subsequently closed and demo listening ports verified empty. Human-test wheel/sdist built; required launcher helpers are in the source distribution and private runtime assets are excluded.

No API business/schema or model/processing algorithm changed, so the full database/API suite was not repeated for this launcher change. Native verification used normal startup against the isolated demo; no destructive application-database test, live cloud, Pi or microphone/camera acceptance was performed. Details and the audit table: [launcher audit](start-launcher-audit.md). Evidence: `.test_artifacts/start-launcher/`.

## Review 1 â€” security, authorization and state transitions

Status: complete. All listed fixes are applied. Seventeen security, API, worker, migration and media tests passed before the second-pass retention regression exposed its separate finding. Ruff and mypy passed.

| Finding | Required fix and verification |
|---|---|
| Rekognition reconciliation could create work after a lost response, including after cancellation | Never issue a new Rekognition start call to discover an unknown job; require provider-verified job resolution; test zero submissions during reconciliation |
| External-I/O boundaries could reuse stale ORM organization/membership state | Refresh authorization state after I/O and before finalization; include active connection/version in effective configuration; exercise revocation/change behavior |
| Device-preferred Hindi could still select an English default voice, and WAV output could contain raw PCM | Use compatible English/Hindi defaults, validate output formats, wrap PCM in WAV; test real WAV headers and locale parameters |
| Shared playback media could be removed before its owning source run expired | Mark shared manifest references and delete only owned objects; enforce source expiry and test standalone playback |
| Storage reads could exceed the limit when an object changes between metadata and read | Bound actual reads, not just metadata; close per-operation resources on application/worker shutdown |
| Connection/profile lists lacked continuation and public enrollment lacked an application rate bound | Add stable bounded pagination and bounded per-process request rate controls; document ingress limits for multiple replicas |
| Credential/identity error boundaries and historical department scope needed broader coverage | Test wrong issuer/audience/expiry, AAD tampering, media revocation, department reassignment and cross-organization access |

## Review 2 â€” resilience, migrations and delivery

Status: complete. All findings were fixed and verified. The final full suite passed 21 tests; the subsequent connection-validation/activation regression also passed.

| Finding | Fix / verification |
|---|---|
| Retention assigned Python `None` to JSONB, producing JSON null and failing the database result-object constraint | Map JSONB with `none_as_null=True`; prove redaction, cleanup, then deletion under the restricted retention role |
| Current Uvicorn creates its own Proactor loop on Windows, overriding the event-loop policy | Supply an explicit Windows selector loop factory; verify the real HTTP server and both worker CLIs |
| Azure Entra speech synthesis needs the resource-bound token format, distinct from fast-transcription bearer auth | Require resource endpoint/ID for Entra connections, construct the correct speech token and test request headers plus escaped Hindi SSML with mocked HTTP |
| Legacy secret references have no encrypted payload after baseline adoption | Reject use with a clear credential-migration error; require replacement through encrypted connection APIs |
| Package/deployment artifacts needed migration-resource and startup checks | Include migrations and signature in wheels, limit source-distribution contents, normalize text files, and verify startup/grant documentation |
| Upload mutation and cancellation needed checks across actual media finalization and worker claims | Verify real WAV finalization, content replacement rejection, cancellation fencing and shared playback cleanup |


Second-pass regression also caught service-generated device activity being labeled as device-uploaded activity without a source event ID. Service events now retain system attribution plus the initiating device/role, and referenced rows are flushed before inserting their activity events. The actual device event endpoint keeps device attribution and supplied deduplication IDs.

Connection access-check failures now persist an invalid per-operation validation result, preventing an older successful check from remaining authoritative. SDK error payloads remain excluded from responses and audit details; a regression simulates timeout and verifies invalidation.

Connection activation changes clear operation validation, requiring fresh checks before resumed dispatch.

## Evidence after Review 2

Full suite: **21 passed**, PostgreSQL 17, real local media inspection, mocked cloud adapters. Follow-up validation/activation regression: **1 passed**. Unicode Hindi unit/provider checks: **7 passed**. Ruff lint/format, mypy, dependency lock check, source/wheel build, packaged-resource checks and real Windows API/worker startup checks passed. Two upstream TestClient deprecation warnings remain; they do not affect the test results.

Live external integrations remain deliberately disabled and untested, as requested. Docker is not installed on this workstation, so its deployment files and CI workflow are supplied but were not executed here. No production deployment or user-facing notification was sent.

## Review 3 â€” additional requested review

Status: complete on 2026-09-17. All three confirmed implementation findings are fixed and verified.

| Finding | Fix / verification |
|---|---|
| Already-redacted, unresolved runs could occupy the entire retention batch indefinitely, delaying redaction and deletion of later expired records | Select only records needing redaction or eligible for deletion, with stable ordering and locked bounded batches. A regression retains 101 unresolved records while redacting a later expired request/result and deleting a later cleaned record under the restricted retention role. |
| Profile section capture settings were not included in the policy used for admission, quota reservation and upload inspection | Apply audio duration and video duration/dimensions/frame-rate limits to effective policy; clamp resolved device settings to current policy caps. Test oversized run rejection, default reservation, real WAV upload rejection and immutable revision/run snapshots when organization caps tighten. |
| AWS SDK retry configuration allowed a second transport attempt after a potentially billable request timed out | Set one total attempt for processing clients. A real Botocore client with a simulated transport timeout made two attempts before the fix; the regression requires one, even when the environment requests more retries. No AWS endpoint is contacted. |

The retry distinction was checked against the [official Botocore configuration reference](https://docs.aws.amazon.com/botocore/latest/reference/config.html). Recovery remains the durable worker's responsibility.

Enrollment already rejects an inactive department at token exchange. Added coverage verifies rejection without consuming the token, successful enrollment after reactivation, and rejection of token reuse. The initial test's HTTP expectation was corrected to the existing 422 contract; this was not an enrollment implementation defect.

The broader package lint check also found an unformatted device probe script outside the earlier source/test checks; its formatting/imports are corrected. Review documentation is normalized to UTF-8.

Final additional-review verification: **25 tests passed** against PostgreSQL 17 with mocked external transports, including real ffprobe media checks. Four focused regressions passed before the full run. Ruff lint/format passed for the whole package (47 Python files), mypy passed for 34 source files, and the dependency lock check passed. Source distribution and wheel builds succeeded; wheel imports, packaged migrations/role catalog/baseline signature, and exact inclusion of all three implementation fixes were verified. Two existing upstream TestClient deprecation warnings remain. Test databases and roles were removed, and the dedicated local PostgreSQL instance was stopped. Live integrations, hosted deployment and Docker execution remain deferred.

## Review 4: database and API end to end

Status: complete on 2026-09-17. Confirmed database/API findings are fixed and verified locally.

| Finding | Fix / verification |
|---|---|
| Connection activation changed validation state without advancing the database configuration version, allowing a stale validation response after deactivation/reactivation | Migration `0004_runtime_guards` includes activation in versioning and validation invalidation. Regression uses direct SQL changes and a simulated in-flight validation response. |
| The language migration left a new trigger function executable by PUBLIC | The new migration revokes PUBLIC execution. Check the ACLs of every application function; normal API language selection still works through its attached trigger. |
| Human-triggered processing and worker dispatch could continue for a revoked device; organization paths were not explicitly checked for device-authenticated run requests | Require an enrolled device with an unrevoked credential for new processing, cancel pending work after revocation, and reject mismatched organization paths. Verify successful recovery after enrollment. |
| Completed history could fill all 50 polling entries and hide new device work | Return actionable work/playback first, then recent completed results; include cloud capture requests awaiting upload. Test more than 50 completed runs followed by a pending run. An actual-media regression also reproduces missing cloud capture work before the fix, then verifies device discovery/upload and human-upload paths. |
| Predictable synthesis format/voice/text errors could be discovered after recording submission intent | Share pure validation between profiles, run admission, worker dispatch and adapters. Invalid queued requests fail while still `not_submitted`, without a provider call. |
| Automatic expiry/cancellation lacked the operational events recorded for other run transitions | Record these transitions in the same transaction, with bounded locked playback-expiry batches and original organization/department context. |
| The API grant script depended on a file outside the API distribution and committed base grants before granting migration-table access | Supply a self-contained, atomic grant bundle checked against the canonical database script. API fixtures now execute this actual deployment script instead of reproducing grants in Python. |

| Explicit null values for required connection settings and enabled providers could raise internal errors during PATCH | Reject null with HTTP 422 before mutation; verify required organization/profile settings also reject it and preserve configuration versions. |
| Database adoption re-encoded URL query spaces for libpq, while runtime connections discarded configured PostgreSQL options | Use SQLAlchemy URL parsing for adoption and preserve runtime options while enforcing UTC and timeouts. Verify adoption, migrations and runtime connections using an unprivileged schema-owner role supplied through connection options. |

| Backup/restore tests need a client compatible with PostgreSQL 17, while the default Ubuntu runner includes version 16 | CI explicitly installs PostgreSQL 17 clients from the official signed repository and selects their psql path. Workflow execution remains deferred on this workstation. |

The four initial boundary regressions failed against the earlier implementation before fixes. The standalone database verifier passed **92 operations**, field/type/nullability and role-catalog comparisons, constraint checks, concurrent administrator protection, runtime privilege checks, and a complete backup/restore with all twelve tables populated under an unprivileged schema owner.

Additional checks cover baseline adoption and every migration as an unprivileged schema owner, plus backup/restore of the current schema, encrypted credentials and Hindi preference followed by HTTP API readiness and authorized reads from the restored database. Live OIDC/AWS/Azure resources remain outside this local verification.

CI client selection follows the [GitHub runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md) and [official PostgreSQL Ubuntu repository instructions](https://www.postgresql.org/download/linux/ubuntu/).

Final end-to-end verification: **33 tests passed** against PostgreSQL 17. The final cloud-capture polling refinement was then verified with **2 passing targeted tests**, covering device discovery, real WAV upload/finalization, human upload, content-replacement rejection and polling across a completed-work backlog. The full suite also covers current-head backup/restore followed by API reads, unprivileged baseline adoption/migrations, actual deployment grants, tenant/role boundaries, encrypted credentials, languages, telemetry/activity, processing, worker recovery and retention.

The standalone database verifier passed **92 operations**, including all-table backup/restore and concurrent administrator safeguards. Ruff lint/format passed for all **50 Python files**, mypy passed for **35 source files**, and the dependency lock check passed. Source distribution and wheel builds passed; wheel imports, migration `0004_runtime_guards`, role catalog, baseline signature, exact reviewed source inclusion and the standalone atomic grant bundle were verified. Real Windows HTTP startup/readiness/authentication plus processing and retention worker CLI checks passed at schema head 0004. Two upstream TestClient deprecation warnings remain.

Disposable databases and roles were removed, and the isolated PostgreSQL test instance was stopped. Live OIDC/AWS/Azure integration, hosted deployment, Docker/CI execution and Raspberry Pi hardware checks remain deferred. Existing API databases must apply `pms-admin migrate` to reach `0004_runtime_guards` before starting this version; the frozen SQL baseline remains unchanged.

## Subscription extension review

Status: complete on 2026-09-17. Database head `0005_subscriptions`; thirteen tables / 241 columns. Confirmed findings are fixed and locally verified.

Review covers required active-plan selection, exact INR/USD price representation, platform-only plan administration/assignment, tenant summary access, migration backfill without removing existing records, reserved invitations, active device/membership counting, reactivation/resend/admin-assignment paths, lower limits/downgrades, direct-SQL/concurrent capacity enforcement, runtime grants, activity events and packaged migration delivery. Caps are configurable provisional defaults and billing period remains unspecified pending user confirmation; external billing/integration is outside this extension.

The first review found that existing-organization backfill queued deferred administrator-coverage events before subsequent ALTER TABLE statements. Migration 0005 now explicitly drains those checks before altering nullability/defaults and restores deferred semantics afterward. The adoption regression includes an existing organization with eleven active devices to exercise this path and grandfathered capacity. Fresh-database quota/assignment tests already passed. A test expectation was corrected from 403 to the existing 404 tenant-concealment contract; no authorization behavior was weakened. The concurrency regression additionally requires an observed PostgreSQL lock wait before releasing the winner's uncommitted last-slot insert.

The second pass strengthens commercial audit evidence by recording exact before/after price, currency and limit edits, and verifies that an upgrade immediately restores additional usable device capacity. Runtime mutation grants remain limited to UPDATE on the two seeded plan records; billing and payment behavior is not introduced.

Final subscription verification: **37 tests passed** against PostgreSQL 17, including the amended audit/upgrade assertions and observed concurrent SQL lock wait. Three focused follow-up tests passed before the full run. The suite covers required plan selection, catalog/admin authorization, exact price serialization and change history, invitation reservations/expiry/resend/acceptance, membership and device reactivation, administrator assignment, per-organization capacity, upgrades/downgrades, limit edits, unprivileged migration/backfill and current-head backup/restore with API reads. Existing authentication, encrypted credentials, languages, media, worker and retention regressions also passed.

Ruff lint/format passed for **53 Python files** and mypy for **36 source files**. Dependency lock verification, source/wheel builds, exact packaged implementation/migration/grant checks, and real Windows API/worker startup checks passed. The isolated smoke database was verified at migration 0005 with **13 tables / 241 columns**. Disposable databases and roles were removed and the isolated PostgreSQL instance was stopped. Two upstream TestClient deprecation warnings remain; external integrations, hosted deployment and Docker/CI execution remain deferred.

Deployment: apply `pms-admin migrate`, reapply `platform/api/deploy/grant-runtime-access.sql` as schema owner, and then start the updated API/workers. Organization-creation clients must supply `subscription_plan_id`. Plan caps remain configurable provisional defaults and billing period remains unspecified; [the subscription contract](../platform/db/subscriptions.md) records these assumptions and the exact counting rules.

## Confirmed limits and repository guidance

The user confirmed Standard at 200 users/1 device and Advanced at 500 users/3 devices. Prices remain INR 350,000/500,000; billing period remains unspecified. Root AGENTS.md now gives concise security, migration, review and testing instructions.

First review: applying lower device defaults through the ordinary catalog-edit guard would reject existing over-limit organizations. Forward migration 0006 therefore takes the administration lock before the plan table lock and transactionally suspends only that guard while updating untouched capacity pairs. It preserves every record, commercial settings and customized capacity pairs, advances changed versions, and restores the guard before commit. Frozen baseline and earlier migrations are unchanged. Readiness and current contract documentation reference the new head.

Second review: confirmed that fresh databases expose the requested limits, existing commercial edits and custom capacity pairs survive upgrades, the database guard is restored, and packaged readiness matches migration 0006. Current documentation no longer describes confirmed caps as provisional. AGENTS.md is 364 words and all its local links resolve. No further implementation findings remain.

Verification: **7 focused PostgreSQL 17 tests passed** (452.70 seconds), covering exact Standard/Advanced API boundaries, existing-database upgrade with customized plans and commercial edits, over-limit record preservation, restored guards, and existing subscription permission/lifecycle/concurrency regressions. Ruff lint/format passed for 54 Python files; mypy passed for 36 source files. Source and wheel builds passed; the wheel contains the exact reviewed migration 0006 and API readiness source. Two existing upstream TestClient warnings remain. The full suite was not rerun for this capacity-default update; its prior 37-test result is recorded above. Live integrations remain deferred.

Deployment: migrate to `0006_confirmed_plan_limits` before starting this API version. No new grants are needed for an installation already at 0005. Customized capacity pairs are preserved; administrator edits can change them deliberately.

## Pi/laptop execution decision documentation (2026-09-17)

Scope: documentation-only update requested by the user. The Pi owns audio/video input and output; local speech transcription runs on a connected Windows CPU laptop using a selected OSS model over local Wi-Fi. Cloud mode goes from Pi to platform API to server-side provider workers without a laptop relay. Model selection, including Whisper large, remains subject to Hindi/English accuracy and CPU latency measurements.

Review: aligned the service plan, API architecture, API README and TODO. Clarified that direct cloud requests preserve platform authorization and server-side provider credentials; existing scoped storage access remains valid. The laptop companion, local streaming, model/configuration extensions and video-display output are explicitly future work. Existing run identity, tenant/department scope, lifecycle/offline restrictions, quotas, retention and no-automatic-fallback behavior remain requirements.

Verification: inspected the five Markdown diffs and checked their relative file links, heading anchors and code-fence balance; all checks passed. Reviewed the final routing, credential and current-versus-planned wording again with no remaining findings. No runtime or database tests were run for this documentation-only change, and no live cloud or Pi/laptop hardware verification was performed. Previous runtime test results above do not verify the proposed Pi/laptop implementation.


## Standalone local audio API review (2026-09-17)

Scope: the user requested an audio-stream receiver under `device`, local CPU transcription with a configurable OSS model, console text output for now, and a future optional text POST receiver. The user explicitly required a model reused across calls. The resulting [audio package](../device/audio-process/README.md) is independent of PMS, its database and cloud providers. No platform runtime/schema changes were made.

Review and fixes:

- A single startup-loaded/warmed Whisper model and cached Silero filter serve every stream. Inference uses one dedicated worker; cancellation does not release native work early or create parallel model calls. Readiness follows successful initialization.
- Local tokens, one stream per token, TLS requirements for non-loopback access, strict PCM/start/control validation, bounded session/chunk/output queues and explicit overload errors protect the standalone installation. Platform tenant/lifecycle/configuration binding remains future integration work.
- Console output is enabled as requested; optional HTTP delivery is disabled until configured. Callback destinations are operator configuration, redirects/proxy inheritance are off, response bodies are not read, and unknown submissions are never blindly retried. This is an in-memory prototype with no durable replay/outbox.
- Final archive inspection with a real local `.env` present found that the source distribution could include it because this standalone package did not inherit the parent ignore rules. Added an explicit source-distribution file allowlist and local credential/cache ignores, rebuilt both archives, and verified they contain no `.env`, models or caches. The final wheel was compared byte-for-byte with the reviewed source. No package was published.
- Review found that Uvicorn WebSocket handshake INFO logs can include query strings despite access logging being disabled. The service suppresses those logs, and a real network regression checks that a rejected URL token is not logged. HTTP client and recognizer detail logs are also suppressed.
- Review found that the inference library can download a missing tokenizer despite its model local-files setting. Startup now requires local model, configuration and tokenizer files before constructing the engine; a missing-tokenizer regression verifies it fails before any model construction. Review also added speech-filter warmup, Hindi Unicode preservation, native output limits, startup failure handling, truncated benchmark-WAV rejection, explicit sender dependency and sender error handling. TestClient mutates header dictionaries; isolated copies corrected the real-transport test fixture.

Verified: **39 tests passed**, including real loopback HTTP/WebSocket transport with a fake recognizer, model reuse across streams, cancellation serialization, slow-inference responsiveness, bounded audio/callback queues and callback no-retry behavior. Ruff lint/format, mypy (9 source files), lock consistency, source distribution and wheel builds passed. Package archives were inspected to exclude models, local credentials and runtime caches. Upstream TestClient/Uvicorn WebSocket deprecation warnings remain.

Review also corrected the queue-time metric to include waiting in the per-stream buffer as well as the shared inference queue; a regression covers the accumulated wait. The native stream timing trials preceded this metric correction, so their raw queue_ms values cover only the shared worker queue. Model provisioning and real inference evidence are recorded below. No PMS/PostgreSQL tests were run for this separate package; no database was opened or migrated. Pi hardware, Wi-Fi/TLS deployment, cloud services and Hindi/mixed-language accuracy remain unverified.

### Real model provisioning and local stream verification

Downloaded the official OpenAI `large-v3` checkpoint (3,087,371,615 bytes) from the publisher's Azure host after the managed network denied Hugging Face. Windows certificate verification remained enabled. Resumable bounded parallel ranges were assembled, and the complete checkpoint matched the publisher SHA-256 `e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb`. Temporary range files were removed after verification.

Converted locally to CTranslate2 INT8 using the upstream Transformers weight mapping, official OpenAI tokenizer asset and CTranslate2 Whisper converter in an isolated tooling environment. Strict weight loading and English/Hindi tokenizer ID/round-trip checks passed. `.models/large-v3/model.bin` is 1,551,326,177 bytes; tokenizer, preprocessor, vocabulary, configuration and a per-file checksum manifest are present. Model files and private `.env` are excluded from package archives.

Real Uvicorn HTTP/WebSocket verification used an 8.55-second synthetic English recording and the actual model. Two streams in each process produced the expected text and console output, with exactly one model construction. Four threads: 15.77-second startup/warmup, 39.17/39.41-second stream completion, 3.23 GB peak process working set. Eight threads: 15.37-second startup/warmup, 39.78/35.71-second completion, 3.23 GB peak. Each stream yielded three speech chunks. This demonstrates functional local transcription and reuse, but not real-time suitability. The four-thread default is retained; there is no automatic model substitution.

Host: Windows, Intel Core Ultra 7 165H, 64 GB installed RAM. The requested 16 GB target, Hindi/mixed-language speech accuracy, Pi hardware and Wi-Fi/TLS deployment were not verified. Evidence and conversion references are retained under ignored `.test_artifacts`; native timing JSON reports identify the earlier queue metric semantics. Verification servers were stopped. The prepared service can be launched from `device/audio-process` with `uv run audio-api serve`.


## Background local audio/text recording review (2026-09-17)

Scope: the user requested local audio and transcript storage without waiting for disk on the transcription path. The standalone receiver now records accepted PCM (including silence) as WAV, final UTF-8 transcript events as JSONL, and a server-generated session manifest. Recording is enabled in the example/generated configuration and this checkout's private settings. Console output remains configurable; the optional callback is still disabled. No platform runtime/schema changes or PMS connections were introduced.

Review and fixes:

- Recording admission uses bounded event/byte budgets and pending-session counts. A dedicated disk thread performs serialization, file writes, cleanup and synchronization independently of the model and WebSocket tasks. `complete` may report `pending`; owner-authenticated recording status distinguishes actual `saved` completion from `incomplete` data.
- Queue overload preserves the already accepted prefix and stops accepting new recording data. Review caught an early failure-state check that would have dropped that queued prefix; regression tests now assert exact retained audio after overflow and disconnect. Genuine disk failures stop subsequent writes, avoiding silent gaps.
- The store defaults to 1 GB, 1,000 sessions and seven days, with a free-space threshold, oldest-finished eviction, active-session protection and reserved metadata space. Review caught quota undercounting of buffered/partially failed writes after another session finalized; per-session reservations now survive recounts and are regression-tested.
- Server-generated UUID paths, a store marker and exclusive process lock protect directory ownership. Unknown contents, hard links, symlinks and Windows reparse points are refused. Retention deletes only verified fixed files within owned session directories. Windows ACLs replace inherited and explicit broad grants; POSIX directory mode is 0700. Files remain local plaintext under filesystem permissions.
- Finalization starts from an incomplete on-disk manifest, closes/syncs files and atomically replaces metadata. Startup recovers unfinished WAV length and partial final JSONL lines and flags size mismatches. Finalization attempts to close every handle even when one close fails. Interrupted recordings retain an incomplete status; recovery cannot reconstruct data lost before flush or exact pre-crash receive counts.
- Storage startup and shutdown have bounded waits. A stalled OS disk call can outlive those waits in its daemon thread, but ASR stays responsive and unfinished recordings never become a false success. Tests check transcript/complete/status delivery while the disk is deliberately blocked, storage unavailability, queue limits, failure finalization, recovery, quota enforcement and owner scope.

Verification: **64 tests passed**, including 24 recording tests, with no skips on this Windows host. Windows ACL, junction and hard-link checks ran against the actual filesystem. Ruff lint/format passed for 20 Python files; mypy passed for 11 source files, and the dependency lock check passed. Existing upstream TestClient/Uvicorn warnings remain. Ruff explicitly excludes runtime recording/model directories so code checks do not traverse protected media.

Real-model comparison: one `large-v3` CPU INT8 model load (21.36-second startup/warmup), four threads, beam one; four paced loopback streams in off/on/on/off recording order. The same 8.55-second synthetic English clip completed in 51.50/51.52 seconds without recording and 53.58/51.22 seconds with recording: means 51.51 versus 52.40 seconds, an observed 0.89-second/1.7% difference. This small sample includes scheduling/thermal variation and does not prove zero recording overhead. Every transcript matched, both saved WAVs matched all original PCM bytes, both JSONL files matched the emitted text, and both pending receipts reached saved without blocking stream completion. The model loaded once across all four streams.

Host: Windows, Intel Core Ultra 7 165H, 64 GB RAM. The model is not real-time with these settings; the 16 GB target, Hindi/mixed-speech accuracy, Pi hardware and Wi-Fi/TLS deployment remain unverified. Evidence is retained under `.test_artifacts/device-audio-recording`; the two synthetic sample recordings remain in the ignored private local store. The verification server was stopped. No PMS/PostgreSQL tests were run, no database was opened or migrated, and no cloud service was contacted for this recording change.

Final review: source/wheel builds passed with real private settings, model files and sample recordings present. Both archives exclude credentials, models, media and caches; all 11 packaged Python source files match the reviewed working files exactly. The source archive also matches the current README, configuration and example settings. All six updated Markdown files passed local-link and code-fence checks. Active private settings enable recording with `large-v3`/four CPU threads and keep the callback disabled. Final authorization, quota, error-state and compatibility review found no remaining implementation blockers within the standalone scope.

## Bounded retries, component fallback and final review (2026-09-17)

Scope: the user requested appropriate retries/fallbacks and a final review. Changes are confined to the standalone audio package, its configuration and documentation. The selected model remains loaded once; PMS, PostgreSQL and cloud integration are unchanged.

Implemented:

- Transient local file creation, positional writes, filesystem synchronization and atomic manifest replacement have at most three attempts per operation by default, with exponential backoff and 20% jitter. Disk work stays on its dedicated thread. Permanent permission, capacity, unsafe-path and validation failures are not retried. Exclusive creation never overwrites an existing file.
- The buffered file writer retries raw data at its original offset, handles short writes, and latches a file off after exhaustion so a later flush/close cannot duplicate an uncertain partial prefix. Storage reservations are charged once and preserve the existing limits.
- Audio and transcript failures are independent. An established session can continue transcript-only or audio-only recording under the same queue/quota/privacy limits. Both failures fall back to the authenticated stream and configured console. No fallback directory, destination, model or cloud provider is silently selected.
- Callback connection/pool failures before submission can retry with the same event ID and JSON body, within one total delivery deadline. Console output occurs once. HTTP rejections and unknown submissions are not replayed; the future receiver's reconciliation/idempotency contract remains required.
- Receipts include fallback mode, component completeness and explicit finalization. An incomplete session may still be draining usable data; clients wait for `finalized=true` before treating component flags as final. Retry counters and delivery attempt counts provide diagnostics without media or credentials.

Review findings and fixes:

1. Retrying a buffered append after a partial failure could duplicate audio/text. Fixed-offset raw writes and a permanent failure latch address this; injected partial/short writes and exhausted retries verify exact bytes and bounded attempts.
2. A response-cleanup exception with a connection-error type could otherwise be mistaken for a pre-submission failure. The dispatcher now tracks receipt of response headers and never retries that case; a dedicated accepted-response regression verifies one POST.
3. Fallback status alone did not say whether its remaining writes had drained. Explicit finalization and per-component flags distinguish in-progress fallback from persisted results. Restart preserves a verified completed transcript when only audio failed.
4. Full-suite testing exposed two test-harness races: TestClient teardown cancelled an ASGI disconnect before cleanup finished, and a manual retention test competed with periodic disk maintenance. Tests now synchronize disconnect cleanup and isolate manual maintenance; a separate periodic-flush regression verifies continued text capture after an audio flush fails.
5. Isolating maintenance exposed a real idle shutdown delay: the recorder did not wake its sleeping worker when all sessions were already finished. Shutdown now signals it immediately. A long-flush-interval regression proves idle shutdown completes within one second; blocked native-I/O shutdown remains bounded separately.

Final verification: **89 tests passed, no skips**, in 22.67 seconds. Four focused review regressions passed before the final run. The full suite includes 25 new retry/fallback/shutdown regressions plus existing model-reuse, protocol, owner-scope, quota, retention, recovery, actual Windows ACL/junction/hard-link and loopback transport checks. Ruff lint/format passed for 22 Python files, mypy for 12 source files, and dependency lock/build checks passed. Eight existing upstream TestClient/Uvicorn warnings remain.

The final wheel matches all 12 reviewed source modules; the source archive also matches the current tests, README and configuration. Both archives exclude credentials, model weights, recordings and caches. Active private settings enable three-attempt recording retries and retain `large-v3`/four threads; the callback remains unconfigured. Local verification evidence is under ignored `.test_artifacts/device-audio-retries`. A final pass checked authorization, privacy, queue/quota accounting, idempotency, cancellation, compatibility and documentation with no remaining findings in this scope.

All provider calls were mocked or unconfigured; no database was opened and no PMS/PostgreSQL tests were run. Native Whisper latency measurements above were not repeated for this retry/fallback change and are identified as historical in the package README. Pi hardware, Wi-Fi/TLS deployment, actual 16 GB performance and Hindi/mixed-speech accuracy remain separate verification work.


## Standalone video receive-and-record API review (2026-09-18)

Scope confirmed on 2026-09-17: implement a separate `device/video-process` service, then narrowed explicitly to receive/save only. No detection, inference, live image extraction, decoding or video re-encoding is enabled. Compressed timestamped baseline JPEGs are copied into playable MJPEG Matroska segments. A separate offline command extracts original JPEG packets from completed recordings while the API is stopped. There is no PMS, database, audio-service or cloud integration, and no model to download or initialize.

Review passes and fixes:

- Authentication uses separate client bearer tokens, owner-scoped receipt lookups, native-client Origin/query restrictions and TLS for non-loopback connections. The CLI distrusts proxy headers and suppresses request URL logs. Local tokens/correlation IDs do not impersonate platform device or tenant identities.
- Input checks bound headers, encoded JPEG sizes, dimensions, frame rate, sequence/timestamps, capture duration and wall-clock lifetime without decoding images. The protocol is explicitly JPEG frames, not a generic H.264/MP4/RTSP receiver. JPEG entropy is not fully validated during recording; stored-byte completion is distinct from image analysis/decodability.
- The single background writer has byte/item limits including in-flight work and reserved finish slots. Pending sessions continue to occupy capacity after a client timeout, preventing repeated timed-out requests from bypassing the limit. Frame acknowledgments are pending until durable segment/manifest completion; cancellation does not cancel native disk work. Idle shutdown wakes the worker immediately; a stalled write cannot delay the caller indefinitely.
- Safe local writes use three bounded transient attempts with fixed-path immutable content, fsync and atomic replacement. A test injects failure after a successful rename and verifies exact output without duplicate segments. Permanent errors do not trigger blind retries. Quota rejection now flushes already reserved accepted frames before rejecting the next frame; real disk failure preserves the committed prefix and marks the session incomplete. Final manifest failure never reports saved completion.
- The private store enforces byte/count/age limits, free-space checks and active-session protection. Review removed repeated summation from the retention loop to avoid quadratic quota accounting at the session limit. Actual Windows ACL, hard-link, junction and competing writer-lock tests passed. Media paths are generated UUIDs and bounded fixed filenames; unknown contents are refused.
- Restart review fixed two crash edges: empty/partial initial sessions that never accepted video are safely removed; interrupted manifest replacement is followed by a fresh file recount, avoiding a stat of the removed temporary manifest. Recovery preserves existing failure reasons and never promotes interrupted recordings to saved. These fixes have focused regressions.
- Offline extraction verifies media hashes, uses private new output directories, enforces frame/byte limits, and holds the exclusive store lock. Actual PyAV packet comparisons prove original JPEG byte preservation; native decoding verifies generated segments are playable. Extraction is not scheduled or invoked from the live API, and extracted files require their own operator-managed retention.
- Real loopback Uvicorn HTTP/WebSocket tests exercise bearer authentication, save receipts, disk recording and the shipped file sender in a separate Python process. Review isolated mutable TestClient header fixtures after they contaminated a native handshake; the corrected native checks passed.

Final verification: **56 tests passed, no skips, in 13.21 seconds**. Ruff lint and formatting passed for 19 Python files; mypy passed for 10 source modules. Dependency lock verification and source/wheel builds passed. Six upstream Starlette/TestClient/Uvicorn/websockets deprecation warning instances remain. The final archives match the reviewed source modules, tests, sender, README, configuration and lock byte for byte; private `.env`, recordings, environments and caches are excluded. Package verification evidence is in ignored `.test_artifacts/device-video/package-check.json`.

Dependencies are installed in the new package's `.venv`, and a private local `.env` was created without printing its generated token. No server was left running. The startup command from `device/video-process` is `uv run video-api serve`. The service plan, architecture, platform README, package README and TODO reflect the receive/save-only decision and deferred hardware/platform integration.

Final inspection covered authorization, privacy, queue/session/quota bounds, retries, crash recovery, offline extraction, packaging and documentation. No remaining confirmed findings were identified within this scope. These local tests do not establish zero recording overhead or sustained camera performance. Pi camera/display hardware, Wi-Fi/TLS deployment, concurrent Whisper/video latency and the actual 16 GB laptop target remain unverified. No platform runtime/schema or audio implementation was changed; PMS/PostgreSQL tests were not run and no database was opened. No live cloud integration was attempted.


## TCP transport assessment and bounded video sender (2026-09-18)

The user requested advice and implementation only if a TCP option improves performance or reliability. Existing binary WebSocket/WSS media connections already use TCP. Reviewed RFC 6455, RFC 9293, Uvicorn settings and websockets client/keepalive documentation. The recorded decision is to retain separate authenticated audio/video connections; no raw TCP listener, new port, receiver wire protocol, live video processing or media format was introduced. See [the transport decision](local-media-transport.md).

A concrete sender bottleneck was confirmed: video transmission waited for each frame receipt before sending the next frame. Added `device_video.sender` and updated the shipped file sender to use separate send/receive tasks with a default four-frame acknowledgment window (configurable 1-16). Only bounded pending metadata is retained, alongside one current/read-ahead frame and existing transport buffers. The sender validates acknowledgment order/timestamps, matching recording identity, and saved frame count/finalization; pending completion stays pending. Default deadlines bound startup/sends/acks to five seconds, completion to fifteen seconds and capture lag to two seconds. Sibling tasks are cancelled on failure; no automatic replay or new-session retry occurs. Ready receipts are flushed to stdout immediately so a caller can retain the recording ID.

Review checked the distinction between acknowledgment and durability, cancellation of blocked sends even after an acknowledgment, EOF/early-close handling, missing or duplicate acknowledgments, premature/invalid completion, intentional capture gaps, window bounds, late capture and failure cleanup. A specific stalled-send regression ensures receipt arrival cannot disable the send deadline. The video client now ignores environment proxies, matching the existing direct audio sender. The native subprocess sender test succeeds with an explicitly unreachable configured proxy, demonstrating direct loopback connection behavior. Certificates remain verified for WSS. The audio sender already sends/receives concurrently; no audio runtime or model change was warranted.

Controlled comparison used the real local Uvicorn/WebSocket API and disk, 18 generated 1280x720 JPEGs of 191,363 bytes at 15 fps. Two trials each for one/four-frame windows, ordered 1/4/4/1. With no injected delay, mean completion was 1.196 versus 1.211 seconds. With ordered receipt delivery delayed by 150 ms, means were 3.055 versus 1.343 seconds, about 56% less completion time for the bounded concurrent sender. All eight sessions saved all 18 frames and preserved exact compressed JPEG bytes. These are synthetic local tests of receipt delay, not real Wi-Fi/TLS/Pi results or a raw-TCP comparison. Scripts and individual results are in ignored `.test_artifacts/device-video-transport`.

Final verification: **81 tests passed, no skips, in 19.36 seconds**, including 25 new sender cases and the enhanced native transport/subprocess sender test. The initial focused sender/native checks passed before the final suite. Ruff lint/format passed for 21 Python files, mypy for 11 source modules, dependency lock and package builds passed, and wheel/source archives were checked byte for byte against current source, tests, sender, README, configuration and lock. Credentials, recordings, environments and caches remain excluded. Six pre-existing upstream deprecation warning instances remain. Final source/review inspection found no remaining confirmed issues within this change's scope.

Both package READMEs, the service plan, transport decision and TODO reflect the decision and reconnect limits. Servers used for verification were stopped. Audio/PMS runtime tests were not rerun because only the audio README and cross-service documentation changed outside the video package; no database or live cloud was accessed. Actual Pi hardware, Wi-Fi loss/jitter, TLS deployment, concurrent audio/video and the 16 GB target remain unverified. Durable reconnect/resume requires a future bounded local spool and idempotent application-level commit design; replacing WebSocket with raw TCP would not provide it.


## Combined final audio/video implementation review (2026-09-18)

Reviewed both standalone services for authentication and local client scope, privacy, input validation, bounded work/queues/quotas, cancellation, retries, crash recovery, senders, packaging and compatibility. This review retains separate WebSocket/TCP services, laptop-local audio recognition and receive/save-only video. Video frame extraction remains an offline command. No platform/PMS, database, live provider or Pi hardware integration was added.

Confirmed findings and fixes:

1. Audio model loading and shutdown could wait indefinitely on native inference through a non-daemon executor. Added a bounded serial daemon worker, a 180-second model-load deadline and a five-second inference shutdown allowance. Model loading/warmup still occurs once, with serial reuse across streams. Shutdown refuses new work, resolves unfinished requests explicitly, retires the runtime and prevents its restart. Python cannot interrupt an in-flight native call; it may remain until it returns or the process exits. Connection, storage and delivery shutdown have separate bounds, not a promised total process-exit deadline.
2. A blocked console write could hold delivery and process shutdown. Console output now uses its own serial daemon worker and a print deadline. An uncertain print is not replayed; console output is retired until restart while configured HTTP delivery can continue. Existing bounded, pre-submission-only callback retries remain unchanged.
3. Audio setup previously wrote the local token without explicitly restricting file access first. It now applies current-account/SYSTEM permissions on Windows or mode 0600 on POSIX before writing credentials and never overwrites an existing file. Actual Windows tests verify private ACLs and failure without credential writes. The existing local audio settings were atomically replaced with identical bytes and a protected ACL; current-account/SYSTEM-only access was independently verified without printing credentials.
4. A crash before the initial audio manifest could leave an empty/partial session directory that prevented storage startup. Recovery now removes only an empty generated directory or bounded temporary initial manifest when no media exists. Unexpected orphan media remains preserved and initialization fails closed.
5. The audio reference sender lacked start/completion deadlines and could treat a normal close without completion as success. It now bounds connection/start/send/close and finish waits, requires a matching completion, cancels sibling tasks on failure, prints the initial receipt immediately and uses absolute pacing. It never automatically reconnects or replays audio.
6. Cancellation during the final video reply could skip stream-capacity release. Release now runs unconditionally. A second inspection also bounded admitted opening/closing handshakes in both services; regressions prove slots are released on stalled success/error paths. A video protocol docstring was corrected to avoid claiming full JPEG entropy validation in the offline byte-extraction command.

Baseline suites passed with audio 89/video 81 tests. Focused regression runs passed before final verification. The final suites passed **104 audio tests in 33.42 seconds** and **84 video tests in 23.88 seconds**, with **no skips**. This adds 15 audio and three video regression cases. Actual loopback WebSockets, native transport/subprocess senders, Windows filesystem permissions, blocked workers, safe retries, recording integrity, recovery, cancellation and owner scope are covered. Existing upstream Starlette/TestClient/Uvicorn/websockets deprecation warnings remain (eight audio and six video instances).

Ruff lint/format passed for 25 audio and 22 video Python files; mypy passed for 13 audio and 11 video source modules. Both dependency locks and source/wheel builds passed. Final archives were compared byte for byte with all reviewed source modules, tests, senders, README, configuration and lock files. Private credentials, model weights, recordings, environments and caches remain excluded. Archive evidence is under ignored `.test_artifacts/device-media-final-review/package-check.json`.

The installed local CPU INT8 `large-v3` also passed two real loopback synthetic English streams with recording enabled: **one model load**, 20.504-second load/warmup, and 78.293/51.302-second completion for each 8.55-second input. Both saved WAV payloads matched the input exactly and both saved transcript files matched the returned events. Completion initially reported pending storage, then owner-authenticated polling confirmed saved/finalized. Console was disabled and the callback remained unconfigured. Verification used a separate private artifact recording directory and stopped its server afterward. Evidence: `.test_artifacts/device-audio-final-review/verification.json` and its script. Other verification ran concurrently, so these times are functional evidence under background load, not a controlled before/after performance comparison.

The final inspection found no remaining confirmed correctness/security defects within the reviewed local scope. `large-v3` remains far slower than real time here. Actual Hindi/mixed-speech accuracy, sustained concurrent audio/video, Pi camera/microphone/output hardware, real Wi-Fi/TLS behavior and the intended 16 GB laptop remain unverified; this host has 64 GB RAM. Durable reconnect/resume and future tenant/platform authorization are still separate work. No database was opened, PMS/PostgreSQL tests were not run because no platform runtime/schema changed, and no live cloud calls were made.


## Patient interview pilot: review 1 (2026-09-18)

Reviewed the new shared contracts, migration 0007 and runtime grants, platform scenarios/sessions/results/feedback, coordinator authorization/recording, Pi adapters and instructor controls. This review is local implementation evidence; it does not imply real Pi, live OIDC/cloud, 16 GB target or educator verification.

Confirmed and fixed: retention policy key mismatch; cancelled sessions needing one late receipt without terminal-state mutation; bounded UTF-8 journal serialization and recovery of incomplete initial manifests; safe idempotent replacement retry after an uncertain rename; bounded disk-worker shutdown; old warmup work being fenced from replacement sessions; split PCM sample boundaries across network chunks; camera failures/pending receipts being visible rather than claiming successful recording; per-capture video retention only shortening the receiver policy; build context excluding local secrets/weights. Regression tests cover those paths and existing suites were rerun.

## Patient interview pilot: review 2 (2026-09-18)

Fresh review checked organization/department/trainee/device scope, platform-admin isolation, profile/user/case revocation at lease renewal, signed grant pinning and expiry, stale playback suppression, no automatic replay of uncertain turns/playback, immutable scenario facts, manual versioned feedback, quota reservations shared with processing runs, private media ownership/hash checks and terminal-only bulk replay. Reviewed bounded queues/native operations, generic error responses, fixed platform proxy routes, origin/host/TLS checks, direct network clients and model API-key handling. No cloud fallback or live video analysis was introduced.

Final verification: platform **45 passed** against the dedicated disposable PostgreSQL 17 test server, audio **104 passed**, video **85 passed**, training **12 passed**: **246 tests, no skips**. The final platform run includes migrations, grants, backup/restore, quotas, concurrency and tenant/department/role/lifecycle checks. The disposable server was stopped afterward. Real HTTP/WebSocket fixture integration uses the actual video recorder and verifies JPEG byte identity, local WAV/journal output, simulated receipt submission and bulk replay. ASR/dialogue/speaker in this integration are explicit doubles. Actual native small Whisper/Qwen/eSpeak measurements are separate: four synthetic speech samples yielded three expected topics and 3.7-5.9 second end-of-input processing times on a 64 GB Core Ultra 7 165H workstation. Text-input Qwen/eSpeak selected 10/10 topics with warm 1.5-1.9 second generation. A later cold secure-model attempt exceeded 30 seconds; its warm repeat succeeded. Authenticated model endpoint returned 200; unauthenticated returned 401; native Hindi WAV generation passed. Model service and temporary test processes are stopped after verification.

Platform/training/video wheels and source distributions built, with the shared-contract wheel built separately. Archive inspection found no private keys, tokens, environment files, recordings or weights; training static assets/scenario and platform migration 0007 are included. Ruff/type checks passed for platform, training and video; shared contracts passed Ruff/mypy. JavaScript syntax check passed. Docker is unavailable, so image build/run is unverified. Package/native/browser evidence is under ignored `.test_artifacts/training-pilot`; source setup and limitations are in `device/training/README.md`.

Outstanding acceptance: representative human Hindi/English/code-switching accuracy, actual Pi capture and audible playback, Wi-Fi/TLS/acoustic synchronization, the target 16 GB laptop, complete instructor acceptance with deployed OIDC, and clinical educator approval. The current measurements do not establish the proposed 2-3 second response target. These are explicit gates, not passed phases or claimed live verification.


Final review closeout: Chrome loaded the actual instructor page, its JavaScript and controls without runtime errors; Clear access worked. This is a page-load/control smoke check, not full educator or live OIDC acceptance. The browser harness initially selected a Chrome extension target; selecting the actual page fixed the harness. JavaScript syntax, Ruff formatting/lint, mypy, dependency locks and package builds/inspection passed for the changed service projects. Shared contracts passed Ruff/mypy and were rebuilt. No application database, cloud provider or Pi hardware was touched. Both reviews are complete; external acceptance items remain unchecked in TODO.

## Patient Scenario Library documentation review (2026-09-18)

Recorded the agreed feature baseline in [Patient Scenario Library](patient-scenario-library.md), linked it from the pilot/service plan, and tracked subsequent planning as incomplete in TODO. Reviewed the document against the requested patient profiles, clinical history, vital signs, fixed/future generated answers, and reusable manikin assignment. Checked consistency with local/cloud responsibilities, immutable scenario versions and expiring session authorization, separate media APIs, record-only video, physical capability limits, and deferred hardware/clinical/performance acceptance. Final document inspection found no conflict with the pilot boundaries.

Documentation only: no runtime, schema, model, or hardware changes. Runtime and database tests were not rerun; existing test counts above belong to the earlier implementation verification and are not new evidence for these future features.

## Patient Scenario Library phase-plan review (2026-09-18)

Inspected the current shared scenario contract, platform training routes/models/migration, coordinator/dialogue path, instructor UI/proxy, and training tests before drafting the [implementation plan](patient-scenario-implementation-plan.md). The plan reuses existing approval/session/media/feedback functions, preserves immutable documents through a separate draft store, and adds explicit compatibility and readiness work. Scoped the first increment to fixed-state interviews with approved answers and two development fixtures; deferred dynamic physiology, new generative answering, physical effects, and broad management features.

Reviewed phase dependencies, measurable completion criteria, tenant/role and learner-disclosure boundaries, version/hash preservation, publication concurrency, uncertain retries/playback, hardware/performance limitations, and the two final implementation reviews. Added neutral learner labels for legacy cases without changing their approved hashes. This is documentation review only, not completion of the planned implementation reviews. No runtime/database tests were run for this planning-only change; implementation checkboxes remain open.


## Patient Scenario Library database review 1 (2026-09-18)

Scope: database-only migration 0008, ORM mappings/schema readiness, deployment grants and read-only verifier, database tests, and documentation. No new API endpoints, shared clinical schema, UI, or device behavior. The existing disposable PostgreSQL 17.10 cluster at `.test_artifacts/pms-api/data`, loopback port 55441, was verified by `data_directory` before use; test fixtures create/remove uniquely named databases and backend roles. No application database was migrated.

Initial focused verification passed 17 tests (new database cases plus existing training/migration coverage). Review then reproduced two additional defects with failing regressions: explicitly setting an expected draft revision to NULL bypassed the inequality check before the trigger incremented it, and the read-only verifier accepted a removed draft-envelope constraint. Fixed the guard with NULL-safe comparison and required the validated envelope constraint in the verifier. Also redacted the new author fixture's representation so failure diagnostics do not print its synthetic JWT. No live credentials were used in tests.

Reviewed separate immutable snapshots/editable drafts, archived content, same-organization references, original create-request fingerprint semantics, publication provenance and uniqueness, quota serialization, READ COMMITTED restriction, worker/retention exclusion, server timestamps, and future API authentication/audit responsibilities. Added upgrade verification with a retained approved version-1 case and active session, and populated-draft backup/restore coverage. Clinical validation and authenticated atomic publication/audit remain explicit future API obligations; database constraints alone do not establish them.


## Patient Scenario Library database review 2 and verification (2026-09-18)

Fresh final review checked the NULL-safe edit guard and its regression, publication locking/snapshot identity, draft and immutable-case provenance, tenant FKs, archived behavior, quota count/serialization, original request fingerprints, worker/retention/PUBLIC exclusions, verifier failure behavior, ORM field coverage, preserved version-1 cases/sessions, transaction/audit responsibilities, and deployment/packaging documentation. No further blocking findings remain in this database-only scope. Full clinical content validation, authenticated authoring/publication endpoints, user-facing projections, and the UI/runtime remain deferred to the next authorized phase.

Verification: full platform suite **55 passed, no skips**, including isolated PostgreSQL migration/adoption, retained approved case/active-session equality, database constraints, concurrency with observed lock contention, restricted grants, populated-draft backup/restore, and existing API regressions. The two newly added review regressions first failed and then **2 passed** after the fixes; these are part of the same test inventory, not two additional unique tests. The suite reports two existing Starlette/httpx/AnyIO deprecation warnings. Initial focused run was 17 passed. Ruff lint and format passed (59 files), mypy passed (37 source files), dependency lock check passed, and wheel/source distribution builds passed. Final archive inspection verified the exact reviewed migration (including the NULL fix), mappings, schema-head readiness, source SQL/grant/verifier scripts, and tests; no private key/environment artifacts were found. Package hashes are recorded under `.test_artifacts/patient-scenario-db/package-verification.json`.

Mapped/current schema: **16 domain tables, 293 columns**, head `0008_scenario_drafts`. Baseline adoption still validates the frozen SQL signature. New drafts are bounded JSONB storage, not a completed clinical schema or executable version-2 runtime. No application database, live cloud service, or Pi hardware was changed. The dedicated test server had zero remaining pms_test databases/roles and was stopped after verification. Documentation links were checked. Database delivery is complete; proceed to API/shared-contract work only after the user's next instruction.


## Patient Scenario Library API plan review (2026-09-18)

Planning-only inspection checked database draft/provenance rules, current shared version-1 Scenario imports, role catalog/access helpers, create/list/approve/retire routes, session admission/leases/control grants, feedback/rubric parsing, and laptop proxy restrictions. The [API plan](patient-scenario-api-plan.md) reuses the completed schema and existing permissions; org administrators author while scoped operators run sessions. Version-2 publication remains distinct from executable support, with explicit admission/delivery rejection until the runtime is upgraded.

Reviewed draft-versus-publishable validation, exact stored snapshot preservation, original-create fingerprint replay, publication replay including approver/approval fields, org-before-draft locking, transactional audit, learner/private projections including search predicates, old-client listing behavior, and explicit API/UI/runtime boundaries. This is a plan review, not either planned implementation review. No runtime code or database changes and no runtime tests in this turn; all API implementation checkboxes remain open.


## Patient Scenario Library API plan revision 2 review (2026-09-18)

Revised the [API plan](patient-scenario-api-plan.md) with execution order, fixed HTTP/request/replay behavior, draft-versus-publication completeness, field groups, implementation boundaries, per-phase tests, and completion gates. Moved safe reads and runtime-version rejection ahead of version-2 publication. Explicitly excluded diagnostic internal codes/tags from learner views and search predicates; a neutral title alone would not prevent that disclosure. Kept role scope, exact stored snapshots, original request fingerprints, approval-aware publication replay, quota/lifecycle checks, and atomic audit aligned with database migration 0008. Automatic clinical-schema conversion, UI, and runtime work remain deferred.

Planning only: no API/runtime/database implementation or runtime tests. The revised eight phases supersede earlier phase ordering, and all implementation checkboxes remain open. Inspected document structure and local links; this is a plan review, not either future implementation review.


## Patient Scenario Library API review 1 (2026-09-18)

Reviewed version-aware contracts without rebinding the version-1 runtime imports, tenant/role projections and hidden-field filters, organization-before-draft lock order, authorization refresh after waits, revisioned saves, creation fingerprints, approval-aware publication replay, exact stored snapshot/hash copying, capacity and archive handling, atomic audit, legacy endpoint isolation and runtime rejection. Integration checks exercise actual restricted database roles; providers are not used by authoring.

Three confirmed input-handling findings were reproduced in six failing regression cases:

1. A cursor with a non-string ID escaped as AttributeError instead of a 422 client error. Cursor field types are now checked before timestamp/UUID parsing.
2. Unknown JSON field names and invalid dictionary keys could echo submitted content in validation error locations. Unknown names/invalid key locations are now replaced with placeholders, including related value errors; error details are bounded.
3. Null characters in clinical content or approval text could reach PostgreSQL's unsupported JSONB text path and appear as temporary database errors. Shared document validation and publication approval reject unsupported text before storage.

After fixes, all 33 contract/review checks passed (27 contract checks plus six review regressions). The regression cases are included in the final suite, not additional unique test claims. Final platform verification and the second final review are recorded below. Evidence: `.test_artifacts/patient-scenario-api/review1-before.txt` and `review1-after.txt`. The two existing test-library deprecation warnings remain.


## Patient Scenario Library API review 2 (2026-09-18)

A fresh pass checked the reviewed fixes, OpenAPI projections, actor-bound creation/publication retries, legacy-key isolation, quotas, archive/retirement, source snapshot identity, SQL parameterization and backend grants, runtime gates, package contents and documentation accuracy. The initial full platform suite passed 96 tests with no skips; the existing companion suite passed 12. Those pre-review results do not substitute for final verification of the fixes.

Found a compatibility gap for an imported/future-format session: admission and lease/control delivery correctly rejected version 2, but the legacy rubric/feedback readers still assumed the version-1 document layout. An isolated regression first reproduced a KeyError in rubric retrieval. Both readers now explicitly reject unsupported schema versions before parsing; existing version-1 behavior is retained. Added coverage for both delivery paths, stopped-session feedback, cross-author key reuse, immutable draft identity, and legacy-create/publication key collisions.

After the compatibility fix, all 15 review/training checks passed. The final full platform suite then passed **105 tests with no skips**, including the four reproduced findings, publication capacity contention, legacy catalog privacy and previous migration/backup/permission coverage. Companion regression suite: **12 passed**. Platform Ruff lint/format passed (66 files), shared-contract Ruff lint/format passed (4 files), mypy passed (39 source files), and both consumer dependency locks passed. The shared library has no standalone lockfile; its dependencies are locked by those consumers. Two existing Starlette/httpx/AnyIO deprecation warnings remain. Final API/shared wheel and source builds passed. Archive inspection compared the reviewed code, migration, tests, runbook and bilingual JSON examples to the workspace and found no private environment/key files. Package hashes and final test counts are recorded in `.test_artifacts/patient-scenario-api/package-verification.json`; full final test output is in `final-tests.txt` alongside it. The disposable cluster had zero test databases/roles remaining and was stopped. Application databases, live providers and Pi hardware were untouched. No further blocking findings remain within the API/shared-contract scope; all eight API phases are complete. UI and version-2 execution remain the next separate increment. This is a second review by the same implementation agent, not a claim of an independent reviewer. Evidence: `.test_artifacts/patient-scenario-api/review2-before.txt` and `review2-after.txt`.


## Patient Scenario Library planned-versus-implemented audit (2026-09-18)

Compared the revised API plan with the implementation and verification inventory; see the [audit report](patient-scenario-api-audit.md). All planned API feature groups are present, but two promised verification items have incomplete evidence: concurrent retirement/lease behavior (A-01) and the kidney example's full API lifecycle (A-02). The earlier statement that every phase was complete is qualified by these open acceptance follow-ups. They are coverage gaps, not newly demonstrated functional defects.

Read the recorded 105-pass/no-skip platform result and prior companion/check results. Rechecked all four distribution hashes and 111 Python source comparisons across current source and release archives; all matched. No fresh runtime, database, provider or hardware tests were run. Added the two follow-ups to TODO; application code and existing artifacts remain unchanged.


## API audit closure and deep audio review (2026-09-19)

Closed A-01/A-02 with `test_scenario_audit_followup.py`: four coordinated retirement-versus-device/control grant tests cover validation before/after retirement, rejection of later renewals and retained history. The kidney example completed its authenticated lifecycle and safe/private projections. The initial kidney test assertion was corrected for expected normalization defaults; no production API defect or schema change resulted. Full disposable PostgreSQL run: **110 passed, no skips**. Cluster `127.0.0.1:55441` had zero remaining test databases/roles and was stopped; application databases were untouched.

The [deep audio report](audio-latency-review.md) contains nine findings and fixes across stale queue age, stuck-native readiness, bounded microphone handoff, brief-noise capture delay, response deadlines, truthful timing, pre-TTS authorization, generator cleanup and failed durable admission. First review traced input through playback/storage and added targeted regressions. Final review revisited cancellation, limits, failure receipts, serialization, authorization and package contents after the fixes. The existing no-raw-TCP decision is preserved: WebSocket already carries audio/video over TCP, and no video model was introduced.

Verification: **106 audio + 21 training tests passed**, including existing real loopback transport and actual video recorder/store tests with explicit ASR/dialogue/hardware doubles. Platform/audio/training Ruff, format and mypy passed (39/13/11 source files). Audio/training lock checks passed. All three wheel/source builds passed; six archives matched 215 local source/assets and excluded private settings, media, weights and keys. Evidence: `.test_artifacts/audio-latency-review/{audio-tests.txt,training-tests.txt,package-verification.json}`, `.test_artifacts/patient-scenario-api/audit-closure-tests.txt`. Existing dependency deprecation warnings remain; they did not fail checks.

Actual local native measurement: eight paced synthetic Hindi/English streams per installed model, one load each, recording off/on/on/off. On Windows/Core Ultra 7 165H/64 GB, small took 2.10-5.26 seconds after input; large-v3 took 12.15-35.71 seconds. Inference dominated; recording samples varied too much to establish a causal overhead or zero-latency guarantee. All eight enabled recordings finalized with expected audio byte counts. Script/raw metrics: `.test_artifacts/audio-latency-review/{measure.py,native-stream-metrics.json,native-progress.txt}`. No live cloud, Pi, Wi-Fi, target-16GB, human speech accuracy, simultaneous-video performance or acoustic playback measurement is claimed. All benchmark servers stopped. Interactive acceptance remains open.


## Whisper medium/turbo comparison and final review (2026-09-19)

Downloaded official OpenAI medium and large-v3-turbo checkpoints, verified their published SHA-256 values, converted locally to CTranslate2 INT8 and checked all converted-file manifests. The standard Hugging Face route failed in this environment; official checkpoint downloads retained TLS verification. Both new model directories are available locally; operational service selection was not changed.

First review checked preselected public FLEURS dev recordings, CC BY 4.0 attribution, unedited complete utterances, synthetic-source limitations, PCM hashes, Hindi combining marks, word/character edit scoring, weighted aggregation, fixed CPU/beam settings, single model residency and timing boundaries. The benchmark now explicitly disables outbound callbacks for future runs. No production code or schema changed.

Final evidence: **92 whole-clip recognition checks and 16 paced loopback API streams**, all four child processes successful. Every recording finalized as saved; final verification found **16/16 exact PCM and delivered/saved transcript matches**. Eight benchmark scripts passed syntax checks. Raw results, transcripts, runtime versions and result hashes are under `.test_artifacts/whisper-model-comparison/`; see the [full comparison](whisper-model-comparison.md).

On the available Windows/Core Ultra 7 165H/64 GB host, four-thread CPU INT8 API median post-input delays were small 2.70 s, medium 11.21 s, turbo 13.01 s and large-v3 21.67 s. Human Hindi WER was 52.00%, 38.67%, 29.33% and 21.33% respectively; only six recordings/75 reference words per model. Prefer turbo over medium for the next bilingual quality trial, while keeping interactive acceptance open. English results are close and include a repeated reference sentence across two distinct recordings. Synthetic drug/symptom and mixed-language failures are explicitly separated from human quality evidence.

Final review inspected every paired output and corrected the report to distinguish recognition sensitivity to the API input window from proven speech deletion: small/medium omitted a phrase on one streamed clip while turbo/large retained it; the original recording remained exact. This needs natural-microphone acceptance, not an unsupported claim of fixed VAD behavior. Numerical tables, memory definitions, asset selection and local links were checked. All benchmark servers exited. Reviews were by the same implementation agent. Application/database suites were not rerun for this asset/benchmark/documentation task; no live cloud, Pi, Wi-Fi, target-16GB, simultaneous-video or end-to-end audible-response verification is claimed.


## Three-audio per-model demonstration review (2026-09-19)

Ran the same three existing clips through small, medium, large-v3-turbo and large-v3 sequentially, one resident model per process: first human English, first human Hindi, then the explicitly synthetic mixed_pain case. Fresh paced 20 ms authenticated loopback API streams used CPU INT8/four threads/beam 1 with recording enabled and console/callbacks disabled. This repeats prior inputs for an inspectable demonstration; it is not a new held-out accuracy benchmark. Application configuration and production code were not changed.

An initial Medium attempt exposed a benchmark-checker error: processed chunks include empty recognition outcomes, whereas transcript events exclude them. Source inspection confirmed the API's existing chunk_skipped/no_speech behavior. Corrected the verifier to match saved event counts against delivered transcript events, preserved the failed attempt's log/partial JSON and recordings, and reran all three Medium tests. The rerun passed, including the empty-result case. Small's completed run was retained; Turbo and Large-v3 then completed normally.

Final review compared all 12 returned transcripts with references, separated semantic quality from spelling-sensitive WER, and reverified **12/12 exact input/saved PCM and delivered/saved transcript matches**. All four final result files are complete and hashed. The offline HTML report contains three embedded WAV players whose payloads match the linked input audio; it uses no external scripts or media. The Markdown report includes per-test post-input/total timing, exact text, word edits, quality notes, startup costs, source attribution and limitations. Both benchmark scripts pass syntax checks. All measurement servers/model processes exited. Browser/audio-device playback, Pi/Wi-Fi, the target 16 GB laptop and full audible patient replies were not verified; platform/database tests were not rerun for this benchmark/documentation work.

Evidence: [three-audio report](whisper-three-audio-tests.md), `.test_artifacts/whisper-three-tests/{run.py,report.py,cases.json,quality-notes.json,verification.json}`, per-model JSON/logs and preserved `failed-attempts/`. Timings are single runs and vary with CPU state; the synthetic mixed clip is not natural Hinglish acceptance evidence.


## Selectable Nemotron integration and final review (2026-09-19)

Added multilingual Nemotron 3.5 ASR Streaming 0.6B through sherpa-onnx CPU INT8 alongside all existing Whisper models. Downloaded the 560 ms export, verified publisher SHA-256, installed four allowlisted model files and retained a per-file manifest. Selection uses AUDIO_MODEL_NAME and a matching optional AUDIO_MODEL_PATH; operational settings/defaults and existing weights were preserved. Serving remains local-only, with one resident model and serialized native work. Each connection owns isolated incremental recognition state; final transcript recording/delivery retains the existing protocol. No PMS/database/video behavior or implicit cloud/model fallback was added.

First review traced selection, startup, true incremental inference, endpoint/flush offsets, state isolation, memory/queue bounds, cancellation, native deadlines, recording/callback behavior and archive handling. The first native run found a Windows DLL collision: sherpa requested ONNX C API 28 but resolved a system runtime exposing API 17. Fixed by loading the compatible project-environment DLL before sherpa; added a regression check. No system DLL was modified. The new API regression initially passed the shared test headers directly to Starlette, which mutated them and caused a later transport test to fail. Corrected the test to copy headers and assert their isolation, then reran the full suite.

Final review rechecked the finished code after fixes, including stream ownership and readiness on native timeout, final-only callbacks, no model reload per connection, exact samples despite framing/padding, empty-result accounting, output bounds, model/engine metadata and Whisper compatibility. Both reviews were by the same implementation agent. Verification: **124 audio tests + 21 training tests + 42 platform tests passed**; **68 PostgreSQL integration tests skipped** because no disposable PMS_TEST_ADMIN_DSN was configured. Audio/platform Ruff, format and mypy passed; audio lock check passed. No application database was touched. Existing dependency deprecation warnings remain.

Real CPU evidence: three paced demonstration streams used one Nemotron load and completed 0.204-0.450 seconds after input on the available Windows/Core Ultra 7 165H/64 GB host. Startup plus warmup was 3.87 seconds; measured peak working set 883 MB, private commit 1595 MB. Accuracy errors remain: omitted English phrase, changed Hindi collision phrase and missing chest-pain symptom in the explicitly synthetic mixed-language test. These clips do not establish clinical acceptance.

Four additional Nemotron streams covered concurrent Hindi/English, nine seconds of silence across a reset and a repeated English stream; one model, four isolated session engines and 138 incremental native calls. A real Whisper-small stream also passed. Final verification found **8/8 exact input/saved PCM and delivered/saved text matches**, verified all Nemotron file hashes and the preserved medium/turbo manifests, and compared **49 packaged source/assets** across the final wheel and source archive. Packages exclude private settings, media and weights. All test/model servers exited.

Evidence: [integration report and configuration](nemotron-integration.md), `.test_artifacts/nemotron-validation/{run.py,smoke.py,verify.py,cases.json,verification.json}`, native result JSONs, private recordings and `device/audio-process/dist`. Actual Pi/microphone, Wi-Fi, target 16 GB hardware, concurrent video load, natural clinical Hinglish and full dialogue/TTS/playback acceptance remain deferred. The existing operational model setting was not automatically changed.


## Optional Whisper GPU execution review (2026-09-19)

Added AUDIO_GPU_ENABLED (default false) and AUDIO_GPU_DEVICE_INDEX (default 0) for Whisper. GPU mode uses CUDA int8_float16 with explicit availability/compute checks, validates the native model's device/precision and warms once before readiness. No silent CPU fallback. Nemotron remains CPU-only and rejects the GPU flag. Status, ready and transcript metadata expose device/precision. Existing model directories, CPU support, serialized work, private recording and optional callback behavior are preserved.

Installed optional NVIDIA Windows x64 runtime wheels in the project environment: cuBLAS 12.8.4.1, CUDA runtime 12.8.90, cuDNN 9.7.1.26. DLL discovery/load and PATH changes are process-local; no system drivers/files were changed. CPU installations need no CUDA extra. First review covered device selection/failure, native verification, dependency markers, DLL handle lifetime, metadata and model residency; corrected metadata-path typing and narrowed optional wheels to the tested Windows platform. Final review revisited the finished implementation, real hardware outputs and packaged sources after these fixes. Both reviews were by the same agent.

Actual NVIDIA RTX 500 Ada laptop GPU run: one Large-v3 load, confirmed native device cuda/index 0/int8_float16. NVIDIA listed the benchmark PID; sampled device-wide memory peaked at 1,909 MiB and utilization at 100% (45 samples, no monitor errors). WDDM per-process memory reported N/A, so the memory figure is device-wide sampled telemetry. Memory returned to zero after the process exited. Model load/warmup: 7.74 s. Same three paced audio clips completed 0.38 s English, 4.26 s Hindi and 1.93 s synthetic mixed after input ended, versus earlier CPU 16.63/21.57/37.80 s. Outputs exactly matched those CPU transcripts, including the unusable synthetic mixed result. Single-run, different-time measurements are not a clinical or worst-case performance guarantee.

Verification: **135 audio tests + 21 training tests passed**, audio Ruff/format/mypy and lock consistency passed. **3/3 exact audio/text recording matches**, final wheel/source builds and **52 packaged source/asset comparisons** passed; private settings/media/weights are excluded. Platform/database tests were not rerun because only audio execution/configuration/metadata changed; no database was accessed. Existing dependency deprecation warnings remain. No Pi, Wi-Fi, target 16 GB, long-duration/concurrent-video or end-to-end patient-response verification is claimed. All test servers/processes exited; operational private settings were not overwritten.

Evidence: [GPU validation report](whisper-gpu-validation.md), `.test_artifacts/whisper-gpu/{run.py,large-v3-cuda.json,verify.py,verification.json}` and the rebuilt audio wheel/source archive.


## Vosk optional CPU adapter and GPU capability review (2026-09-19)

Added optional Vosk 0.3.45, explicit small English/Hindi model selection, one resident model with isolated streaming state, matching-language validation before recording/audio reception, bounded result accumulation and explicit GPU rejection. Existing Whisper CPU/GPU, Nemotron, private settings and installed models are preserved. Both publisher and pinned public Hugging Face installers use bounded size/checksum/extraction controls, no stored credentials and no runtime model downloads.

First review covered model selection, native thread ownership, state reset/isolation, internal endpoint accumulation, language failure, output bounds, metadata, retry behavior and archive safety. Corrected Vosk metadata to model_default / no applicable configured thread count, checked result types before trimming, and limited retries to transient GET failures. Final review revisited dispatch compatibility, optional imports, early language rejection, safe failure and evidence limits after fixes. Both reviews were by the same implementation agent.

152 audio tests and 21 training tests passed; Ruff, formatting, mypy (19 source files) and lock consistency passed. Mock tests cover residency/isolation, endpoint retention, empty final flush, silence, output bounds, missing dependency/model, GPU flags, authenticated API metadata, serialized execution, language rejection/session cleanup, allowlisted ZIP extraction, unsafe/incomplete archives, integrity failure, transient retries, permanent refusal and no overwrite. Platform/database tests were not rerun; no database was touched.

Native capability probe verified the Windows wheel's GPU batch-model entry point is an unconditional NULL-return stub. GPU inference was not run; no WSL/Docker/CUDA compiler is installed. Real CPU recognition could not run because the model downloads were blocked: original host and direct Hugging Face mirrors returned 403, and the requested official Hugging Face client attempt also failed. The user deferred benchmarking while code/checks were finished. No Vosk speed/quality, native model loading or exact real-audio recording claim is made.

See [full status and sources](vosk-validation.md); evidence is in `.test_artifacts/vosk-validation`. Downloading actual archives and running the English/Hindi recordings remains an explicit pending acceptance task.

Vosk package review: final wheel/source builds passed with 58 exact source/asset comparisons. Both optional extras are declared; installed Vosk and all three existing NVIDIA runtime dependencies were verified. Package verification excludes private settings, weights and recordings. CLI help exposes the explicit --vosk-source option. No real model inference was run.


## Standalone local Qwen3 4B installation and native review (2026-09-19)

Implemented the requested isolated local-llm folder with pinned Qwen3 4B Q4_K_M, llama.cpp b11046 CPU/CUDA runtimes and Windows batch entry points. Model downloaded from Qwen's official ModelScope revision and verified against the matching official Hugging Face SHA-256; GitHub runtime archives passed publisher SHA-256. No system driver, existing audio model or platform/database behavior was changed. Python runtime scripts use only the standard library.

First review checked integrity/retries/archive bounds, conditional dependencies, input/configuration bounds, loopback authentication, secret handling and process lifetime. Native testing found a logging-level mismatch in the strict GPU readiness check and a Windows lock-byte read/unowned-unlock failure during duplicate startup. Fixed both, added a real Windows locking regression, then reran affected checks and the complete native validation. Final review covered the corrected implementation and raw evidence. Both reviews were by the same agent.

14 unit/regression tests, Ruff, formatting and compilation passed. Actual native GPU offloading was 37/37 layers; three short English/Hindi/fictional-patient requests used one resident process and completed in 0.14/0.92/0.57 seconds after request submission, with about 0.07-0.08 second first-token latency. Startup including integrity checks was 11.45 seconds. Sampled device-wide GPU memory peaked at 2,769 MiB, utilization 93%; this is not a worst-case bound. Explicit CPU mode passed a separate arithmetic smoke test with zero GPU layers.

Actual start-llm.bat launched from another directory, inferred and exited successfully. chat.bat attached without reloading. Missing/wrong API keys, duplicate starts and oversized context were rejected. Normal and abrupt launcher exits released the native process; final GPU memory was zero. Independent Windows ACL inspection was denied by the host even with escalation; ACL-setting calls and actual private-key authenticated batch access succeeded, and no permission weakening was applied.

See [complete validation and remaining limits](../local-models/validation.md). No platform/database/audio tests were rerun for this isolated folder, and no database was accessed. Hindi fluency and clinical scenario adherence need broader evaluation; no Pi/Wi-Fi, shared Whisper/video/TTS workload or patient platform integration was claimed.


## Local LLM follow-up implementation review (2026-09-19)

Reviewed and fixed request deadlines that could be exceeded by slow header/SSE reads, concurrent first-key creation, overlapping installers, base-config schema gaps, malformed/disconnected response handling and skipped cleanup after termination errors. Added Windows locks, exact GPU layer verification, controlled client failures and independent job/lock cleanup. Preserved one resident model, explicit GPU/CPU selection, local authentication and no automatic inference replay.

25 unit/regression tests, Ruff/format and compilation passed. Native full GPU 37/37, partial GPU 17/37 and CPU inference passed. All four batch entry points were exercised from another directory; missing/wrong credentials and oversized context were rejected, duplicate starts preserved the existing process, and normal/abrupt exits released native resources. Setup testing exposed restrictive legacy runtime ACLs; repaired those public folders and restored private state to the interactive account/SYSTEM only. A separate run under that account verified the ACLs, setup and launch batches. No key values were logged or regenerated.

First review reproduced failures before fixes; final review inspected corrected code and actual evidence after permission repairs. Both passes were by the same agent. No platform/database/audio changes or database access; those unrelated suites were not rerun. Broader Hindi/clinical acceptance, Pi/Wi-Fi and shared Whisper/TTS GPU-load testing remain pending. See [full findings and evidence](../local-models/review.md), `.test_artifacts/local-llm-review/{before-fixes.txt,results.json,user-account.json,checks.json}`.

## Human microphone -> PMS -> Qwen implementation (2026-09-19)

Implemented migration 0009, scoped encrypted LLM connections, bounded idempotent requests and atomic audits, pooled async llama.cpp JSON/SSE inference, lifecycle rechecks, quotas, leases and retention. Added the `human-test/` desktop screen with finalized audio-turn assembly, in-memory conversation, visible capture/cancellation controls, and normal/isolated-demo launchers. The demo uses a separate private PostgreSQL cluster and locally signed fixture identity through normal PMS authentication. Existing application database and live identity configuration were not altered.

Review 1 corrected provider async-generator task ownership, historical department narrowing, ASR completion validation, cancellation/reset races, expiry cleanup, process ownership and private Windows account access. Database integration caught deployment grant expectations and the scenario verifier's exact-head compatibility; both now match the additive schema. Review 2 reproduced and fixed native HTTP-disconnect cleanup under middleware/AnyIO cancellation, then removed a costly duplicate Hindi final-answer redraw. Native stream cancellation completed in 157 ms, following inference succeeded, Hindi display/reset/silence preservation worked, and the post-fix GUI timer gap was at most 141 ms in the measured run. Both reviews were by the same agent.

Final full PMS suite: **141 passed, zero skipped**, including real Qwen JSON/SSE and dedicated disposable PostgreSQL migration/data-preservation, grants, authorization, concurrency, lease/retention and credential-rotation checks. Ruff, format and mypy (43 source files) passed. Additional suites: **12 human-test, 152 audio, 85 video, 21 training, 25 local-llm**, all passed. Existing framework/WebSocket deprecation warnings remain; no failures. Setup and actual demo batch from another directory passed. Human-test/PMS wheels and sdists built; private files are excluded and the PMS wheel includes migration 0009. Private demo/model key ACLs independently verified as launching account/SYSTEM only.

See [complete planned-versus-implemented report, latency and limitations](../human-test/validation.md) and [run instructions](../human-test/README.md). Hardware evidence is a real half-second microphone capture plus fixture-fed GUI/audio tests, not an unobserved human conversation. Clinical response acceptance, Pi/Wi-Fi, camera, TTS, live cloud and production deployment remain deferred.

Final warm arithmetic samples: direct median 110 ms, PMS median 172 ms; PMS non-provider overhead median 77 ms. Final ASR finalization 1.625-3.219 seconds for the four language/mode fixtures; native JSON disconnect reached `failed/client_disconnected` in 1.016 seconds without replay. Sampled device-wide GPU use peaked at 2,769 MiB and summed Python/llama working sets at 3.64 GiB; this is observational, not a capacity guarantee. Multi-chunk input produced one generation, silence none, and every owned demo/test port was closed after verification.

The final filesystem review also found inherited workspace access on the disposable PostgreSQL test cluster. After shutdown, its data/WAL directory was restricted to the interactive account/SYSTEM and a WAL-file ACL was independently verified. This test-data permission correction did not alter application code or the application database.

## OpenAI/compatible LLM extension and token review (2026-09-19)

Implemented forward migration 0010 and explicit provider settings while preserving the local Qwen protocol. OpenAI uses Chat Completions with max_completion_tokens and store=false; compatible endpoints select the standard token field and streamed-usage option. Provider credentials stay in the existing tenant-bound vault, separate from human/audio tokens. Public TLS endpoints require a deployment allowlist and external-call gate; DNS validation/pinning preserves TLS hostname checks and connection-pool isolation. No automatic provider fallback or inference retry was introduced.

Review 1 findings and fixes:

- Endpoint edits could otherwise forward an existing secret to a new destination. Provider/base-URL changes now require a freshly supplied key; malformed/long key handling is covered without echoing secret values.
- Local Qwen extensions and max_tokens were not a portable OpenAI contract. Local options are now isolated; OpenAI uses max_completion_tokens; compatible endpoints configure their supported field explicitly. No failed POST is resent with guessed parameters.
- Cached/reasoning token details need subset accounting. Usage parsing retains validated counts, consumes final usage-only SSE events, leaves missing usage unknown and keeps conservative reservations for uncertain calls.
- Empty, refused and filtered output must not be accepted into conversation history. Both provider modes fail appropriately; the desktop also rejects empty final answers, including old cached results.
- Login expiry needed checks at dispatch and completion, beyond periodic polling. Added those checks, retained lifecycle/revision/lease rechecks, and gated in-flight remote completion if external access is disabled.
- A new post-health authorization check accessed an expired ORM identity after rollback. Integration testing found it; snapshotting the user ID before rollback fixed it. Status checks now recheck connection revision/lifecycle after provider GET.
- Fixed 30/35-second socket read limits could cut off a reasoning response before the configured request deadline. PMS and desktop reads now honor their bounded overall deadlines.
- Provider destination validation also rejects multicast/reserved addresses, mixed DNS answers and control/encoded/dot-path URLs. Tests check pinned socket IPs, original TLS SNI/verified context and separate pools for separate hosts sharing an IP.

Targeted database/API verification: 17 passed, including a real 0009-to-0010 upgrade preserving local connection ciphertext/settings/revision and a running request, schema mapping, existing authorization/concurrency/retention/rotation checks, mocked remote JSON/SSE, credential redaction, quotas and expiry. Desktop: 14 passed. Static checks and PMS/desktop builds passed; both wheel/sdist packages exclude private runtime paths, and PMS packages include migration 0010.

Review 2: rechecked final provider routing, encrypted-secret boundaries, revision/lifecycle checks, atomic reservations/audits, request recovery, cancellation, bounded parsing, migration preservation, runtime grants and package contents. No unresolved findings were identified in this implemented scope. Prior frozen migration 0009 matches its previously recorded SHA-256.

Final verification: **207 PMS tests passed, zero skipped**, including native Qwen JSON/SSE and all disposable PostgreSQL migration, grants, authorization, concurrency, lease/retention and rotation regressions. The full run took 422 seconds. **14 desktop tests passed**. Required `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/pms_api` passed (45 source files); desktop Ruff/format also passed. PMS and desktop wheel/sdist builds and private-path exclusion checks passed. Existing two Starlette/AnyIO deprecation warnings remain; no test failures. Qwen loaded once with 37 GPU layers; the owned model server and dedicated PostgreSQL test cluster were stopped afterward.

Raw evidence: `.test_artifacts/llm-provider-review/pms-tests.txt`, `native-metrics.json`, `package-checks.json`, and `final-checks.json`. This follow-up reran the changed PMS/desktop scope; previous audio/video/training verification is recorded above and was not repeated because those implementations were unchanged. Native verification used the installed local model; OpenAI/compatible cloud contracts used mocks. No real cloud key or paid API request was used. Live account/model entitlement, hosted deployment, Pi/Wi-Fi and clinical behavior remain unverified/deferred.


## Optional medical model support — 2026-09-19

Scope: selectable QwenMedic Q4_K_M and English-only Whisper Medical, explicit installers/conversion dependencies, and an optional desktop demo profile. No PMS database/API source changes. Existing Qwen3 4B, Whisper and other ASR choices remain intact.

Review 1 inspected source/revision/checksum handling, atomic publication, no remote model code/pickle loading, runtime dependency separation, GPU/CPU selection, English validation before recording, resident model reuse, private credentials and unchanged PMS mediation. Fixed converter dependency isolation, forced local safetensor loading, model alias selection in both native server/client, and separate saved demo connection IDs.

Review 2 inspected installation retry/restart behavior, readiness/model matching and missing-model behavior. Fixed partial source-lock restart behavior, bounded metadata, model-specific setup instructions, exact model checks at readiness, current saved connection validation through the supported listing endpoint, nullable publisher metadata typing and a regression test's mutation of shared WebSocket headers. No pending confirmed code finding remains; actual medical checkpoint compatibility remains unverified.

Verification: **160 audio + 31 local LLM + 17 desktop tests passed**, Ruff/formatting, audio mypy and both Python package builds passed. Actual Torch/Transformers-to-CTranslate2 conversion and native CPU encoding passed with a tiny random synthetic fixture, including verified sources, atomic publication and cached reinstall. This does not establish medical model accuracy. The pinned native llama.cpp CPU quantizer was checked separately. Evidence: `.test_artifacts/medical-models/`.

Native existing-flow compatibility passed for English JSON and Hindi SSE: microphone-equivalent WAV -> audio WebSocket -> human controller -> real authenticated PMS -> resident Qwen3 4B -> answer. ASR finalization was 1468/2500 ms, LLM generation 1687/3359 ms, and both ended with `stop`. Missing medical models fail before starting the demo database. Owned processes were stopped. No live cloud call or Pi/hardware microphone test was performed. The full disposable-PostgreSQL API suite was not rerun; schema and API code were unchanged, while the native demo used its existing isolated database.

**Outstanding external blocker:** both requested Hugging Face medical repositories return corporate HTTP 403 Access Denied. Official client attempts also failed; verified Windows-certificate and explicitly requested SSL-disabled diagnostic requests produced the same denial inside/outside the sandbox. The optional installer now uses Windows trusted certificates with TLS verification enabled. Neither medical checkpoint is downloaded, loaded, or benchmarked; future native accuracy/latency/GPU checks remain open in TODO. [Setup and exact status](medical-models.md).

## Scenario category defaults and selected local models — 2026-09-19

Scope: forward migration `0011_scenario_categories` adds the shared nine-column category catalog, ORM mapping and three active English/Hindi defaults: Cardiology, Nephrology and Respiratory Medicine. The domain schema now has 19 tables and 338 columns. Seeds and their three system audit events commit atomically. Existing scenario specialty text, published snapshots, frozen SQL and earlier migrations are unchanged. Category HTTP selection and additional patient cases are outside this increment.

`pms-admin init-database` and `platform/db/init.bat` create the configured application database when absent, then upgrade it through Alembic. The explicit deployment-owner URL and existing PostgreSQL installation/login roles are required. Repeated and concurrent initializer calls preserve existing records and category customizations. Unmanaged application schemas require verified baseline adoption. Runtime grants permit category SELECT only for the API, with no category privileges for processing/retention or PUBLIC.

Review 1 inspected creation/upgrade failure handling, SQL identifiers, default privileges, migration atomicity, stable category identity, Unicode labels and runtime access. Fixed a transient PUBLIC-access window by creating a database with connections disabled until its ACL/UTC configuration succeeds. Prevented CLI settings/database exceptions from exposing credential-bearing values. Updated exact-head readiness, grant-bundle parity, ORM column checks, schema verification and deployment documentation. A failed initial ACL setup leaves the new database closed for owner repair; no database is automatically deleted or existing unmanaged schema stamped.

Review 2 checked preservation, repeat/concurrent initialization, migration rollback/retry, category constraints, packaging and model selection. PostgreSQL tests inject an audit-insert failure and verify that the category table, seeds and migration revision roll back together before a successful retry. They also verify unchanged existing data, retained names/deactivation, immutable identifiers, no duplicate seed/audit records and least-privilege grants. Both final wheel builds include the changed sources and exclude private environments, runtime/model assets and credentials. No unresolved implementation finding remains in this scope.

Actual local application update: backed up the existing private `human_test_demo` database on loopback port 55444, ran the Windows initializer twice, and applied/verified the runtime grants. Exactly three categories and three seed audit events exist at head `0011_scenario_categories`; all pre-existing non-audit row content is unchanged. The owned demo database process was stopped afterward. The Windows PostgreSQL service and unrelated databases were not modified.

The user also selected **Qwen3 4B and Whisper large-v3** as defaults. Qwen is now explicit in `local-models/config.json`; the standard desktop demo, desktop default/example and existing private model selectors use large-v3. Optional medical and other ASR adapters remain available. The combined demo keeps Qwen on GPU and Whisper on CPU for the 4 GiB GPU; standalone Whisper retains its existing GPU flag. Qwen native startup verified its pinned model/runtime and offloaded 37 layers. All five installed Whisper large-v3 assets match the saved conversion manifest checksums. No download was needed. This update does not claim new Whisper latency/quality measurements or a live microphone/Pi test.

Final verification: **218 PMS tests passed, zero skipped, in 475.71 seconds**, including native Qwen JSON/SSE and dedicated disposable-PostgreSQL migration, adoption, preservation, backup/restore, constraints, permissions, concurrency and audit rollback checks. **17 desktop tests and 31 local LLM tests (35 subtests) passed**. Required PMS Ruff, formatting and mypy passed (46 source files); desktop Ruff/format and both package builds passed. Two existing Starlette/AnyIO deprecation warnings remain. An earlier full-suite attempt was interrupted by Windows test-runner cleanup of the disposable cluster; the runner was fixed to use file output, bounded execution and process-matched cleanup, and the final clean rerun above passed. This was a validation harness issue, not a failed application migration.

Evidence: `.test_artifacts/scenario-categories/full-tests.txt`, `focused-tests.txt`, `local-database.json`, `model-defaults.json`, `native-metrics.json` and `package-checks.json`. The Qwen server and owned disposable PostgreSQL cluster were stopped after the final run. Cloud contracts remain mocked; hosted deployment, live cloud and Pi/hardware verification remain deferred.
## Alex identity and patient rehearsal — 2026-09-19

Identity increment final evidence: **220 PMS tests passed, zero skipped, in 668.83 seconds**, including native Qwen JSON/SSE. The dedicated disposable PostgreSQL cluster and native server stopped cleanly. Focused identity/category/migration/grants tests: 21 passed. The local `human_test_demo` upgrade to 0012 preserved old non-audit content; one Alex and one atomic identity audit were verified after two initializer runs. Ruff, formatting, mypy (46 sources) and package/private-file checks passed. Two existing Starlette/AnyIO warnings remain. Evidence: `.test_artifacts/patient-identity/`.

Rehearsal review 1: checked the nine complete bilingual templates against the version-2 contract; one shared Alex identity; private setup ownership, permissions, revision concurrency, lifecycle and auditing; LLM request provenance; prompt projection; token bounds; desktop threading/cancellation; and migration/runtime-grant parity. Fixed a PL/pgSQL shared-trigger field-resolution error before applying 0013 to the application DB. Tightened JSON envelope checks so missing required version/code/title fields cannot pass through SQL NULL semantics. Bound request provenance to organization **and user** in the composite foreign key. Setup saves check both selection and template revisions. Successful patient finalization serializes against setup updates using the organization lock.

Prompt review: `config.json` is used by standalone console chat, not automatically by the native HTTP server. Shortened its default patient instruction; new demo connections copy it as fallback. PMS selected-case calls replace the connection instruction with patient-topic routing context. Instructor content/never-disclosed topics are excluded; no raw model routing text is streamed. Invalid/unknown output produces stored clarification. An initial native Qwen prompt returned empty topic selection for a name question; explicit patient pronouns and compact positive routing examples corrected the probe. Tokenizer and provider usage both measured 643 prompt tokens for the representative chest-case name question, leaving 1,213 tokens after the 128-output reservation and 64 margin. Final native Hindi/JSON/SSE checks are tracked in the audit.

The local DB now has head 0013, three categories, one Alex and nine cases (three/category), nine case seed audits, and unchanged prior non-audit data. A private backup preceded two successful initializer runs; runtime grants were reapplied/verified. Desktop tests cover save-before-conversation, restoration, case switch, no automatic microphone, setup-bound calls, history trimming and existing audio/cancellation behavior. Visual review inspected native Windows Setup and Conversation captures; fixed footer clipping and improved combobox contrast. The final verification matrix and second review are recorded in [the audit](human-test-patient-workflow-audit.md).

Review 2 follow-up fixes: kept legacy general-completion fingerprints unchanged by omitting absent practice fields from the fingerprint payload, preserving pre-upgrade request idempotency; added a regression against the old fingerprint contract. Remote patient calls now retain the connection's configured completion allowance so reasoning-capable providers are not forced into the local 128-token routing cap. Both OpenAI and compatible remote JSON/SSE patient routes have mock protocol tests. Large local inputs that use the conservative counting fallback are labeled as estimates, not exact tokenizer results. Fixed a pause-before-task-creation race by scheduling cancellation on the worker loop, and added a deterministic desktop regression. Added scrollable setup content, preserved footers at smaller sizes, and implemented/reviewed the requested centered skin-toned manikin with selected observations and real workflow status.

Review 2 completed: lip movement/blinking now follows displayed answers for a bounded 2–12 seconds, cancels on workflow changes and closes cleanly. Fixed continuous capture cutting the expression short: capture resumes independently while the animation finishes, so no artificial ASR/model delay is added. Desktop tests verify expression completion, listening-state restoration and cancellation. Reinspected final ownership/revision locks, private data boundaries, prompt selection and package contents; corrected outdated desktop documentation about generic-only behavior and setup permissions.

Final checks: **228 full PMS tests passed, zero skipped** (792.02 seconds), followed by **85 targeted API regressions** after final compatibility fixes (211.09 seconds); **20 desktop tests** passed. These overlap and are not additive unique counts. Local LLM checks in this increment: **31 tests / 35 subtests**. API Ruff, formatting and mypy (49 sources), desktop Ruff/format and both wheel/sdist builds passed. All four archives contain required new sources and exclude private runtime assets. Two existing Starlette/AnyIO warnings remain. Both review passes were performed by the same agent.

Real local demo verification: saved and tested all nine cases with Qwen; initial complaint prompts used 641–675 tokens including the supplied case, plus 128 output and 64 safety reservation within 2,048. The edited 37.9 °C observation was reflected correctly. Native desktop restored and saved the setup, displayed the real patient answer and animated the manikin without opening a microphone. Default English chest case was restored. Owned service/test ports were closed after verification.

The prerecorded audio check exposed a genuine quality limitation: Whisper large-v3 CPU recognized the English onset question exactly but rendered the synthetic Hindi question incorrectly. Finalization took **16.390 / 16.906 seconds**; PMS took **1.203 / 0.797 seconds**. Garbled Hindi correctly returned clarification. The exact Hindi question supplied as text produced the expected Hindi duration answer in **0.500 seconds** through PMS. No model/prompt workaround was introduced to hide the recognition failure. Audio quality/latency remain unresolved limitations, not passing accuracy acceptance; no human microphone, Pi, camera or live-cloud claim is made. See the [final audit table and measurements](human-test-patient-workflow-audit.md) and `.test_artifacts/patient-workflow/` evidence.

## Everyday-question patient answering (2026-09-19)

Reported symptom: every utterance outside the 22 seeded clinical topics returned `dialogue.clarification` verbatim, including "what did you eat yesterday", "when did you sleep", "turn to your left side" and plain "hmm". Diagnosis: no refusal, safety filter or content block exists on this path. `modules/patient_context.py` asked one model call for `{"topics":[...]}` over the whole topic index, discarded all provider prose, and rendered the single clarification string whenever the list came back empty. Qwen thinking mode was ruled out as a cause: it is disabled at the server (`local-models/scripts/run.py`), per request (`integrations/llm/client.py`) and in the tokenizer pre-pass (`integrations/llm/budget.py`), with `temperature=0, seed=42`.

Measured basis for the redesign: the routing prompt carried every topic's answer text, costing 2,758 bytes for 22 topics. Carrying `id|intent` only costs 1,625 bytes for 22 and 3,056 bytes for 32 — against the previously recorded calibration of roughly 4.1 bytes per token, about 745 tokens, leaving the 2,048-token window comfortable with 96 routing output plus 64 margin. Answers now travel only in the second prompt, for the one to three routed topics.

Review 1 findings, all fixed before the final run: the spoken prompt hard-coded the `system` role and broke OpenAI connections configured for `developer`; the persona line included `on_question` facts, so age could be volunteered while answering an unrelated question, and is now restricted to `volunteered` facts; the routing call's token usage was dropped from the stored result and is now reported as `routing_usage` alongside the spoken call's `usage`; `patient_preview` dereferenced `case.history` before its own filter, crashing on a document with no history section. A stale `session.REVISION` pin caused six cross-module failures in the first full run (readiness 503 plus an alembic head assertion) and was aligned along with the deployment verifier and README schema head.

Review 2 confirmed the disclosure and blast-radius boundaries: `never`-disclosure topics, symptoms and history sections are excluded from both prompts by the projection, not by the caller; `instructor` objectives, notes, rubric and diagnosis reach neither prompt; unrouted history sections are not sent at all. The spoken call is buffered rather than streamed through, so generated wording is released only after the number/length/truncation guard accepts it — a rejected answer falls back to the literal authored text as `scripted_case`. Consumers were checked: the desktop reads only `text`, `finish_reason` and two timing keys via `.get()`, tolerates the added keys and the now-nullable `first_token_ms`, and its `validate_done` non-empty-text requirement still holds because publication guarantees bilingual clarification text.

Checks: **233 PMS tests passed, 2 skipped** (754.79 seconds) against a dedicated disposable PostgreSQL 17 cluster created for this work and removed afterwards, followed by 23 targeted practice/LLM regressions (120.66 seconds) after the review fixes. **20 desktop tests** and **33 local-LLM tests / 39 subtests** passed. API Ruff, formatting and mypy (49 sources) passed; the shared contracts package passes Ruff at the repository's 110-column style. The two skips are the opt-in native tests.

Explicit limitation: the two skipped native tests are the only end-to-end coverage of the two-call turn against the real model, and they were **not executed** — no local Qwen server was running during this work. Routing accuracy for the new `kind` classification, the added everyday topics and the added latency of the second call are therefore unverified against Qwen3 4B. No live, latency or clinical claim is made. Manikin physical capability is still unmodelled, so `command_ack` only acknowledges an instruction.


## Local/cloud model integration (2026-09-19)

Forward migration 0015 and PMS-driven Azure/OpenAI/Whisper selection completed two review/fix passes. See the [cloud audit](cloud-models-audit.md) for findings and verification. The full API run initially had 246 passes, two opt-in native skips and two stale expectation failures; final affected reruns passed 19 cloud/migration checks, three credential checks and 20 shared database/training/processing checks. Desktop cloud/legacy tests passed 30, launcher tests passed 60, API and desktop Ruff/format checks passed, and API mypy passed for 55 sources. Package builds and a native hidden-window Models-dialog smoke passed. New parallel speech-output tests showed intermittent Tk installation-file loading failures, recorded separately rather than claiming a green full-desktop suite. Cloud calls use mocks; PostgreSQL checks use a dedicated disposable cluster. The application database and existing services are untouched.

## Final online enablement review (2026-09-19)

See the [follow-up audit](online-enablement-final-review.md) for confirmed findings,
fixes, complete provider/client verification and actual local readiness. This review
adds no migration and preserves concurrent work. Provider traffic is mocked; the
existing launcher remains configured with cloud calls disabled. Full API regression
verification passed on a separate disposable PostgreSQL 17 cluster: **263 passed,
2 opt-in native-model tests skipped** (669.68 seconds). Final desktop checks passed
**43 tests with one opt-in native-voice skip**; launcher checks passed **68 tests**.
API/client Ruff and formatting, API mypy (55 sources), package builds and the
native Models-dialog smoke passed. The final inspection confirmed the fixes and
that existing migrations and private package boundaries were preserved. Live
provider inference, accuracy and latency remain unverified.

## Offline models and processing final review (2026-09-19)

The [offline audit](offline-models-final-review.md) records the stream-handshake
fix, five new client regressions, native ASR recording checks and actual
Whisper → desktop controller → PMS → Qwen patient answers. Existing application
data and configuration were preserved. The installed Whisper and Nemotron models
have completed 30 native audio streams across six execution configurations;
recognition quality is recorded separately from functional success. The three
opt-in native PMS tests passed against a dedicated disposable PostgreSQL cluster.
The broad API run passed **263 tests**, with the three separately executed native
tests skipped deliberately (688.88 seconds); no database tests were skipped.
Audio 163, desktop 49 (including native English synthesis), launcher 68,
local-LLM 33 and video 85 checks passed. API/audio/desktop static checks and
API/desktop builds passed. Both review passes are complete. All review-owned
model servers and the disposable PostgreSQL cluster stopped cleanly; existing
application data, settings and processes were preserved. Optional medical/Vosk
assets, Hindi voice output and natural clinical speech quality remain explicit
limitations in the audit.

## Consolidated correctness review (2026-09-19)

The [final follow-up audit](final-correctness-review.md) records fixes for malformed
ASR capabilities/readiness, unbounded status responses and missing total readiness
deadlines. Twelve regression cases reproduced failures before the fix; all eighteen
new tests now pass. Full desktop **67**, launcher **68** and PMS provider/client
**80** checks passed, together with static checks and the rebuilt desktop package.
The final inspection verified response cleanup, credential redaction, correct
packaged source and unchanged API source/migrations. Prior full database and real
model evidence remains explicitly identified as preceding verification, with live
cloud and hardware limitations retained.

## Larger desktop manikin (2026-09-19)

The patient now occupies about two-thirds of the conversation area, with existing
controls grouped on the right. First review added visible scrollbars and checked
long-title wrapping. Final inspection covered three window sizes, Hindi text,
scrolling and unchanged workflow/animation handlers. All 67 desktop tests passed
with the installed-voice check enabled; Ruff lint and formatting passed.
[Layout measurements and preview](../human-test/validation.md#larger-manikin-layout-2026-09-19).

## Local model activation (2026-09-19)

Implemented installed-model dropdowns and authenticated, launcher-owned switching
without closing Human-test. Review fixes cover uncertain PMS saves, post-commit
local-file failures, rollback supervision, stale revisions, language restrictions
and confirmed Windows child-process release. Desktop 79, launcher 86 and local-LLM
34 checks passed, with static/package checks and two native passes on dedicated
disposable PostgreSQL clusters. The final pass exercised the control client/server
and actual CPU/GPU process replacement. Missing optional model assets and Nemotron
recognition limitations are recorded in the [audit](local-model-activation-review.md).

## Online model selection and switching (2026-09-19)

Reviewed the supported online speech/LLM and separate platform media paths. Added
provider/deployment labels, access checks before desktop activation, connection
revision fences, publication-time operator checks, explicit unknown-save handling
and recovery when the previous profile is unavailable. Cloud speech/LLM selections
preserve existing video/output sections; those remain independent PMS device jobs.
Same-host compatible endpoints retain local network policy. No migration, cloud
credential provisioning or application-data update was required.

Two review passes completed with fixes and regressions. Full PMS API: 270 passed,
3 opt-in native tests skipped, with every disposable PostgreSQL test exercised.
Desktop: 94 passed; launcher: 87 passed. API/client lint, format, type and package
checks passed. Mocked provider tests cover online choices and AWS/Azure media
profile changes; no live cloud inference or Pi hardware was claimed.
[Detailed audit and limitations](online-model-switching-review.md).

## Patient voice selection (2026-09-19)

Human-test now uses the saved PMS patient sex for local Piper speech: male Alan,
female Lessac, with a male default and same-language fallback for missing female
files. PMS already supplies the necessary identity field, so no API, database,
prompt or credential changes were required. Voices are warmed and cached rather
than loaded for every reply.

Two reviews checked propagation, fallback, cache bounds and existing interview
behavior. Fixed a Windows download-cleanup handle leak and verified five retries.
All 114 desktop tests passed with real voice synthesis enabled; lint, formatting,
types, build and installed-voice checks passed. Hindi speech and live hardware
verification remain outside this change. [Audit and evidence](patient-voice-review.md).

## Patient LLM latency (2026-09-19)

Enabled a bounded 256 MiB native prompt cache and avoided a second completion for
single exact patient attributes. Narrative and mixed questions retain routing,
generated wording and the existing validation/fallback path. GPU sharing, patient
context, authorization, quotas, token limits and uncertain-submit handling remain
in place. Added explicit wording-call timing and a reproducible native benchmark.

Eight sampled turns averaged 3.75 s before and 2.38 s after on the existing
16-layer GPU allocation, with all expected topics selected. Two reviews completed;
updated old call-count expectations and verified one/two-call usage through mocked
Azure/OpenAI paths. API coverage was completed in parts after interruption: 282
enabled cases covered by the broad run, focused fixes and 87 resumed checks; one
ASR integration check skipped, native Qwen checks exercised. Desktop 114, launcher
87 and local LLM 35 passed; static/package checks passed. Review-owned services
were stopped. [Measurements, exact verification parts and limits](llm-latency-review.md).

## Local patient output defaults (2026-09-19)

Set local patient routing to 75 output tokens and generated answers to 100.
New local PMS connections and the standalone console default to 100; existing
local patient connections receive the caps after PMS restarts. Smaller explicit
limits, cloud allowances, the 2,048-token context and conservative quota accounting
remain intact. The benchmark now imports the production caps. Earlier latency
measurements used 96/192 and were not rerun for this defaults change.

Reviewed request construction, effective local configuration and documentation.
The JSON/SSE regression asserts the actual outgoing 75/100 limits. Focused API
checks: 73 passed, including disposable PostgreSQL integration and mocked cloud
compatibility; no selected checks skipped. Local LLM: 35 passed. Ruff lint/format
and mypy passed after correcting mixed line endings in two edited Python files.
No application database, running model or cloud service was changed.

## Hindi patient speech installation (2026-09-19)

Installed male/female Hindi Piper voices and retained both English voices. Added
pinned nested bzip2 archive support to the existing installer, with exact member
selection, individual hashes and safe temporary-file cleanup. Two reviews checked
installation integrity, language/gender routing, cached loading and existing
playback controls. Human-test: 120 tests passed with real synthesis enabled;
lint, format, types, offline build and installer verification passed. Native Hindi
WAVs and a real laptop output-stream check completed. No API/database changes or
live cloud/Pi checks. [Audit and measurements](hindi-voice-review.md).

## Setup navigation and answer latency (2026-09-20)

Confirmed that setup saving resets history and reuses application/model resources;
15 repeated desktop transitions showed no timer/task accumulation. Twelve fresh
native Qwen patient requests stayed stable across three rounds. Found excessive
CPU work in default resident Piper thread pools. Added a two-thread CPU session
loader with idle spinning disabled; isolated Hindi synthesis became faster and
the two-second idle sample fell from 5.313 CPU seconds to zero. This removes a
source of competition with Qwen, without claiming a measured full-interview gain.

Coalesced pending voice work and discarded obsolete warmups on Stop/Back so a new
answer cannot be dropped behind stale loads. Preserved parallel voice selection,
prosody and playback-progress changes, and updated test doubles for those
interfaces. Two reviews completed; final desktop suite: 122 passed, no skips;
lint, format, mypy and offline build passed. No API/database change or live cloud
test. Restart Human-test once to replace loaded ONNX sessions.
[Detailed findings, measurements and limits](navigation-answer-latency-review.md).

## Smaller Qwen and live model switching (2026-09-20)

Installed publisher-verified Qwen3 1.7B Q8_0 as an independent selectable option,
retaining 4B as the default. Added profile, pinned asset, dedicated batches,
installed-model discovery and saved-alias startup handling. Two reviews covered
integrity, process ownership/release, PMS publication, desktop route propagation
and recovery. Fixed inactive/failed recovery being reported as active in the
catalog and made integrity-repair guidance name the selected setup batch.

Native authenticated switching with a fresh disposable PostgreSQL cluster passed
4B → 1.7B → 4B → 1.7B, with unchanged Whisper running on GPU. The old LLM process
exited and GPU memory dropped before each replacement; repeated identical
selections kept the processes. Prerecorded audio produced a patient answer
through PMS after every switch. Standalone CPU and full-GPU 1.7B inference passed;
all test-owned services stopped afterward.

English fixture completions were about 1.9–2.6 times faster with 1.7B. The Hindi
comparison exposed wrong routing for onset and medications: 1.7B had 8/12 expected
topic matches, versus 4B's 12/12. This model limitation remains documented; the
benchmark intentionally flags it and patient guards were not relaxed.

Checks: 37 local LLM, 93 launcher and 12 desktop model tests passed. Focused PMS
checks: 87 passed, two database cases skipped without a disposable test DSN;
separate native integration used only its isolated cluster. API lint/format/types,
affected local/launcher lint/format and Human-test types passed. Parallel voice/UI
work and the application database/model selection were preserved. No live cloud
or Raspberry Pi checks. [Audit, timing and GPU evidence](smaller-qwen-review.md).


## Online Nemotron configuration (2026-09-20)

Configured the requested compatible endpoint/model and optional persisted operator
settings. Review preserved explicit environment disablement, published-profile
precedence, key encryption/redaction and revision-checked publication. Verified
HTTPS through the existing PMS transport; no TLS bypass or transport change was
needed. Launcher regressions: 98 passed. API suite: 154 passed, 129 database cases
skipped without a disposable DSN; lint/format/types passed. Masked key entry,
authenticated JSON/SSE responses and default-profile publication passed against the
requested live Nemotron endpoint with TLS verification enabled. The provider suite
including the added TLS regression passed all 60 tests; final focused launcher
configuration checks passed all 32 tests. A fresh combined startup restored the
online default with existing local speech; patient identity/complaint requests
succeeded in 0.72 s and 4.02 s. Test-owned services stopped afterward. Final review
confirmed route persistence, encrypted credentials and preserved language/media
settings.
[Detailed evidence](nemotron-online-review.md).


## Azure Whisper with online Nemotron (2026-09-20)

Configured the requested Azure resource/deployment with original-language
transcription and encrypted credentials, retaining the Nemotron connection. Live
checks exposed the oversized Azure model catalog, unsupported v1 audio route on
this deployment and an expired identity read during speech status. Fixes add a
1 MiB Azure catalog-only bound, explicit validated deployment API versions and
identity snapshot/reload across the readiness transaction. TLS/DNS protections,
quotas, credential redaction, revision checks and no-replay behavior are retained.

English/Hindi synthetic transcription, Azure-to-Nemotron patient response, and
a fresh cloud-only model startup passed. Human-test now loads Cloud mode with
no local ASR/LLM engine. Full API: 172 passed, 134 DB cases skipped in the no-DSN
run; separate isolated provider/cloud checks: 102 passed initially, followed by
all four readiness cases passing after fixture corrections. Launcher: 102 passed.
Lint/format/types passed. Final review confirmed compatibility, bounded responses,
encrypted credential reuse and fresh authorization; no unresolved findings.
[Full evidence and limits](azure-whisper-online-review.md).

## Final online speech/response review and busy recovery (2026-09-20)

Reviewed the real Human-test controller through Azure transcription, Nemotron
routing/generated responses and retained-result recovery. Fixed confirmed cached
speech authorization after department reassignment, stale transcription recovery
after Reset, and rejection of valid Hindi answers due to Nemotron's inconsistent
optional reasoning-token breakdown. Valid totals remain strictly checked; unknown
breakdowns are omitted rather than reported as zero.

Added the requested in-memory utterance queue with three retries after 1, 2 and
3 seconds for explicit capacity rejections only. The completed speech stage is
reused during LLM retries. Cancellation stops waits; partial output, unknown outcomes,
timeouts, credentials, configuration and daily quotas do not trigger resubmission.
Tests cover queued data, fresh attempt keys, bounded exhaustion and status recovery.

Final API run: 175 passed, 136 DB cases skipped without a test DSN. Separate isolated
PostgreSQL cloud/LLM suites: 125 passed with cloud transports mocked. Human-test:
138 passed, four opt-in installed-voice checks skipped. Lint/format/types passed.
Live English/Hindi identity and generated complaint turns passed, including SSE,
JSON, language preservation, saved-result/audio recovery and fresh Cloud startup.
An observed Azure 429 exhausted its bounded retry budget; separately submitted
remaining checks later passed. Saved model/patient configuration stayed unchanged,
and check-owned services stopped. Final review found no unresolved implementation
issues in scope; physical audio quality and hardware remain unverified.
[Detailed evidence](online-speech-response-final-review.md).

## Local speech and response final review (2026-09-20)

Exercised five installed speech models and both Qwen sizes through the actual
Human-test controller, authenticated audio service, PMS HTTP API and fresh private
PostgreSQL clusters. Twelve audio requests completed, with recognition failures
reported separately from transport success. Replaced model processes exited;
unchanged models stayed resident. CPU-only Qwen and saved-response recovery passed.

Fixed Whisper turbo's Auto detection selecting Urdu for the Hindi fixture: choose
the highest-probability advertised English/Hindi language before decoding text.
Explicit selections and transcription behavior are preserved. Four regressions
and a fresh English/Hindi turbo-to-Qwen flow passed. Nemotron still misrecognizes
the English onset fixture identically in whole-clip and streaming modes; its Hindi
fixture passed. Prior Qwen 1.7B Hindi routing limitations remain applicable.

Final checks: audio 167 passed; launcher/local LLM 139 passed plus 39 subtests;
desktop 138 passed with four opt-in voice skips; API 175 passed with 136 database/
opt-in skips without a dedicated DSN. Relevant lint/format/types passed. Final
inspection preserved authorization, bounds, encrypted credentials and unknown-
outcome replay protection. Saved Cloud configuration hashes stayed unchanged,
and all test-owned services stopped. Physical audio and Pi hardware remain untested.
[Detailed evidence](local-speech-response-final-review.md).

## Local model execution stays on the laptop (2026-09-20)

A profile that publishes a **local** model is now executed by the machine that asks
for the turn, and PMS is never on that turn's data path. Everything else still comes
from PMS for local and cloud profiles alike: device registration, the processing
profile and its published revision, the patient case/persona, the practice selection
and language, the LLM connection with its encrypted credential, policy limits,
retention and audit. Previously the desktop app sent a local turn to PMS
`/llm/completions`, which dialled the laptop's loopback model server — a server a
deployed PMS cannot reach, and a path that placed the prompt and answer in a service
that has no reason to see them.

The two-call patient turn (routing, fact guard, prompt budget, event shape) moved into
the shared `training-contracts` package, so the platform and the laptop build a turn
from the same code. The effective route now publishes `llm.execution`
(`caller`/`platform`), `local_port` and `local_context_tokens`; the credential is never
part of a route, and Human-test reads its own model server's key from
`HUMAN_LOCAL_LLM_KEY`. Only two things legitimately differ between hosts, both owned by
whoever runs the model: a local call's output allowance (75 routing / 100 voice, because
llama.cpp counts reasoning inside the allowance) and prompt measurement (llama.cpp's own
tokenizer versus the conservative remote estimate).

The boundary is enforced in four independent places: `/llm/completions` refuses a
`local_llama_cpp` connection with 409 `llm_local_execution_required` and creates no
request row; connection status reports `declared` with `inference_verified: false`;
the provider transport refuses loopback/private/reserved destinations outright; and
endpoint configuration accepts a loopback base only for the declaration-only local
provider. A local turn therefore consumes no quota, holds no endpoint slot and has
nothing to recover or replay.

So that training activity stays visible when the model never leaves the laptop,
forward migration `0016_local_turns` adds an append-only, text-free record
(`POST /organizations/{org}/llm/local-turns`): counts, timings, the authored routing
outcome and the identity of route, connection and practice snapshot. The schema forbids
unknown fields, a trigger rejects every `UPDATE` and allows `DELETE` only after
`expires_at`, the API role holds `SELECT, INSERT` only, and retention deletes expired
rows. Reports are accepted only for a revision whose published LLM really is local, only
for the revision/connection pair the profile published, only within 55 minutes, and are
idempotent on `turn_key`. The record is stored as reported: the platform was not on the
data path and cannot attest it, and a configuration edit made a moment later must not
erase a turn that already happened. Failing to store it never costs the learner an
answer they already have.

Reviewing the finished work found and fixed three real problems: the new table had no
runtime grants (503 at first use), the `/local-turns` scope check did not reject an
inactive or unknown department the way platform-executed turns do, and the latency
benchmark still drove the PMS provider path at loopback — it now runs the laptop path
(`human-test/scripts/benchmark_patient_latency.py`) and measures the same pipeline.
Deployment and desktop documentation that still described PMS calling the local model
was corrected.

A second review pass over the finished implementation found three more, each fixed here:

- **The report schema refused the fact guard's own outcome.** When the spoken call ran but
  `spoken_answer()` rejected its wording, the pipeline reports `scripted_case` with
  `provider_calls: 2`; the endpoint required generated wording for any two-call turn and
  answered 400. Exactly the turns the guard acted on were the ones that could not be
  recorded. The rule now reads: a routed topic, a matched routing outcome and a case answer
  go together; generated wording spends both calls; a second call only ever speaks routed
  facts. `test_local_parity.py` now drives every outcome the shared pipeline can build
  through `LocalTurnEvent`, so the pipeline and the report contract cannot drift again.
- **The launcher never exported `HUMAN_LOCAL_LLM_KEY`.** The documentation and the desktop's
  own error message both said the stack launcher supplies this laptop's model-server key, but
  `human-test/scripts/demo.py` did not put it in the desktop environment — so every question
  on a local profile would have failed with "start it with the stack launcher", and no
  `--check` run would have shown it, because `--check` never asks a question. The key is now
  part of the handover (a private `human.env`, alongside the tokens already there) and a launcher
  test asserts it survives the credential-stripping handover and is what
  `human_test.config.Settings` reads.

  The first attempt at that fix landed in `Demo.start()` — a startup path the launcher never
  takes. `main()` always passes a bootstrap `--processing-mode`, so `Demo.start()` had delegated
  every real launch to `model_startup.start()` since PMS-published profiles were introduced, and
  its 190-line body was dead code that still looked authoritative. The export now sits in
  `model_startup.start()`, guarded by `required_services(route)["llm"]` so a cloud profile does
  not carry this laptop's key, and reads the file through one `local_model_key(root)` helper
  shared with connection bootstrap. The dead body and the duplicated environment dict were
  deleted, leaving a single startup path — two paths were the reason a fix could be applied to
  the wrong one and still pass its test.
- **A slightly fast laptop clock silently dropped every record.** `occurred_at` had to be at
  or before the platform's clock, so a laptop seconds ahead lost all of its turn metadata. A
  report up to five minutes ahead is now stored at its arrival time and anything further off is
  still refused; the 55-minute backward window is unchanged.

Two smaller corrections: the desktop swallows an unexpected report-shape error instead of
turning it into a failed turn after the answer was already delivered and spoken, and the
boundary document now records the one display-only difference that remains (a plain local
turn with no case arrives in the window in one piece, because the local client buffers and
validates the whole response, while a cloud turn's deltas stream through PMS).

Verification: PMS **335 passed, 1 skipped** against a disposable PostgreSQL 17 cluster,
including the local-turn and host-parity cases (identical prompts and identical events
apart from the two intended differences) and the platform-refusal cases. Human-test
**184 passed, 6 skipped**; launcher **103 passed**. Lint, formatting and mypy are clean on
both sides. Opt-in real-model coverage moved to `human-test/tests/test_native_local.py`,
where the turn actually runs, and `platform/api/tests/test_offline_native.py` now asserts
the real ASR → desktop → resident Qwen round trip leaves PMS holding metadata and zero
`llm_requests` rows. After the launcher correction above, launcher **103 passed** again
(three consecutive runs; one pre-existing loopback flake in the mailbox test passes in
isolation) with human-test **184 passed, 6 skipped** and clean lint, formatting and mypy.
PMS sources and migrations were not touched by that correction, so the platform run above
still stands.

A real local turn was then run against the resident Qwen3 4B (37 layers on GPU) through
`human-test/tests/test_native_local.py` with `HUMAN_TEST_NATIVE_LLM=1`, which needs no
database: eight questions on the dry-cough case all routed correctly. `name`, `age` and
`temperature` answered from exact authored facts in one call (282–297 ms); "What did you eat
yesterday?" and "When did you sleep last night?" spent the second, spoken call (890 ms and
1,157 ms total); `hmm`, "turn to your left side" and an out-of-scope question answered from
authored `case_backchannel`, `case_command_ack` and `case_clarification` text with no second
call. The Hindi question was answered in Devanagari keeping the authored 35. Both prompts were
measured with `method: native_tokenizer` (routing 729 tokens, voice 134, inside the 2,048-token
window), and the reported record carried no question or answer text. That run also fixed a
defect in the opt-in test itself: its default model was `qwen3-4b`, but PMS publishes the served
alias `qwen3-4b-local`, so the check failed readiness out of the box for anyone who ran it
without overriding `HUMAN_TEST_LLM_MODEL`.

Not verified here: `start\start-human-test.bat --check` for a local and a cloud profile.
The attempt was made and refused at the first step — `postgres.exe` prints "Execution of
PostgreSQL by a user with administrative permissions is not permitted", so the launcher's
private cluster cannot start from this session's console. Run both `--check` modes, and one
real local question, from a normal non-elevated console. The Raspberry Pi capture/speech
code is planned separately. [Boundary, enforcement points and test map](local-execution-boundary.md).

## Human-test camera layout (2026-09-20)

Reorganized Conversation into a full-width control bar and two panels, with about
60% of the width reserved for the left manikin/instructions and 40% for the right
question, answer and camera. The recording path spans the right panel below the
capture controls and above a bounded 200×150 preview. Recording dimensions and
privacy/lifecycle behavior are unchanged.

Native layout checks passed at 1080×800, 1180×860 and 1440×900 with Models visible,
including containment, full button labels, larger-left proportions and path order.
Real webcam preview and three playable recordings passed, including stop/restart,
Back and Close; temporary camera media was deleted. Generated-frame native checks
passed after the final path placement. Full desktop suite: 170 passed, six opt-in
voice/model skips; final video suite: 15 passed. Final lint/format/types passed.
Screenshots contain generated frames only. No cloud, database or Pi checks were
needed for this presentation change. [Evidence](human-test-camera-layout-review.md).

## Five speech/response retries with paused audio (2026-09-20)

Human-test now retains the current input across five retries after 1, 2, 3, 4 and
5 seconds. Capture closes before uploads, and the window pauses microphone and
speaker activity throughout retry waits/requests, shows accurate waiting/active
status, and provides a cancellation button for spoken and typed questions. Typed
questions also stop previous playback. Success dispatches one final spoken answer;
exhaustion restores Start microphone. Unknown outcomes and partial responses remain
protected from replay.

Desktop suite: **184 passed, 6 opt-in skips**; lint, format and types passed. The
native Tk check with controlled busy HTTP responses and real waits passed recovery,
retention, cancellation, playback/capture interlocks and final exhaustion. Both
stages measured approximately 1, 2, 3, 4 and 5 seconds between attempts. No live
provider or database changes/checks were required. This supersedes the earlier
three-retry behavior. [Evidence](online-busy-retry-review.md).

## Concise patient clarification (2026-09-20)

The long stock unknown-question response is now rendered as "Sorry, doctor, I'm
not sure. Please ask about my symptoms or medical history." The shared patient-turn
code also shortens its matching Hindi translation. Exact matching preserves custom
authored wording, including replies that extend the old stock prefix. Rendering
does not mutate saved documents or require resaving setup. Frozen migrations and
previously cached results retain their original text.

Regression checks cover all nine 0014 case documents in English, Hindi and automatic
language mode, unknown questions, malformed routing and unauthored topics. They
verify the exact answer, one routing completion with no extra spoken completion,
answer-source metadata and snapshot preservation. Existing command, backchannel,
boundary and factual-answer tests remain passing. Review confirmed both execution
hosts use the shared renderer and that no authorization or database write path changed.

Verification: full API suite **192 passed, 158 skipped**; desktop local-execution
and conversation-flow suites **39 passed**. No disposable `PMS_TEST_ADMIN_DSN`
was configured, so database integration checks were skipped. API Ruff lint/format
and mypy passed, as did the changed shared module's checks. Initial `uv` commands
could not access its cache in the sandbox; approved reruns passed. Model calls were
mocked; no live cloud, model, microphone or Pi verification is claimed.

## Occasional patient speech gestures (2026-09-20)

Human-test adds one occasional wrist or index-finger movement during patient
speaker playback, with a mandatory still reply afterward. The existing speaker
progress counter gates motion without modifying audio processing. Review covered
silent recovery, voice samples, muted/unavailable output, retries, cancellation,
navigation and timer cleanup. No API, database, authorization or model-call path
changed. Desktop checks: **197 passed, 6 opt-in voice/model skips**; Ruff lint,
format and mypy passed. Native Tk geometry checks preserve face animation and
canvas item count. [Behavior and performance evidence](patient-gesture-review.md).

## Organization online request and total-token allowance (2026-09-20)

Final agreed policy: 5,000 accepted online completion requests and 5,000,000 combined
input/output tokens per organization per UTC day, shared across its users/devices.
Local execution is exempt. A patient turn counts as one accepted request, while
all routing and voice usage contributes tokens. Concurrency slots, authentication,
scope, lifecycle, lease fencing and per-call prompt limits remain enforced.

Admission reserves combined capacity under the existing organization lock;
complete successful provider usage settles once with the result/audit transaction.
Missing, invalid or unsuccessful usage retains the reservation. Replays do not
recharge; rejected admissions do not submit inference or add a request. Migration
`0017_llm_total_quota` adds two fields, preserves old fields, backfills trustworthy
historical totals and bounds unknown history conservatively. Known local history
is exempt. Runtime grants already cover the columns and readiness requires the new
head. Config/examples/runbooks use `PMS_LLM_DAILY_TOTAL_TOKENS`; the output-only
setting is obsolete. Desktop errors distinguish request and token limits and show
the 00:00 UTC reset time.

Review checked tenant/member isolation, concurrent admission, settlement integrity,
UTC rollover, missing usage, replay, one/two-call patient accounting, local exemption,
append-only terminal records and populated migration preservation. The full API run
completed with 362 passed, four fixture failures and one skipped. The four tests
stubbed prompt fitting without supplying its required remote context; the fixtures
now explicitly set 8,192 tokens. All 37 patient regressions passed on rerun. Combined
final coverage is **366 passed, 1 skipped**, with no database tests skipped. The one
skip is the opt-in native ASR/Qwen roundtrip. Standalone populated migration testing
also passed. API Ruff lint/format and mypy passed; the two subsequently adjusted
fixture files passed their relevant lint/format checks.

Desktop retry/error-message checks: **31 passed**. Launcher settings checks:
**34 passed**. Offline simulation reviewer/HTTP-observer checks: **8 passed**.
The observer retains only bounded error identifiers from failed API responses and
does not consume successful SSE streams, so human-readable quota messages cannot
misclassify a final quota rejection as a recovered earlier speech-busy failure.
Changed desktop files and simulation scripts passed lint/format checks. The test
server was an isolated disposable PostgreSQL cluster on port 55445; application
data on 55444 was never used by destructive tests.

After the user's pause, current source was reread before narrow edits. Hashes
confirm their recent app, capture, configuration, cloud-audio, launcher-test and VAD
documentation files stayed unchanged. Existing TODO content was preserved verbatim
with this follow-up appended. The active demo already had `0017_llm_total_quota`;
read-only inspection confirmed 5,000/5,000,000 defaults and readiness HTTP 200, with
52 accepted requests and 111,355 tokens charged/reserved in that snapshot (62,203
reported plus 49,152 retained for three uncertain failures). The upgrade helper
refused the running stack before making changes, so no restart or new backup was
performed by it. No live provider inference or new 25-question cloud run was made.

JUnit, raw logs, preservation hashes and demo inspection evidence are under
`.test_artifacts/org-total-token-quota/`. Remaining fixes and repeat-run instructions
are in the [fix plan](simulations/alex-cardiology/fix-plan-2026-09-20.md). Upstream
speech throttling and complete live audio correctness remain unverified after this
quota change; the existing baseline is unchanged.

## Speech retry rounds and centered status panel - 2026-09-20

Cloud speech retains the same bounded WAV across ten rounds of five retries,
waiting 1–5 seconds within each round and three seconds between rounds. There is
one initial submission: 51 submissions maximum, with 177 seconds of scheduled
waits plus request time. Response models retain their five-retry policy. Only
explicit capacity rejections can be resubmitted; quotas, authorization failures,
partial delivery and unknown outcomes still stop. Definite rejected attempts get
distinct request keys; the latest recovery key is retained.

Structured retry events drive a bordered panel centered below the conversation
toolbar. Its clock animates, the countdown follows each retry/round wait, and the
elapsed timer continues across rounds. Request-in-progress text replaces the
countdown while submitting. Cancel uses the existing task cancellation path;
success, exhaustion, terminal errors and shutdown hide the panel and cancel its
timer. The simulation records these events and budgets all allowed speech and
response attempts before its watchdog can stop a turn.

Verification: **267 desktop tests passed, six skipped** (two opt-in resident Qwen
checks and four installed-voice timing checks). The focused retry suite contains
52 passing cases, including final-round success, exact exhaustion, non-default
settings, cancellation in/between rounds and unknown outcomes after recovery
attempts. Retry/playback checks passed together (68 passed, four opt-in voice
checks skipped); the three desktop workflow tests passed after layout refinement.
All nine offline simulation checks passed. Desktop lint/format and mypy (19 source
files) passed; the changed simulation scripts passed lint/format.

The final native Tk smoke test passed with actual 1–5 second waits and the
three-second round pause, synthetic PCM and mocked HTTP. It verified the panel at
1080×800 and 1180×860, toolbar clearance, moving clock, countdown changes, recovery,
exhaustion, Cancel during the round pause and microphone/speaker interlocks.
Review found unnecessary repeated placement during geometry changes; the panel
now updates placement only when needed. The test waits for Tk mapping and cancels
the panel's timer through its owner before cleanup. Final screenshots were
visually inspected; earlier geometry-timing test failures were resolved.

JUnit reports, before-edit snapshots and the review diff are in
`.test_artifacts/speech-retry-rounds/`; screenshots and `ui-result.json` are in its
`ui/` folder. [Rerun instructions](simulations/alex-cardiology/README.md) cover both
offline checks and the native UI test. Existing capture/controller files remain
byte-for-byte unchanged; configuration, cloud audio and app changes were narrow
additions preserving the user's VAD and readiness work. No API/schema change,
database test, service restart, live cloud call or new 25-question run was made.
Live provider recovery remains unverified.

## Azure Realtime Whisper live compatibility probe - 2026-09-20

The user explicitly requested a live check of their Azure deployment with the
existing key. A bounded probe read the active Whisper connection for the demo
organization and exact supplied hostname using the API database role in a
read-only transaction; credential decryption stayed in memory. No profile,
database record or production adapter was changed.

The supplied `model=gpt-realtime-whisper` URL returned HTTP 400
`OperationNotSupported` before audio submission. The documented
`intent=transcription` endpoint accepted the same key and `session.update` with
type `transcription`, deployment `gpt-realtime-whisper`, English and 24 kHz PCM16.
Three synthetic questions from the existing Alex suite matched their expected
transcripts. First deltas arrived in 1.063–1.078 seconds from audio start; final
transcripts arrived 0.765–0.922 seconds after commit. All three produced text before
audio transmission ended, within one persistent session, without 429s or retries.

The probe is separate from PMS processing/admission, so these direct Azure calls
are not PMS usage records. It retains only allowlisted diagnostics, fictional
transcripts and timings. Offline PCM conversion/redaction checks and script
lint/format checks passed. No full API/database suite was needed for this isolated
probe. Hindi, clinical accuracy, sustained load and end-to-end application behavior
remain unverified; this small success does not establish that earlier throttling
is resolved.

[Results, reproduction and required integration](simulations/azure-realtime-whisper/README.md)
link to the timestamped redacted event evidence. The app still needs a dedicated
streaming adapter, authenticated media path and selection support before rollout.

## Continuous listening, startup recovery and selectable Realtime Whisper - 2026-09-20

Ordinary failed questions now leave an active microphone session enabled, retain
a bordered failure notice, and schedule fresh capture after three seconds. No
unknown audio or response is automatically replayed. The most recent failed
submission keeps its recovery key across subsequent successful questions. Manual
pause/cancel/close is respected, including pending recovery timers; the existing
busy-retry exhaustion exception is retained. Terminal events can replace a stale
display update when the queue is full, preventing a failed turn from leaving the
interface locked. A stale static microphone-off label was removed. Existing VAD,
capture tuning, readiness resilience, speech retry rounds and quota work were
preserved; the controller change only clears the new recovery reference on reset.

The launcher now records the failed model/speech stage and an allowlisted error
code. Five transient cloud readiness failures open with a warning; malformed
configuration, credentials, policy and patient access still block. Its read timeout
is 15 seconds, covering PMS's default two five-second probes and 0.25-second
backoff. Previously its five-second timeout could cut off PMS's second attempt.
The supplied historical launcher log discarded provider details, so this timing
mismatch cannot conclusively identify the cause of that individual failure.

The existing Azure speech connection type now accepts `whisper` or
`gpt-realtime-whisper`, with separate connections shown in Models. The new adapter
opens a transcription WebSocket session, converts the admitted bounded 16 kHz WAV
to 24 kHz PCM16, commits it once, correlates the final transcript by item ID, and
closes the session. Session validation sends no audio. Endpoint allowlisting,
public DNS address pinning, TLS hostname checks, disabled proxies/redirects,
bounded events/deadlines and credential-log suppression were reviewed. Failures
after any audio send remain unknown. The existing PMS admission, recording,
lease, idempotency, tenant/department and lifecycle paths are reused; no database
migration was needed. This is recorded-question transcription, not live partial
microphone captions or persistent sessions across turns.

Verification:

- Full API suite on disposable PostgreSQL port 55445: **402 passed, 1 opt-in native
  audio test skipped**. No database tests were skipped. Final adapter/security
  additions and rerun: **29 passed**, producing **408 distinct passing API tests**
  across the full suite and final targeted run. The PowerShell wrapper reported
  exit 1 because it treated uv's package-build stderr as `NativeCommandError`;
  the pytest log and JUnit report independently contain zero failures/errors.
  The direct final adapter run exited 0.
- Desktop: **281 passed, 6 skipped** (two resident-Qwen checks and four installed
  voice checks). Launcher: **114 passed**. Existing simulation checks: **9 passed**.
- API/desktop Ruff checks, formatting and mypy passed; simulation scripts passed
  lint/format checks. Source snapshots and comparison preserved unrelated files.
- Native Tk [recovery result](simulations/continuous-listening/results/20260920T152438_708293Z/result.json)
  and [screen](simulations/continuous-listening/results/20260920T152438_708293Z/recovering.png):
  one start, three simulated failures, four fresh captures, one spoken answer,
  unchanged failed-turn history and manual pause respected. The existing busy
  window smoke also passed real retry waits, round countdown, exhaustion and
  cancellation. These UI checks used synthetic audio and mocked services.
- Authorized [live adapter check](simulations/azure-realtime-whisper/results/20260920T151606_113741Z/registration.json):
  **4/4** synthetic English transcript comparisons passed with the same encrypted
  resource key. Original Whisper took 2.000 seconds; three Realtime sessions took
  3.515–4.625 seconds each. A separately audited/validated **Azure GPT Realtime
  Whisper** choice was added; the active profile hash stayed unchanged. Provider
  probes are separate verification calls, not PMS usage records. No claim is made
  that this short check resolves sustained throttling or proves Hindi/medical
  accuracy; the full 25-question live app rerun remains outstanding.

Reproduction: [native recovery runner](simulations/continuous-listening/README.md)
and [Azure registration/probe](simulations/azure-realtime-whisper/README.md).
Detailed JUnit, source comparison and aggregate evidence are in
`.test_artifacts/continuous-listening-realtime/`. Close Alex and its launcher,
then launch again to load the updated API/desktop code; existing running services
were not interrupted.

## Cloud/local switching and local cleanup — 2026-09-20

Fixed the cloud-to-local occupied-port failure and the missing laptop-key handover
from a cloud-started desktop. Added **Stop & clean local services** to Models,
using authenticated, administrator-authorized, serialized and idempotent cleanup
of the fixed LLM/audio/video service ports. Cleaned services stay stopped until
local activation. Saved profiles, models and recordings are preserved, and local
LLM prompts/answers remain between the desktop and its loopback model server.

Verification: **135 launcher, 283 desktop and 84 API boundary/provider tests passed**;
six opt-in desktop model/voice checks skipped. Native Tk cleanup controls and an
actual Windows listener termination/rebind passed. The user's blocking LLM listener
was stopped and its port verified free. API/desktop lint, format and type checks
passed. No API/schema changes or database integration run; no live cloud/hosted/Pi
claim. Details and native installed-model evidence: [review](model-switch-cleanup-review.md).

## Patient routing quality, per-call budgets and thinking control — 2026-09-20

Diagnosed in-scope questions being answered with the out-of-case clarification. Two
measured causes: the provider is not deterministic at `temperature: 0` (nine of ten
identical calls routed correctly, one refused), and a refused turn stays in the
conversation the router reads, after which the same question routed correctly only one
time in ten. Revised the shared routing rules, split the routing and spoken token budgets
into configuration for local and remote execution, applied one history policy on both
hosts, and added an off-by-default `disable_thinking` option for OpenAI-compatible
deployments.

Verification: a three-session, 150-turn simulation against both configured models, scoring
in-scope recall and guard behaviour separately with one held-out session. Local `qwen3-4b`
is deterministic and improved from 84/93/90/94 to 97/96/96/96 of 111 across history depths
0/2/4/6, with guards from 31-32 to 33-35 of 39. Three cloud repeats of all 150 turns gave
93.7% against 92.5% before, held-out 96.9% against 95.8%, with all 39 guard turns correct
in every repeat and no boundary message ever routed to a topic. The cloud gain is inside
run-to-run noise at three repeats and is reported as such. Thinking suppression was
measured and rejected for this model: three times faster, 4.5% accurate. The 2048-token
local window was verified with llama.cpp's own tokenizer at 1194 tokens worst case.

**409 API tests passed against a disposable PostgreSQL 17 cluster** (one skipped), plus
283 desktop and 135 launcher tests. API lint, format and type checks passed. No hosted
deployment, live Pi hardware or scenario-authoring change. Details, per-arm tables and
limitations: [review](patient-routing-quality-review.md).

## Continuous listening and truthful status — 2026-09-21

The microphone shared a lifecycle with transcription, answering and playback: it was opened per
question and closed again while that question was processed. Idle capture also gave up after
five seconds and reopened 400 ms later, so a question begun in that window lost its opening
syllables, and in cloud mode the device was already released before the network request. The
status badge mapped three states and sent everything else to "Ready", so a working machine
looked idle while the line above it showed the truth.

One stream is now held open for a whole interview. A reader task owns the device and keeps a
500 ms pre-roll behind the gate so speech onset survives; one worker consumes finished
questions in order, owns no device, and takes typed questions through the same queue so the
conversation history cannot be reordered. Idle silence makes no request and reopens nothing.
The duration limit and driver-overrun budget became per question, a failed question leaves the
session listening, and the microphone and processing pipeline report on separate surfaces. The
playback guarantees are unchanged but now kept by muting instead of closing: the patient's own
answer is never captured back, and a device that stops progressing releases the microphone
rather than stranding input.

Stated plainly: speech during playback is still not captured. This removes the idle gap and the
processing gap, not the playback gap, which needs tested echo cancellation or a verified
headset mode.

Verification: **296 desktop and 135 launcher tests passed**, including eleven new listener tests
driving a scripted device - two minutes of silence, speech long after the old cutoff, pre-roll
onset, endpoint, refusal rather than truncation, operator send-now, playback muting, queue
saturation, device failure and per-question loss accounting. Desktop lint and format pass. No
real microphone, no live cloud or hosted run, and no API or schema change. One pre-existing
minute-rollover flake in `test_video.py` is recorded. Details and limitations:
[review](continuous-listening-review.md).


## GitHub device-poc import (2026-09-21)

Prepared the existing standalone workspace for publication into
`O230008-CTO-10006ZE690/Pratham-POCs`, branch `main`, folder `device-poc/`,
using the billing workspace's existing SSH host alias and Git identity. Local
source paths are retained. The publisher preserves all unrelated remote root
entries, validates both fetch and push destinations, rejects unexpected changes
inside `device-poc/`, and uses fast-forward publication without automatic retries.

Expanded the root ignore rules for credentials, private bootstrap configuration,
dependencies, runtime data, recordings, downloaded models, caches, and generated
verification/build artifacts. Source JSON, example environment files, dependency
locks, migrations, SQL, tests, documentation, and illustrative images remain included.
The import contains 457 files and 13 parseable JSON files. No ignored files were
staged. A credential-pattern scan found only test sentinels, validation URLs, and
the CI-only PostgreSQL password; this is a scoped pattern review, not a guarantee
that arbitrary embedded secrets can be detected.

Verification: all six `start/tests/test_publish.py` tests passed against disposable
local Git repositories, covering dry runs, committed-only mapping, idempotency,
preservation of billing/root files and later unrelated edits, refusal of remote
device changes, existing folders without state, incorrect push destinations,
and concurrent push rejection. Lint and format checks pass for the new publisher
and tests. Changed setup/documentation files pass whitespace inspection. The full
initial import retains three pre-existing whitespace diagnostics in
`device/audio-process/pyproject.toml`, `docs/platform-service-plan.md`, and
`platform/db/table-fields.md`; no unrelated formatting was changed.

No application behavior or schema was changed. Application tests, PostgreSQL
integration tests, cloud services, deployment, and hardware checks were not run
for this repository-binding task. The nested GitHub workflow is preserved as
source; it does not activate GitHub Actions from inside `device-poc/`.
See [publishing instructions](github-publishing.md).

## Local conversation history — 2026-09-21

Implemented optional client-reported text archival alongside the existing text-free local metrics contract. Local inference remains on the desktop. Review found and fixed UI backlog exceptions propagating into recording, historical department defaulting during delayed uploads, and malformed recovery/HTTP payloads terminating the uploader. Isolated PostgreSQL verification uses the owned disposable server at port 55446 under `.test_artifacts/local-history-20260921/pgdata`; the application database is not used for destructive tests. The evidence and remaining operational limits are recorded below.


Review fixes:
- A full UI event queue could propagate a status exception into a completed turn. History notifications now tolerate unavailable UI delivery; the recorder also retains a failed-save count for the History view.
- Delayed uploads could adopt a new default department. Archive uploads now require their explicit historical scope and recheck current membership before idempotency lookup.
- Malformed recovered records, identity responses or acknowledgements could stop background recovery. Recovery validates and quarantines damaged files; malformed HTTP replies remain retryable without replaying inference.
- Slow receipt cleanup could repeatedly POST an already accepted exchange. The uploader now waits for the disk receipt; failed deletion suppresses further uploads during the process and leaves the identical durable record recoverable after restart.
- Failed/cancelled turns retain input and outcome without inventing a completed answer. Exact final authored/generated text is captured independently of internal routing output.
- Concurrent work added migration 0019 while rollout was underway. Readiness and current-head references were aligned with that migration; its existing changes were preserved. The archive migration remains 0018.

Verification evidence under `.test_artifacts/local-history-20260921/`:
- The full API run completed with 421 passed, one failure in the new test's invitation-token fixture lookup, and one opt-in native audio integration skip. The fixture was corrected. The final archive + migration rerun at the current head passed all eight tests with no database skips (`api-current-head.log/xml`); the archive-only rerun also passed all seven tests. This records the full run and the corrective rerun separately rather than claiming one clean final full-API run.
- Final desktop archive/local-execution tests: 35 passed, including queue pressure, exact answer pairing, failed/cancelled outcomes, Unicode display, restart, identity mismatch, lost/malformed acknowledgement, slow cleanup and failed unlink. Launcher tests: 135 passed.
- Real local Qwen verification: two resident-model tests passed. The dedicated real HTTP API/PostgreSQL test passed: an online pair matched the delivered answer, an offline pair survived desktop restart, and recovery uploaded it with no model client initialized and no PMS inference request. Only fictional test questions were used. The separate 11-pair native capture timing test used a mocked archive destination, explicitly distinct from the real archive test.
- Hidden Tk smoke rendered ten exact input/response pairs and selected the correct detail row. No visible user window or speaker playback was started by this check.
- Final API Ruff check and format check passed (121 files); API mypy passed (60 source files). Desktop Ruff check and format check passed (75 files); desktop mypy passed (23 source files).
- A snapshot diff confirmed the frozen SQL baseline remained unchanged. Existing migrations were not rewritten. Concurrent silence/routing/quota edits were preserved; broad checks were repeated as their files changed.

Performance evidence (`benchmark-final.json`, 100 synthetic exchanges per mode): enqueue p99 was 0.399 ms with successful archival, 0.400 ms with unavailable PMS, and 0.105 ms with a slow disk. Every mode reported zero failed saves and zero incomplete shutdown flushes. Updated history-disabled turn-return p50 was 30.966 ms; successful archival was 30.804 ms; the pre-change controller was 93.022 ms because it awaited the simulated metrics request after answer delivery. Answer delivery p95 was 32.026 ms disabled versus 37.470 ms saved in this run, showing background scheduling overhead rather than proving zero impact. Successful archival used 1,828 ms process CPU and 720,426 bytes peak traced Python allocation over the 100-turn stress run. The real Qwen comparison (ten alternating samples per mode) measured median turn return at 1,585.17 ms disabled and 1,543.97 ms enabled; that small sample is compatibility evidence, not a guarantee of identical latency. Persistence performs no disk or HTTP waits on the response task.

Private local demo rollout: a private PostgreSQL backup was taken before upgrading, runtime grants reapplied, and both history flags enabled. Readiness and authenticated history identity/list reads passed on current head 0019; all 26 existing text-free metrics records remained present. There were no historical paired-text records to backfill. The smoke API and owned native model were stopped afterwards; the launcher remains stopped, ready for the next normal start. No cloud calls or production database tests were performed.

Operational limits remain explicit: memory-only queued records can be lost on a crash; disk exhaustion is reported without failing the answer; finalized files are private OS-protected text, not application-encrypted; stale authentication needs renewal and restart; local pending retention is at most 24 hours and server retention at most seven days, tightened by tenant policy. Microphone/speaker end-to-end and Raspberry Pi/cloud verification remain outside this change.


Final verification closure: the latest broad desktop run reported 321 passed, one failure in a concurrently added test missing its `CONCISE_CLARIFICATIONS` import, and six optional native/voice skips. That import was subsequently corrected in the shared workspace. The final combined archive, local-execution, flow and cloud-model regression rerun passed all 79 tests (`desktop-regressions-final.log/xml`), including the failing test and the two earlier silence-behavior assertions. Two of the six optional checks were also run separately against the resident local Qwen model and passed; the four installed-voice synthesis checks remained skipped. API native audio integration remained skipped; the new text/native archive test passed separately. The owned disposable PostgreSQL server at port 55446 was stopped after verification; the private application database at port 55444 was left running. All archive implementation phases and review fixes are complete.

## Patient turn recovery — 2026-09-21

Made the model useful on the turns it was previously failing, without loosening any disclosure
guarantee. Three distinct causes were producing a stock line where a real answer was available,
and one published budget was being ignored.

Changes:
- **The spoken allowance was never wired.** `turn_budget` has accepted `voice_cap` since the
  two-call split, and neither host passed it, so a local spoken call used the shared
  `VOICE_TOKENS` default of 100 — roughly 400 characters of English and considerably less
  Devanagari. An answer that stops on `length` is discarded by the guard and silently replaced by
  the literal authored line, so the cap was quietly converting generated wording into stiff
  scripted text. `patient_voice_tokens_local` (256) and `patient_voice_tokens_remote` (unset, so a
  reasoning model keeps the connection's allowance for deliberation) are now published on the
  route and passed on both hosts. The measured local spoken prompt uses 45% of the window, so the
  larger reserve costs nothing.
- **An unusable routing object is now repaired once.** Eight causes collapse into
  `routing_status: "invalid"` — prose around the object, a code fence, a hallucinated, duplicate
  or over-long topic list, an invalid kind, a missing or extra key, and truncation on `length` —
  and most are formatting slips rather than the case failing to hold the answer. The retry drops
  the conversation to the message being answered, appends `REPAIR_RULE` after the topic index and
  is allowed `repair_budget` — double the routing allowance, floored at it and capped by the spoken
  one — so a truncated attempt gets room (150 tokens local, 1,024 remote) without inventing a third
  configured number. The unusable reply is never fed back. A routed decision is never retried, and
  a second failure keeps the authored clarification.
- **Optional in-character deflection.** `model_options.patient_deflection_mode: "generated"`
  spends the spoken call on an "I did not follow" that names up to eight topic *intents* instead
  of the stock clarification. The prompt carries no authored answer, no persona fact and no
  instructor content, so it cannot disclose a case fact however the model replies; the spoken
  guard is unchanged and a rejected reply falls back to the authored line. Off by default because
  it is a provider call spent on a turn with no fact to speak.
- **An unrecognized utterance answers in character.** The desktop reported "No speech detected"
  to a learner who simply had not been heard. It now speaks a language- and sex-matched request to
  repeat, makes no provider call, and does not enter the conversation — a run of unheard attempts
  must not push the real question out of the history the router sees next. Hindi inflects for the
  speaker, so both forms are provided.
- **Reporting and reservations follow the extra calls.** `frame` counts every completion actually
  spent and adds `routing_attempts`, `routing_repaired_from` and `routing_repair_unavailable`.
  Migration `0019_patient_turn_recovery` widens the recorded call count to three, adds
  `patient_deflection` to the authored outcomes, and raises the reserved-output ceiling to 16,384.
  Admission reserves routing, the repair, and the spoken call when either generated wording or a
  generated deflection is configured.
- **`scripts/audit_patient_index.py`** reports, per case, the topics that can never be routed
  because they are concealed or missing a translation, and every prompt against the window that
  binds it. All 18 shipped cases fit: routing at 55%/71% of the local window for 22- and 32-topic
  cases, the repaired attempt at 83%, spoken at 45% and deflection at 27%, using a pessimistic
  three bytes per token. No shipped case has an unaskable topic, so authoring gaps do not explain
  the reported wrong answers.

Review fixes found in this change:
- `repair_budget` first handed the retry the whole spoken allowance. That reserved 4,096 output
  tokens to emit about fifteen, and the database-backed tests showed it as an authored-mode turn
  reserving 4,608 instead of the routing allowance alone. It is now double the routing allowance,
  floored at it so a connection that speaks in fewer tokens than it routes in cannot shrink the
  retry, and capped by the spoken allowance so it still cannot overrun the connection.
- The repair result was not threaded into the routed-answer paths, so a three-call turn reported
  two. Caught by the new test asserting the count against the runner's own call log.
- A failed repair would have cost the whole turn. The provider has already answered once and
  there is an authored line to fall back to, so a refused or unreachable retry now degrades to
  that line and is reported as `routing_repair_unavailable` rather than counted as a completion
  or hidden. Without this, a transient 429 on the retry would have turned a turn that previously
  returned the clarification line into a failed request.
- The new status string was not in `manikin.PHASES`, so the badge would have held "Transcribing"
  after an unheard question. It is mapped to Ready and `MISHEARD_STATE` is asserted against
  `phase_for` so the two cannot drift.
- Behaviour changes were made explicit in existing tests rather than worked around: the stock
  clarification test now states that `unknown` costs one call and `invalid` costs two, and the two
  silence tests assert the in-character reply while still proving no upload, no transcription
  request and no completion.

Verification evidence:
- Isolated PostgreSQL 17 verification used an owned disposable server on port 55461 under
  `.test_artifacts/patient-turn-recovery-20260921/pgdata`, created and stopped for this change.
  The application database on 5432 was not used. `test_local_turns.py` and `test_migrations.py`
  passed 27 tests against it, so migration 0019 applies on a real server and the widened
  `provider_calls` and `answer_source` CHECK constraints accept the new records and still reject
  an incoherent one. Alembic reports a single head, `0019_patient_turn_recovery`.
- Platform API, full suite against that disposable server: **433 passed, 2 skipped, no failures**
  (21m 28s). The 2 skips are the opt-in native-audio integration checks. An earlier full run
  against the same server had 6 failures, all of them expectations this change moves: three
  reserved-token assertions (which exposed the `repair_budget` defect above), two
  `provider_calls == 1` assertions on an invalid routing outcome, and
  `test_patient_identities.py::test_alex_identity_constraints_and_runtime_access`, which passes
  standalone and in every later run and was cross-test interference in that 94-minute run rather
  than a defect. The fast run without a DSN is 258 passed, 176 skipped. Ruff check and format check
  passed (121 files); mypy passed (60 source files).
- Desktop: the full suite ran 321 passed, 6 skipped, with one failure in
  `test_video.py::test_native_tk_checkbox_preview_stop_and_error` - a `TclError` reporting that Tk
  was not installed properly, raised while the platform database suite was running in parallel.
  That test passes alone and with its whole module (15 passed), is unrelated to this change and is
  in a file this change does not touch, so it is recorded as Tk resource contention rather than
  claimed as a clean full run. Ruff check and format check passed (75 files); mypy passed (23
  source files).
- The frozen SQL baseline was not touched and no existing migration was rewritten. Concurrent
  work in the same worktree — local conversation history, the metrics reporter, and the readiness
  `REVISION` alignment to 0019 — was preserved.

Limits that remain explicit:
- No cloud or local model was called. Every result above is from mocked providers and the seeded
  fictional cases; the repair retry and the deflection have not been measured against
  `nemotron-3-super-120b` or a resident Qwen, so their real effect on answer quality is unproven.
- `start/cloud-models.json` still declares `context_tokens: 8192`. The audit reports 4,964 as the
  minimum for a 32-topic case with a full conversation, so the value works, but the deployment's
  real window was not confirmed and raising it was deliberately left to the operator.
- No confidence signal exists anywhere: `logprobs` is not requested on either host. A confidently
  wrong topic still produces a fluent, guard-passing answer to the wrong question, and nothing in
  this change detects it. Measuring routing accuracy on captured transcripts remains open.
- `routing_attempts` is derivable from the recorded `provider_calls` and `answer_source` but is
  not itself a column, so a repaired turn is identified indirectly in the local-turn records.


## Shared UI import cleanup — 2026-09-21

The user confirmed that only reusable UI components and utilities should remain. The imported code was in `platform/ui/`, with no existing repository consumer. Removed the copied authentication and business-console apps (customer, product/catalog, audit and dashboard screens, session/API adapters and their tests), the duplicate `apps/apps/console` tree, copied dependencies/build output/coverage, JANSO logo/wordmark assets, and catalog-specific attribute/custom-field editors and field-set adapters.

Retained generic form controls, navigation/layout components (including the reusable AppShell component), overlays, tables, filters, charts, themes, formatting, cursor-query state, and presentation-permission utilities. The package is now `@pms/ui`, with matching `pms-` CSS tokens/classes and `pms.` preference keys. Added an npm workspace/lockfile and a single `@pms/ui/styles.css` entry. The consuming application owns branding, authentication, data loading, server permission enforcement, and API limits. Review removed stale exports/comments, orphaned logo styles/tokens and the automatic external Google Fonts import; defaults now use system fonts.

Verification: `npm run typecheck` passed; `npm test` passed 1,541 tests across 44 files. After the final font/token cleanup, all 260 affected tests across six files passed. A package-content/export inspection checked 15 exports and 79 packed files; JavaScript and CSS entry bundles compiled successfully. Remaining source comprises 78 reusable source files and contains no copied application references or automatic external font requests. No backend, database, or deployment verification was needed for this UI-only change.

The previously untracked source was preserved before deletion in the private, ignored recovery archive `.test_artifacts/ui-cleanup-20260921/original-source.zip` (264 source files; generated dependencies/builds/reports excluded). Per-file hashes are in `original-manifest.json`; test and bundle evidence are in the same artifact directory. Future consumers must use the new package and style namespaces; no runnable app shell was retained. Usage and the removal list are documented in `platform/ui/README.md`.


## Shared common control review — 2026-09-21

Reviewed the reusable `@pms/ui` package after the import cleanup. The scope is shared component behavior, accessibility semantics and composition; no copied application or model-specific integration was added.

Confirmed findings and fixes:

- **Form behavior:** `Button` used the browser's implicit submit default, so an ordinary Cancel/action button could submit its surrounding form. It now defaults to `type="button"`; explicit submit/reset behavior is preserved. Loading state cannot be hidden by a caller's `aria-busy={false}`.
- **Field descriptions:** `TextField` referenced a hint that was absent when an error rendered. Native attribute spreading could also replace internal error/loading semantics in both `TextField` and `Select`. Descriptions now merge caller ids with only the rendered internal messages, with component error/busy states taking precedence.
- **Form ownership:** a loading `Select` disabled the native control and mirrored its selected value without copying the external `form` association. The hidden mirror now belongs to the same form; explicitly disabled fields remain excluded.
- **Dialog composition:** hidden inputs, hidden/inert ancestors, disabled fieldsets and negative tab stops could defeat initial focus and wrapping. Empty or busy dialogs had no focusable fallback. Panels now accept programmatic focus; the shared helper filters unavailable controls and traps both Tab directions when empty. Child-consumed Escape is respected and nested dialog Escape does not also close the parent. A shared per-document lock preserves scrolling until the final dialog closes, including out-of-order closing, and restores the prior inline overflow value and priority. Focus restoration carries the original opener through an out-of-order close.
- **Search inside dialogs:** after respecting child-consumed Escape, a closed, empty `SearchSelect` still consumed Escape without doing anything. It now lets that event reach the containing dialog; existing close-list/clear-query behavior remains.
- **Navigation safety:** footer and rail destinations bypassed the URL allowlist. Unsafe destinations now render as plain text. The common validator also rejects slash/backslash destinations that browsers normalize into protocol-relative external hosts.
- **Tabs:** repeated tab keys in separate groups produced duplicate DOM ids, and a removed active tab left the whole group outside the keyboard tab order. Panel-scoped/generated ids prevent collisions; the first remaining tab stays reachable without silently changing the caller's selection. Scope lengths disambiguate ids containing separators.

Compatibility: consumers must explicitly mark submit actions with `type="submit"`. A tab panel now labels itself using `tabButtonId(active, panelId)`, with the same unique `panelId` passed to `Tabs`. These contracts and examples are documented in `platform/ui/README.md`; the imported package still has no existing repository application consumer.

Verification:
- Initial reproductions: 18 failing regression cases before fixes; the follow-up review reproduced search-select Escape consumption and a tab-id separator collision before fixing both.
- Final `npm test` from `platform/ui`: **1,565 passed across 45 files**, including **24 new regression cases**. The new cases exercise native form submission/reset, external forms, accessibility descriptions, keyboard interactions, nested menus/dialogs, hidden controls and React StrictMode cleanup.
- `npm run typecheck`: passed.
- `npm pack --dry-run`, public export inspection and esbuild entry checks: passed; 15 exports, 79 packed files, 78 source files, successful JavaScript and CSS bundles. No copied application references or automatic external font requests were found.
- Final scoped source diff inspected; all reproduced findings were fixed. Private baseline, diff, failing/passing logs and bundle evidence are under `.test_artifacts/ui-controls-review-20260921/`.

Limits: interaction tests use jsdom with the installed React 19 development dependencies; no real-browser layout, screen-reader, React 18 runtime, hosted deployment or consuming-application verification is claimed. No API/database behavior changed, so backend and database tests were not run for this UI-only review. Unrelated worktree changes were preserved.


## Local audio simulation and transcription display fixes - 2026-09-21

Investigated the reported intermittent Transcribing display before preparing controlled audio. Reproduced and fixed a `None` answer-duration division that stopped Tk's event pump after empty recognition, a stale processing badge after transcription failure, and a microphone-reader failure that could strand the active frame iterator or lose its stop notification behind a full queue. Incomplete audio remains refused; no failed or unknown submission is automatically replayed.

Verification: four new regression cases reproduced the defects before the fixes. The combined flow/capture/listening suites passed 88 tests; the full desktop suite passed **326 tests, six optional checks skipped**. Desktop Ruff lint and formatting and mypy passed. No backend/database behavior or schema changed; database integration tests were not run for this desktop change.

A real local Whisper large-v3 CUDA and Qwen3 4B simulation asked 12 spoken questions for each of two fictional seed cases. **24/24 transcripts matched**, no audio blocks were lost, one input stream served the entire run, and the real hidden Tk UI reported zero callback errors. Empty recognition and a subsequent question both completed normally. Post-capture transcription was 0.594-0.844 seconds (median 0.734); the local answer stage was 0.922-2.906 seconds (median 1.125). The saved authored-answer profile selected **22/24** expected topics; both errors were the associated-symptoms question returning symptom-details text. Direct-text comparisons confirmed routing confusion and rejected prompt variants that did not reliably resolve related follow-ups. No speculative prompt or saved configuration changes were retained.

The simulation replaces the physical microphone with paced generated PCM, and uses fixture case publication and a local metrics observer. It exercises production endpointing, the local ASR websocket, controller, native Qwen and desktop display. It does not verify room acoustics, physical microphone quality, audible playback, PMS persistence, cloud services or Pi hardware. See [full questions, answers, findings and evidence](local-audio-verification-20260921.md). All owned services were stopped; the private application database was left unchanged.

## Expanded 50-question local interview - 2026-09-21

Prepared 25 cardiology and 25 respiratory questions before execution, spanning all 32 available authored case topics. Used the same real local Whisper large-v3 CUDA and Qwen3 4B models, continuous listener, controller and hidden Tk UI, with 44 clean, two quiet, two noisy and two paused generated inputs. The saved authored-answer profile and two-message history limit were preserved. Expected topics were used only by the simulation evaluator; the production model never received them. No production routing rules, prompts, case answers or configuration changes were made for this expanded run.

All 50 turns completed, with **42/50 matching topic sets** (cardiology 23/25; respiratory 19/25). Eight failures were retained verbatim: associated symptoms (10, 11, 31, 32, 33), treatment (34), its follow-up (35), and sleep (38). The normalized literal transcript check matched 48/50; manual review found the remaining differences were equivalent numerals and UK/US spelling. The paused treatment question gained an internal question mark, whose effect on routing was not separately isolated. The follow-up follows an already incorrect answer, so its failure does not independently establish inadequate history retention.

No dropped audio or device status blocks, no UI callback errors, no idle-silence submissions, and one input stream opened/closed. Every planned turn reached Complete. Empty recognition produced the repeat request, drained all UI events and allowed the next local question to complete. Transcription finalization was 0.594-1.094 seconds (median 0.829); the answer stage was 0.985-3.329 seconds (median 1.320). Owned model services stopped and ports 8787/8773 closed after the run.

Reviewed all recorded answers and exported the [complete question/answer report](local-audio-50-questions-20260921.md) and [CSV](local-audio-50-questions-20260921.csv). The simulation/export scripts passed Ruff lint and formatting checks. This expansion changes simulation/documentation only; it did not rerun API/database tests or claim physical microphone, speaker, cloud, Pi or persistence verification. The prior desktop-fix test evidence remains separate above. Raw results, per-turn events and generated WAV files are preserved under `.test_artifacts/local-audio-50-20260921/`.

## Nephrology: new category and case topics - 2026-09-21

Changed the simulation to the catalog's unused Nephrology category, with 25 flank-pain and 25 kidney-condition follow-up questions. All 50 phrasings differ from the previous set and cover the 32 available case topics. The harness now validates question-file case/topic identifiers against the existing seed catalog, selects those cases in file order and resets conversation history between cases. The report groups results by case and includes routing status, answer source and model-call counts in the CSV. Production code, prompts, authored case answers and saved model settings were unchanged.

Real local Whisper large-v3 CUDA and Qwen3 4B processed all 50 generated audio inputs using the same authored mode, context 2048 and history limit of two messages. **43/50** exact topic sets matched: flank pain **22/25**, kidney follow-up **21/25**. Of seven mismatches, three returned symptom details for frequency/associated-symptom questions (6, 9, 10); two failed routing validation after two calls and used clarification (32, 34); one treated dialysis history as a movement instruction (36); and one added an unsolicited allergy topic to the correct fluid/salt answer (39). The latter explains 44/50 expected-answer containment versus 43/50 exact topic matches. Question 6 also required a repair and finished with a valid but incorrect topic. The medication name/strength follow-up (38) matched and retained the authored unknown details. Review also noted the existing `as I mentioned` wording in question 11 despite that fact not yet having been disclosed.

Transcripts matched literally after punctuation/case normalization in 49/50 turns; the remaining difference was the equivalent numeral rendering `0 to 10`. All turns reached Complete, with zero UI callback errors, dropped blocks, device status blocks or idle-silence submissions. One input stream served the run and closed. Empty recognition asked for repetition, drained the UI queue and allowed the subsequent local question to complete. Post-capture transcription was 0.625-1.250 seconds (median 0.883); answer processing was 0.922-3.891 seconds (median 1.164).

Verification: Ruff lint and formatting passed for both changed simulation/export scripts. All 50 exported CSV transcripts, answers, cases, expectations and routing diagnostics were checked against raw results and the prepared question file. SHA-256 before/after checks confirmed 37 monitored application/shared-contract/local-model Python and configuration/catalog files unchanged. Owned services stopped and ports 8787/8773 closed. [Full questions and actual answers](local-audio-50-nephrology-20260921.md), [CSV](local-audio-50-nephrology-20260921.csv), and raw evidence/manifests under `.test_artifacts/local-audio-50-nephrology-20260921/` retain the findings. Prior reports were preserved. No API/database tests were needed for simulation/documentation changes; physical microphone, room acoustics, speaker playback, cloud, Pi and persistence verification remain outside this run.

## PMS management API phases 1-7 — 2026-09-22

Implemented the API-only management plan; no UI files were changed as part of this work. Forward migration `0020_management_api` preserves existing OIDC identities and adds explicit local/OIDC account state, Argon2id credentials, rotating local sessions, purpose-bound action tokens, database-backed authentication limits, encrypted durable email delivery, archive/version fields, identity-bound invitations, and platform model definitions. Runtime grants keep credential, delivery, and catalog tables from processing/retention workers.

The API now covers local setup/login/refresh/logout/password recovery and change/email confirmation; global local-user creation/detail/update/archive/restore; membership detail/invitation cancellation/removal/restore; platform organization creation/detail/archive/restore; department detail/archive/restore; device filtering/sorting/paging and DELETE-as-retirement; provider/model catalogs; tenant model bindings; and connection/profile detail, lifecycle, validation, and immutable publication. Catalog categories include text/conversation, ASR, TTS, vision/video/OCR, embeddings, reranking, and image/video generation. Catalog metadata does not enable a missing adapter. Existing OpenAI, Azure OpenAI, compatible/local LLM, AWS media, Azure Speech, Azure Video Indexer, and local processing paths remain the executable contracts.

First review findings fixed: archived organizations, memberships, departments, and users now block access; archive dependencies are checked before changing profiles/connections/models; local/OIDC invitations bind authentication method when email is ambiguous; unknown-account login performs dummy Argon2 verification under a process concurrency bound; searches are case-insensitive and wildcard-escaped; management writes support optimistic versions; model metadata cannot inject credentials, destinations, headers, validators, or code; and expired security/delivery state receives bounded cleanup. The second pass checked route ordering/OpenAPI, secret projections, tenant scoping, refresh replay, last-administrator/database guards, cursor binding, provider/model compatibility, runtime grants, frozen migration history, and packaging. It added the local administrator bootstrap and independent deployed-secret/SMTP requirements.

Final API review found and fixed an administrator-availability edge case: a local identity with incomplete password setup could previously be counted by database last-administrator guards. Database coverage and settings guards now count local administrators only after setup, and tenant administrator assignment rejects pending local accounts. Actor reloads explicitly reject archived users, password recovery performs the same bounded Argon2 work for known and unknown emails, and the runtime role no longer has unused `DELETE` access to local credential rows. Regression coverage checks the migration predicates, rejected pending-tenant assignment, last-usable-admin behavior, and the narrower deployment grant.

Verification from `platform/api`: `uv run pytest -q` passed **266 tests** with **177 skipped**; all skips are opt-in PostgreSQL/live/native checks because `PMS_TEST_ADMIN_DSN` and external resources were not supplied. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/pms_api` passed. `uv build` produced both wheel and source distribution. Focused management/security/provider tests passed 36 with 33 PostgreSQL-dependent skips. `git diff --check` found no whitespace errors. The OpenAPI regression asserts the agreed authentication, lifecycle, device, provider, model, and binding routes.

Remaining verification limits: migration execution, runtime grants, database constraints, concurrent refresh/reset/admin/seat races, and full HTTP local-account flow require the dedicated disposable PostgreSQL server and were skipped rather than run against an application database. SMTP, OIDC, cloud providers, hosted deployment, and physical devices were not contacted. New Anthropic, Gemini/Google, Bedrock, embedding, reranking, vision/OCR, and generation entries are catalog-only until reviewed operation-specific adapters exist. No automatic provider fallback or uncertain external-request replay was added.


## 2026-09-24 - Tenant Excel member imports

Scope: tenant-only role-specific Excel templates, validation and commit APIs; durable import history and encrypted invitation delivery; four-step web wizard and private error/result downloads. New forward migration 0026 preserves existing users, memberships and tenant/subscription state. Single invitations reuse the same preparation rules.

Review 1 (authorization, lifecycle and atomicity): checked human/member permission on every endpoint/download, global-admin exclusion, fixed batch role and department, inactive identity behavior, existing-account preservation, live seat checks, concurrent batches and repeated commit. Confirmed fixes: recheck local-auth configuration at commit, and suppress queued invitation delivery after department deactivation. Added regressions for local-auth changes, one remaining seat under concurrency, runtime worker privilege exclusion and failed-row rollback of account/setup/audits.

Review 2 (untrusted workbooks, delivery failure and UI recovery): checked ZIP/XML bounds, formula-safe exports, error-workbook reuse, saved batch recovery, encrypted tokens, stale send leases, history expiry and response privacy. Confirmed fixes: bound actual cell coordinates as well as row coordinates; mark a damaged encrypted payload failed without holding up later invitations; correct workbook/user-facing punctuation and improve card spacing, download-button separation and role-independent confirmation wording. Expanded the deployment-grant contract assertion for API-only import tables. Added hostile-coordinate and damaged-payload/deactivated-department regressions. Final inspection found no outstanding authorization or data-integrity issue.

Verification (final results recorded below): the real headless Edge/Next/API/PostgreSQL journey covers five paths: sign-in/tenant entry, actual Excel template and upload, validation/errors download, persisted partial import/results/idempotency, and mobile/history recovery. Screenshots and generated XLSX files are local ignored artifacts under .test_artifacts/member-imports-web. SMTP and live identity-provider delivery remain deferred; delivery tests use mocks. The browser test owns and stops its API, and all PostgreSQL tests use the dedicated disposable server on port 56362.

An initial unconstrained parallel UI run hit timeouts in existing tenant/model editor tests; the complete suite passed with two workers without changes to those components. Windows Alembic subprocesses intermittently exited 3221227274 during isolated fixture setup, including outside the sandbox. The final two affected checks passed when rerun without pytest output capture; no application code was changed to mask those setup exits. This was not an application assertion failure. No application database was migrated and no cloud emails were sent.

Final verification: full API suite **343 passed, 245 opt-in tests skipped** without the dedicated DSN/browser settings; Ruff check and format check passed (162 files), mypy passed (71 sources). All **29 dedicated import/workbook/migration checks** passed across the final run, the two setup-only reruns, and the separate maximum-batch test. The expanded regression run also passed all **18 existing people/subscription checks**. Dedicated PostgreSQL cases exercise real runtime grants, upgrade preservation/constraints, tenant boundaries, row rollback, concurrent duplicate/seat behavior, expired validation, identity preservation, encrypted email leases/manual recovery and cleanup. These targeted runs do not imply that all 245 opt-in cases were executed.

Web: **387 tests passed in 55 files** with two workers, TypeScript passed, production Next build passed. The final real browser journey passed all five paths (52.78s); generated template/error/result XLSX files were reopened and inspected for expected sheets/row counts and absence of formula cells. Desktop/mobile screenshots were reviewed. A maximum **200-person local-account import** validated in **1.59s** and committed all 200 invitations in **8.22s**, with the local disposable database and SMTP disabled; this excludes eventual email delivery and is not a hosted performance guarantee. Temporary Next/API processes were stopped and ports 3124/8137 confirmed closed. Deployment still requires migration 0026 and refreshed runtime grants; no application DB connection is configured in platform/api/.env in this workspace.


## 2026-09-24 - Existing content and configuration web management

Scope: existing platform categories, fictional patient identities and embedded case Q&A; explicit language/platform options; tenant patient practice setup, scenario library, provider connections, processing profiles, real departments, sessions/reports/recordings and personal settings. The screens reuse the console layout, UI components and CSS. Migration 0027 adds database-maintained versions to existing catalog records without adding any entity or table. Existing import and human-test work was preserved.

Review 1 (authorization, data integrity and lifecycle): inspected platform versus tenant access, department scope, version checks, concurrent updates, runtime grants, immutable case associations, private media and saved practice snapshots. Fixes include reloading platform authority after the administration lock, checking observed versions before archiving/publishing, retaining prepared documents during case activation, and using actual feedback score values (met/partial/not_met) while excluding unobserved items. Tests cover atomic audit rollback, one-winner concurrent updates, stale draft publication/archive, retained snapshots, safe media metadata and scope-bound session cursors. No platform-administrator bypass to tenant history or media was added.

Review 2 (UI contracts, validation and failure recovery): inspected action payloads against API response shapes, optional credential updates, explicit language selection, read-only tabs, dirty-form handling, error privacy, loading states and navigation permissions. Fixed the practice selection response wrapper and platform configuration version, preserved existing credentials on ordinary edits, kept published tabs navigable, cleared obsolete history entries when knowledge changes, rejected blank catalog descriptions, and added a shared action boundary so interrupted requests leave forms usable without automatically retrying writes. Removed the obsolete preview badge. Reviewed desktop and mobile layouts using local browser artifacts. Final inspection found no outstanding confirmed authorization or data-integrity issue.

Final API verification: `uv run pytest -q` passed **350 tests**, with **254 optional PostgreSQL/browser/live/native tests skipped** in the no-DSN run. `uv run ruff check .` and `uv run ruff format --check .` passed (169 files); `uv run mypy src/pms_api` passed (73 sources). Separately, all **56 targeted catalog/training/scenario/practice/web-management/migration checks** and **4 existing configuration/tenant-management compatibility checks** passed across their final runs using the dedicated disposable PostgreSQL server on port 56362 where required. These include both migration upgrades and API/worker/retention grant boundaries. They do not imply that all 254 optional checks ran.

One isolated PostgreSQL fixture initially exited with Windows Alembic subprocess status 3221227274; the affected check passed on a no-capture rerun. Test expectations were corrected for tenant-not-found privacy, proper run admission and valid media retention fixtures. No application behavior was changed to conceal that subprocess exit. The previous read-only case-table assertion was updated to the intentional, restricted API INSERT/UPDATE grant.

Final web verification: **407 tests passed in 59 files** with two workers, workspace TypeScript checks passed, and the production Next.js build passed. The real headless Edge/Next/API/disposable-PostgreSQL browser check covers eleven journeys: sign-in/context, category lifecycle, patient CRUD, embedded Q&A persistence and activation validation, platform options, repeated practice setup saves, department lifecycle, provider connection lifecycle without contacting a provider, local profile publication/revisions, scenario validation/review/publication/retirement, and history/mobile destinations. Browser artifacts are ignored under `.test_artifacts/catalog-web`.

Deployment limits: apply migration **0027_catalog_management** and refreshed runtime grants to the configured application database before running the updated API. No application database connection is configured in `platform/api/.env`, so no application database was migrated. Cloud providers, SMTP, hosted deployment and physical devices were not exercised. Existing device training sessions still require version-1 scenarios; the new structured authoring UI makes this existing runtime restriction visible rather than changing it. See [web management contract](web-content-management.md).

Final browser rerun against the production Next build passed all eleven journeys in 32.34 seconds. Loaded desktop/mobile screenshots were inspected; the mobile check waits for actual rows before checking overflow. The owned Next/browser/API processes were stopped and ports 3124/8137 were confirmed closed.


## 2026-09-24 - Combined Windows platform launcher

Added `start/start-platform.bat` and its Python supervisor. It resolves paths independently of the working directory, validates local API configuration and installed dependencies, checks ports, waits for API/database readiness, then starts the Next.js development UI with a matching API URL. Existing environment files are not rewritten. Database provisioning, schema migration, administrator setup, workers, Human-test and model startup remain separate.

Review checked secret-safe diagnostics, localhost binding, inherited UI environment, readiness identity, startup failures and process ownership. Windows children wait on a startup gate until assigned to the kill-on-close job, so cleanup includes Node descendants and never stops unrelated services. Follow-up review found and fixed a restart edge case: exclusive bind probing rejected recently closed HTTP connections in TIME_WAIT. Listener probing now permits restarts while still rejecting active listeners; actual service binding handles races.

Verification: all **11 launcher tests passed**, including real Windows descendant cleanup, occupied-port ownership, recently closed connections, schema mismatch, rejected configuration redaction, UI environment isolation, failed second-service startup and successful check cleanup. Ruff lint/format checks passed. Batch help and validation failure were verified from outside the repository root. A real Next.js child reached login readiness, stopped with its descendants and released its listener. The combined check started the actual API, whose readiness endpoint reported `database_unavailable` for the current application configuration; the launcher timed out with a safe diagnostic and stopped its owned API. Full application database readiness/login was therefore not verified, and no database configuration was changed. No cloud or hardware calls were performed.


## 2026-09-24 - Human-test uses the shared platform API only

User requirement: one platform API/database, with database configuration and access confined to backend services. Removed PostgreSQL creation/start/stop, SQL roles/grants/migrations, private API startup, locally signed identities and database retention startup from Human-test launchers. Compatibility demo batches now use the same authenticated API client flow. Human-test runs with its own Python environment and no database-driver/runtime imports. The model-default helper also uses the existing API exclusively.

Review 1 checked all Human-test runtime scripts for direct database access and API-process creation. A regression scans imports and executable names; tests verify client state contains only local companion credentials and never creates pms.env or identity keys. The configured API origin, token and organization are validated without exposing rejected values. Startup reads an existing published profile; it does not create a tenant or bootstrap a profile.

Review 2 checked custom API ports, model switching, reused launcher scope, child environments and cleanup. Fixed model-switching requests to use the configured API origin and ensured restarted audio receives the correct client-state environment file. API/PG/database secrets are stripped from desktop, companion and web UI child environments. Backend API and PostgreSQL are outside every client cleanup path. Existing legacy .local/demo files remain untouched and unused; client files now live under .local/platform-client.

Verification: **134 focused launcher/supervision/local-model/client-boundary tests passed**, **13 desktop model-selection tests passed**, and all **11 platform-launcher tests passed**. Ruff checks/formatting and git diff --check passed for the changed code. The real Human-test batch help works from the Human-test environment; a deliberately invalid client API configuration failed before starting companions and printed no rejected URL/token. API/cloud interactions in launcher tests were mocked; no live inference, hardware, application database migration or data transfer was performed.

The initial broad script run also exposed two pre-existing GPU-policy test failures: test_devices.py expects 16 GPU layers for a small shared GPU, while the committed devices.py already specifies 18. Neither file was changed in this task. The final focused run excludes that unchanged file; this is not a claim that the entire script suite passes. An initial attempt to collect script and desktop tests together encountered duplicate test_local_models module names; they were rerun separately in the appropriate environments and passed.

Operational setup: start/start-platform.bat owns API/UI startup. Then start/start-human-test.bat uses HUMAN_PMS_URL, HUMAN_PMS_TOKEN and HUMAN_ORGANIZATION_ID from human-test/.env, plus optional HUMAN_PROCESSING_PROFILE_ID. A valid platform token and published conversation profile are required. Clients never receive database connection settings. See start/README.md and human-test/.env.example.


## 2026-09-24 - Human-test central API boundary audit and follow-up fixes

Completed a second, deeper audit of startup, desktop API routing, patient conversation authorization, local inference, cloud speech, history outbox identity isolation, model switching, companion control, recovery and shutdown. Human-test has no private platform API, SQL runtime or database lifecycle. Its loopback HTTP mailbox controls local companion processes only; all business reads/writes remain authenticated calls to the configured central API. No backend schema or runtime code changed in this follow-up.

Review 1 removed unreachable demo profile/cloud-connection provisioning, backend environment override helpers, and startup reads of legacy cloud-models.json. This prevents old operator settings or malformed obsolete files from influencing the client. Fixed .env history opt-out being overridden, scoped/size-bounded/redacted startup and model-default API requests, local-model port/caller-execution mismatch, and desktop/API credentials inherited by model children or GPU probes. The central API cannot occupy managed companion ports. Renamed isolated_demo gating to managed_local_services to reflect the actual process-control boundary. Existing private legacy files were not opened, deleted or migrated.

Review 2 found and fixed connection reuse by model name without checking its port, in both local activation and the default-model helper. Port mismatch fails before stopping or publishing models. Running launcher reuse now requires the configured API/tenant, current published profile/revision/hash, and the same login/department. Only a one-way session binding is stored in private status; renewed tokens require restarting the desktop. Explicit department configuration is passed to the child, including environment overrides. Enlarged bounded launcher-status reads to the configuration-response limit so valid published prompts do not break reuse. The companion mailbox's authenticated business-data paths return 404. Final inspection confirmed API/DB remain outside process recovery/cleanup and unknown profile publications are never blindly replayed.

Verification: **169 launcher tests passed** (full scripts suite); **453 desktop tests passed, 6 opt-in tests skipped** (2 resident-Qwen checks and 4 installed-voice checks). Added complete startup coverage against a mocked central API at a custom origin/port, proving all requests are GETs to that origin, platform credentials remain scoped, tenant denial starts no services, and no platform/API environment or database is provisioned. Regression cases cover profile drift, login/department mismatch, history preference precedence, model connection ports, denied/oversized/invalid responses, rejected private-service entrypoints and child credentials. Updated two stale GPU test expectations to the already committed 18-layer policy without changing the runtime budget, and the stale cloud-silence test to require no answer and zero provider calls, consistent with the existing input-ignore behavior. A new oversized-response parametrization initially exceeded Windows environment limits via its generated test ID; short explicit IDs fixed the test harness.

Changed-code Ruff lint/format checks passed and normal git diff --check passed. A diagnostic run disabling Git CRLF normalization incorrectly treated repository CRLF endings as trailing whitespace; no file normalization was performed, and the normal repository-configured check passed. Real batch --help and fail-closed invalid API configuration checks passed with the Human-test environment; no GUI, model, API or database process was started by these smoke checks. No application database migration, disposable database integration, paid/cloud inference, microphone/camera or hardware test was needed/performed for this client-only follow-up. Mocked API tests are not live backend/cloud certification. No background services were left running by this work.

Current architecture/setup: [Human-test API boundary](human-test-api-boundary.md), [launchers](../start/README.md), and [central cloud configuration](cloud-models.md).


## 2026-09-24 - Human-test end-to-end desktop review

Reviewed launcher configuration, patient setup/catalog selection, continuous listening and typed questions, model publication/recovery, answers and speech, history upload/isolation, native animation/video layout, cancellation and shutdown. Human-test remains a client of the central API; no backend runtime/schema change was needed in this review. Existing unrelated workspace changes were preserved.

Review 1 fixed patient identity labels that still named Alex, a patient card populated from the first catalog identity instead of the selected case document, duplicate case titles overwriting choices, and stale patient/vital state after empty or failed reloads. Patient names now follow the saved case; neutral labels are used before selection. Shutdown now closes server conversations within a one-second budget concurrently with local history/metrics flushing, so an unavailable API cannot consume the desktop's shutdown deadline. Unreadable successful model publications now require a refresh instead of permitting replay. Invalid completion reasons are rejected before speech or completed-history insertion.

Review 2 fixed the typed-question entry remaining disabled during a continuous listening session, while preserving busy-retry input locking. Hardened malformed publication IDs and completion-reason types. A model selection saved by the API but rejected/unusable in the desktop also locks further saves until refresh. Regression tests cover both malformed saved routes and application failures. The retry window smoke was stale: its per-turn microphone stub did not intercept the current continuous Listener and could reach the hardware input path. Replaced it with an explicit synthetic continuous listener and a hardware-reader prohibition. Its final successful run is synthetic; the initial failed run is not evidence of hardware quality. The smoke also now checks session persistence and handles Windows minimizing a transparent test window.

Verification:

- Full desktop suite: `human-test/.venv/Scripts/python.exe -m pytest -q -rs` from human-test: **465 passed, 6 skipped**, 105.98 seconds. After the final saved-but-unapplied guard, the affected switching/lifecycle suite passed **29 tests**, including two additional regressions (467 distinct desktop tests passed across these runs). Skips: two opt-in resident-Qwen tests and four installed-voice tests. The focused run reported only a Windows pytest cache write-permission warning; assertions passed.
- Full Human-test scripts suite: **169 passed**, 19.51 seconds. Full start/tests suite: **17 passed**, 53.65 seconds.
- Central API/PostgreSQL: **14 distinct tests passed** across test_human_test_journey.py, test_patient_conversations.py and test_local_conversation_turns.py. The broad run passed 13 and exposed a stale test that deactivated a connection by SQL without its required revision increment. Changed that test to use the real authorized archive endpoint; all three revocation cases then passed. No database test in this selection was skipped.
- The new journey uses the real desktop Controller/PMSClient, FastAPI authentication/permissions and PostgreSQL through a test transport. It saves patient setup and completes one deterministic local turn in each of three categories, uploads and reads all three history records, rejects another tenant and expired login, prevents inference during API failure, ignores empty/thank-you input, and closes HTTP clients/outbox threads. Local LLM responses are mocked, and no central inference request is created. JWT expiry tests account for the server's configured clock leeway.
- Database DSN points only to the dedicated disposable PostgreSQL server on port 56362; SHOW data_directory was verified as .test_artifacts/db-sync-20260922/pgdata. Fixtures migrate fresh databases through 0027 and remove them. The application database and the pre-existing test server lifecycle were not changed.
- Four native Tk smoke scripts passed: model selection/permissions, manikin gestures/layout, synthetic camera recording/playback, and busy retry/cancellation. Layout checks include 1080x800, 1180x860 and 1440x900. Retry checks exercise actual one-through-five-second delays, retained payloads, exhaustion, speaker interlocks and between-round cancellation. Video uses generated frames, not camera-quality measurements.
- Human-test Ruff lint and changed-file formatting passed; API Ruff lint, all 170-file formatting checks, and mypy for 73 source files passed. Normal git diff --check passed. No cloud calls, application migrations, deployment or publishing were performed.

Operational limitation: the normal configured launcher cannot yet start an authenticated session because human-test/.env is missing HUMAN_PMS_TOKEN and HUMAN_ORGANIZATION_ID. The read-only configuration probe stopped before starting services or making API requests. Configure an authenticated central-API login/tenant and ensure the published profile is available before attempting a real session. The automated API journey uses disposable test identities; it does not establish application login readiness, real LLM answer quality/latency, cloud readiness or microphone/camera quality. See [API ownership and startup](human-test-api-boundary.md).


## 2026-09-26 - Database, scripts and models synchronization

Verified the migration chain, SQLAlchemy mappings, SQL installation/grant/verifier scripts, initialization wrapper, API/worker readiness, packaged wheel and local LLM defaults/assets. The current contract is **0028_language_validator_acl, 34 domain tables and 594 columns**, excluding the two role views and public.alembic_version. Fresh-database comparison checks every column name, PostgreSQL type, nullability and primary-key column using the unprivileged API role. Historical baseline adoption also matches the full ORM contract and preserves existing records. The six frozen installer SQL files and packaged baseline are identical; they remain the historical baseline rather than being rewritten into a second current-schema installer.

Review 1 found four concrete failures: the authoring SQL verifier rejected current revisions after 0024; old category/patient grant tests still expected read-only API access despite catalog CRUD; and two language validation functions introduced in 0024 retained implicit PUBLIC execution. Updated the obsolete grant expectations while retaining worker/retention denial and all constraint checks. Added forward migration 0028 to revoke PUBLIC function access, and updated the deployment grant bundle to grant execution explicitly to the API role while denying the worker/retention roles. The migration changes no table, column or application data. The SQL verifier now checks the authoring storage structures/guards directly instead of maintaining a global migration allowlist.

Review 2 synchronized readiness and deployment documentation with 0028, corrected feature-specific documentation that incorrectly described 0025/0026/0027 as the current head, and fixed readiness accepting the first row of a multiple-head Alembic state. API and worker readiness now require exactly one expected revision. Added regression coverage for old, empty and multiple-head states; every ORM column/key; packaged baseline parity; a single migration head; and explicit language-validator privileges. Existing baseline, data-preservation, grant, initialization concurrency/idempotency, catalog CRUD and backup/restore tests remain in force.

Verification:

- Focused migration/schema/grant/catalog suite: **39 passed, 1 skipped**, 109.42 seconds. The sole skip is the opt-in running Next.js catalog browser check (PMS_CATALOG_WEB_ORIGIN absent); no selected PostgreSQL test was skipped.
- Final schema/readiness, Human-test API journey, patient-practice and worker suite: **32 passed**, 165.03 seconds. Four schema tests overlap the prior run, giving **67 distinct passing tests** across the two final runs. The initial four failures above were all corrected and rerun successfully.
- PostgreSQL tests used only the confirmed dedicated server on port 56362, whose data directory is .test_artifacts/db-sync-20260922/pgdata. Fixtures create/drop unique disposable databases and roles; backup/restore preserves encrypted credentials and application records, then verifies API readiness. The pre-existing test server was left running.
- API Ruff check passed; formatting passed for 172 files; mypy passed for 73 source files. Normal git diff --check passed. Dependency deprecation warnings in FastAPI/Starlette test transport do not affect assertions.
- Built the API wheel into .test_artifacts/schema-sync-20260926/dist. All 28 packaged migration modules, frozen SQL baseline files and readiness source match the workspace byte-for-byte. No .env, local state or model files are included. platform/db/init.bat --help successfully resolves the API-owned initializer; no client owns database initialization.
- Local configuration, supported model mapping and API default agree on qwen3.5-4b / qwen3.5-4b-local, port 8787 and the 256-token output default. The installed Qwen model and configured runtime passed manifest/size/SHA-256 verification without starting inference. Existing tenant-published model selections could not be inspected because the application API/database setup is unavailable.

Application deployment remains pending: the API's configured PostgreSQL connection fails with OperationalError, and PMS_MIGRATION_DATABASE_URL is not configured. Read-only connection probes made no changes. Requested that the operator restore the intended database connection and set the owner URL privately in platform/api/.env. Once available, apply the full Alembic chain and reapply platform/api/deploy/grant-runtime-access.sql using the real API/worker/retention roles before starting this API version. No alternate application database, credentials or identities were invented. This verifies source/package/disposable-database synchronization; it does not claim that the unreachable application database was migrated or that live model answers were tested.


## 2026-09-26: Central API development setup and Human-test startup

Configured the existing PostgreSQL installation on localhost:5432 for the central API. The device_platform database was absent; the API-owned initializer created it and applied all 28 migrations. Provisioned distinct pms_owner, pms_api, pms_worker and pms_retention login roles with generated credentials in the ignored API .env. Runtime roles have no superuser, CREATEDB or CREATEROLE permissions. Applied the maintained runtime grant bundle. Human-test contains only API/client configuration and connects to no database.

Added a first-administrator --local-password-stdin bootstrap option for PMS_ENVIRONMENT=local. It requires enabled local authentication and explicit verified-operator acknowledgement, hashes a bounded password with Argon2id, commits identity/credentials/audit atomically and refuses an existing administrator. Other environments reject the option; the SMTP bootstrap path remains available. Created a local development administrator, a Patient Practice Development tenant through the authenticated API, and its published qwen3.5-4b-local profile through the existing API-only model script. Private login details are in platform/api/.local/admin-login.json; the API-issued revocable 30-day session is in human-test/.env. No credentials are committed or printed.

Review 1 found the integration fixture could inherit the development migration URL from .env. It now explicitly uses its disposable database owner URL for migrations and disables dotenv loading for fixture settings; the signing-key unit test also ignores developer dotenv settings. Review 2 found the desktop rejected the example's blank optional connection UUID. Blank optional UUID selections now map to None while malformed identifiers still fail, and mandatory credentials remain enforced.

Verification:
- 34 distinct API tests passed: local bootstrap/management (21 passed initially, one native migration subprocess exited unexpectedly; that test passed on an isolated rerun) plus 12 authentication-session regressions. No selected database test skipped. PostgreSQL tests used only the confirmed disposable server at port 56362, data directory .test_artifacts/db-sync-20260922/pgdata.
- 46 Human-test settings and central-API boundary tests passed, including the copied .env.example and blank/malformed identifier regressions.
- API Ruff checks/formatting and mypy passed (173 files formatted, 73 source files type-checked); changed desktop files pass Ruff checks/formatting.
- Actual central API readiness, administrator login, tenant model-management access and published model retrieval returned success. Desktop settings and required credentials validate in English with published model routing enabled.
- Live start/launch.py --check passed for the existing central API, Qwen3.5-4B, CUDA speech recognition and video recording companion. It stopped its own companions cleanly; the existing API/UI remain available. The desktop window, microphone/camera capture and answer-quality inference were not exercised by this startup check; no paid/cloud request was made.

Concurrent edits under start/ belong to separate work and were preserved. Local configuration and credentials remain ignored. No publishing was requested for this setup task.


## 2026-09-26: Five actual Human-test desktop questions

Started both start/start-platform.bat and start/start-human-test.bat. The platform batch verified/reused the healthy central API and UI; Human-test opened the actual desktop with Qwen3.5-4B and its local speech/video companions. Saved the English Chest discomfort interview through the desktop and submitted five typed questions in one conversation: identity, occupation, presenting complaint, onset/relief follow-up and the capital of France. All five answers matched the configured fictional case or the requested general fact. The name Alex was used for the patient, not the trainee.

Desktop answer times were 6.95, 1.92, 5.03, 4.84 and 2.97 seconds (mean 4.34 s). The central API recorded exactly five local model turns, one model call each, all with finish_reason=stop; model-only totals were 6.609, 1.875, 4.984, 4.813 and 2.844 seconds. Screenshots and the exact question/answer table are in .test_artifacts/live-five-20260926/report.md and results.json. History text storage remains disabled as configured; answers were read from screenshots and timing records fetched through the API. The initial verification harness was corrected to use timing records after discovering transcript storage was off; no turn was replayed. Speaker output was enabled; microphone ASR, camera capture and subjective audio quality were not tested. API/UI and the Human-test desktop/companions were left running for the operator. No application code was changed for this live test.


## 2026-09-26: First-run web administrator setup

Implemented /setup using existing authentication layout, fields, notices and theme tokens. The wizard verifies a private installation key, collects the operator's administrator details, confirms the password, reviews name/email/role and links to sign-in after creation. Fresh /login redirects into setup. Existing installations retain their accounts and normal sign-in. Missing configuration and API outages show actionable states; no default administrator email/password is seeded. init-local enables local authentication and generates an independent PMS_INITIAL_SETUP_KEY, without printing it. Removed the superseded private bootstrap email/password settings.

GET /auth/setup exposes only required/available. POST /auth/setup/verify and POST /auth/setup require the deployment key, use constant-time comparison and database rate limits. Creation hashes the chosen password with Argon2id outside the administration lock, then rechecks for any user under that lock and atomically commits user, local credential and redacted audit. Any existing identity (including archived/inactive/OIDC) closes this initial-install path. Existing last-administrator constraints prevent reopening via ordinary management. Existing tables, migration head 0028_language_validator_acl and runtime grants suffice; no migration or new entity. Trusted CLI compatibility remains optional.

Review 1: database integration caught an unsupported rate-limit category; corrected to the existing account_action category with an isolated initial_setup source namespace. Settings validation now hides raw secret inputs in exception strings. Corrected the retry link to reload the setup status after an outage. Added regression coverage for invalid keys/Unicode, validation and secret redaction, missing configuration, disabled local auth, archived identities, atomic audit rollback, concurrent setup and completed-install rejection.

Review 2: reviewed API authorization/locking/transaction boundaries, Next server-action input whitelisting, same-origin transport, uncached status, redirects and secret lifetime. Made /setup explicitly dynamic. Browser visual inspection found an unwanted outline around the programmatically focused heading and duplicate password-strength advice on confirmation; fixed both while retaining accessible step focus and password autocomplete. No remaining confirmed authorization, integrity or compatibility finding in this scope.

Verification:
- 54 distinct relevant API tests passed: 13 initial-setup, 8 local-bootstrap, 12 auth-session, 14 management and 7 unit tests. No selected database tests skipped. Used only the verified disposable PostgreSQL at 127.0.0.1:56362, .test_artifacts/db-sync-20260922/pgdata, with per-test databases/roles and maintained least-privilege grants. The application database on 5432 was not changed.
- 431 distinct web tests passed: full existing/new suite 427 plus four setup-route tests. An initial unconstrained parallel run timed out two UI tests under host load; all 427 passed with two workers. The 13 affected wizard/route/CSS tests passed again after final visual fixes.
- API Ruff check and format check passed (176 files); mypy passed (74 source files). Web typecheck and production Next build passed, including /setup rendered dynamically.
- Actual headless Edge -> Next server actions -> FastAPI -> fresh PostgreSQL passed on local test ports 3124/8134: root/login redirect, no exposed setup key, wrong-key rejection, password confirmation, desktop/mobile review, exactly one hashed credential plus setup audit, stale-tab closure, authenticated platform login, HttpOnly/SameSite session cookie and fresh-browser setup rejection. Zero page exceptions. Final screenshots and sanitized browser-results.json are under .test_artifacts/initial-setup-20260926. Test-helper SQL placeholder/label-selector issues were corrected before the successful final runs.
- Browser fixture removed its disposable database/roles and private control-key file. Temporary API/UI and the dedicated test PostgreSQL were stopped afterward; application API/UI/Human-test remain stopped. Shared Windows PostgreSQL remains available. No cloud/SMTP/hosted deployment or hardware verification was performed.

No commit or publishing requested for this task. Existing and concurrent changes were preserved.


## 2026-09-26: Follow-up review of pending setup and launcher changes

Reviewed the current uncommitted setup UI/API, local bootstrap, configuration/test isolation, Human-test optional identifiers, launcher reuse/readiness and Windows cleanup changes. Also inspected the requested platform administrator in the application database read-only: exactly one matching active verified local identity, Argon2id hash, completed credential setup, platform_admin tenant-management grant, one provisioning audit event, and current schema. Its credentials and existing accounts were not changed by this review.

Confirmed and fixed two input-validation gaps:
- The local bootstrap command accepted email/name text that could create a credential unusable by the login API. It now uses the existing LocalUserCreate validation before reading/hashing the password or opening a database transaction, normalizes the validated email/name, and returns a static error without echoing rejected values.
- Initial setup did not reject null characters/unpaired Unicode surrogates before hashing or PostgreSQL encoding. It now reuses PeopleInput validation for identity text and SecretStr contents. Invalid input returns a redacted 422 before authorization/hashing/database work. The web installation-key action maps this validation failure back to the installation step instead of advancing to administrator details.

Added five bootstrap identity regressions, one API regression exercising nine malformed-field cases, and a web action regression. Re-reviewed authorization, singleton locking, atomic audit/credentials, setup closure, secret handling, existing-account compatibility and owned-process cleanup after fixes; no remaining confirmed blocking finding in scope.

Verification: 60 API tests passed on the verified disposable PostgreSQL server at 127.0.0.1:56362 (no selected database tests skipped); 432 web tests passed with two workers; 84 relevant Human-test configuration/flow/local-execution/cloud-model mock tests passed; all 21 launcher tests passed, including real Windows descendant cleanup. API Ruff check/format check passed (176 files) and mypy passed (74 source files). Production Next build and subsequent web typecheck passed. An earlier typecheck overlapped Next dev regeneration of .next/types; it was rerun successfully after the launcher stopped and the production build completed.

Actual start/start-platform.bat --check started API 8000 and UI 3000, verified database schema/UI configuration readiness, and stopped its owned services. No Human-test/model companion was started. The disposable PostgreSQL was stopped after tests. Shared Windows PostgreSQL remains running. Local proof is under .test_artifacts/review-20260926; cloud/SMTP, hosted deployment and hardware verification remain outside this review. No commit/publish was requested.


## 2026-09-28: Tenant administration popup and clearer actions

Replaced the bottom administration card with a top-right Tenant administration button and the shared Modal, Tabs, fieldsets, buttons and notices. Subscription now distinguishes capacity/plan changes from dates and status management. Administrators shows current assignments before an explicitly labelled existing-account search and assignment flow. No entities, API contracts or database changes were introduced.

Review 1: preserved permission gates, archived-tenant restrictions, tenant/version arguments and server-confirmed saves. Fixed stale search results and selections, caught rejected search requests, separated load/search/mutation errors and synchronized selected plan after saved tenant changes. Assignment confirmation identifies both tenant and account and explains promotion of an existing membership to tenant-wide administration. Existing administrators cannot be selected again.

Review 2: inspected shared nested-dialog focus/Escape behavior and actual desktop/mobile screenshots; confirmed scrollable modal body, visible dismissal controls and top-right trigger. Reviewed loading/retry, failed plan saves, disabled in-flight confirmations, reopening state and role visibility. No remaining confirmed blocking findings in scope.

Verification: all 50 tenant web tests passed (seven files, including ten popup/detail tests); web typecheck, browser-fixture syntax and diff whitespace checks passed. Live headless Edge against the already-running local UI/API on 3000/8000 passed top-right action placement, plan confirmation/cancel, administrator details/account search, stale-result clearing, empty matches, mobile sizing and focus restoration, with zero page exceptions and zero tenant mutations. Screenshots and sanitized result.json are under .test_artifacts/tenant-admin-20260928. Existing services were left running. The existing mutating browser-console-tenants fixture was updated for the popup/labels but not executed; API/database suites, production build and cloud/hardware tests were not run for this UI-only change. Earlier unrelated working-tree changes were preserved.


## 2026-09-28: Administrator provisioning, self-protection and stalled web pages

Platform user creation now offers Platform administrator or Tenant administrator. Tenant selection loads permitted nonarchived tenants, including inactive tenants awaiting a first administrator. The central API creates the account, credential setup delivery, identity-bound tenant-wide administrator invitation and audits atomically under the existing administration lock. Subscription seats remain reserved for pending invitations. Password setup and explicit acceptance are required; accepting as the first administrator does not activate an inactive tenant. Platform user list/detail responses and filters identify tenant administrators. Self-disable and self-archive are rejected by the API and server actions and unavailable in list/detail controls. No new entity, migration or runtime grant.

Review 1 covered permissions, tenant isolation, pending/expired invitations, archived tenants, concurrent subscription capacity, audit rollback, password setup and the inactive-tenant bootstrap dependency. Added ordinary-member inactive-tenant rejection coverage to bound the administrator exception. Review 2 exercised real browser creation and lifecycle paths, invitation delivery messages, stale versions, modal state, mobile layout and self-protection. Corrected browser selectors to use displayed account names and updated configuration tests for the phase-based Next configuration. Final review found no remaining confirmed blocking issue in scope.

The reported permanent Models skeleton was reproduced: both page and layout JavaScript returned 404 while the server-rendered shell remained visible. Direct API list/context calls took 16-43 ms. Concurrent Next development/review/build processes had shared generated output. The Next configuration now separates production (.next) from development (.next-dev-<instance>); the Windows launcher uses the UI port as the instance, and manual simultaneous servers must select distinct PMS_WEB_INSTANCE values. Launcher/npm development use Turbopack. Shared console loading feedback was added. Directory reads now exit the skeleton state after 20 seconds with Retry, discard late timed-out responses, and clear timers on completion/unmount. Tokens and authorization remain server-only; no shared identity/data cache was introduced.

Verification:
- 53 distinct relevant API tests passed across the management, people, auth, subscription and administrator runs, including nine new administrator tests. The initial two test-assertion issues (role filtering and a psycopg LIKE placeholder) were corrected; all eight initial administrator tests then passed together, and the additional inactive ordinary-member regression passed separately. One intermediate fixture subprocess failure was resolved on rerun. No selected database tests were skipped. Tests used only the verified disposable PostgreSQL server on 56362, never application PostgreSQL on 5432.
- Full web suite: 452 passed across 65 files. Web typecheck and production Next build passed. API Ruff check/format check (177 files) and mypy (74 source files) passed. All 21 Windows launcher tests passed. CRLF-aware diff whitespace check passed; unrelated pending work was preserved.
- Real headless Edge -> Next 3124 -> API 8137 -> disposable PostgreSQL completed ten browser checkpoints: login, own-action protection, tenant administrator creation and invitation outcome, platform administrator creation/edit/setup resend, other-account lifecycle, tenant invitation/resend/acceptance, stale-member rejection, member lifecycle/revoke, and mobile layout with zero page exceptions. Earlier runs were interrupted by disposable PostgreSQL stalls; the complete final journey passed in 57.89 seconds. The interrupted fixture database and its three roles were identified and removed; final fixture cleanup succeeded.
- Read-only browser checks against local application UI/API 3000/8000 covered Models, Tenants, Users, Devices, Logs, Clinical specialties, Patient profiles, Cases & Q&A and Settings. After a production build while the development UI stayed running, all pages loaded without missing bundles or runtime errors; final link navigation was 756-1551 ms and warmed Models/Tenants/Users full loads 1117-1363 ms. Cold development visits still compile and can take a few seconds. Evidence is in .test_artifacts/admin-roles-20260928/performance.json and .test_artifacts/people-web.
- Restarted the application API/UI to load the fixes; they remain running. Review UI/API and disposable PostgreSQL were stopped. No Human-test, cloud/SMTP integration, hosted deployment or hardware test was started. No commit/publish requested.


## 2026-09-28: Tenant directory association management

Added Administrator directly after View on /tenants. The selected-tenant popup reuses the shared modal, tabs, tables, filters, paging, notices and confirmation dialogs. Users supports searching eligible existing accounts, direct association with a tenant role, role changes, enable/disable, removal and disabled restoration. Devices supports registration, searching another tenant for transfer, rename, activate/deactivate and permanent registration removal. Tabs load on demand; queries and failures use the bounded directory loader and retain retry behavior.

Platform membership endpoints require organization and user grants, plus the dedicated tenant-administrator grant when changing either an existing or new administrator role. Every membership mutation is scoped to its tenant, serialized with the existing administration lock, audited atomically and version checked. Existing database quota and last-administrator constraints remain authoritative. No implicit tenant media/configuration access or global-account mutation was added. Registration and transfer use the existing fleet endpoints; transfers retain original-tenant history, retire and revoke the source registration, and create a new inactive registration requiring fresh enrollment. No database entity, migration or runtime grant was added.

Review 1: checked tenant scoping, old/new administrator-role authorization, inactive tenant bootstrap, concurrent quota limits, last-admin protection, audit rollback, stale versions, search races, confirmation cancellation and removed invitations. Fixed restoration of removed account-bound invitations by requiring completed setup and an enabled existing account, revoking the old invitation token and restoring only disabled membership. Added a regression test. Corrected rename validation and test fixture assumptions about subscription device capacity and audit-table naming. Signed device pagination tests use the name sort used by the UI; legacy default-ID cursor compatibility remains intact.

Review 2: rechecked final authorization and transaction boundaries, lifecycle behavior, server-action validation, modal focus/close locking, lazy tabs and mobile layouts. Inspected desktop/mobile screenshots; no remaining confirmed blocking finding. Removed temporary review TypeScript includes while preserving the existing default/3000 development output isolation. Corrected documentation placement and the outdated tenant-preview description.

Verification:
- Relevant API integration suites passed across final runs: tenant associations, people management, device management, management API, administrator accounts and subscriptions, including concurrent quota/audit rollback and last-admin protections. All selected database tests ran on the verified dedicated PostgreSQL server at 127.0.0.1:56362, data directory .test_artifacts/db-sync-20260922/pgdata. No selected database tests were skipped. One migration startup error during host resource contention passed on an isolated rerun.
- The real Edge -> Next -> FastAPI -> disposable PostgreSQL browser journey passed all eight checkpoints in 47.28 seconds: button placement/selected tenant, existing-user association, scoped role/lifecycle, last-admin refusal, device registration/lifecycle, transfer/new identity, rename/removal, and mobile fit/focus restoration. Zero page exceptions. An earlier concurrent browser run hit a database connection timeout; the sequential rerun passed. Its interrupted synthetic fixture database and three roles were verified by test identity, creation time and data directory before removal.
- All 467 web tests in 67 files passed. API Ruff check/format check (180 files), mypy (75 source files), UI/workspace typecheck and production Next build passed. CRLF-aware diff whitespace check passed.
- Restarted the application API/UI with the updated endpoints. Read-only browser sign-in to localhost:3000, /tenants, Users and Devices tabs and popup close passed without account/device mutations or browser errors. Screenshots and sanitized results are under .test_artifacts/tenant-associations-20260928.
- Temporary review UI/API and the dedicated disposable PostgreSQL were stopped. Application API 8000 and UI 3000 remain running. Human-test and local model services were not started. No cloud/SMTP, hosted deployment or hardware verification was performed.

Existing unrelated changes were preserved. No commit or publication was requested for this task.

## 2026-10-01: Ubuntu single-VM deployment script

The Windows archive build succeeded; all 730 ZIP entries passed integrity and SHA-256 checks. The API wheel contains migrations. The Ubuntu script checks manifest hashes and unsafe paths before extraction; creates distinct database owner/API/worker/retention roles and private keys; rebuilds dependencies on Linux; configures HTTPS, Nginx and systemd; and checks readiness before declaring success. Cross-revision upgrades require explicit authorization, maintenance mode, a private PostgreSQL backup, and a checked database restore on failure. Same-revision rollback switches code only. The migration-owner URL is separate from the service environment.

Review corrected release-directory access, inherited environment overrides, explicit-exit recovery, and cross-revision rollback behavior. Bash syntax and six standard-library tests passed for embedded Python syntax, secret separation, valid extraction and tampered/path-traversal rejection. The Azure VM, PostgreSQL, Nginx, systemd, Certbot, OIDC, SMTP and Blob integrations were not tested from this Windows workspace. Real deployment and rollback drills remain open in TODO.

Follow-up review: service users and role-specific environment files now isolate API, worker, and retention database passwords; the editable master stays root-only. Bootstrap checks an existing database owner and encoding before mutations, creates UTF8/UTC databases, and refuses elevated existing roles. An isolated PostgreSQL 17 cluster completed role creation, all API migrations, runtime grants, pg_dump, and single-transaction pg_restore. The target Ubuntu VM and certificate flow are still untested.

## 2026-10-01: Tenant clinical ownership planning review

Scope: design and repository inventory only. The implementation plan is in [tenant clinical ownership](tenant-clinical-ownership-plan.md); no API, schema, UI, device runtime, or VM behavior changed in this planning task.

Inspected the current global clinical catalog models/routes, patient rehearsal selection and conversation consumers, tenant scenario draft/publication and session routes, role grants, web navigation and server actions, Alembic migration/grant pattern, and the current Ubuntu deployment notes. Confirmed that the three clinical catalog tables are global and writable with platform settings authority, while published training scenarios and sessions are tenant-scoped. Identified the existing global-selection foreign keys, broad scenario-author and session-start grants, and old API replicas during cutover as material implementation risks.

Plan review fixes: made the legacy-or-tenant practice reference transition explicit because the old global FK columns are NOT NULL; required old selection snapshots to remain historical while new rehearsal starts use tenant-approved content; required reuse of the existing /scenarios library; and separated tenant processing profiles from clinical scenario facts. The plan calls for two later code reviews, a tenant clinical-content review, staging migration rehearsal, and target-VM verification. Reviewer-separation and self-assignment policy remain Phase 0 product decisions.

Documentation verification: the new UTF-8 plan is readable, has eight ordered phases and no trailing spaces; 28 explicit existing-path references resolve. The TODO diff whitespace check passed after the appended planning entry. No runtime tests or live deployment were run for this documentation-only task.

## 2026-10-01: Ubuntu single-VM deployment VM-local follow-up

The generated production configuration now needs no manual environment edit. It enables local password authentication, disables provider-dependent email/OIDC actions, and uses a 5 GB private media directory shared only with the API and worker service accounts. Cross-process quota locking prevents concurrent writes from exceeding that bound. The deploy command installs Nginx and Node.js/npm, creates the API virtual environment, installs locked Node/Python dependencies, bootstraps PostgreSQL, and exposes the initial setup key only to an interactive VM terminal. Full API verification passed with 374 tests and 287 environment-dependent skips; Ruff check/format, mypy, six deployment unit tests, Bash syntax, and the isolated PostgreSQL bootstrap/migrate/grant/dump/restore drill passed. The target Ubuntu VM, Azure network rules, Let's Encrypt issuance/renewal, and live rollback remain unverified from Windows.

## 2026-10-01: Tenant clinical ownership Phase 0 review

Phase 0 contract, access matrix, source dependency inventory, migration rehearsal, and findings are in [Phase 0 review](tenant-clinical-phase-0-review.md). The new read-only SQL inventory is in `platform/api/deploy/tenant-clinical-inventory.sql`. It ran against the local application database at Alembic `0028_language_validator_acl` with a repeatable-read, read-only transaction. Local counts: three active global specialties, one active fictional profile, nine active global cases, one tenant with one practice selection, no draft/scenario/session/enrolled device, and zero missing or mismatched reference checks. Case revision greater than one reflects the earlier language migration and does not prove manual customization. No clinical document, name, credential, or media value was printed. The target Ubuntu VM database was not inspected.

Source review found four cutover risks: Platform Admin still has global catalog read/write routes; scenario and training responsibilities use broad existing grants; optional physical device serials lack global uniqueness; and version 3 authored case content cannot currently run through the version 1 device training runtime. The plan now requires an enforceable physical-identity policy and validated runtime conversion or support. No schema/API/UI/runtime mutation was made in Phase 0. Before application-database migration, review the target VM inventory and the publication/capability defaults. The local SQL execution is evidence only for the local database, not the VM.

## 2026-10-01: Tenant clinical ownership Phase 0 final review

Reviewed the Phase 0 report, source claims, inventory SQL and migration gates against the current schema and routes. Fixed three misleading inventory measures: `training_scenarios` includes unapproved versions, so approved and awaiting-approval counts are separate; `enrollment_state='enrolled'` can remain after credential revocation, so enrollment and unrevoked-credential counts are separate; and an expired session can retain an active status until cleanup, so active unexpired and expired-status counts are separate. Historical missing-membership counts are now informational, not tenant-reference failures. Added unusable practice-selection counts, bounded SQL statement/lock timeouts, and a visible read-only-transaction indicator. Clarified the direction of historical foreign-key references and that instructor capability is for eligible staff roles.

The revised SQL executed successfully against the local application database at `0028_language_validator_acl`; all four reference-integrity counts and the newly distinguished local usage counts were zero. A local `psql -X -v ON_ERROR_STOP=1` invocation succeeded without logging the password. The query ran only in a read-only transaction; the Ubuntu `sudo -u postgres` command has not been run. The VM database, capability implementation, schema migration, clinical review and device runtime remain unverified.

## 2026-10-01: Tenant clinical ownership Phase 1 final review

See [Phase 1 review](tenant-clinical-phase-1-review.md) for migration, backfill, authorization, data-integrity, and rollout evidence. Local disposable PostgreSQL 17 verification passed: 654 API tests passed, 11 opt-in/native/Hindi tests skipped, and no database tests skipped. Ruff check/format, mypy, and diff whitespace checks passed. The application and Ubuntu VM databases were not migrated; the existing platform catalog routes remain until the coordinated Phase 2 cutover.

## 2026-10-01: Tenant clinical ownership Phase 2 final review

See tenant-clinical-phase-2-review.md. Forward migration 0030 adds audited membership capabilities and fixes the tenant catalog update guard. New tenant-bound catalog routes, safe reader projections, scoped starter import/copy, optimistic revisions, and API-role global catalog write revocation were reviewed. Phase 3 scenario/training permissions and Phase 4 web routes remain deployment gates; no application or VM database was migrated.

Disposable PostgreSQL review: 25 focused migration/catalog/grant tests passed. The full API run had 652 passed, 11 skipped, and three obsolete global-write-grant assertions; the three corrected assertions and final Phase 2 changes passed in a 22-test affected rerun. Ruff check and format, mypy, schema synchronization, and CRLF-aware diff whitespace passed. The full suite was not rerun after final corrections; the affected rerun covered final code changes. No confirmed Phase 2 authorization, data-integrity or audit finding remained in the final review.


## 2026-10-01: Tenant clinical ownership Phases 3-7 final local review

See [combined review](tenant-clinical-phases-3-7-review.md) and [Ubuntu rollout checklist](tenant-clinical-rollout.md). Review 1 corrected attribution, migration and fixture compatibility, route access, and the deployment backfill. Review 2 fixed unchanged-content draft attribution and a postcutover inventory false positive; the real browser case-to-draft journey passed after its dialog locator was scoped.

Local verification: full API 660 passed and 11 opt-in checks skipped on disposable PostgreSQL 17; two final-code regressions passed; web 474 passed across 68 files; shared UI 1577 passed earlier; workspace typecheck and production build passed; device coordinator 8 passed; real Edge to Next to API to disposable PostgreSQL passed all four journey checkpoints. API Ruff check and format check and mypy passed. Six deployment unit tests and the opt-in isolated PostgreSQL bootstrap, migration, inventory, grant, dump and restore rehearsal passed. The 737-entry release archive passed manifest integrity and source checks.

The application database and target Ubuntu VM were not migrated. VM inventory, HTTPS and Nginx, tenant clinical sign-off, physical device identity and wipe, two-tenant hosted smoke, and rollback evidence remain operator or hardware gates. No GitHub publication was requested.


## 2026-10-01: Tenant clinical deployment readiness follow-up

A fresh review found that HTTP readiness could succeed against an unmanaged old process bound to API port 8000 or web port 3000 while the new systemd service failed. The Ubuntu script now requires the active managed API and web MainPIDs to own their listeners, and separately requires worker and retention services to be active. iproute2 is installed for the listener check. The rollout script checksum was updated; the release zip is unchanged because the script is a separate transfer file.

Verification: seven deployment unit tests passed, including wrong-listener and inactive-service regressions. Bash syntax and CRLF-aware diff checks passed. The target Ubuntu VM, systemd, Nginx, certificate and rollback remain unverified locally; the operator checklist still requires those live checks.

## 2026-10-01: Human-test tenant clinical compatibility review

The desktop still assumed the historical global case catalog and described organization administrators as the only patient-setup users. Review found no patient-profile choice, no legacy-selection explanation, a preview that could show an older embedded identity after a tenant profile edit, and a profile picker that could drop a second patient with the same display name. The client now filters active tenant cases by specialty and patient profile, disambiguates equal profile names with their unique code, previews the current profile, rejects legacy selections before conversation submission, and explains empty/changed catalogs and explicit clinical author plus processing access. The API remains the authority for tenant scope, lifecycle and save concurrency.

The full Human-test suite passed with 473 tests and 6 opt-in voice/model checks skipped. After the final profile-preview correction, 8 focused patient-workflow tests passed; Ruff check passed, and formatting and mypy were rechecked. No live tenant API, cloud service, audio device or hosted VM was exercised.

## 2026-10-01: Human-test end-to-end tenant review

The local review followed tenant catalog permissions and lifecycle through desktop preview, private selection save, conversation admission, local inference metadata and history. The existing API/client journey passed against dedicated disposable PostgreSQL 17 with tenant isolation and denied cross-tenant catalog access. Review found that the desktop assumed English complaint/onset and all eight case vitals even though active version-3 tenant cases may omit onset/vitals or use Hindi as source. The preview now displays available source text, leaves missing observations editable, and requires staff to fill all eight before save.

A profile-language edit after case activation could cause an uncaught ValueError during selection save. PMS now returns patient_language_unavailable (422), and the desktop maps it to an actionable message. A PostgreSQL regression changed an active profile to Hindi-only occupation/background content, attempted an English setup, and confirmed no selection revision or save-audit mutation. The current API guide and patient-practice contract were corrected to distinguish tenant behavior from historical migration 0013 notes.

Final affected API/client/catalog checks: 34 passed against disposable PostgreSQL; API Ruff check/format and mypy passed. Full Human-test suite: 473 passed, 6 optional voice/model checks skipped; desktop Ruff check/format and mypy passed. The Windows transfer build completed with a production Next.js build and two wheels. Archive manifest hashes and API source/wheel parity were verified; the new archive hash is recorded in the tenant rollout checklist. The local database cluster was stopped after checks. Hosted Ubuntu, HTTPS, live audio/cloud, staff-laptop and physical-device checks remain operator gates.

## 2026-10-01: Final tenant clinical web and transfer review

A final Patient setup review found web gaps: historical global selections could be treated as current when their IDs and revisions happened to match a tenant case; an in-flight case response could reselect a case after staff cleared it; and an empty catalog lacked guidance while the no-case message directed staff to a platform administrator. The web form now requires an explicit active tenant case, clears all prior tenant state on context or reload, ignores superseded case/save responses, locks choices during a save, and directs staff to a tenant clinical author. The server action now explains incomplete case/profile localization and case/profile mismatches. A later pass removed a false loading state after catalog errors, explained specialties without cases, cleared old vital values and treated null observations as missing. Seven component regressions and an error-mapping regression cover these paths.

Final web verification: 482 tests passed across 69 files with four Vitest workers and a 10-second test timeout; TypeScript passed; the production Next build passed. An unrestricted repeat exceeded the default 5-second timeout in unrelated UI tests under runner load; the bounded rerun passed those tests and the full suite. API Ruff check, Ruff format check and mypy passed. API source was unchanged in this follow-up. The prior full disposable-PostgreSQL API run passed 660 tests with 11 opt-in skips, and 34 affected API/client tests passed after the last API fix. A redundant full API repeat was started and stopped before completion; it is not counted as a pass.

The rebuilt Windows transfer archive is start/dist/pms-platform-20261001-112934-136b9b.zip, SHA-256 5f91d4d2966763fd3f382a1fe5583e7e43a681d7d0cd57b900880b8e6ce281fc. Its 737 entries passed manifest hashes; 450 source entries and API wheel source matched the workspace. Migration 0031, grants and the web fix are present, with no private environment or key filenames. The rollout checklist now names this archive. Target Ubuntu deployment, HTTPS, hosted two-tenant journey, staff-laptop client and physical device verification remain unperformed operator gates.

## 2026-10-01: Web-to-API deployment routing follow-up

The web service already sets PMS_API_BASE_URL to http://127.0.0.1:8000/api/v1 and the server-only transport uses it at request time. A review of the HTTPS Nginx template found that its broad /api/ location intercepted the Next.js member-import download route at /api/member-imports/download. The deployment script now proxies only /api/v1/ to FastAPI, leaving the download route with the web service. A routing regression checks both paths and the runtime API base. The rollout checklist includes a hosted template-download smoke check.

Bash syntax and all eight deployment archive tests passed. A fresh production build generated start/dist/pms-platform-20261001-115504-c32fd0.zip, SHA-256 3bf7cdaf58d8aedc94a3d5458336a5c8e8ed9f2dc22235ddc359e890f5f8b7a7. Its 737 manifest entries, 450 source files and API wheel source passed local integrity checks. The updated deploy-platform.sh SHA-256 is bec3c84e52819e6d3e4719a149f71f5d94c8f1b97d290b4cb0ea72cdef680137. No target VM, live Nginx or HTTPS request was made in this review.

## 2026-10-01: Azure VM deployment recovery and live review

The first managed deployment migrated the database to `0031_case_draft_provenance` and started the API, but `pms-web` failed because Next.js tried to load `next.config.ts` after `npm prune --omit=dev` removed TypeScript. The service account could not install it into the read-only release. Converted the config to `next.config.mjs`, kept the Next configuration and tests aligned, and rebuilt the transfer archive. A subsequent deployment passed local API/web readiness but its immediate HTTPS probe received 503 just after Nginx reload. A bounded HTTPS retry fixed this suspected reload timing race; its success and failure paths have a regression test. The final deployment completed with release `20261001-121621-11314` active.

The final archive `start/dist/pms-platform-20261001-120323-d2df3b.zip` has SHA-256 `dcf3602aebd4397cc10af97904daaf664b38c5de2f214a508f966942443540fa`; all 736 manifest entries verified and the JavaScript runtime config is present. The deployed script has SHA-256 `b6e94a9de2ec1d4a4bb981f69f52c59a23a4b8ecf2d322a2d033bfc77e2de732`; VM hashes matched both files. Local UI typecheck and production build passed, all 1,577 UI-package tests passed, and a bounded full web rerun passed all 482 tests across 69 files. An earlier unrestricted web run had 479 passes and three default-timeout failures under load; those failures also passed in a focused rerun. Bash syntax and all nine deployment tests passed. The initial web test run overlapped with `npm ci` and is invalid; it is not counted.

On the VM, a custom-format backup was created before the retry at `/var/backups/pms-platform/pre-redeploy-20261001.dump` (463,766 bytes, mode 600); `pg_restore --list` succeeded. The read-only inventory ran at revision `0031` with zero tenants, selections, scenarios and sessions, zero reference-integrity issues, and the expected seeded global catalog (3 specialties, 1 fictional profile, 9 cases). All four services are active, with no error-priority journal entries since the final start. The API and HTTPS web readiness endpoints returned 200; external HTTPS returned 200 for the web app and readiness and 405 for GET `/api/v1/auth/login`, confirming FastAPI routing. The browser entry redirects to `/setup` because no administrator exists. Certificate renewal, rollback to a healthy prior release, authenticated two-tenant behavior, staff-laptop Human-test and physical device verification remain open.

## 2026-10-01: Live Users page server-action fix

After initial administrator setup and creation of one tenant, the hosted `/users` page showed a generic load failure. API logs showed GET `/platform/users` succeeded with 200, while the Next.js journal rejected a non-async object export in a `use server` module. Source review traced it to `CLINICAL_CAPABILITIES` in `capability-actions.ts`, imported through `MemberCapabilities` on the Users page. Moved the constant and related types into `clinical-capabilities.ts`; the action module now exports only async functions. A new AST regression checks every `use server` module in `src/lib` for runtime exports that Next.js cannot use as actions.

The Windows archive `start/dist/pms-platform-20261001-123541-a91b86.zip` has SHA-256 `d06fb2437d37b22ab6bd77d4a77997215ab3f7bbe8e78f490816530e39b70a69`; all 737 manifest entries verified, including the new module. TypeScript, the production Next build, the focused 23 tests, and the full web suite (483/483 tests across 70 files) passed. Before deployment, a custom-format database backup was saved at `/var/backups/pms-platform/pre-users-fix-20261001.dump` (913,968 bytes, mode 600); `pg_restore --list` succeeded. The managed detached deployment completed at `/opt/pms-platform/releases/20261001-123654-13281`. All four services are active, external HTTPS readiness returned 200, and anonymous GET `/users` redirected to `/login` without reproducing the server error. Database counts remained one user and one organization. The administrator confirmed the signed-in `/users` list loaded after a hard refresh. No administrator password or session token was requested or handled.

## 2026-10-01: VM local user provisioning

The hosted Create user 503 was traced to an SMTP-only guard in VM local mode. Authorized account creation and invitation now use private one-time setup and invitation links; list/detail responses remain token-free. The full finding, regression, disposable PostgreSQL, archive, backup and hosted rollout evidence is in [VM local user provisioning review](vm-local-user-provisioning-review.md). The hosted submission created a second user and one invitation; setup completed and browser sign-in succeeded. The administrator reported both links visible.

## 2026-10-01: Unified tenant administration

The tenant list and detail routes now open the same four-section administration dialog for subscription, administrators, users and devices. Permission-gated tabs, confirmation, tenant-state refresh and association regressions were reviewed. See [tenant administration unification review](tenant-administration-unification-review.md). The hosted VM was not changed.

The tenant LLM page also exposed an omitted VM-local `PMS_LLM_ENABLED` setting. The generated configuration now enables tenant LLM connection management and retains the separate external-call gate. Existing configuration is preserved for an operator-controlled later update. The web page shows a single clear disabled state. See the same review for verification; the VM remains unchanged.

## 2026-10-01: Tenant administrator clinical default and cards

Tenant administrators now receive clinical author access from their active tenant role, and their Home and Settings pages show the three clinical content destinations. Other card visibility and direct-route authorization were reviewed separately. See [tenant administrator clinical default review](tenant-admin-clinical-default-review.md). The hosted VM was not changed.

## 2026-10-02: Platform device model profile assignment

Platform administrators can assign a tenant's published processing profile to
a device, selecting Local, Cloud or mixed model routes by operation without
opening tenant credentials or media. See [device model profile assignment review](device-model-profile-assignment-review.md).

## 2026-10-02: Tenant onboarding, device authority, and import history final local review

The four-step tenant page now provisions an active tenant, accepted administrator, and new or transferred device in one database transaction. A transfer retires the source registration and gives the destination a fresh device ID without copying private configuration or history. Platform authority is required for device registration, published profile assignment, and LLM/model management; tenant device edits remain scoped to private fields. The import template accepts an optional local password, generates one for each new local account left blank, stores completed passwords in tenant-and-batch-bound AES-GCM escrow, and exposes them through audited import detail and password-only downloads until the 30-day import expiry. Migration 0032 adds the physical manikin type and escrow columns while preserving legacy device records and prior data.

Review findings fixed: the Alembic revision identifier initially exceeded its version column, the escrow size constraint needed to cover the allowed Unicode password and row limits, and two old API tests still used the retired tenant device-registration route. The Settings move initially made Departments a fourth tenant card; it is now a separate Settings link, leaving exactly the three clinical cards. The device form binds current department and published profile choices to the selected tenant, and the server rejects tenant profile reassignment and tenant device creation. The final review found no further confirmed authorization, data-integrity, or compatibility defect.

Local verification used dedicated disposable PostgreSQL at port 55467. The API suite was covered in ordered segments while the two obsolete route assertions were corrected: 273 passed/3 skipped before the first assertion, 358 passed/6 skipped before the second, and the remaining segment passed 52/2 skipped; the corrected LLM quota and subscription files passed 17 and 6 tests separately. The final migration/schema-sync rerun passed 5 tests. The full web suite passed 504 tests across 73 files before the final Settings presentation change, and its 10 focused Settings tests passed afterward. API Ruff lint/format, mypy, web workspace TypeScript, and CRLF-aware diff whitespace checks passed. Skipped tests are opt-in native or external checks; this was local unit/integration verification, not a hosted browser or hardware check. No deployment build or VM update was made.

## 2026-10-02: Tenant creation and member import follow-up review

Rechecked tenant wizard state, accepted administrator provisioning, transfer rollback, import validation and commit, password escrow, history authorization, and the Next.js download proxy. Fixed three UI findings: rejected device/user searches could leave the wizard busy indefinitely; the tenant page showed required-field errors before the first Continue attempt; and Import History briefly reported no imports while loading, gave no recovery state on a rejected request, and cramped its action row on narrow screens. The history page now remounts on a tenant-context change. Added a 512 KiB ingress limit to the API upload route so oversized workbooks are rejected before parsing, matching the template and parser contract. The server action maps that 413 error to the workbook-size message.

Focused disposable-PostgreSQL verification: tenant provisioning and import files passed 33 tests, including the new upload-limit regression. Two subsequently added authorization/rollback cases passed separately: duplicate or unfinished administrator accounts leave no tenant/device, and completed password history is unavailable to an outsider or after expiry. The expiry test initially violated the existing database date-order constraint; its fixture dates were corrected and it passed. A final copy review found that the external sign-in workbook still implied blank passwords would be generated; its instructions and wizard now say to leave that column blank. The workbook unit regression passed, and web wizard/import tests passed 10 cases after this correction. Ruff check, Ruff format check, mypy, workspace TypeScript, and CRLF-aware diff checks passed. The earlier full API/web runs remain the broader baseline; this follow-up used focused tests. No build, hosted deployment, or VM update was performed.

## 2026-10-02: Clinical catalog, Q&A, and related masters review

Reviewed tenant clinical specialties, patient profiles, embedded case Q&A, scenario draft copies, staff practice choices, role grants, menu and Settings routes, and the API/UI payloads. Platform administrator access still gives no implicit tenant clinical content access; tenant administrators receive clinical author access from their active tenant role. Case associations stay within one tenant; the case document snapshots current master data when the case is saved, while scenario versions and saved practice retain their own snapshots.

Two confirmed issues were fixed. First, archiving a specialty or patient profile correctly blocked active dependent cases, but editing the same master to `is_active=false` bypassed that guard. Both write paths now use the same active-case check under the existing tenant write lock. An integration regression verifies both masters reject deactivation without a version change, and that a case cannot reactivate while its specialty is inactive. Second, valid incomplete version-3 case documents can omit presentation, dialogue, history, or instructor sections; the web Q&A editor assumed these sections existed. The catalog and scenario editors now supply empty editing sections in memory and preserve entered content. The web action now maps the actual API lifecycle error codes and uses a generic duplicate-name message for all three masters.

Verification: 65 focused disposable-PostgreSQL catalog/practice/scenario/migration tests passed; one unrelated Alembic fixture subprocess crashed while the full web suite ran concurrently, then the same test passed alone. Full API run without the disposable DSN: 374 passed, 309 opt-in integration/native tests skipped. Full web suite with two workers: 509 passed across 73 files. API Ruff lint/format and mypy, workspace TypeScript, and CRLF-aware diff checks passed. The first full web run had three 5-second timeouts under concurrent database load; all passed in the controlled rerun. No deployment build, hosted browser check, or VM update was performed.

## 2026-10-02: Device model picker, client binding, and local schema sync

Reviewed the platform device model picker, API profile metadata and assignment checks, and the human-test local model inventory. Added an optional device-bound read path for human-test with tenant/department and device lifecycle checks. See [device model profile assignment review](device-model-profile-assignment-review.md) for code, focused tests, full API/web checks, and the local 0028-to-0032 migration/backfill evidence. No hosted VM update or deployment build was performed.

## 2026-10-02: Platform administrator role and console review

Traced Platform Admin navigation and direct-route guards through tenant, account, fleet, model, LLM, subscription, health, and audit pages and their API permissions. Tenant clinical content, configuration, processing, and media still require an accepted tenant membership; the platform role alone does not grant that access. Reviewed wizard provisioning, user creation, existing administrator assignment, published device profile options, connection credential redaction, and archive/version guards.

Fixed two confirmed API gaps. The older tenant administrator assignment route could promote an existing member without advancing its management version and could create a second association when an unbound invitation already matched the user's email. It now rejects that pending invitation, requires a verified account, advances the version on a real promotion, and treats repeat assignment as idempotent. Platform Settings now rejects default tenant policies that exceed the resulting platform policy limits, preserving new tenant creation. The web console gives actionable errors for both validation cases. No schema change was needed.

Verification: three new regressions and five related role/fleet/wizard integration cases passed on the dedicated disposable PostgreSQL server at port 55467. The full API run without a test DSN passed 374 tests with 312 opt-in database/native checks skipped; the full web suite passed 512 tests across 73 files. API Ruff lint and format checks, mypy, and web workspace TypeScript passed. These were local checks; no build or VM update was performed.

## 2026-10-02: Tenant administrator role and self-access review

Reviewed the Tenant Admin role grant and active accepted membership checks, clinical specialty/patient/case authorship, member and import scope, department controls, tenant device editing, and the separate Platform Admin authority for device registration, LLM connection management, and model catalog changes. Settings still presents only the three clinical cards for Tenant Admin, with Departments as a secondary link. The clinical author grant is intrinsic to the active tenant administrator role; no additional capability assignment is needed.

Fixed a confirmed self-access gap: a tenant administrator with another active administrator could previously disable or archive their own membership through the tenant member API. The shared membership mutation helpers now reject both actions on the caller's membership, including direct and platform association routes. The Members list and direct detail page disable those actions for the signed-in person, and the console gives a tenant-specific error if a direct action is attempted. Other members remain manageable, and existing last-administrator database protection remains in place.

Verification: the new disposable-PostgreSQL regression passed for both Tenant Admin and ordinary user self-actions; a seven-case focused database pass covered clinical authorship/isolation, imports, LLM authority, and device registration. Full API run without a test DSN: 374 passed, 313 opt-in database/native checks skipped. The full web suite passed 514 tests across 73 files. Ruff lint/format, mypy, and workspace TypeScript passed. No deployment build or VM update was performed.

## 2026-10-02: Browser session lifetime and expiry review

The browser uses one opaque, server-verified credential; bearer access/refresh tokens remain a separate API client flow. The prior browser default expired after eight hours, while the remember checkbox extended server access to the bearer refresh period. An open console tab had no expiry check, so it could keep showing a signed-in screen after server revocation until navigation.

Browser sessions now have a fixed, configurable `PMS_LOCAL_BROWSER_SESSION_HOURS` lifetime (24 hours by default, 1-168 allowed). Remembering controls only whether the HttpOnly cookie persists across browser restarts; it does not extend server authority. The console revalidates every minute and on focus/visibility return, clears invalid session/context cookies through a server action, and navigates to login. API outages preserve the cookie so a transient failure cannot masquerade as sign-out. Explicit logout still revokes the API session before clearing the cookie. Existing bearer refresh rotation and replay checks remain unchanged.

Verification: all 12 disposable-PostgreSQL auth session tests passed, including configured expiry, revocation, replay, and parallel browser requests; the changed lifetime test passed again after its final assertion update. The full API run without a disposable DSN passed 374 tests with 313 optional database/native tests skipped. The full web suite passed 517 tests across 74 files; focused session tests passed after the final interval test was added. Ruff lint/format, mypy, workspace TypeScript, and scoped diff checks passed. No deployment build or VM update was performed.

## 2026-10-02: Automatic tenant patient profile and case label

Reviewed the wizard, standard, and pending Platform Admin tenant creation paths, the tenant clinical catalog, the global fictional patient starter, and the legacy catalog backfill. Each new tenant now receives one independent copy of the deployment-managed `alex` starter profile with its own tenant ID. It is inactive until the tenant administrator reviews and activates it. No specialty or case is created. The profile insert and audit event share the tenant creation transaction; a later wizard failure rolls them back. Platform administrators receive no clinical profile content in the provisioning response or through the tenant catalog API. Existing tenants are unchanged. The starter import endpoint remains idempotent and returns the tenant's already-provisioned profile.

The wizard review and completion text disclose the automatic inactive profile. The two role menus, Settings card, and catalog heading now use **Case drafts & QnA**; navigation permissions and API routes are unchanged.

Verification: ten focused disposable-PostgreSQL provisioning/catalog/backfill tests, nine Platform Admin lifecycle tests, and one patient-practice integration test passed. Full API run without a disposable DSN: 374 passed, 315 optional database/native checks skipped. Full web suite: 517 passed across 74 files on the profile implementation. After the label edit, 60 affected web tests and workspace TypeScript passed. API Ruff lint/format, mypy, and CRLF-aware scoped diff checks passed. No build or VM update was performed.

## 2026-10-02: Three default tenant clinical specialties

Selected Cardiology (heart and circulation), Respiratory Medicine (lungs and breathing), and Nephrology (kidney conditions) from the existing reviewed starter catalog. All three tenant creation routes now copy these specialties with distinct tenant IDs, inactive status, source provenance, and audit events alongside the fictional Alex profile in the same transaction. The tenant administrator can review, edit, and activate each copy independently. No case or QnA is created; existing tenants are unchanged. The wizard review and success states disclose the three new defaults.

Reviewed tenant boundaries, a failed device transfer rollback, starter import idempotency, parent activation rules, and the specialty cap with the new baseline count. A newly added regression activates Cardiology in one tenant and confirms the other tenant's copy remains inactive and cannot be read through the first tenant's ID.

Verification: 48 related disposable-PostgreSQL provisioning/catalog/backfill/patient-practice tests passed, followed by two final provisioning/isolation regressions. The full API run without a test DSN passed 374 tests with 315 optional database/native checks skipped. The full web suite passed 517 tests across 74 files, including the wizard copy assertions. API Ruff lint and format checks, mypy, web workspace TypeScript, and scoped CRLF-aware diff checks passed. No build or VM update was performed.

## 2026-10-02: Automatic tenant case drafts

Reviewed the six case-editor sections, the fixed bilingual global starter records, tenant-owned case schema and grants, all three tenant creation paths, and practice activation rules. Selected `alex_chest_discomfort` and `alex_wheeze`: their current source documents contain presentation, history, eight vital measurements, disclosure settings, 32 Q&A topics, and instructor fields, and pass the document publication validator. The symptom patterns and escalation teaching points were checked against [AHA stable-angina](https://www.heart.org/en/health-topics/heart-attack/angina-chest-pain/angina-pectoris-stable-angina) and [acute-coronary-syndrome](https://www.heart.org/en/health-topics/heart-attack/about-heart-attacks/acute-coronary-syndrome) material, [NICE chest-pain assessment](https://www.nice.org.uk/guidance/cg95/chapter/Recommendations), and NIH NHLBI guidance on [asthma symptoms](https://www.nhlbi.nih.gov/health/asthma/symptoms) and [attacks](https://www.nhlbi.nih.gov/health/asthma/attacks). The exact field values and source links are in [the default case reference](default-tenant-case-drafts.md).

New tenants receive independent inactive copies of the two drafts in the same transaction as their own specialties and Alex profile. Each case is bound to its tenant-specific parent IDs, has new record and source-provenance IDs, a case-specific diagnosis prompt, objectives and assessment rubric, and an audit event. No case is exposed in the platform provisioning response or usable for practice until tenant clinical review and parent/case activation. Existing tenants remain unchanged; the fixed starter import endpoint returns the existing tenant copy when requested again.

Verification: the related disposable-PostgreSQL run passed 47 tests and found one migration-test fixture that assumed one case per tenant; its cross join produced a duplicate-code error before the intended foreign-key assertion. Narrowing the fixture to one row fixed it, and that test plus the provisioning/audit check passed on rerun. A later content assertion was corrected from the old 0013 source's 22 topics to the current 0014 source's 32 topics; the final provisioning check passed. The full API unit run without a disposable DSN passed 374 tests with 315 optional database/native tests skipped. The full web run passed 517 tests across 74 files; the final wizard-copy test passed separately. Ruff lint/format, mypy, and web TypeScript checks passed. No build or VM update was performed.

## 2026-10-02: Final tenant clinical starter review

Traced the wizard, pending platform, and self-service tenant creation routes to the same transaction-scoped starter helper. Reviewed source revision provenance, tenant-specific specialty/profile/case IDs, parent bindings, the bilingual 32-topic Q&A documents, instructor content, permissions, inactive lifecycle, and the UI catalog and wizard paths. Confirmed the two case drafts remain absent from patient practice until the tenant activates a matching specialty and profile, then the case.

Fixed a source-integrity gap: automatic tenant creation now requires the same reviewed global starter revisions as manual starter import. A changed specialty, patient profile, or case source causes tenant creation to roll back instead of copying unreviewed content. The wizard now explains the source-catalog problem. The API guide describes this fail-closed behavior. No schema or runtime grant change was needed.

Verification: 51 related tests passed against the dedicated disposable PostgreSQL server, including all three changed-source rollback regressions and activation into patient practice. The full API run without a test DSN passed 374 tests with 318 opt-in database/native tests skipped. Focused web catalog and wizard tests passed 20 cases; the full web suite passed 517 tests across 74 files after the wizard error-message change. API Ruff lint and format, mypy, web TypeScript, and scoped diff checks passed. This was local code review and testing; no build or VM update was performed.

## 2026-10-02: Published tenant starters and shared Patient setup

Reviewed the three tenant creation paths, scenario publication checks, tenant case activation, Patient setup permissions, migration constraints, and runtime grants. Each new tenant now receives two active immutable version-1 scenario snapshots from the reviewed chest-discomfort and wheeze source cases. `publication_source=system_starter` and a linked tenant case ID distinguish these from clinician-approved publications; no reviewer identity or approval statement is fabricated. The tenant-owned editable case drafts and their specialty/profile parents remain inactive for tenant clinical review. The same transaction creates a tenant-wide Patient setup suggestion linked to the chest-discomfort case. Authorized staff explicitly save a personal setup after activation; the tenant administrator can select another active case with a revision guard. Existing tenants and personal selections are unchanged.

The migration enforces same-tenant case references, source-specific publication metadata, one system starter per case, and revisioned tenant default updates. API routes enforce active accepted membership, tenant scope, administrator-only default changes, current case revision, language support, and audit events. The UI labels system starters and offers explicit default adoption. Tests covered provisioning rollback, tenant isolation, cross-tenant FK rejection, activation, stale case/default revisions, and role denial.

Verification: 10 provisioning tests passed on the disposable PostgreSQL server. The broader scenario/practice/migration/training run had 60 passes and one Windows Alembic subprocess crash during fixture setup; rerunning the three affected cases in isolation passed. The full API run without the database DSN passed 374 tests with 319 opt-in database/native skips. The full web suite passed 520 tests across 75 files with a 10-second per-test timeout; its earlier default-timeout run had two slow UI timeouts, both of which passed in isolation. Ruff lint/format, mypy, TypeScript, and scoped diff checks passed. No build or VM update was performed.

## 2026-10-02: Tenant default Case QnA review

Traced the frozen bilingual source catalog through tenant case preparation, tenant-scoped API detail, the Case drafts & QnA editor, and immutable published runtime snapshots. All 32 QnA topics, both answer languages, and on-question disclosure reach the tenant case. The editor binds the saved specialty/profile IDs and preserves bilingual answers when one language is edited. The source catalog is not changed by provisioning.

Found an assessment gap in the defaults: the chest-discomfort rubric asks about pain radiation and associated warning symptoms, while the original starter QnA had no direct answers for them; the wheeze rubric similarly lacked direct answers about speaking ability and recent reliever/controller use. New tenant copies replace three general prompts per case with these case-specific bilingual questions and fictional answers, preserving the 32-topic runtime limit. The selected assessment domains align with [NICE recent-onset chest-pain guidance](https://www.nice.org.uk/guidance/cg95/chapter/Recommendations) and [NIH NHLBI asthma-attack guidance](https://www.nhlbi.nih.gov/health/asthma/attacks); this source check does not certify the fictional answers or Hindi wording clinically. Tenant clinical review remains necessary. The UI now states that editing QnA does not mutate an existing published version.

Verification: 26 provisioning/catalog tests passed on the dedicated disposable PostgreSQL server, including tenant QnA values and languages, unchanged source records, immutable published snapshot after a tenant edit, authorization, and rollback cases. Full API run without a test DSN: 374 passed, 319 opt-in database/native checks skipped. Full web suite: 521 passed across 75 files with a 10-second per-test timeout. Ruff lint/format, mypy, web TypeScript, and scoped diff check passed. No build or VM update was performed.

## 2026-10-02: Unified platform model configuration and device assignment

Reviewed the previous split between catalog metadata, tenant LLM connections, media provider connections, processing profiles, device editing, and Human-test runtime routes. Added one Platform Admin Models workspace for tested cloud text configurations (OpenAI, Azure OpenAI, Anthropic, OpenAI Compatible), reported laptop local Qwen/Whisper availability, media connections, profiles, catalog metadata, and device assignment. Legacy model URLs redirect to the workspace. Tenant administrators no longer have model, connection, or profile management grants; the API enforces the same boundary. Existing published tenant profiles and connection data are preserved.

The review found and fixed a credential vault identity mismatch, repeated assignment consuming the tenant's ten-connection limit, stale or spoofable local inventory fields in enroll/heartbeat, the ability to choose an audio route unsupported by Human-test, a missing path to media/profile editors, and old device dropdowns that implied independent operation overrides while selecting whole profiles. The device assignment now reuses one tenant binding per model, publishes a versioned device profile atomically, and requires a compatible speech route. Cloud edits deactivate managed bindings until a successful bounded synthetic retest; an unknown provider POST is not retried. Provider keys remain encrypted and are not returned to the browser or device. A device report requires its enrolled credential and expires after 24 hours.

Verification: full API unit run 381 passed, 321 opt-in database/native skipped. Isolated disposable PostgreSQL 17 migration/schema/grant and model assignment suites passed (15 selected tests), plus the final cloud update/retest and device assignment regressions. Full web suite 522 passed across 76 files; TypeScript passed. Human-test boundary suite 43 passed. API Ruff lint/format, mypy, Human-test Ruff lint/format, and scoped Git diff checks passed. Live cloud/provider and hardware verification were not performed. No build, VM update, commit, or publication was performed. See docs/platform-models.md for the operator workflow and current supported model boundaries.

## 2026-10-02: Model workflow follow-up review

Reviewed device token pairing, inventory refresh, tenant scope, cloud credential testing, and published device routes.

Fixed a mispaired device credential path: the API checks the requested device ID against the authenticated device before storing inventory, and Human-test verifies the bounded acknowledgement before loading its route.

Fixed Models Refresh to reload the selected laptop inventory and tenant profile choices; local model options stay scoped to the selected laptop.

Verification: 381 API tests passed with 321 opt-in database/native skips; 8 targeted tests passed on a disposable PostgreSQL server; 523 web tests and 44 Human-test external-PMS tests passed. API Ruff lint/format, mypy, web TypeScript, Human-test Ruff lint/format, and scoped Git diff checks passed. No build, VM update, commit, or publication was performed.


## List-page UI standardization - 2026-10-03

Completed all six phases in [the task checklist](list-page-ui-plan.md). Standardized
search/select/date/action dimensions, stacked labels, widths, spacing and wrapping
on the affected list pages and tenant association panels. Preserved immediate and
debounced search behavior, native Apply/Clear submission, query limits, tenant scopes,
permission gates, sorting and pagination. Ordinary forms were not restyled.

Review 1 found inherited form margins, mixed control heights and custom toolbar widths.
Review 2 found constrained desktop tables collapsing under wrapped filters and an
orphaned platform-log Clear action; fixed the table minimum height and grouped actions,
then reran affected checks and inspected the final screenshots/diff.

Verification: shared UI suite 46 files / 1,577 tests passed; full web suite 538 tests
passed; final affected Logs/Subscriptions run 14 tests passed. Sixteen focused regressions
were added, including integrated Models tabs, scoped device filters and deferred log
submission. Workspace typecheck and final production build passed (exit 0).
Browser checks passed for 69 component-rendered list states and 1,449 configurations,
covering narrow/short windows, three themes, 200% text scaling, long options, keyboard
focus and pager reachability. No remaining confirmed list-filter defects were found.

Evidence: `.test_artifacts/list-ui-standardization-20261003/`, including
`browser-results.json`, `web-reviewed.json`, `actions-final.json`, `build-reviewed.txt`,
`typecheck.txt`, screenshots and the task baseline/diff. Browser data was mocked and
rendered locally in Edge, not a live authenticated integration or cross-browser check.
Database tests were not run because no API/schema/database changes were made. An
existing autoprefixer warning in TenantProvisionWizard.module.css remains outside this
list-only scope. Concurrent scenario/navigation work was preserved; its earlier test
failures cleared on the final full web run.


## Unified console back navigation - 2026-10-03

- Completed [the navigation TODO](back-navigation-todo.md). Reviewed 37 console
  routes: 32 non-root page routes, Home and four redirect-only routes.
- Added shared BackNavigation for explicit parent links and guarded callbacks,
  consistent 44px targets, theme styling, wrapping and keyboard focus. Standardized
  list/detail/create/error pages and removed duplicate return controls. Model
  details return to /models?tab=catalog. Editor guards, wizard steps, permissions
  and existing scoped list behavior are preserved.
- Review found and fixed the missing loaded-state catalog Back control and the
  wrong model return tab. Removed obsolete imports. No outstanding task findings.
- Verification: 1,577 shared UI tests passed; 547 web tests in 80 files passed;
  UI typecheck and production build passed. Initial unrestricted test workers
  caused two unrelated authentication test timeouts; the complete web rerun with
  three workers passed, including both tests. Existing Settings assertions were
  updated to account for the accessible Back control and keyboard order.
- Browser: 57 rendered states, 1,081 checks, zero failures, covering mobile/tablet/
  desktop, three themes, doubled root text size and keyboard focus. Visually
  inspected mobile Devices and desktop Models captures. Final whitespace check
  passed. Existing TenantProvisionWizard align-items:end build warning remains.
- Evidence: .test_artifacts/back-navigation-20261003/ (final-tests.log, tests.log,
  typecheck.log, build.log, browser-results.json and screenshots). Browser uses
  actual component DOM from mocked tests with shared/application CSS; it does not
  claim authenticated live-server, cloud or hardware verification. API/database
  checks were not run for this UI-only change. Concurrent unrelated work preserved.


## 2026-10-03: VM upgrade and cross-revision recovery

The authorized release upgrades the VM from `0033_tenant_training_starters` to
`0035_unified_scenarios`, with the current API and UI from commit `5c7e116`.
The build ran in an isolated checkout because a dependency directory was locked
in the working UI. Archive: `start/dist/pms-platform-20261003-122633-74a0de.zip`;
SHA-256: `e879b5a04b149f5714eb474d5a6b9971e1aca459664d08a93aaafab6ecb63265`.
All 778 manifest entries and 125 packaged API source/migration files matched.

Review reproduced a recovery defect: plain `pg_restore --clean` cannot drop an
old primary key when a table added by the upgrade references it. Recovery now
removes the managed application schema and replays the backup in one PostgreSQL
transaction. The generated SQL stays in the root-private temporary directory.
An isolated regression verifies that new dependencies are removed on successful
recovery and that an injected SQL failure preserves the pre-restore schema/data.
The migration preservation test also now explicitly checks the default values
of newly added model-management and scenario provenance/specialty columns.
No frozen migration or application business behavior was changed.

Verification: 10 deployment tests passed, including a fresh disposable PostgreSQL
bootstrap, migration, runtime grants, backup, successful recovery, and failed
recovery transaction. The focused migration/model/scenario run had 18 passes
and one stale migration assertion; after updating the new-column assertions,
the migration test passed. Full API unit run: 381 passed, 325 opt-in database/native
tests skipped. A broader PostgreSQL run was stopped after the first 10% to focus
on the affected upgrade paths; it is not claimed as a complete integration run.
All database tests used dedicated disposable servers, never the VM/application
database. API Ruff lint/format and mypy passed. Web: 555 tests passed; shared UI:
1,577 tests passed; TypeScript and production build passed. Initial UI runs had
Windows CRLF-sensitive assertions and a timeout; normalized isolated sources
and bounded-worker reruns passed without UI code changes. An existing CSS
autoprefixer warning remains.

Hosted deployment completed at `/opt/pms-platform/releases/20261003-123443-80462`.
API/web/worker/retention started at 2026-10-03 12:35:55 UTC; all are active with
zero automatic restarts and no error-priority service messages during verification.
The API and PostgreSQL both report `0035_unified_scenarios`. All 478 deployed
source/wheel checksums match the archive (Linux-generated UI build files were
excluded from that source comparison). Existing private configuration hashes are
unchanged. Before/after counts match: 3 users, 2 tenants, 2 memberships, 2 devices,
2 published scenarios, no scenario drafts, conversations, or LLM connections.
The three runtime database roles remain unprivileged; the new model-credential
and scenario-default tables grant read/insert/update only to the API role and
no access to worker/retention roles. Nginx configuration and both readiness
endpoints pass.

Pre-upgrade backup:
`/var/backups/pms-platform/pms-platform-20261003-123552-80462.dump`, mode 600,
492,333 bytes, revision `0033_tenant_training_starters`; `pg_restore --list` passed.
Previous release remains `/opt/pms-platform/releases/20261002-063745-39175`.
The external headless Edge check returned 200 for the login page and readiness,
401 for anonymous admin API access, and redirected the protected Models page
to login. There were no browser JavaScript errors or failed requests; the hosted
login screenshot was inspected. No application account, credential, or content
was created or edited during these smoke checks.

Evidence is in `.test_artifacts/vm-deploy-20261003/`, including deployment and
verification logs, archive checksums, test logs, browser results, and screenshot.
The dedicated local test server was stopped. No cloud-model call, hardware test,
or authenticated browser workflow is claimed. Changes remain uncommitted;
GitHub publication was not part of this deployment.

## Models management workspace review (2026-10-03)

In progress: [Models TODO](model-workspace-todo.md); final evidence and reconciliation will be recorded in [Models review](model-workspace-review.md). Dedicated disposable PostgreSQL uses loopback port 55453. No application database or live provider is used.


### 2026-10-03 - Tenant administration tab presentation (local)

- Reviewed Subscription, Administrators, Users and Devices. Added scoped CSS with responsive cards, usage metrics, administrator account rows, aligned search/selection forms, organized filters and consistent actions. Restricted-access views use available width; the shared modal focus trap, keyboard tabs, confirmation flows, permission gates and lifecycle restrictions remain intact.
- Verification: tenant-details, tenant-associations and tenant-list tests passed (30); web TypeScript check passed. Browser layout review used component-rendered mocked fixtures with shared styles and the new module styles: 10 states at 320, 390, 768, 1024 and 1440 pixels (50 checks), including expanded forms, read-only and archived tenants. No viewport/body overflow or clipped dialog controls; screenshots visually inspected. Evidence: `.test_artifacts/tenant-admin-tabs-20261003/`.
- Presentation-only local change; no API/database changes, destructive database tests or hosted deployment performed for this redesign. Browser checks use fixtures, not a signed-in live session.


### 2026-10-03 - Focused tenant user and device workflows (local)

- List screens now launch exclusive tasks. User addition separates account search/selection from role selection and confirmation. Device registration and transfer show only their own fields/results. During a task, unrelated list filters/actions, administration tabs and Done are hidden; Back restores the list. Review cancellation retains the draft; successful changes return to the list. Account-creation guidance appears for an empty account search and clearly identifies the separate Users & administrators page.
- Reviewed unchanged mutation APIs, permission/lifecycle gates, version/ETag checks, request guards, and confirmation behavior. Added task-heading focus, focus restoration and explicit return labels on review. Tests cover isolation, back/reset, late search after exit, account-creation guidance, registration review/correction/success, and transfer isolation.
- Verification: 35 related tests passed (18 associations, 11 details, 6 list); final affected associations rerun passed after review-label changes. Web TypeScript check passed. Mocked component snapshots checked in Edge at 320, 390, 768, 1024 and 1440 pixels in light and dark themes: 11 states, 110 layout checks with no overflow; desktop/mobile screenshots inspected. Evidence: `.test_artifacts/tenant-task-flows-20261003/`. Temporary capture test removed. Live browser helper selectors updated but its authenticated scenario was not run.
- No API/database change or deployment; browser visual evidence uses mocked data rather than a signed-in session.


### 2026-10-03 - Focused Models management: completed

Models now contains only model management and relevant filters/actions. Device assignment, provider connections and processing profiles have separate pages. See the [completed TODO](model-workspace-todo.md) and [planned/implemented reconciliation and review](model-workspace-review.md). Verification: web suite 566 passed; final affected rerun 32 passed; API suite 386 passed/333 skipped; isolated PostgreSQL 21 passed; local authenticated browser scenario 1 passed; Ruff, mypy and web typecheck passed. No live provider, application database or hosted deployment was used for this work. Rollout requires migration 0036 and updated runtime grants.


### 2026-10-03 - Models UI clarity follow-up: complete

Reworked header/list grouping, visible Edit, removable applied filters, status presentation, grouped wider editors and responsive spacing. Kept CSS scoped to Models; no API/database changes. Review fixed mobile row spacing and a shared CSS specificity conflict. Verification: 39 affected UI tests plus final 9-test rerun, web TypeScript check, authenticated fixture CRUD and 60 light/dark layout checks at five widths; representative screenshots inspected. [Reconciliation and evidence](model-workspace-review.md#ui-clarity-follow-up). Local work only; no hosted deployment or live cloud calls.


### 2026-10-03 - Devices Configure models popup: complete

Replaced navigation from the device action menu with a focused modal. Fixed device/tenant context, current setup, conditional local speech controls, optional media changes, guarded saves and draft protection. List filters persist; focus returns after close/save. Removed the old assignment component and bulk-device choices loader; old links redirect to the popup. Review fixed deep-link hydration, unchanged-save handling and warning presentation. Verification: 33 focused tests, 586 full web tests, final 9 dialog tests, web TypeScript, 8 isolated API assignment tests, authenticated browser assignment and 20 light/dark layout checks. Disposable database and temporary web server stopped. No API schema changes or deployment. [Reconciliation and evidence](model-workspace-review.md#devices-popup-follow-up).


### 2026-10-03 - Second tenant administration UX review

- Replaced nested confirmation popups for adding users, registering devices and transferring devices with an explicit final step in the original modal. Each review has a structured summary, a single confirm action and a return-to-edit action. Transfer retains its destructive consequence notice and danger action. Existing membership/device lifecycle actions retain their shared confirmation dialogs.
- Reduced task dialog width, aligned headers/forms, simplified mobile progress to a current-step label, and made review summaries wrap for long values. Focus announces the step and resets body scrolling. Escape returns from review to the draft; save-in-progress disables back/close/repeated submission. Corrected a browser-observed frame where old navigation/footer could remain visible when opening a task by synchronizing task state before paint.
- Verification: 37 related tests passed (20 associations, 11 details, 6 tenant list); affected association tests passed again after the final Escape behavior change. Web typecheck and scoped diff checks passed. Added regression assertions for one dialog, step isolation, correction after errors, preservation of registration/transfer details, and prevention of duplicate requests while busy.
- Browser evidence uses actual bundled React components and their CSS, with mocked API boundaries (not static HTML). 84 layout/state checks across 320/390/900/1440 pixel screens, a short 600-pixel-high window, dark mode and 200% text. Completed user, registration and transfer transitions, inline error correction, focus restoration and tab containment; empty/error searches, long tenant names and read-only access included. No horizontal overflow or browser page errors. Screenshots inspected; evidence in `.test_artifacts/tenant-ux-review-20261003/`.
- No authenticated/live API verification, database changes or deployment in this review. Updated authenticated browser helper review selectors without running its live scenario.


### 2026-10-03 - Direct models rearchitecture: reviewed

Typed models now own local/cloud configuration and encrypted credentials; device selections use one atomic save. Removed connection/profile steps from active UI and new writes, consolidated two physical configuration tables into compatibility views, and preserved historical execution and tenant scope. Review fixed retention-role scope lookups, capture-limit preservation, optional preference clearing, patient conversation canonical routing, validation errors, stale/uncertain saves and filter alignment. Web: 578 passed; API non-database run: 378 passed/332 skipped, with targeted disposable PostgreSQL migration/security/runtime suites run separately; Human-test: 54 passed; authenticated browser: 1 passed and 32 layout checks. Ruff, mypy and web typecheck passed. See [full reconciliation and evidence](direct-models-review.md) and [completed TODO](direct-models-todo.md). No application database migration, live cloud call, hardware verification, hosted deployment or publishing was performed.


## 2026-10-03 - models and device selection only

Final cleanup removes legacy management APIs and UI, tenant pickers and desktop mutation. 0038 preserves provenance, removes device/organization profile columns and makes legacy configuration immutable. Authorization rejects tenant/device model management. Final review fixed a remaining profile label and the all-None device status summary. Verification: 379 API passed/334 skipped; 11 targeted PostgreSQL checks plus 2 strengthened access checks (overlap); 554 web plus 47 affected checks after final fixes (overlap); 59 desktop; browser 32 responsive layouts; Ruff/mypy/TypeScript passed. Broader legacy database fixtures still need porting; no full DB-suite claim. No application migration, deployment, live cloud/hardware, commit or publish. See [full reconciliation](direct-models-review.md).


## 2026-10-04 - database, models and scripts synchronization

Completed: local database backed up and upgraded from 0035 to 0038; runtime grants and ORM verified; API readiness 200. Added read-only/apply sync scripts and aligned startup/transfer scripts. Verification: 10 initial disposable checks, 9 expanded schema checks, 379 API passed/336 skipped, 174 launcher tests, 30 platform checks plus 13 subtests, Ruff/mypy passed. See [database synchronization review](database-sync-review.md) for evidence and limitations.


## 2026-10-04 - Three default local Models page entries

- Added forward migration `0039_default_local_models`; the historical baseline and earlier migrations remain unchanged. Fresh `init-database`/deployment finishes with exactly Whisper large-v3, qwen3.5-4b-local and eSpeak NG visible and active. Other supported models can still be added explicitly.
- Migration archives only recognized, unchanged, unused starter records. It preserves tenant scope, credentials, administrator-created/edited models, disabled/archived entries, recorded usage and every device assignment. It locks administration/model/selection writes and commits each retirement with a system audit record using the configured audit retention policy. Historical rows and foreign keys remain intact.
- Readiness now requires 0039; owner-only tenant catalog backfill accepts the new head. Existing runtime grants, API permission checks and schemas are unchanged. Deployment already calls `init-database`, so no special deployment switch or recurring seed/reset is needed.
- Verified 21 distinct targeted checks across runs on a new disposable PostgreSQL server at loopback port 55464: 3 default-model tests, 9 schema/grants/sync checks, 7 direct-model API/device tests and 2 populated migration/adoption tests. Tests cover exact fresh defaults, repeat initialization, deleted/renamed defaults, custom/cloud/tenant models, usage, settings, device assignments, audit events, runtime permissions and Qwen3.5/Whisper device routing.
- Initial test failures were fixture issues (health URL, tenant lifecycle and immutable scope) and an existing direct-model fixture relying on the previous Qwen3 default. Corrected the fixtures and reran all affected checks successfully. Final review found no remaining authorization, integrity or compatibility issue in the change.
- Full API run without a database DSN: **379 passed, 339 skipped**. The skipped PostgreSQL suite was not all rerun; the 21 targeted checks above were exercised separately. Ruff check, Ruff format check (205 files), mypy (81 source files) and Git whitespace checks passed. Existing Starlette/httpx deprecation warnings remain. Deployment source collection includes migration 0039; the two new files have Git intent-to-add entries so the existing packager can include the migration. No release archive was built.
- This change sets Models page database defaults only. It does not download/install/load device runtimes or create device assignments. No application/hosted database migration, hosted deployment, cloud inference, hardware run, commit or publication was performed in this source-change task. The earlier requested local cleanup remains intact; deployment must apply 0039 before running this API revision.


## 2026-10-04 - Configure model choices before installation

- Diagnosed the local application database read-only: Whisper large-v3, qwen3.5-4b-local and eSpeak NG were active/shared; Manikin demo 2 was a pending manikin without reported inventory/engines. The old laptop/fresh-inventory/engine filter hid all three. There were no active cloud or video models. The user confirmed that assignment must be possible before installation.
- Device choices now mark active configured models selectable after tenant-scope and archive filtering, for either Local or Cloud. Saves retain Platform Admin permission, active tenant/department/device, non-retired lifecycle, tenant ownership, model kind/mode/status and revision checks. No device is automatically assigned. Enrollment, local runtime availability, provider enablement and execution authorization remain execution requirements; saving configuration makes no inference call.
- Updated local instructions and empty dropdown text. Existing selected inactive/missing models remain visibly unavailable and cannot be saved until cleared/replaced. Mode changes still clear incompatible selections; atomic snapshots and stale/concurrent-save protection remain intact.
- Verification: 10 distinct isolated PostgreSQL direct-model tests passed across final runs (the final affected rerun passed 2 tests). Covers pending manikin with no inventory, enrolled laptop with empty/stale inventory, all three local defaults, all four configured cloud types with mock credentials, secret redaction, tenant/role boundaries, inactive models, mode/kind rejection, snapshots and concurrency. Updated the old stale-inventory rejection test to verify stale reporting remains accurate while configuration stays available.
- UI: 13 affected tests passed; final dialog rerun 11 passed after correcting a test-only TypeScript query option. Web TypeScript passed. Full API run without DB fixtures: 379 passed, 342 skipped; those database tests were not all run. Ruff check/format and mypy passed. No live cloud inference or hardware verification was performed.
- Applied to the running local platform: stopped the inspected local launcher, used `platform/db/sync.py --apply` to back up and apply pending 0039, verified ORM/schema/runtime grants, then restarted via `start/platform_web.py` in a hidden process. Backup: `.local/db-backups/20261004T041802383050Z.dump` (archive index checked by sync). API and UI readiness both returned HTTP 200. Read-only post-check confirmed exactly the same three active local models and no assignment changes to Manikin demo 2.
- Review confirmed no source schema change beyond the already prepared 0039 defaults migration. No hosted deployment, provider calls, commit or publication. The disposable test server on port 55464 was stopped; the application database remains running.


## 2026-10-04 - Permanent platform-wide device unique IDs

- User decisions: require a manually entered ID at creation, maximum 50 characters, immutable across edits and tenant transfers; backfill existing registrations with their UUID strings. Implemented case-insensitive platform-wide uniqueness, whitespace trimming, rejection of blank/control-character IDs, and permanent reservation after retirement. Internal registration UUIDs remain separate for tenant history and credentials.
- Forward migration 0040 adds the identity reservation registry, format/uniqueness/FK/current-registration constraints and immutable triggers. Existing registrations and all historical references are preserved; each backfill gets an atomic system audit entry. The frozen baseline and prior migrations are untouched. Only the API role receives registry SELECT/INSERT; worker/retention have no registry privileges and runtime UPDATE/DELETE is prohibited. Readiness and synchronization verify the new head and grants.
- Fleet creation and onboarding require the ID; duplicate reservations return a generic 409 without disclosing tenant information. Updates reject the field. Transfers reuse the source identity, retire/flush the old registration before inserting the replacement, and preserve existing authorization, etags, subscription checks, audit atomicity and tenant-private history boundaries. Lists/search expose the ID, all creation forms require it and enforce maxlength=50, and edits show it read-only. Frontend update payloads omit it even if a draft is modified programmatically.
- Verification on disposable PostgreSQL at 127.0.0.1:55464: 48 focused checks passed (one legacy test excluded), covering identity validation, concurrent cross-tenant duplicates, direct SQL immutability, transfer/retirement reservation, populated and repeat migration, tenant onboarding, schema/runtime-grant verification and direct-model configuration tests passed. Seven additional checks passed for subscription-capacity concurrency and both plan boundaries, fresh/upgrade model defaults, and populated direct-model migration. No destructive tests used the application database.
- Full API run without a DB DSN: 387 passed, 345 skipped; the skipped PostgreSQL suite was not all rerun. Ruff check, format check (207 files), mypy (81 files), UI workspace TypeScript and Git whitespace checks passed. Full web suite: 562 passed across 78 files with two workers; a final affected action/wizard rerun passed 12. Initial unconstrained UI parallelism caused timeouts and cascading assertions; the bounded full rerun passed without raising test timeouts. Existing React act and dependency deprecation warnings remain.
- Known pre-existing test limitations: test_platform_assigns_published_tenant_model_profiles_without_private_access calls removed legacy profile/connection routes (404); test_manual_subscription_upgrade_preserves_existing_assignments expects default_profile_id, removed in earlier migration 0038. The former was excluded from the final focused run; the latter failed in the broader upgrade sample. These are not reported as passing. Corrected the current transfer regression to assert ID/history/model-selection isolation instead of a removed profile field, and supplied required IDs in registration/quota/browser fixtures.
- Local rollout completed: stopped the verified workspace launcher, ran platform/db/sync.py --apply, and restarted start/platform_web.py hidden. Backup: .local/db-backups/20261004T043215771103Z.dump (archive index checked). Schema/ORM/migration/grants agree at 0040. Read-only verification found one existing device, one UUID backfill, one reserved identity and one backfill audit. API and UI readiness both returned HTTP 200.
- Final review covered authorization, concurrent uniqueness, rollback behavior, transfer ordering, tenant isolation, immutable API/DB/UI behavior, runtime permissions and deployment packaging. New migration/test/document files have intent-to-add entries for the repository source collector. No hosted deployment, live cloud/hardware verification, commit or publication was performed.

- Cleanup: the dedicated disposable PostgreSQL server on port 55464 was stopped after the final checks; the updated local application remains running.


## 2026-10-04 - Tenant administration scope

- Removed the Users tab and panel entry from the shared Tenant administration dialog. The tenant-list Administrator action now opens Administrators; Subscription and permission-gated Devices remain. Administrator assignment continues through its existing dedicated action, with account-search permissions and confirmation unchanged. General tenant membership controls are no longer reachable from this dialog.
- Device registration already required device_unique_id after migration 0040. Strengthened the registration regression to check required/maxlength=50, review display and the submitted ID; preserved existing DB/API uniqueness and immutability.
- Verification: 38 affected UI tests passed across tenant administration, details, list and device actions; all UI workspace TypeScript checks passed. Browser fixture updated for administrator-only assignment and required device ID, syntax-checked only (no live browser mutation run). Git whitespace check passed. No additional API/schema change, database test, deployment or publication was needed for this UI change.


## 2026-10-04 - Platform options layout

- Added page-scoped CSS for consistent section spacing, label/input alignment, provider selection cards, language rows and footer actions. Container queries stack the overview and fields at smaller widths. Uses existing design tokens and components; no global CSS overrides. Corrected the shared adjacent-field margin within this page after visual inspection showed a 16px alignment offset.
- Retained configuration-version saves, English validation, maintenance confirmation and disabled controls for read-only accounts. Added guards against submitting read-only/busy forms, a read-only explanation, and removed the indefinite loading message after failed loads; successful reload clears the stale error. No API or database changes.
- Verification: 35 related UI tests passed (platform options, settings routes and catalog actions); the final four component tests passed again after a test-only typing correction. All UI workspace TypeScript checks and Git whitespace checks passed. Existing unrelated React act warnings remain in settings route tests.
- Rendered the real component and app styles in an isolated Edge/Playwright preview with mocked settings reads/saves. Inspected desktop/mobile/dark screenshots; verified 1440px, 768px and 390px layouts have no horizontal overflow and desktop input rows share top coordinates/heights. Mocked language creation/save passed without browser errors. Evidence is under .test_artifacts/platform-options-20261004/. This is component visual verification, not an authenticated live settings write. No production setting, cloud service, database migration, deployment or publication was performed.


## Scenario simplification review — 2026-10-04

Scope: schema v4 allows presentation/symptoms, history and eight vitals. Removed Q&A/Instructor/fact-disclosure UI, API fields, tenant seed additions and direct legacy create route. Forward 0041 converts active and historical case records, increments revisions, recomputes snapshot hashes, carries only valid existing language stamps and clears submissions. Historical compiled prompts are removed and contexts closed at the user's explicit request; transcript/result/audit records remain. No dedicated Q&A table exists, so dropping shared scenario/session tables would delete required functionality. Frozen migration files remain unchanged.

Verification so far: 7 focused contract/API/upgrade tests on disposable PostgreSQL; 10 tenant provisioning tests; 14 companion mock/coordinator tests; 21 UI tests; API and device mypy pass. Existing API non-database run passed 387, with 345 database tests skipped. Additional legacy training integration run hit 11 fixture setup failures at the retired /organizations/{id}/profiles endpoint, before scenario setup; not presented as passing. New runtime uses bounded local inference, retains lease/hash checks and authorization, and has no automatic external provider fallback.

Review fixes: preserve clinical facts and existing valid approvals while changing hashes; redact historical prompts that cannot be safely split into clinical versus old Q&A text; disallow removed keys in database checks; widen bounded companion input for the existing maximum case-document budget. Deployment and browser verification recorded below once completed.


Final verification and local rollout: schema 0041 was applied with platform/db/sync.py --apply after stopping the verified workspace launcher. Backup .local/db-backups/20261004T050556159899Z.dump was created and its archive index checked. Database, ORM, migration head and grants agree. Read-only verification found 9 global templates, 1 tenant case, 1 draft and 1 private selection all valid v4, zero retained historical system prompts, and zero active training sessions. API/UI HTTP readiness returned 200; live OpenAPI exposes only v4 authoring and no direct legacy create.

Final checks: API pytest 392 passed / 347 skipped without a disposable DSN; targeted disposable PostgreSQL contract/authoring/upgrade suite 7 passed and tenant provisioning 10 passed. Companion mock/coordinator suite 14 passed; UI scenario/catalog/practice 21 passed; final editor regression 14 passed after removing the legacy raw-record display. API and companion mypy/ruff passed; API formatting and UI typecheck passed. Browser preview used actual components/styles with mocked actions: 65 layout/theme/zoom combinations passed with no overflow or browser errors, exactly three clinical tabs/eight vitals, and desktop/mobile screenshots inspected. Legacy training integration's 11 fixture errors at the previously removed /profiles route remain explicitly unresolved; Pi, live inference and cloud verification were not performed.


## Scenario follow-up review - 2026-10-04

Confirmed findings and fixes:
1. Training admission still required the retired profile UI/API; new direct model selections could never satisfy it. Added admission for active local conversation + Whisper + eSpeak, preserving enrollment, agent, independent review, tenant/department scope, quotas, configuration hashes and lease checks. Existing legacy admission remains compatible. Updated training fixtures to configure models through current APIs; original 11 training integration tests pass.
2. 0041 advanced source case/template revisions without advancing current references, making current copied drafts falsely stale and risking loss of author edits on refresh. Added forward 0042 with the 0041 audit timestamp and exact previous revision as guards. Genuine stale sources and records edited after conversion remain untouched. Populated upgrade regression verifies custom draft documents, source references, private selection revisions, trigger restoration and repeat upgrade.
3. Adding a blank symptom emitted an invalid empty localization object, preventing incomplete-draft saves. Omit the optional description until text exists; publication still requires it. UI/API regression tests added.
4. Companion clinical replies used weaker validation than web practice, allowing JSON or analysis labels to be spoken. Reuse accepted_text and retain the 600-character speech cap; reject malformed/partial replies without a retry.
5. Updated inconsistent current schema-head documentation.

No published migration was rewritten. 0041 remains unchanged; 0042 contains metadata-only repairs. Live cloud inference and Pi hardware remain deferred. Final verification and rollout follow below.


Follow-up final verification: API full run without a disposable DSN passed 393 tests, with 351 database tests explicitly skipped. On disposable PostgreSQL at port 55464, the 11 original training integration tests passed; three additional missing-model/configuration-revocation cases passed, and the full clinical contract/authoring/populated-upgrade suite passed 9 tests. Device clinical/coordinator mocks passed 18 tests; UI catalog/scenario workflow passed 15 tests. API and device ruff, formatting and mypy passed; web TypeScript and Git whitespace checks passed. These are targeted database checks, not a claim that the entire database suite was run.

Local rollout: stopped the verified workspace launcher and ran platform/db/sync.py --apply. Backup .local/db-backups/20261004T051442170926Z.dump was created and archive-index checked. Database, ORM, migration head and runtime grants agree at 0042_clinical_source_references. Read-only validation confirmed 9 global templates, 1 tenant case, 1 draft and 1 private selection remain valid v4; no historical system prompts or active training sessions were present. Restarted the workspace services; API and UI readiness both returned HTTP 200. The disposable PostgreSQL test server was stopped. No cloud call, Pi hardware run, live model inference, commit or publication was performed.


## Tenant onboarding alignment - 2026-10-04

Reviewed the three tenant creation routes, shared starter helper, current Practice selection APIs, wizard and Settings. The backend already creates v4 clinical cases without Q&A, Instructor or disclosure content. Corrected wizard messages that claimed specialties were inactive and that published Practice choices required catalog activation. It now distinguishes active specialties, inactive editable cases/profile, active system starters without tenant clinician approval, and private user Practice selections. Device enrollment and model configuration remain explicit next steps. Settings no longer advertises QnA. Replaced the obsolete default-case reference (which still documented 32-topic answer banks and instructor fields) with current provisioning/content/lifecycle behavior, and aligned the API guide. Prior dated review entries remain historical evidence.

No API business logic, permissions, schema, seed data, or existing tenant records were changed. The previously requested Presentation placeholders and UI lengths remain in the working tree. Verification follows below.

Verification: 23 UI tests passed across tenant provisioning, Settings and catalog editing; web TypeScript and Git whitespace checks passed. All 10 tenant provisioning integration tests passed against dedicated disposable PostgreSQL on port 55464, covering wizard, platform and self-service routes, v4 starter contents, Practice selection while catalog cases are inactive, tenant isolation, lifecycle, source-change rollback, and device transfer. No tests in this targeted database run were skipped. Existing dependency deprecation warnings remain. No application database write, migration, live cloud/hardware check, commit or publication was performed for this alignment.


## Desktop-only Practice - 2026-10-04

Final scope follows the user's clarification: Practice runs in the desktop app, not the web interface. Removed both web routes (/practice and the historical /patient-setup), their components/styles, server actions and access helper, navigation items and Settings card. Renamed the remaining My sessions navigation group to Training and aligned onboarding/dashboard copy. Practice APIs, DB tables, records and provisioning defaults are retained because the desktop app uses them. No database removal migration was applied; the schema remains 0042.

Review found the desktop formerly required a scenario selected on the web. It now fetches the existing authenticated scenario-options endpoint, selects the saved/default/first compatible published scenario, supports switching between duplicate titles using distinct labels, filters by available desktop languages, restores saved vitals, and saves explicitly with the existing private-selection revision. An unavailable saved scenario is not silently restored or saved. Model execution, authorization, tenant boundaries, private ownership and backend validation are unchanged. Old catalog-form compatibility remains in the desktop app.

Verification: 64 web tests passed across navigation, shell, Settings, dashboard, catalog actions and onboarding. Web TypeScript passed after regenerating route types that referenced the deleted pages. Desktop setup/workflow tests: 12 passed, plus two Tk window regressions passed in separate processes (Windows Tk cannot reliably initialize twice in one process). Desktop ruff and mypy passed; mocked setup does not claim live model/hardware verification. Existing API behavior was retained; no database test or migration rerun was required for a backend change. Local services were restarted after removing stale generated route types. Final readiness/route checks follow below.

Final checks: regenerated Next route types contain neither /practice nor /patient-setup; API and UI readiness return HTTP 200. Live OpenAPI retains the desktop scenario-options endpoint. No removal migration exists and backend implementation/grants have no diff. No commit, publication or live inference was performed.


## Dedicated session start page - 2026-10-04

Start session now links to /sessions/new. The page groups device/learner, published scenario/language and session duration, with a responsive summary and separate request confirmation. Added loading, unavailable-choice and failure states, field validation with focus, minute-to-second conversion, and duration presets. Existing history, feedback and stop controls remain available. Review caught and fixed shared field margins misaligning adjacent controls.

Route, menu action and server actions require the existing results, processing, playback and instructor permissions; tenant context is checked before requests. Options exclude unenrolled devices and scenarios without supported published content/languages. Backend readiness/admission rules remain authoritative. Pending submissions prevent duplicate clicks; manual retries of unchanged input retain their idempotency key. No Python API or database changes were required.

Verification: 12 new component/server-action tests and 9 affected list regression tests passed; web TypeScript and Git whitespace checks passed. Browser checks with mocked actions passed at desktop, tablet, 390px mobile, 320px mobile and dark desktop sizes, with no horizontal overflow or browser errors; submission and confirmation passed. Evidence is in .test_artifacts/start-session-20261004/verification.json and adjacent screenshots. Local API readiness returned 200; unauthenticated /sessions/new returned 307 to /login. These checks did not create an actual device session or verify hardware/cloud execution. No database tests were run because the API/schema are unchanged. No commit or publication was performed.


## Tenant and role review - 2026-10-04

Scope: tenant provisioning, administrator recovery, member invitations/imports/lifecycle, department boundaries, clinical responsibilities, devices, sessions, navigation, settings and server-action permission alignment. The human-test desktop app is excluded; prior desktop changes are preserved. No application database cleanup or tenant data deletion is part of this review.

Confirmed UI findings fixed: trainee navigation incorrectly required detailed device/configuration permissions for basic Devices and personal Settings; session stop/feedback controls checked processing permission without instructor capability or ownership; saved clinical responsibility assignments could not be revoked after a role/scope change made them ineligible; assignment controls were available before their state loaded. Updated permission gates, ownership checks, loading/retry behavior and regression coverage. The API remains authoritative and already enforced these boundaries. Removed the unreachable TenantUsersPanel and its unused web action/type module and tests; tenant administrator and device administration tabs remain. Removed a leftover Practice destination filter.

Added an opt-in browser regression using a dedicated disposable API on port 8146 and isolated Next instance on 3146. Real login and navigation passed for org_admin, org_user, org_read_only and org_trainee, including device detail/edit visibility, session-start controls and direct-route denial, personal Settings and denied administration routes. API checks verified tenant isolation, no implicit platform access and trainee configuration denial. No real session, cloud inference or hardware execution was triggered. Evidence: .test_artifacts/tenant-role-review-20261004/browser-verification.json and role screenshots.

Initial verification: 393 API tests passed without a test DSN, with 351 database/opt-in tests explicitly skipped; API ruff, formatting and mypy passed. All 556 web tests passed with two workers; an earlier unrestricted run timed out one wizard test under load, which passed in both focused and bounded full runs. Web TypeScript passed. Broad isolated PostgreSQL results and any follow-up fixes are recorded below after completion.

Follow-up findings: two stale database regression expectations were corrected without changing production rules. Self-archiving membership now asserts the existing 403 self_membership_action guard. Catalog import now selects an unimported starter case and verifies existing provisioned specialty/profile lifecycle is preserved (active specialty, inactive profile). Added a revocation assertion after demotion and verified it remains revoked after restoring the eligible role. The affected two tests passed; five other clinical capability/authorization database tests also passed.

Regression maintenance: the broad disposable PostgreSQL run passed 171 tests and exposed 18 stale tests referencing retired profile/connection management APIs, legacy scenario documents, or outdated status expectations. Updated affected tests to exercise direct runtime-model assignment, encrypted model credentials and revision conflicts, local engine advertisement, v4 scenario publication, privacy and fail-closed runtime compatibility. Existing authorization and processing rules were retained. The backup/restore regression now compares the current schema and verifies restored model-owned credentials; all provider submissions remain mocked. Focused rerun results follow.

Final verification: every failure from the initial 189-test PostgreSQL selection passed in focused reruns after fixture/expectation maintenance. Scenario-review and direct-model assignment regressions passed, including added rejection coverage for unsupported runtime versions. The processing/database-review rerun passed 13 tests; its remaining capture-policy expectation was corrected to the current policy response and passed separately, with an additional over-limit admission check. The broad 18-minute selection was not repeated in full; the original 171 passes and focused follow-ups are separate runs. All tests used disposable PostgreSQL on 127.0.0.1:55464, never the application database. The complete API suite was not rerun with a database DSN; the earlier 351 skipped cases are not represented as all passing.

Final API ruff, formatting (212 files), and mypy (81 source files) passed. Web TypeScript and all 556 web tests passed; real browser checks for four tenant roles had no page errors. Local API readiness and UI login both returned HTTP 200. No production API business rules or schema changes were needed. No application records were deleted, no human-test desktop files were changed by this review, and no live cloud/hardware checks, commit, or publication were performed.

## Cloud model review - 2026-10-04

Reviewed current runtime-model management and dispatch for 11 provider/type combinations: four conversation providers, three ASR providers, two TTS providers and two video providers. Fixed lost optional settings on edit (Whisper model/API version, AWS staging prefix), missing temporary AWS session-token input, inaccessible conversation protocol/reply controls and speech output format. Aligned Whisper create-time endpoint allowlisting with dispatch and rejected malformed provider credential headers. Azure resource synthesis now uses /tts/cognitiveservices/v1; ASR connection checks use transcription locale access rather than the TTS voice catalog. No desktop implementation or application records changed.

Added POST /platform/runtime-models/{id}/test and Models Test connection. This access-only check has a 30-second deadline, requires the saved revision and active platform access, releases the transaction before network I/O, reauthenticates afterwards, checks lifecycle/provider availability again and locks the current revision while recording a sanitized audit result. Tests cover stale edits, revoked administrator permission, disabled external calls, redacted SDK failures, encrypted credential retention/clearing and deletion. A success explicitly reports inference_verified=false. No durable test-success flag can incorrectly survive a model edit. No schema migration is required.

Verification: initial selected PostgreSQL/direct-model/adapter suite 26 passed. Final provider-management/adapter/browser selection 27 passed, plus the added permission-revocation regression passed separately. Full API suite without a test DSN: 418 passed, 354 database/opt-in tests skipped; the full database suite was not run. Web component/server-action tests: 27 passed; TypeScript passed. API ruff, formatting (213 files) and mypy (81 files) passed. Real browser-to-Next-to-disposable-API flow passed create/edit, credential redaction, deployment-disabled test feedback, selection/save/reopen, delete and 40 responsive light/dark captures with no browser errors or overflow. Evidence: .test_artifacts/cloud-model-review-*.log and .test_artifacts/cloud-models-20261004/result.json.

All provider calls in automated verification were mocked. Live cloud inference, provider accounts, hosted deployment and Raspberry Pi hardware remain unverified. Existing user work was preserved. No commit or publication was performed. Provider references and test limitations are in [cloud model management](cloud-model-management.md).

Final local activation: restarted the existing platform launcher after verifying its process identity. API readiness and UI login returned HTTP 200; live local OpenAPI contains the new runtime-model test route. The disposable database and isolated browser-review server were stopped. Restored the review-only Next tsconfig rewrite; final Git whitespace checks passed. Provider enablement, endpoint allowlists, credentials and external-call settings were not changed in the application environment.

## Device model configuration review - 2026-10-04

Scope: Configure model dialog and server actions, platform device choices/save, four model kinds in local/cloud mode, execution snapshots, model edits/deactivation, clearing assignments, tenant/department boundaries and transfers. Desktop implementation remains excluded. Assignment still works before enrollment or local installation; execution retains its enrollment, runtime capability, provider and tenant checks.

Fixed three findings: failed dialog reloads retained editable stale choices; the dialog did not reflect tenant/department lifecycle blockers; disabling an assigned cloud ASR model made the shared conversation route try to load a now-empty speech binding. Reloads now clear old choices, submission checks the device identity, choices and save share lifecycle checks, and disabled speech is represented accurately without preventing access to the independently configured conversation model. Disabled speech still cannot execute. No schema/data migration is needed.

Added regressions for per-device clearing and old-configuration rejection, unchanged neighboring devices, tenant/department/device blockers, disabling/restoring cloud speech, and transfers retaining physical identity while copying no model assignments. Extended the real browser flow to switch Local to Cloud, reopen saved choices, and clear all four slots. Final verification results follow.

Verification: the selected device/model/identity suite passed 33 checks initially; the new two-device isolation fixture hit the Standard plan one-device quota. Corrected that fixture to provision the Advanced plan, and its focused rerun passed (34 selected checks passed across these runs). Final disabled-cloud-speech regression and real browser flow passed separately (2 tests). The browser covered switching local to cloud and clearing/reopening all slots, plus 40 light/dark layouts without overflow or page errors. Web tests: 23 passed; TypeScript passed. Full API suite without a test DSN: 418 passed, 358 database/opt-in tests skipped. API ruff, formatting (214 files), and mypy (81 source files) passed. Evidence: .test_artifacts/device-model-review-*.log and .test_artifacts/device-models-20261004/result.json.

Database checks used disposable PostgreSQL on port 55464. No application records were deleted or migrated, and no real inference, external cloud, hardware execution, commit or publication was performed.

Local activation completed: restarted the verified platform launcher, and both API readiness and UI login returned HTTP 200. Stopped the disposable database and isolated review UI. Restored the review-only Next tsconfig rewrite. Existing application provider settings and model assignments were preserved.


## Human-test desktop compatibility review - 2026-10-04

Reviewed current desktop startup, device assignments, published-scenario Practice, microphone/typed requests, conversation contexts and local history. Confirmed and fixed disabled/job-only speech being treated as active Azure speech during startup/readiness, unnecessary local speech companion requirements, and unsupported microphone capture. The shared desktop capability check supports local Whisper and Azure OpenAI Whisper; other ASR assignments remain device-job processors, with typing available. Desktop playback remains installed Piper and camera capture remains local recording; the model summary now makes this distinction explicit and includes all four device assignment slots.

Model reload formerly called Controller.use_models on the Tk thread; closing a previous conversation could then fail to schedule its coroutine and stop event processing. Reload now applies on the worker, fences closed/stale dialogs, exposes failure/retry state, resets the conversation and returns to setup. Scenario language filtering is reapplied instead of replacing it with every model language. Null initial vitals render as blank entries; save validates all eight current contract fields, finite/range limits and blood-pressure order.

Removed unused local model publication/activation and loopback mailbox implementations, client settings and their obsolete tests. They called retired tenant connection/profile APIs and were no longer launched or shown. Retained installation discovery/checks, companion ownership/supervision, privacy boundaries, recording and history tests. Updated read-only model configuration and mandatory device registration UUID instructions; the physical device unique ID is not an authentication or API UUID replacement.

Real desktop-to-API contract checks use the existing disposable PostgreSQL fixture with current migrations and runtime grants. They exercise local/cloud assignments, v4 scenario setup, regular org_user access without clinical author rights, conversations, stale saves, reassignment rejection and local history upload/read/idempotency. This found an additional API bug: close still required clinical author access for published-scenario conversations. Close now uses locked published-scenario access, retains private ownership and legacy author checks, and records its audit atomically. No migration is needed. API calls in this review do not run inference.

Final verification results follow. Native Tk tests use separate processes where Windows Tcl cannot reliably initialize twice after window teardown. Earlier desktop failures included an obsolete model-options test and incomplete fake-window state; these test fixtures were updated to the current contract. The launcher readiness timeout test no longer imports the uninstalled backend package into the desktop environment.

Final review also expanded launcher environment filtering to remove AWS, Azure Speech/identity and Anthropic variables as well as existing backend/OpenAI credentials from desktop and companion processes. Tests cover inherited and explicit child environments.

Verification: full desktop suite 469 passed, 6 opt-in checks skipped (2 resident local Qwen and 4 installed-voice checks). Full launcher suite 153 passed. Native Tk setup/model-dialog regressions passed, including minimum-window geometry. The final isolated PostgreSQL desktop/API selection passed 2 parameterized local/cloud tests with ordinary org_user access, cross-owner denial, revoked processing permission, repeated-close idempotency and one audit event. Full API run without a database DSN: 418 passed, 360 database/opt-in tests skipped; this is not a claim that the whole database suite ran. API ruff, formatting (215 files), and mypy (81 source files) passed; desktop ruff and mypy (26 source files) passed, with changed production Python files formatted. Git whitespace checks passed.

Stopped disposable PostgreSQL on port 55464. Restarted the verified local platform launcher to activate the API fix; API readiness and web login both returned HTTP 200. No application data migration/deletion, private configuration edit, live cloud inference, microphone/camera/voice quality assessment or physical-device execution was performed. Restart any existing Human-test window/launcher to load the desktop changes. No commit or publication was performed.


## Human-test final desktop review - 2026-10-04

Fixed four remaining recovery/lifetime issues: cancelling a model reload left Reload disabled; closing the dialog after a successful apply could leave the main screen on the old setup; a failed or cancelled readiness probe could leave its sibling running; and an uncertain conversation start reused its idempotency key with changed input/output settings. Reload cancellation now offers retry, committed model changes always refresh setup, readiness waits for all cancelled probes to finish, and context retries retain the complete original payload until setup/reset clears it. Local route validation happens before speech probe coroutines are created.

Added six desktop regression cases for cancellation, dialog closure, failed/cancelled readiness, invalid local configuration and exact-payload retry/reset. Extended the real desktop/API local and cloud checks to drop the first response after the API commits a conversation, change desktop input/playback settings and recover through the same request. Existing scope, permission, reassignment and close/audit checks still pass. No provider inference is invoked by these checks.

Verification: full desktop suite 475 passed, 6 opt-in checks skipped (2 resident local Qwen and 4 installed-voice checks). Focused desktop selection: 46 passed. Disposable PostgreSQL/API integration: 2 passed. Full API suite without a test DSN: 418 passed, 360 database/opt-in tests skipped; only the two selected integration cases were run against PostgreSQL in this final pass. Desktop/API ruff and mypy passed; changed desktop files and all 215 API Python files passed formatting checks. The earlier launcher suite remains 153 passed; launcher code was unchanged in this pass. Git whitespace checks passed.

Stopped the disposable PostgreSQL instance on port 55464 after verification. Application data was untouched. No live cloud, microphone/camera/voice quality or physical-device verification was performed. Restart the desktop to load these fixes. No commit or publication was performed.

## Fresh Ubuntu VM deployment - 2026-10-04

User explicitly authorized dropping the old VM platform database and deploying the current API/UI. Verified the pinned SSH host key for 57.159.29.252 and the configured target: local PostgreSQL device_platform owned by pms_owner. The prior managed release was 20261003-123443-80462 at schema 0035_unified_scenarios. Other databases and database roles were retained.

Built current working-tree deployment sources in an isolated copy using start/build_platform.py after the original local build encountered locked UI dependency files. Restored the local dependency installation; no UI source or lockfile diff remains. The Windows production UI and both Python wheels built successfully. Archive: pms-platform-20261004-070535-24f2c8.zip, SHA256 ee295becf6acf0abb540a7e74a8e6e989fefbe9295a98b99a00b88ba0d5a2ea4. Uploaded archive integrity was verified before mutation.

Placed Nginx in maintenance mode, stopped all four application services, confirmed no application database sessions, and saved a root-private recovery dump/configuration under /var/backups/pms-platform/fresh-20261004-071757. Dropped the complete device_platform database. Archived old release pointers and old media in that private recovery directory; retained release directories, PostgreSQL roles, runtime configuration and HTTPS certificates. Rotated the initial installation key without exposing it. Ran the existing start/deploy-platform.sh against the new archive; it recreated the database, rebuilt the UI on Ubuntu, initialized all migrations/defaults, reapplied runtime grants and started the services.

Active release: /opt/pms-platform/releases/20261004-071802-102844. API and database revisions both match 0042_clinical_source_references. Verified zero users, organizations, memberships, devices, scenario drafts, training scenarios, patient conversations and legacy LLM connections. Exactly three active local defaults exist: Whisper large-v3 (ASR), qwen3.5-4b-local (LLM), and eSpeak NG (TTS). These are catalog defaults; model runtimes were not downloaded to the VM.

Verification: API/web local readiness and public HTTPS readiness returned 200. API, web, worker, retention and Nginx are active with zero restarts. First-administrator setup reports required=true and available=true. Checked all 486 deployed source/wheel hashes against the transfer manifest, validated the recovery dump and Nginx configuration, and confirmed no stale previous-release rollback pointer remains. Real Edge browser checks at 1440px and 390px passed: setup form visible, no horizontal overflow or page/HTTP errors, and homepage redirects to /setup. Evidence: .test_artifacts/vm-fresh-20261004/browser-result.json and setup screenshots.

Public entry: https://eval.centralindia.cloudapp.azure.com/setup. The operator retrieves the new installation key only in a private VM terminal with sudo bash /home/evaluator/pms-fresh-20261004/deploy-platform.sh setup-key, then creates the first administrator. No administrator/test tenant was created by verification. External cloud calls remain disabled as configured; live inference and physical-device execution were not tested. No Git commit or GitHub publication was performed.


## 2026-10-04 Device-only desktop pairing and database/script/model alignment

Implemented a native Tk setup screen shared by launcher entry points. It accepts the platform origin, immutable device unique ID (or registration UUID), and one-time enrollment token. The API matches the ID before consuming the token, returns scoped identity, and exposes authenticated device identity plus a public HTTPS-compatible API readiness route. Enrollment itself needs no human login. The resulting device credential drives Practice and model access; no user account is fabricated. Credentials are stored privately and atomically; enrollment tokens are never saved. Enrollment response loss is not automatically replayed. Model startup failure retains successful enrollment for retry. Network/model work stays off the UI thread; cancellation stops owned services. Optional desktop history settings remain respected.

Migration 0043_device_practice adds exclusive human/device ownership to five existing tables with same-tenant and same-owner foreign keys, immutable selection/conversation ownership, and a credential version on device cloud requests. Human-owned data is retained. API execution checks device lifecycle, tenant/department scope, fixed conversation context and assigned models; administration/authoring remain human-only. Audits now identify the authenticated device. Device history uses a server-verified device identity namespace. Review fixed a department-device cloud Practice restriction and rechecks model assignment after a cloud health probe.

Alignment review found the owner-only deployment catalog backfill's head allowlist missing 0043; fixed and regression-tested. Updated readiness, ORM, migration documentation and grant commentary. Strengthened platform/db/sync.py to check device ownership constraints and exact API/worker/retention grants, alongside its existing column/type/nullability checks. A permission-drift regression deliberately grants worker conversation access and confirms rejection. Frozen SQL baseline and prior migrations were not changed.

Verification:
- Desktop full suite: 483 passed, 6 environment-dependent skips. Subsequent added/affected pairing and history tests: 21 passed. Launcher suite: 153 passed.
- Native Windows Tk smoke passed: minimum-size action visibility, input bound, responsive enrollment progress, retained enrollment on model failure and reconnect retry. Repeated after optional-settings fix.
- API full suite without test DSN: 418 passed, 364 PostgreSQL-dependent skips. Targeted disposable PostgreSQL: final pairing/schema suites 14 passed, separate migration upgrade 1 passed; desktop API compatibility, device configuration and unique-ID tests also passed (17 additional tests). Pairing tests cover local/cloud and tenant/department devices, wrong ID without token consumption, single-use token, owner isolation, direct ownership mutation rejection, audit attribution, local metadata/history, disabled scopes, changed assignment during provider health and revocation. Cloud calls were mocked.
- API and desktop Ruff check/format and mypy passed; Windows-aware Git whitespace checks passed. Production UI/API transfer build passed with the existing nonblocking flex-end compatibility warning.
- Broader historical PostgreSQL suites were attempted but encounter pre-existing fixtures posting to the removed tenant /llm/connections API. These are not reported as passing. The migration preservation test was updated to acknowledge the already-authorized 0041 historical case simplification and new nullable owner fields; real baseline-to-head upgrade, ORM shape and existing record preservation passed.

Local database: sync --apply created .local/db-backups/20261004T124909946349Z.dump, upgraded to 0043 and verified ORM, constraints and grants with no connected services. VM release 20261004-125002-107925 was deployed using the standard script, forward migration and private backup /var/backups/pms-platform/pms-platform-20261004-125119-107925.dump. Existing IDs/counts preserved: 2 users, 1 tenant, 1 membership, 1 device, 13 model records, 1 device assignment, 2 published scenarios. API/web/worker/retention/Nginx are active. Public HTTPS API/web readiness and device identity authentication passed; 488 source/wheel checksums verified. The actual desktop PairingClient also passed readiness against the deployed HTTPS API. No real device was enrolled or credential rotated during verification; no cloud inference, microphone/camera or Raspberry Pi hardware verification performed.


## 2026-10-04 Requested latest API/UI/database VM redeployment

Compared all 486 deployment source files byte-for-byte with the tested transfer archive; no source differences were present. Redeployed that verified archive through start/deploy-platform.sh, rebuilding the API packages and production UI on Ubuntu. Active release: 20261004-125312-109062. Database was already at 0043_device_practice; initialization, catalog backfill and runtime grants completed without a new schema migration or reset. Created and verified a fresh private backup at /var/backups/pms-platform/pms-platform-redeploy-20261004-125341.dump.

Post-deploy verification passed: database/ORM types and nullability, device ownership constraints, runtime grants, all five platform services active, public HTTPS API/web readiness, unauthenticated device-identity rejection, and 488 source/wheel checksums. Existing IDs/counts retained: 2 users, 1 tenant, 1 membership, 1 device, 13 model records, 1 device assignment and 2 published scenarios. No device credential was rotated and no cloud inference was submitted. No source changes required repeat unit tests; the production build and deployment checks ran again. Existing nonblocking CSS compatibility build warning remains.


## 2026-10-04 - Desktop provisioning and offline download review

Scope: desktop-only setup management. Added icon-only header access with tooltip; confirmed handoff stops owned companions before opening provisioning. Local reset uses the launcher's ownership lock, validates exact generated targets before deletion, replaces the private device credential with a cleared marker, and blocks legacy environment fallback. Models, media/history and the platform device registration remain. Existing tenant/device API authorization is unchanged.

Offline installer review: allowlisted assets and commands, confined paths, credential-free child environment, bounded/redacted progress, owned-process cancellation, startup/install mutual exclusion, conservative disk budgets, CPU default/optional CUDA. Existing Qwen/voice checksum installers are reused; Whisper stages outside the active model directory and loads with local_files_only=True before publication. Found and fixed CPU-only Qwen inheriting the repository CUDA preference, Tk timers left behind on setup reopen, and the gear hover replacing connection status (now a tooltip).

Evidence: desktop pytest 485 passed / 6 skipped (opt-in resident Qwen and installed-voice execution); launcher pytest 166 passed; Ruff check and formatting passed; mypy passed for 27 desktop source files. Native Windows connection_window_smoke.py passed pairing/resume, minimum-size action visibility, download responsiveness/cancel, disabled connection actions during installation, manage-mode auto-connect suppression, explicit reset, actual desktop gear/tooltip and clean exit. Regression coverage also includes provisioning ownership locks, retained history, legacy suppression, failed download not published, successful staged destination, installer cancellation, secret filtering and CPU fallback. Download/native-model operations use mocks here; no real multi-GB download or hardware inference is claimed. No new API/DB changes or database tests were required for this desktop change.


## 2026-10-04 - Human-test provisioning/download/session follow-up review

Confirmed and fixed: setup checked launcher ownership only after enrollment, allowing a second window to replace saved pairing while another session/installer owned the installation. Ownership now starts before any enrollment/resume request and remains held through startup; failure cleanup releases it. Cancellation now prevents the next network request, but enrollment that already completed is privately persisted. Malformed error-code types and deeply nested error JSON no longer escape safe connection errors.

Download review fixes: an existing Whisper directory could pass structural discovery but fail native load on every retry without redownloading; it now enters verified staging repair. A rename failure during publication restores the previous model directory. Repairs and optional CUDA installation check available disk space. Missing uv, disk limits and failed local loading now have safe allowlisted error messages across the installer process boundary. File discovery uses the requested checkout and treats malformed metadata as unavailable. UI close now ignores late installation scan events; pressing Enter on Offline models no longer starts enrollment. Previous model directories are retained on successful repair and documented. No model assignment, provider fallback or server registration deletion was introduced.

Training verification: extended test_device_desktop_pairing.py to drive the actual desktop Controller through multiple turns, local model HTTP protocol, API-admitted immutable contexts, telemetry, reset/close and a fresh conversation. Real API/SQL authorization blocks another owner and revoked device credentials before further inference. Four combinations cover local/cloud and organization/department device scope. The two existing user-owned desktop/API compatibility cases also passed. One initial new test incorrectly expected GET on a closed conversation to return a closed resource; corrected it to assert the documented 409 conversation_closed plus the persisted closed database state. Full API checks also caught a stale exact-text grants assertion missing migration-0043 comments; synchronized the assertion without changing grants, migrations or API production code.

Verification: desktop pytest 488 passed, 6 opt-in execution checks skipped (2 resident Qwen, 4 installed voices); launcher pytest 173 passed; API pytest without test DSN 418 passed, 365 database/opt-in checks skipped. Separately ran 6 actual integration cases against a newly initialized disposable PostgreSQL cluster under .test_artifacts/desktop-review-20261004, loopback port 55465, with per-test databases, forward migrations and runtime grants; all passed. Stopped that server after tests. Native Windows connection_window_smoke.py passed actual gear/tooltip, pairing/resume, reset, minimum-size layout, responsive download cancellation, close-during-download and late-event handling. Desktop/API Ruff and formatting passed; mypy passed for 27 desktop and 82 API source files. Existing FastAPI/Starlette test-client deprecation warnings remain.

Limits: cloud/model responses and download payloads are mocked. No new multi-GB model download, real provider inference, microphone/camera capture, voice-quality assessment or VM redeployment was performed. Application databases and saved device provisioning were untouched. Changes remain available in the workspace for review.


## 2026-10-04 - Hosted sign-in failure and stale deployment recovery

Investigation: all five managed services and public/local readiness endpoints were healthy. The web journal recorded a Server Action absent from the deployed build, consistent with an already-open login tab surviving redeployment. A fresh browser sign-in using a nonexistent diagnostic account reached authentication and returned the expected invalid-credentials response. No existing account password was needed or changed.

Fix: LoginForm recognizes the installed Next.js client's UnrecognizedActionError, clears the entered password, disables repeated sign-in submission, and offers Refresh page with an explanation that the platform was updated. A full reload obtains current action references. Ordinary connectivity errors still permit retry; credentials are never automatically replayed. Added a regression for the stale action, password clearing and disabled replay. Deployment documentation now explains refreshing older tabs.

Verification: 10 login tests plus 18 session/watcher/auth-layout tests passed; web TypeScript check passed. Production build passed on Windows and Ubuntu (existing nonblocking TenantProvisionWizard CSS warning remains). Used the existing pinned SSH host key and private credential prompt. Created and verified backup /var/backups/pms-platform/pms-platform-login-20261004-133130.dump. Standard deploy activated release 20261004-133134-110590. Schema remained 0043_device_practice; existing user, tenant, device, model, selection and conversation identifiers were preserved. Source/wheel manifest checksums, deployed browser text, five service states and public HTTPS readiness passed.

Live headless browser verification injected an obsolete, valid-format action reference: HTTP 404 led to the refresh prompt, empty password and disabled Sign in. Clicking Refresh page loaded the current application, and the following diagnostic sign-in reached authentication and returned the expected invalid-account message. No real-user successful sign-in or provider inference is claimed. Existing open tabs still need Ctrl+Shift+R once to load the updated client. No Git publication was performed for this fix.


## 2026-10-04 - Human-test inventory HTTP 422 on manikin enrollment

Confirmed cause: the VM had one manikin registration and recorded an inventory HTTP 422. The deployed endpoint rejected every non-laptop registration, although enrollment and device-only practice support manikins. Removed this obsolete device-type gate from reporting and platform inventory inspection. Active device authentication, submitted-ID matching, tenant/department lifecycle checks, supported unique model names, bounded payloads, audit records and atomic persistence remain in place. No schema, grant, device-type or enrollment reset is required. The desktop now maps known inventory error codes to safe actionable messages, bounds all response bodies, and handles malformed error shapes without exposing server bodies or credentials.

Verification: 181 launcher tests passed, including 8 new inventory error/bounds cases. API checks: 418 passed and 370 database/opt-in checks skipped in the broad run without a DSN. Separately, 10 real PostgreSQL cases passed on dedicated disposable loopback port 55465: 2 inventory contract cases and 8 actual desktop pairing/Controller flows across manikin/laptop, local/cloud and department/no-department combinations. These cover report immediately after enrollment, empty inventory, supported models, mismatched device IDs, user-token rejection, invalid/duplicate aliases, inventory inspection, conversation turns/reset, history isolation and revocation. Inference is mocked; no hardware or real provider inference is claimed. Disposable PostgreSQL was stopped afterward. API/launcher Ruff and formatting, API/desktop mypy and production builds passed. Existing CSS and test-client deprecation warnings remain.

Deployment: verified backup /var/backups/pms-platform/pms-platform-inventory-20261004-134606.dump; standard deployment activated release 20261004-134610-111886. Schema remains 0043_device_practice. Existing user, tenant, device, model, selection and conversation identifiers were preserved. Manifest/source checks, installed Python module, five service states and public HTTPS readiness passed. A live request using the existing protected desktop enrollment returned HTTP 200 for identity, accepted the actual installed-model inventory, and returned HTTP 200 for assigned model configuration. No credential rotation or re-enrollment was performed. No Git publication was performed for this fix.


## 2026-10-05 - Device session queue and assigned Human-test practice

Implemented a per-device Sessions workspace with batch trainee planning, shared defaults and individual case/language/duration choices, waiting-session editing/removal, accessible and drag reordering, pause/resume, active-session ending and scoped history/results. Learner and desktop case selectors consume all API pages. Earlier training history remains accessible. Home activity and trainee statistics include assigned practice.

Human-test previews the assigned case/language and observations before Begin, keeps the trainee visible, binds the conversation to that assignment, preserves it through Previous, and advances after Complete & Close. Web end stops capture/playback before acknowledgement. Standalone practice remains available without a ready assignment; an arriving assignment waits for an existing standalone conversation, including its Previous screen. Unsupported assigned languages cannot silently fall back. New cases absent from the initial catalog load explicitly at Begin. Assignment changes never start recording automatically.

Forward migration 0044_session_queue adds scoped queue/session tables, immutable attribution/deadlines, lifecycle triggers and one-active-session uniqueness. Every assignment has a fixed 24-hour deadline from creation, including already-started assignments; duration and short device leases also stop active sessions. API expiry maintenance runs without a connected desktop. Organization locking serializes admission/reorder/batch capacity; revision checks and idempotent request keys protect retries. Scoped instructor permissions, active trainee membership, device credentials, department, published cases and model configuration are checked server-side. Queue transitions and audits commit together. API runtime grants include the new tables; worker/maintenance grants explicitly exclude them. Old standalone request fingerprints remain compatible.

Verification: broad API pytest without a database DSN: 430 passed, 376 skipped (database/opt-in tests), with existing test-client deprecations. Five new PostgreSQL integration cases passed on a dedicated, freshly initialized disposable server on loopback port 55446, with per-test databases, migrations and runtime grants. They cover concurrency, ordering, pause/edit/remove/idempotency, immutable 24-hour deadlines, background expiry, learner isolation, actual saved local-text attribution, dashboard counts, revocation, lease loss, standalone handoff and web completion. A broader database run passed 11 cases (including eight existing desktop pairing flows); six older patient-conversation fixtures failed before execution because they still call the removed /llm/connections endpoint. This is not a clean full database-suite result.

Desktop full pytest: 498 passed, 6 optional installed-model/voice checks skipped; after final language-preview guards, 22 focused queue/scenario tests passed. Native Tk smoke passed assigned defaults, two sequential trainees, Previous, desktop completion and web stop, using in-memory platform/controller doubles. Existing native setup layout checks passed at 1180x860, 1080x800 and 1080x680. API/desktop Ruff and formatting passed; mypy passed for 84 API and 28 desktop source files. Web suite passed all 568 tests with two workers (the initial unrestricted-worker run encountered CPU-contention timeouts); focused queue tests and TypeScript passed. Final production build exited 0, with the existing unrelated TenantProvisionWizard CSS warning. Headless Edge checks of the actual component with mocked server actions passed desktop/mobile layout, planning dialog, overflow and console checks. Evidence is under .test_artifacts/session-queue-20261005. The disposable PostgreSQL server was stopped after verification.

Final review checked tenant/result boundaries, immutable identity/deadlines, simultaneous admission, stale queue revisions, standalone Previous, runtime ownership, failed-begin cleanup, acknowledgement retries, expiry and stop-before-handoff. No provider/hardware integration, hosted redeployment or Git publication was performed. Installation requires applying migration 0044, the updated runtime grants, and updating API, web and Human-test together; see docs/device-session-queue.md.


## 2026-10-05 - Final session queue review and fixes

Review covered queue edits and polling races, admission versus device previews, tenant/department and result scope, fixed expiry, runtime ownership, desktop completion/recovery, database grants and compatibility with existing standalone/device flows.

Fixed five confirmed issues: (1) an open web edit keeps its original revision so polling cannot authorize overwriting a concurrent edit; (2) a delayed planning response cannot replace a newer polled queue; (3) Human-test uses the immutable case/language returned by Begin and refreshes the catalog when needed, rather than stale pre-claim choices; (4) session lifecycle notifications survive a full desktop display queue instead of leaving start/finish controls stuck; (5) the learner picker excludes department-restricted learners for an organization-wide device, matching server admission rules, while department devices offer matching and organization-wide learners. Conflict guidance now explains refreshing and reopening an edit panel. Added regressions for each issue. No new schema or grant changes were required by these fixes.


Final-review verification: 13 queue/desktop PostgreSQL integration cases passed, followed by 3 review cases including the new picker-scope regression (14 distinct cases across these runs), using only the dedicated disposable loopback database. The server was stopped afterward. Broad API pytest: 430 passed, 376 database/opt-in checks skipped; the new scope regression was verified separately with PostgreSQL. Focused desktop queue/listening/scenario tests: 45 passed. Native assigned-session Tk smoke passed. Web queue tests: 10 passed, including both new polling-race regressions; TypeScript passed. API and desktop Ruff/format checks passed; mypy passed for 84 API and 28 desktop files. The full desktop run encountered a prolonged execution stall: 504 passed, 6 optional model/voice tests skipped, and one existing wall-clock-dependent readiness retry assertion failed (one attempt rather than three after the deadline elapsed). This broad run is not reported as a clean pass. The six obsolete legacy API fixtures noted in the earlier review remain outside this queue change; no full database-suite pass is claimed. Hosted deployment, provider calls and physical hardware remain unverified.

Readiness follow-up: all 18 tests in test_readiness_resilience.py passed on the isolated rerun (8.73 seconds), including the failed retry assertion. No readiness production code or timeout was changed. Final inspection found no further confirmed queue defects within this review scope.


## 2026-10-05 - Session recordings and background synchronization

Implemented enrolled-device archives for local/cloud practice: immutable session/context/case snapshot, trainee or explicit standalone ownership, transcript turns, microphone PCM, actual patient playback PCM and existing camera segments. Added forward migration `0045_session_archives`, runtime grants/readiness, scoped resumable chunk API, capacity reservation, receipt-preserving retention, paginated web history/private streaming downloads and sync status separate from completion.

Desktop capture uses an 8 MiB/256-command nonblocking intake and independent disk/upload threads; SQLite WAL, stable IDs, per-chunk checksums, final manifests, restart recovery and a hidden post-exit uploader preserve acknowledged ownership without replaying inference. Transfers pause during microphone listening, inference, playback and camera capture; defaults are one 256 KiB part and 512 KiB/s. Local quotas, disk reserve, interruption reporting and operator retry avoid false complete status. No full recording re-encoding was added. See [recording sync](session-recording-sync.md).

Verification: API ruff/format/mypy (85 source files) passed. General API suite: 430 passed, 381 skipped without the integration DSN; the skipped database tests are not claimed as run. Disposable PostgreSQL at loopback port 55446 exercised archive creation, metadata immutability, checksums, interrupted acknowledgements, manifest completeness, concurrent quotas, permission isolation, transcript validation, upload grace, retention and desktop-to-API interoperability. Archive/pairing/ACL rerun: 13 passed; queue and additional database review checks passed in the earlier targeted batch after fixing the public trigger-function ACL finding. No application/production database was used.

Desktop full run initially reported 508 passed, 6 skipped, three legacy recorder-test compatibility failures and one transient native Tcl startup failure. The recorder integration was corrected; focused history/sync/video rerun passed 35 tests, followed by 134 passed/4 skipped for listening/flow/speech/queue/scenario checks, 46 passed/4 skipped for sync/speech/history, and 76 passed for final flow/listening/video checks. Native queue handoff and setup layout smoke tests passed. Desktop ruff/format/mypy passed (29 source files). Synthetic slow-HTTP capture intake measured approximately 0.02-0.04 ms p99 in sampled runs; this measures enqueue cost, not end-to-end model latency or a hardware guarantee. The real loopback detached-helper test passed.

Web component/queue tests passed 12 tests; authenticated streaming proxy tests passed 3 tests (server AbortSignal methods stubbed because JSDOM lacks them). Typecheck and production build passed; the build retains an unrelated existing TenantProvisionWizard CSS compatibility warning. Review fixes included Windows fsync access, continuous-listening pause/capture, post-rename recovery, capture finalization barriers, tenant-scoped assignment FK, archive listing indexes/summary queries, private trigger functions, bounded recovery and renewed archive identity after New conversation. Final focused reruns are recorded below.

Limitations: power failure can lose unflushed/queued capture, and no sync can continue while the computer is off. Such interruptions are marked incomplete. Media retention can end before the seven-day upload grace. Earlier uncaptured recordings cannot be reconstructed. Live cloud storage, hosted deployment and Raspberry Pi/audio hardware validation remain deferred. The changes have not been published or deployed.

Final focused verification: 5 archive/ACL PostgreSQL tests passed with immutable case/context snapshots; 8 desktop sync tests passed; the additional camera-recovery/over-quota regression passed. Final flow/listening/video rerun passed 76 tests. Git whitespace inspection passed with Windows CRLF accounted for. The disposable PostgreSQL server was then stopped.


## 2026-10-05 - Database, script and ORM synchronization

The configured local application database at loopback:5432/device_platform was at 0043_device_practice. The existing platform/db/sync.py --apply flow created and inspected a private backup, upgraded through 0044 to 0045_session_archives, reapplied runtime grants and verified all ORM columns/types/nullability, primary keys and table/view kinds. A subsequent independent read-only sync check passed. No schema/model discrepancy remained; no frozen baseline or existing migration was rewritten. Backup: .local/db-backups/20261005T121308844232Z.dump (private and Git-ignored).

The sync script now also checks queue/archive role privileges and enabled lifecycle guards. The backup directory receives explicit private access on Windows. Regression tests intentionally add forbidden worker SELECT privileges to all four queue/archive tables and disable an archive guard; verification rejects each drift and passes after rollback. Schema-sync and grant-contract tests passed: 11 tests on the dedicated disposable PostgreSQL server at loopback:55446. API Ruff, formatting and mypy passed. No destructive tests used the application database. Hosted deployment, hardware and GitHub publishing were not performed.

General API suite: 430 passed, 381 skipped with no integration DSN in that run; the 11 targeted database checks above ran separately. Scoped whitespace review passed. The disposable test PostgreSQL server was stopped afterward; the local application database remains running and synchronized.

## 2026-10-05 - Hosted database, API and web deployment

At the user's request, deployed the current platform source from local commit `d560dba` to `eval.centralindia.cloudapp.azure.com` using the managed Ubuntu deployment script and pinned SSH host identity. Windows transfer build and Linux production rebuild passed. The archive SHA-256 was checked before execution; all 500 deployed source/wheel manifest entries were verified afterward. Deployment-script tests passed all 11 cases using the API virtual environment (an initial system-Python run lacked the installed API package).

Replaced release `20261004-134610-111886` with `20261005-123505-133772`. The maintenance-window upgrade stopped managed writers, created private backup `/var/backups/pms-platform/pms-platform-20261005-123624-133772.dump`, applied forward migrations 0044 and 0045 and refreshed runtime grants. Read-only verification confirmed `0045_session_archives`, ORM columns/types/nullability and primary keys, table/view kinds, lifecycle guards and least-privilege runtime grants. The deployment and independent verification exited successfully; rollback was not needed.

Pre-deployment record IDs remained present afterward: one organization, three users, one device, one device-model selection, 11 model definitions, 13 runtime models and four patient conversations; training sessions were empty before deployment. The existing training signing identity was preserved. No credentials, private key contents or tenant record IDs are included in this evidence.

API, web, worker, retention and Nginx services were active. Public HTTPS API/web readiness, login and training verification-key endpoints passed. Unauthenticated device identity and recording-download proxy requests returned 401. API/web HTTPS readiness also passed independently from the operator workstation. The existing TenantProvisionWizard CSS compatibility warning remains non-blocking. No destructive test suite ran against the hosted database. Hosted deployment health is now verified; physical-device practice, live provider calls, cloud storage and end-to-end recording transfer remain unverified. Deployment does not update other computers' Human-test installations; the local Complete & Close confirmation changes remain separate workspace edits.

After successful verification, the user authorized cleanup. Under the deployment lock, validated resolved paths, checked running-process references and inspected the retained backup with `pg_restore --list`. Removed 12 superseded release directories, older inspected database backups and obsolete operator upload folders/files. Retained the current release, immediate rollback release `20261004-134610-111886`, matching private pre-upgrade database backup and its 0043 revision marker, configuration/keys, media and deployment evidence. Reclaimed 9.36 GiB; the root filesystem now has approximately 55 GiB available (12% used). Repeated the schema/grants, preserved-record, signing-identity, five-service, HTTPS/authentication and 500-checksum verification after cleanup; all passed. Cleanup receipt remains private on the VM.


## 2026-10-05 - Plan sessions dialog usability

Reworked the session planner into a default-settings panel, searchable trainee picker and numbered session cards, with a fixed header/device identity and footer for Cancel/Add, selected count and total planned duration. Added draft up/down controls that preserve each trainee's own settings, clear selection/empty-search states and a visible 50-trainee limit. Existing request idempotency, edit revision handling, server actions and fixed 24-hour expiry remain intact.

Fixed shared field-sibling margins overriding grid alignment and page-section margins displacing the native dialog below the viewport centre. The body now scrolls independently of the actions, with responsive field layouts and existing theme tokens. Reused the shared dialog accessibility hook for focus containment, Escape, return focus and body-scroll locking; closing controls disable during submission.

Verification: 14 focused queue/archive component tests passed, including new draft-order/settings preservation and search/remove regressions. Typecheck passed. One intermediate test run exceeded its existing one-second asynchronous lookup timeout under concurrent builds; the final focused run passed without relaxing timeouts. Native headless Edge checks used real components/styles and mocked server actions at desktop, laptop, tablet, phone, 320px width, short viewport and dark theme. All seven passed whole-dialog/footer visibility, no horizontal overflow, default control alignment, focus containment, Escape/return focus and scroll-lock restoration. A 50-trainee draft respected the cap and submitted exactly 50 assignments. Screenshots and private verification output are under `.test_artifacts/session-planner-20261005/`. Initial browser review caught the focus and viewport offset issues above; both were fixed and the full browser matrix rerun successfully.

Final production build passed with the latest viewport-spacing fix present in the emitted CSS. The existing unrelated TenantProvisionWizard autoprefixer warning remains. Whitespace review passed.

No database/API contract changes or hosted deployment were performed for this UI revision. Browser actions were mocked; live scheduling is not claimed by these checks. Earlier desktop confirmation and VM deployment evidence edits were preserved.


## 2026-10-05 - Sessions workspace, history and detail UX review

Reviewed the complete current `/sessions` workspace after the planner update. Replaced button-style view selectors with the shared keyboard-accessible Tabs and named panels. Added a device/connection toolbar, active-practice card, next-trainee and queue summary, consistent lifecycle/sync badges, readable dates, responsive queue/history/recording rows and scoped CSS. Removed obsolete selectors and verified every CSS-module class referenced by the session components exists. Older-session navigation now has distinct list/detail titles and returns directly to `/sessions`; other HistoryWorkspace consumers retain their previous headings/navigation.

Extracted focused history, session detail and presentation components. History now distinguishes loading, empty and failure states and supports retry, explicit pagination and duplicate-row protection. View session opens immediately with loading/error feedback, structured timing/practice facts and a readable trainee/patient transcript. Recording details use the same modal structure, private media cards, separate sync explanations, partial conversation errors and explicit conversation pagination. Shared overlays retain actions while their bodies scroll. Close/replace/context-change guards discard stale read responses. Server permissions, request idempotency, queue edits/expiry and download authorization remain unchanged; no API/database changes were needed.

Verification: 20 focused component tests passed, including new history-loading/error/retry, pagination/deduplication, details retry/speaker rendering, context-change response rejection, trainee-only navigation, keyboard tabs and closed-recording response regressions. Typecheck passed. Headless Edge exercised the actual components and CSS with mocked server actions: 39 views spanning desktop, laptop, tablet, 390px/320px phones, dark mode, empty/error/loading/offline and trainee-only states. Page/dialog bounds, horizontal overflow, tab navigation, focus containment and dismissal passed, with no browser console errors. Screenshots were inspected for queue, history, session details and recording details. The earlier planner browser suite also passed all seven layouts, the 50-trainee cap and mocked submission after the workspace CSS changes. Evidence is private under `.test_artifacts/sessions-workspace-20261005/` and `.test_artifacts/session-planner-20261005/`.

The final production build passed, including type validation and all 37 generated static pages. The existing unrelated TenantProvisionWizard CSS compatibility warning remains non-blocking. Whitespace review passed.

This UI revision remains local. Browser data/actions were mocked; hosted scheduling, provider calls and hardware were not exercised. Prior desktop confirmation and deployment/cleanup evidence edits were preserved. No commit or publication was performed for this request.

## 2026-10-05 - Hosted Sessions UI deployment

At the user's request, deployed the reviewed planner and Sessions workspace/history/details/recordings UI to `eval.centralindia.cloudapp.azure.com`. Built transfer archive `pms-platform-20261005-131113-ffe575.zip` (SHA256 `7729f65adadee46f1c8fee8adb841b4a349405c86cc6e24dd964ff79eb6f3945`) with the standard Windows builder; all 24 session-related archive entries matched the current workspace. Staged the three new deployment source components so the standard tracked-source packager could include them; no commit or GitHub publication was performed. The managed deploy script independently rebuilt the web application on Ubuntu and activated release `20261005-131148-135440`. Both production builds passed; the existing unrelated TenantProvisionWizard CSS warning remains.

Deployment and independent verification completed with exit 0. Database revision remains `0045_session_archives`; no schema change or restore was needed. Read-only verification passed for database/ORM/grant alignment and lifecycle guards. Pre-deployment organization, user, device, model selection, model definition, runtime model and conversation identities remain present; the training signing identity is unchanged. API, web, worker, retention and Nginx are active, public HTTPS API/web readiness and signing-key/login endpoints passed, and device identity/private recording endpoints reject unauthenticated access. All 503 source/wheel manifest checksums matched. `/sessions` and `/sessions/earlier` require sign-in; all ten Sessions build JavaScript/CSS assets were retrieved over public HTTPS and matched the Linux build bytes. Previous release `20261005-123505-133772` remains available for rollback.

Private deployment logs/exit receipt and preservation checks are under `/home/evaluator/pms-sessions-20261005/`; local operator helpers are under `.test_artifacts/vm-sessions-20261005/`. This deployment verification does not claim an authenticated live scheduling/recording exercise or physical-device test. Earlier component and browser UI verification remains applicable; local Human-test confirmation changes are desktop code and are not distributed by the server deployment.

## 2026-10-05 - Members directory presentation review

Reworked `/members` with a dedicated CSS module, a directory panel, aligned search/role/status/department filters, separate sort controls, filter reset, a persistent import-history link and clearer invitation/import actions. Member rows combine initials, name and email, use lifecycle badges and retain a direct Edit action alongside the shared accessible menu for secondary operations. Narrow layouts give identity its own full-width row and compact labelled access facts. Detail pages now group account facts, readable timestamps and responsibilities; invitation/edit forms use consistent spacing and an introductory panel. Shared platform user screens retain their existing action controls and permission gates.

Preserved server-side filtering and cursor pagination, management versions, invitation lifecycle restrictions, self-disable/archive protection, confirmations, private one-time access links and all API contracts. No additional list or statistics requests were introduced. Empty filtered lists offer reset; empty directories offer invitation; failed/loading lists no longer display a stale pagination summary. Updated existing browser scenario selectors for the member action menu.

Verification: all 37 focused tests across people-list, people-editor, member-page and member-capabilities passed, including menu-based self protection, rejected confirmations, private access links, empty-state invitation and server-query filter reset. Typecheck and the first production build passed. Headless Edge exercised actual components/styles with mocked server actions across 28 views: desktop, laptop, tablet, mobile, 320px, dark theme, directory/details/invitation/filter states and empty/error/loading/platform states. Menu placement, Escape/focus return, page/dialog bounds and horizontal overflow checks passed with no browser runtime errors. Screenshots were inspected; review improved mobile identity width and corrected sort-field sibling margins. A fixture timing check was corrected to await drawer animations, and a fixture text-encoding issue was fixed before the passing run. Private evidence is under `.test_artifacts/members-ui-20261005/`.

Final verification: the affected 12 directory tests passed again after the last copy adjustments, and the final production build passed with all 37 static pages generated. All 23 referenced CSS-module classes exist. Whitespace review and the updated browser scenario's syntax check passed. The existing unrelated TenantProvisionWizard autoprefixer warning remains non-blocking.

This revision is local; no hosted deployment, commit or publication was performed. Browser server actions were mocked; live invitation delivery and authenticated end-to-end database operations were not exercised. No API/schema changes or database tests were needed for this presentation change. Unrelated Sessions and Human-test work was preserved.


## 2026-10-06 - Human-test result and recording sync review

Reviewed capture intake, WAV/turn durability, SQLite recovery, uploader ownership, stable chunk identities, acknowledgement/delete ordering, retry selection, archive status and retention. Application code was not changed. Confirmed open findings: LocalStorage acknowledges without explicit durable flush; detached drain exits on a still-owned uploader lock during shutdown; a quota-rejected item starves later valid turns; a transient SQLite lock kills the disk writer while intake still accepts data. Also documented default 24-hour media expiry versus seven-day upload window, conflated incomplete/pending status, memory-only loss window and performance limits. See [full review](session-sync-review-20261006.md).

Verification: existing sync suite passed all 8 tests. Slow mocked HTTP capture enqueue p99 was 0.037 ms, maximum 0.069 ms for 100 frames; this is not a hardware/contention measurement. Four fault/interleaving probes passed, reproducing starvation, shutdown handoff, dead writer and metadata reservation after foreground busy became true. A synthetic LocalStorage write made zero fsync calls; power-loss data loss was not simulated. Probes are under .test_artifacts/session-sync-review-20261006/. All 4 API archive integration tests were skipped because no dedicated PMS_TEST_ADMIN_DSN was configured. No application database, live cloud, hardware, hosted deployment, runtime fix, commit or publication. Findings remain open in TODO.


## 2026-10-06 - Human-test result and recording sync implementation

Implemented the user-authorized follow-up to the historical review above. Results asynchronously await a durable JSON/journal receipt (five-second wait budget with explicit pending notification); active PCM flushes per second and finalized audio/video/results/receipts use durable publication. LocalStorage flushes before publication/acknowledgement. No platform schema or grants changed. Local journal upgrades are additive and reopen-compatible.

SQLite contention keeps the background writer alive; fatal journal failure disables intake. Upload workers recover connection failures and detached helpers wait for prior ownership. Persistent item/manifest deadlines prevent rejected work from starving unrelated results; permanent/expired captures stay local, 401 pauses all requests, and explicit Retry rechecks restored 403 access. Stable chunk identities/checksums retain idempotency without rerunning models. Server transfer/capture fields and UI deadlines distinguish pending uploads from incomplete capture; tenant expiry is unchanged.

Verification: desktop full suite 527 passed, 6 skipped (optional native runtime checks), followed by the final focused sync suite: 19 passed, including two additional access regressions. API full suite 432 passed, 383 skipped without a test DSN; isolated archive/storage/VM queue suite 11 passed and desktop local/cloud compatibility 2 passed with a dedicated disposable PostgreSQL cluster at loopback port 55447. Relevant broader media/conversation checks had 4 passes and 7 setup errors: obsolete optional-history fixtures POST the removed /organizations/{org}/llm/connections endpoint and fail with 404 before business assertions. These unrelated fixtures were preserved and remain a verification limitation. The dedicated cluster was stopped after testing; no application database was used.

UI archive/session tests: 9 passed; UI types passed. API and desktop Ruff lint/format and mypy passed; the shared durability helper passed Ruff. Final WAV recovery and detached loopback helper checks: 2 passed. Slow mocked HTTP capture enqueue p99 was 0.007 ms, maximum 0.014 ms for 100 frames; this measures intake only, not sustained disk/hardware load. Failure tests cover acknowledgement loss, uncertain storage writes, lock contention, ownership handoff, malformed chunk receipts, incomplete transfer, expiry, worker health and old-journal reopen.

Reviewed final authorization, retention, acknowledgement/delete ordering, worker locks, retry scheduling, error handling and compatibility. Limits: abrupt failure can lose bounded queued/unflushed capture; default media retention is 24 hours while result upload permits at most seven days; no power-loss, live cloud or target-hardware guarantee. No hosted deployment, commit or publication. See [sync guide](session-recording-sync.md) and [historical review](session-sync-review-20261006.md).


## 2026-10-06 - Patient background and local-first conversation

Implemented the authorized phased follow-up. Version 5 adds five localized bounded background areas and explicit approved choices, fixed by conversation identity; version 4 remains readable. Forward migration 0046 preserves existing documents, enforces database shape/size validation and grants only the API the new validator. Background and permission edits invalidate language review; publish/copy/practice/runtime paths retain tenant and lifecycle checks. The new Patient background tab and review previews expose the complete author policy. Refreshing a clinical-only source preserves background authored in a version-5 draft.

The local path uses one short plain-text generation, a 128-token default and two dialogue pairs. Clinical facts and current question remain intact under exact native token fitting. Snapshot compilation occurs once; bounded metadata/token caches expire and clear on native failure without resubmitting uncertain generations. Desktop/device snapshots are privately saved on background storage before durable results/warmup; mutable status cannot replace fixed context, conflicts/unsafe links are rejected, and queue rejection can retry. Existing result/recording sync changes were preserved.

Verification: full desktop 532 passed/6 skipped; full API 441 passed/388 database skips without a test DSN. Isolated background/schema/desktop checks passed 15, and refreshed version-4/5 case-to-device workflows passed 2. The earlier isolated broader run passed 27 with 7 obsolete history-fixture setup errors (removed connection route), retained as a limitation. Final affected API/shared prompt checks passed 60/5 database skips; the final background permission-hash check passed 10/2 database skips. Final desktop sync/cache checks passed 24, with 5 snapshot tests rerun after the last safety adjustment; final cache/model copy checks passed 10. Full device suite passed 34, and final clinical rerun passed 12. Eight focused UI tests, TypeScript and production build passed. API/desktop/shared lint/format and API/desktop/device mypy passed. Changed device formatting passed; whole-tree formatting reports the pre-existing test_coordinator.py. Dedicated PostgreSQL on port 55447 and the isolated native servers were stopped. No application database or live cloud calls were used.

Actual installed Qwen3.5-4B, 2048-token context and 16 GPU layers: the final reduced-prompt counterbalanced sample used 18 warm answers per policy. Mean prompt size fell from 1241 to 831 tokens; complete-answer median fell from 2.75 s to 1.95 s and p95 from 6.31 s to 5.09 s. The proposed latency gate passed in this sample, while earlier larger prompt revisions had inconsistent tails. Native fitting averaged 35 ms baseline and 43 ms compact. All turns used one generation. Thirty-one semantic probes and three approved-choice replies exercised known background, unknown prior medicine/ear/antibiotic facts, mixed sleep/treatment answers, general knowledge and history removal. Ambiguous questions can still elicit generic uncertainty instead of a clarification question; model semantic correctness is not certified generally.

No hosted rollout, commit or publication. Migration/grant rollout, reviewing/publishing restored cases, Hindi/other-model/native stress and hardware/audio qualification remain explicit follow-up work. See [full review](patient-background-review-20261006.md) and [phased TODO](patient-background-todo.md). Existing legacy document bytes were preserved when appending this evidence.


## 2026-10-06 - Patient background: two follow-up review passes

Completed two sequential reviews of the current patient-background implementation, fixing confirmed findings after each. Pass 1 moved prompt preparation before device session admission and rejects unavailable/stale translations without stranding a warming session. It also chooses the last two completed playback pairs before applying the history allowance. Pass 2 adds an incremental SQLite snapshot-size column, accounts for retained and interrupted snapshots, reserves storage before file writes, reuses reservations on retry, and includes snapshots in camera recovery quotas. It fixes the race where a fast disk failure was overwritten by activation, preventing later begin retries.

Regression coverage exercises repeated rejected start and corrected start, failed playback between completed pairs, old-journal upgrade/restart, retained acknowledged snapshots, capacity-change retry, immediate failure, partial replacement failure and reservation reuse, and camera recovery quota exhaustion preserving originals. The final affected desktop suite passed 28 tests; the full device suite passed 36. Ruff, changed-file formatting and desktop/device mypy passed, as did API Ruff, formatting and mypy. The complete desktop/API runs, explicit skips and scope limits are recorded in [review evidence](patient-background-two-pass-review-20261006.md). Database-dependent checks in this follow-up used no DSN and were skipped; prior isolated database evidence remains separate. No live cloud, deployment or hardware verification was added.

No new generation calls or foreground filesystem work were added. Snapshot accounting runs on the disk worker and during bounded startup recovery; this is not a new native hardware latency benchmark. Existing unrelated work and legacy document bytes were preserved.


## 2026-10-06 - Native patient-background local-model qualification

Real installed Qwen3.5-4B tests exposed unsupported personal inferences despite prompt-only safeguards. Compiler 34 uses one generation to select compact frozen source IDs for new English v4/5 personal/clinical answers; the host validates the entire view and selected IDs and speaks stored wording. General knowledge uses a short separate prompt. Fixes preserve units/qualifiers, deduplicate exact prose, protect clinical precedence, actor/event/subject distinctions, missing parts, other-person ownership and completed-history references. Complete measurement/social questions and a supported frequency follow-up shed unrelated facts without deleting them from the snapshot. Compact views omit host-only area metadata while accepting old complete views; forged metadata is rejected. Older snapshots/non-English contracts remain compatible. There is no routing, repair, paraphrase or judging generation, no default model/Whisper sharing change and no database scenario publication.

Two grounding/validation reviews and final inspection covered immutable snapshots, selected-source validation, output bounds, unknown-versus-negative facts, context fitting before token reservation, secret/media exclusion from turn metrics and existing authorization/lifecycle gates. Final annotation fixes make the changed conversation modules explicitly type-checkable; the portable directory flag lookup preserves directory flushing and Windows write-through behavior. Regression and replay evidence are recorded in the feature review.

Final compiler-34 native result: four 25-question sets repeated twice, 200/200 completed answers, no protocol failures and no incorrect or unsupported claims found in manual fixture review. Exactly one generation per answer; all 200 prompts plus output/safety reserves fit 2,048 tokens, maximum prompt 1,108. Actual full-GPU offloading 33/33 layers, six threads, thinking disabled, temperature 0. Combined 192 warm samples: median 2.12 s, nearest-rank p95 5.00 s. All four individual sets met the unchanged <=3 s median / <=6 s p95 target. Startup 10.51-13.35 s is separate. Earlier 16-layer runs had substantial tail drift and did not consistently meet the target. Full-GPU text timing does not qualify shared Whisper/TTS, capture/playback, other languages/models or Raspberry Pi.

Checks: full API 546 passed / 388 database skips; full device 36 passed. Full desktop 538 passed / 6 skipped with one sandbox-only Tcl/Tk access failure; its native widget test and affected local-execution/sync tests then passed with runtime access (44 passed). Final affected API/shared run passed 144 / 2 database skips, followed by 136 conversation/durability regressions after annotations and 2 final directory-flag regressions. API/desktop/device Ruff and prescribed mypy passed; API and desktop whole-tree formatting and changed device/shared formatting passed. Explicit changed shared typing passed 10 files. The extra whole-shared check still reports 26 schema/registry errors also present in the committed baseline; the baseline comparison reported 28 including two projection annotations now fixed. This optional broader type check is not reported as passing. Existing device whole-tree test-format debt remains separate.

Replaying 880 archived fictional completions preserved final rendering contracts; it is not new inference or approval of rejected candidates' general facts. No disposable PostgreSQL DSN was configured for this phase; database checks were skipped and prior isolated migration evidence remains separate. No live cloud, hosted deployment, application scenario approval/publication, audio or Pi verification. Root document updates preserve existing bytes and unrelated workspace work. See [native evidence and actual 25 answers](patient-background-local-qualification-20261006.md).


### Human-test conversation performance, 2026-10-06

Review/evidence: docs/conversation-performance-review-20261006.md.
Scope is desktop/launcher only; API/database/web contracts and grants are unchanged.
Initial combined Large-v3/18-layer GPU run completed 25 fictional questions but
failed the speed gate (warm median 5.73 s, p95 9.22 s). Current saved profiles
are preserved; faster local combinations are being compared without cloud calls.

Final performance evidence: 100 native synthetic questions completed across three runs.
Latest small-Whisper/full-GPU run failed the speed gate: median 4.00 s, p95 7.81 s;
local saves median 12.81 ms, p95 24.09 ms. One rain/ring recognition error remains.
Two reviews fixed durable playback gating, UI delivery persistence, closure queue
capacity, capture muting, cancellation, fallback and context-bounded GPU allocation.
Full desktop 562 passed / 6 skipped; launcher 189 passed; API 546 passed / 388
database skips (no disposable DSN). See feature evidence for qualification limits.
Final playback-drain and test lifecycle/minute-boundary/GUI cleanup fixes passed
the complete desktop rerun (131.28 s, no warnings); journal suite 20 passed.

### Cross-scenario local conversation review, started 2026-10-06

The requested nine-scenario, ten-question matrix is in progress. Early native
results confirm incorrect lifestyle narrowing of mixed identity/intake queries,
clinical followups routed as general advice, and a false general rain qualifier.
Fixes and final evidence will retain pinned sources, one generation, 2,048 tokens
and required durable saving before speech. No schema/authorization changes.


### VM and local database synchronization, 2026-10-07

User-authorized hosted upgrade completed. VM release 20261007-023328-171421 replaced 20261005-131148-135440; local and VM schemas now match 0046_patient_background. Required private backups were created and inspected. ORM/grants/lifecycle checks, all five services, HTTPS readiness/authentication, 509 source/wheel checksums, ten hosted UI assets and 507 workspace-source matches passed. Existing tenant records, complete model/assignment rows and training signing identity were preserved. Previous release remains available for rollback.

Full API 564 passed/388 skips without a test DSN; affected disposable PostgreSQL checks 134 passed. A broader catalog run retained three historical expectation/invalid-fixture failures (138 passes), documented separately. Full desktop rerun 562 passed/6 opt-in skips; UI package 1577 passes, constrained-worker web rerun 588 passes; API/desktop lint/format/mypy and UI type/build checks passed. Actual verification, backups, hashes, initial overloaded-run failures and scope limits: docs/vm-update-20261007.md. No paid cloud inference or Pi verification.

VM final review: Human-test scripts 189 passed. Platform launcher checks used the API environment: 39 passed/1 opt-in skip plus one fixture failure, then three focused checks passed after preserving Windows SystemRoot in that fixture. A type-only A/B probe identified Ed25519 generation failing with that OS variable cleared; ACL creation succeeded in both probes. Runtime key handling and the deployed archive were unchanged. Final read-only local sync and external HTTPS checks passed.


### Portable Human-test Windows package, 2026-10-07

Added start/build-human-test.bat and start/build_human_test.py for fresh, frozen Windows x64 CPU/CUDA packages. Private standalone Python/Tcl/native libraries preserve the current launcher and companion layout; destination machines need no Python or uv installation. Source allowlists exclude credentials, .env, enrollment, databases, models, recordings and runtime state. Model/voice downloads use bundled interpreters instead of replacing them via uv sync.

Review one fixed the dependency on system-installed Visual C++ libraries by bundling allowlisted application-local CRT DLLs from Visual Studio redistribution files. Review two restored installer path/reparse validation, added spawned-process checks, and corrected numeric CRT-version selection with regression coverage. Both final ZIP SHA-256 values and every manifest entry (CPU 14274, CUDA 14422) passed; archive scans confirmed private-state exclusion and packaged resource presence. Relocated CPU executable self-test and --help passed with Python/uv absent from PATH and invalid Python environment overrides. Real connection/offline-model tabs opened and closed without enrollment or network. Packaged CUDA probe detected this laptop GPU without model inference.

Verification: 194 complete launcher/packaging tests passed; after the last builder-only numeric-version correction, all six packaging regressions passed. Changed-file Ruff lint/format and git whitespace checks passed. Initial sandbox cache/temp/process failures were rerun with approved normal access. Private receipts: .test_artifacts/portable-release-20261007/verified.json. Build outputs are ignored under start/dist; no cloud/API/schema/deployment changes. Remaining qualification: unsigned package, separate clean Windows machine, real microphone/camera/GPU inference and platform sync; native imports/probes are not those acceptance tests. Model weights and Piper voices must be downloaded separately; each destination needs its own enrollment.

### Portable hosted API and GPU defaults, 2026-10-07

Review one found that only the pairing screen had the hosted HTTPS default: desktop Settings, ExternalPMS and Demo retained localhost. They now share human_test.connection.DEFAULT_PLATFORM; saved/explicit origins still override defaults. Review two found that copying the repository LLM config would retain 99 layers, and the shared-GPU policy would cap another branch at 18. Portable builds now serialize 20 layers and 2048 context into their own config without changing the source config; the shared budget cap is 20, while lower overrides/CPU fallback and the measured small-ASR branch remain supported. Native self-test asserts these defaults before ZIP creation.

Verification: full desktop 563 passed/6 optional skips, launcher plus portable tests 200 passed; all seven portable regressions passed after strengthening the context-default test. Changed-file Ruff lint/format, desktop mypy (30 files) and git whitespace checks passed. An initial combined pytest collection hit the existing duplicate test_local_models filenames; each suite then ran separately. No API/schema/VM changes or live cloud requests. Native 20-layer inference latency and a separate clean Windows machine remain unqualified. Final archive verification will be recorded below after both rebuilds finish.

Final rebuilt CPU/CUDA archives (031219-855375 and 031219-856531) passed SHA-256, every manifest entry, private-state exclusion, packaged 20-layer/2048 defaults and resource checks. CPU relocation passed native self-test and CLI startup with Python/uv absent from PATH; real connection screen displayed the hosted HTTPS default and closed without network or enrollment. One preliminary verification reached CUDA before its SHA file existed; the complete check passed after the build finished. Receipt: .test_artifacts/portable-release-20261007/verified-defaults.json. Both build commands completed successfully; no edits to packaged runtime source occurred during the builds.


## 2026-10-07 - Human-test portable IP protection, two reviews

Review 1: native compilation of 15 critical conversation/model/speech/listening/
durable-sync modules; other first-party code becomes sourceless bytecode, with
small direct-script shims. Confirmed source is omitted, Pydantic schemas and spawn
entry modules remain compatible, resources/third-party licenses stay intact,
and no compiler/runtime protection dependency ships to the destination.
Found and fixed MSVC linker path-length failure by flattening generated C paths
inside a temporary build directory. Build errors fail closed with no ZIP release.

Review 2: added release gates rejecting unexpected source, critical-module
bytecode, missing entry shims/bytecode and generated C/object/debug artifacts.
Enforced wheel-only pinned build tools and isolated them from distribution
runtimes; excluded build-tools directory from Git. No confirmed remaining
authorization, privacy or sync behavior regression in this packaging scope.
Obfuscation raises inspection cost; recoverable bytecode and native strings are
an explicit limitation, not a secret-storage mechanism or security boundary.

Actual compiled-code verification: desktop 563 passed, 6 optional hardware/model
skips; protected launcher/setup scripts 193 passed; build protection regressions
11 passed. Initial two video test failures came from a test-runner spawn guard
and relative-path bug; corrected the runner, verified all 15 recording tests,
then reran the complete desktop suite successfully. Ruff check/format and diff
whitespace checks passed. Cloud requests use mocks; no database changes/tests.

CPU and CUDA default-script builds passed native imports, canonical hosted API,
20 GPU layers, isolated Python paths, Tcl and recording-process spawn checks.
Both ZIP SHA-256 values and every manifest entry were verified, with source/
compiler-artifact/private-state exclusions. Extracted both to a different path
containing spaces and ran native self-test/help with Python/uv absent from PATH
and invalid PYTHONHOME/PYTHONPATH. CPU pairing/offline-tabs GUI smoke also passed
using bundled Python with enrollment/network requests blocked.

A small legacy-case assembly benchmark returned identical output hashes:
source median 1.8429 ms versus compiled 1.7442 ms per operation. This is a prompt
assembly check only, not an end-to-end inference or live GPU latency guarantee.
No runtime decryptor, unpacking or license/network check was introduced.

New protected distributions (not the earlier source-containing portable ZIPs):
- Human-test-windows-x64-cpu-20261007-033832-050015.zip: 348008637 bytes; 14248 manifest files; SHA-256 ec1010d5954b19912f4fa545bc151246520b1e27c6c1847ac5359fe29597bab6.
- Human-test-windows-x64-cuda-20261007-033905-028291.zip: 1656118532 bytes; 14403 manifest files; SHA-256 31e0243e37d1867b3338271608b435933861cd0b1c060bfe67a66da339683173.

Still pending: clean-machine live microphone/camera/GPU inference/platform-sync
qualification and the user's model selection before bundling any model weights.
Build instructions and protection limits: docs/human-test-portable.md.
Private reports/runners are ignored under .test_artifacts; ZIPs under start/dist.


## 2026-10-07 - End-to-end portable build/obfuscation review and fixes

Confirmed and fixed findings:
- Builds/partial ZIPs previously appeared under finished release names.
  Hidden .building staging and .partial archives/checksums now remain until
  self-test, protection gates, archive writing and hashing succeed.
- Debug source and protected packages shared indistinguishable names.
  Editions now explicitly include protected or debug-source.
- Broad source-prefix copying could include unrelated data/resources and
  directory junction parents. Copying now accepts Python plus explicit known
  resources; all parent links/junctions and escaping paths are rejected.
- Protection validation missed unlisted bytecode and Cython/stub/header source.
  Exact bytecode/shim inventories and wider case-insensitive leak gates added.
- Build imports left caches containing absolute builder paths. Native launcher
  and subprocess self-tests suppress writes; all import caches are removed before
  packaging. Both final archives were verified without __pycache__ entries.
- The ZIP writer did not compare actual archived bytes with the manifest.
  Streaming hashing now aborts if a file changes after manifest creation.
- CUDA self-test did not verify optional NVIDIA package availability. Added.
- Host checks accepted any 64-bit Python, including ARM64, for an x64-labelled
  build. Builder and compiler helper now require the win-amd64 interpreter ABI.
- Functional setup failure: isolated ._pth omitted script directories, so Qwen
  install/run could not import common/client/process_guard, and offline setup
  could not reliably import local_catalog. Add relative human-test/scripts and
  local-models/scripts only to the desktop interpreter. All interpreter paths
  remain inside the extracted distribution. Expanded self-test now imports these
  helpers and runs offline setup, Piper/Qwen installers and Whisper CLI --help.

Two reviews with confirmed findings fixed; no unresolved packaging/protection
finding in reviewed paths. Regenerated CPU and CUDA packages through the default
build scripts after the final installer fix, with 15 native extensions retained.
Verification: 16 build regressions passed, protected launcher/setup scripts 193
passed. Ruff check/format and git diff whitespace checks passed. Both final native
self-tests passed hosted API/default layers, all three runtimes/native imports,
installer entry points, Tcl and recording-process spawn. Exact ZIP hashes and
all manifest files checked, native/source/private-state/cache exclusions checked;
both editions extracted to a path with spaces, self-test/help ran with Python/uv
absent from PATH and invalid PYTHONHOME/PYTHONPATH. Final CPU pairing/offline-tabs
GUI smoke passed with network/enrollment blocked. No runtime business logic,
database/API schema or inference architecture changes. Full desktop business
suite remains covered by the prior compiled 563-pass/6-skip evidence; not rerun
for these packaging-only fixes. No live cloud/hardware qualification claimed.

Use these final fixed releases; earlier ZIPs have the installer-path limitation:
- Human-test-windows-x64-cpu-protected-20261007-054224-752137.zip: 336869745 bytes; 12975 files; SHA-256 97f177791de33159a855aaf3d5992d6797571702c780c7fe29248c1bdda45749.
- Human-test-windows-x64-cuda-protected-20261007-054235-059254.zip: 1644982401 bytes; 13130 files; SHA-256 7c32736c6345756b98bd839b4bdd61dea177f6fabb3bcb36ebe1b388d9a58d60.

Remaining limits: clean Windows machine, microphone/camera/GPU inference and live
platform sync acceptance remain separate. Model weights still await user model
selection; native binaries/strings and bytecode remain recoverable. Build-time
checks add no runtime network/decryption operation. Private reports live under
.test_artifacts/portable-release-20261007 and portable-cython-build; not committed.


## Protected desktop Downloads review - 2026-10-07

Added a Downloads account-menu link between separators immediately above Sign out,
and a responsive Windows portable directory with protected GPU/CPU downloads,
checksums and enrollment/model-download instructions. API and web guards require
an active platform admin or an active, accepted organization-wide tenant admin.
Platform access applies to these shared installer artifacts, not tenant media.
Listing, GET, HEAD and resumed requests all recheck current access. No migration,
model assignment or inference behavior change was introduced.

Review 1 fixes: release the authentication/read transaction before long file
streams; preserve Range/If-Range in the web proxy; correct executable name and
login redirect; stream responses without ZIP buffering or browser-visible tokens.
Requests have bounded metadata/header reads and the connection timeout ends when
headers arrive, allowing slow downloads to continue.

Review 2 fixes: reject debug packages, edition mismatches, malformed manifests and
linked artifact paths; preserve the private API read group before atomic catalog
replacement; retain immutable filenames and SHA-256 verification at publication;
support Space activation for the new keyboard menu link. Failed publications keep
the previous catalog. Artifacts stay outside public assets and git.

Verification: API full suite 574 passed, 389 skipped (existing disposable-DB tests
without PMS_TEST_ADMIN_DSN). Dedicated PostgreSQL 17 on 127.0.0.1:55479 separately
passed all 11 download tests, including real tenant role/revocation/suspension and
runtime grants; that test server is stopped. API ruff check/format and mypy passed.
Release publisher regressions: 4 passed. Complete shared UI suite: 1578 passed;
complete web suite: 594 passed. Later page/console/menu additions and Space fix
passed affected tests (48 web tests and 33 shared tests); production builds and
TypeScript checks passed. Previewed the actual page at 1440 and 390 pixels with
the design-system styles and no horizontal overflow.

VM: private persistent /var/lib/pms-downloads, root:pmsapi, directory 0750 and
files 0640; web service direct filesystem access denied. GPU ZIP 1644982401 bytes,
SHA-256 7c32736c6345756b98bd839b4bdd61dea177f6fabb3bcb36ebe1b388d9a58d60;
CPU ZIP 336869745 bytes,
SHA-256 97f177791de33159a855aaf3d5992d6797571702c780c7fe29248c1bdda45749.
Both complete ZIPs streamed through the hosted web proxy with matching checksums.
Web peak RSS was 247844 KiB, below either a full GPU ZIP or unbounded file buffering.
Live platform-admin and tenant-admin page/catalog, HEAD, byte resume and invalid
range checks passed; anonymous API/proxy access was 401 and page required login.
Temporary verification sessions used existing accounts and were revoked finally.
No completed regular-member VM account was available: member denial is covered
by isolated API/PostgreSQL/UI tests, not claimed as a live member login check.
Final reviewed release 20261007-065833-186923 passed the repeated live admin,
anonymous, page/catalog, HEAD, resumed-byte and invalid-range smoke checks.
All five managed services remain active; artifact storage survives deployments.
Model weights are still separate setup downloads; existing portable hardware/model
qualification limitations remain recorded in the portable-build review above.
Private verification and preview artifacts: .test_artifacts/downloads-20261007.


## Downloads menu and transfer follow-up review - 2026-10-07

Reviewed the account menu, page, API authorization, private artifact storage,
streaming/ranges, and operator publication. Fixed confirmed findings:

- Edition-only download URLs could change releases between page view and request,
  or between interrupted requests without If-Range. Page links now pin SHA-256;
  GET/HEAD/resume reject a different current digest with 409. Refresh the page and
  start a new download after a release change. Legacy API links remain compatible.
- Pointer/programmatic item focus could leave keyboard selection on another item.
  UserMenu now updates the selection on focus; Space activates the focused link.
- Every proxy failure told the user to sign in. Errors now distinguish session
  expiry, permission denial, invalid requests, missing/changed releases and outage;
  HEAD errors have no body, and upstream private error details remain hidden.
- Concurrent publishers could overwrite an immutable filename after an exists
  check. Same-directory hard linking now publishes without replacement and validates
  existing bytes. Catalog size derives from the verified copy rather than a later
  source stat. File metadata and Linux directory entries are fsynced at publication.
- A broken catalog symlink appeared to be an empty catalog. It now fails closed.
  Download size units are labeled MiB, and GET declares its binary response class.

Second review checked compatibility, authorization, atomic publication failures,
revocation, malformed input, bodyless HEAD and streaming performance implications.
No complete-ZIP buffering, per-request hashing, DB schema change or model change.

Verification: API full suite 575 passed, 389 existing PostgreSQL tests skipped
without PMS_TEST_ADMIN_DSN; the later broken-link regression was covered separately.
All 13 download tests then passed on dedicated disposable PostgreSQL 17 at
127.0.0.1:55479, including real membership lifecycle and runtime grants. That
server is stopped. Publisher regressions: 6 passed (including concurrent creation
and source mutation). Full shared UI: 1580 passed; full web: 606 passed. API ruff
check/format, mypy, both TypeScript checks and production build passed. Existing
unrelated CSS/autoprefixer and test act warnings remain outside this change.

Deployed release 20261007-110932-192104 to the authorized VM. Public hosted checks
passed for platform and tenant admins on both CPU/GPU editions: page digest links,
catalog, pinned HEAD, resumed byte contents, 416 and stale-digest GET/HEAD 409.
Anonymous catalog/proxy denied and page required login. Temporary verification
sessions were revoked finally. Linux publisher smoke covered new/repeated publish
and immutable conflict. All five services are active; private artifact ZIPs and
existing application data remain preserved. Complete ZIP checksums were already
verified in the preceding review; this review repeated HTTP metadata/range/error
checks, not the full multi-GB transfers. No completed member VM account exists;
member denial remains covered by isolated API/PostgreSQL/UI tests.


## Member workbook false-positive validation review - 2026-10-07

The generic UI error claimed that all macros, formulas and external links were
forbidden. Ordinary Excel email/web hyperlinks created External relationships
and were rejected. Removed those content/relationship bans and the misleading
UI mapping. Optional Password headings are now included in the header error.
The .xlsx format, compressed/expanded size and row/column bounds still apply;
encrypted/malformed archives and unsafe XML remain unreadable. Only Members
data is imported; macros/embedded objects are ignored, links are not fetched,
and formulas are not evaluated. Formula cells use Excel's saved values. Missing
values and Excel error cells get specific row/column correction messages.
Plain text worksheets retain the single-load path; the second data-only view
is opened only when Members contains formulas.

Review 1 covered hyperlink false positives, cached identity/password values,
all-formula rows, output text storage and tenant/commit boundaries. Review 2
fixed empty-string formula caches for optional passwords, skipped genuinely
blank cached rows, and identified cached Excel errors before importing them.
An isolated migration check also exposed an old expectation that the retired
default_profile_id column survive the head upgrade. Its assertion now explicitly
permits the null column removed by migration 0038 while preserving all remaining
tenant values; no migration or production schema was changed for this fix.

Verification: full API suite 579 passed, 390 database-dependent tests skipped
without PMS_TEST_ADMIN_DSN. On dedicated disposable PostgreSQL 17 at localhost
55479, all 34 member import cases passed, including real validate/commit using
cached formulas and passwords, lifecycle/permissions, capacity, concurrency,
reports and idempotency. The corrected migration regression passed separately.
That server is stopped. Both web import files passed (11 tests); API ruff
check/format, mypy and production UI build/type checking passed. Existing
unrelated CSS build warnings remain. No live email/SSO integration was tested.

Deployed release 20261007-120546-195190 to the authorized VM. Installed API/UI
source hashes match the package manifest. An installed-runtime fixture accepted
an email hyperlink, ignored macro/external-link parts and used saved formula
values including an empty optional password; an unsaved result identified the
Full name cell. Public API and web readiness passed; all five managed services
are active. Schema remains 0046_patient_background, with existing records and
signing identity retained by managed deployment. The hosted runtime fixture did
not create import batches/users; actual validation/commit was tested on the
disposable database, not claimed as a live production user import.


## Desktop download filename and extraction review - 2026-10-07

Local API attachment names are now Desktop-App-GPU.zip and Desktop-App-CPU.zip.
The Downloads page uses Download Desktop App links and shows those short names.
Private release filenames remain immutable and versioned; API catalog, digest
pinning, SHA-256 ETags and streaming are retained. No in-flight ZIP is rewritten.
Future portable builds use Desktop-App-GPU or Desktop-App-CPU as their ZIP root
folder, reducing extraction path length and keeping editions in separate folders.
Manifest paths remain relative to that folder and checksums cover the actual ZIP.
Existing multi-GB ZIPs were not rebuilt or modified; their internal folder change
requires a new build. The VM was not updated, per the user's local-only scope.

Two inspections checked short names for GET/HEAD/ranges, UI details/links, archive
folder contents and interrupted/mutated publication behavior. Local affected
Python checks: 37 passed, 1 PostgreSQL lifecycle case skipped without disposable
DSN; download UI/route tests: 15 passed. Full API: 581 passed, 390 database-dependent
tests skipped. API ruff check/format, mypy and both UI TypeScript checks passed.
No live download, Windows extraction or hardware run is claimed for these changes.


## Enrollment token visibility review - 2026-10-07

Review 1 traced tenant-admin issuance through the server action and enrollment
API. The raw token was shown inline below the action buttons, without a Copy
button or a focused success dialog. Credential status not_issued is expected
until the Desktop App/device agent exchanges the token for its device credential.
The API stores only the enrollment token hash; a hidden token cannot be fetched
again. Issuance still requires tenant management permission and confirmation,
with the existing device credential invalidation warning.

Replaced the inline result with an Enrollment token ready dialog containing the
Device ID, selectable read-only token, expiry, Copy token and clipboard failure
fallback. Display no longer waits for a status refresh, and refresh transport
failure preserves the successfully issued token with a warning. A synchronous
pending guard prevents overlapping submissions. Raw tokens remain in component
memory only and are hidden after expiry, dismissal, device lifecycle restrictions,
context/device changes or loss of management permission.

Review 2 checked confirmation transitions, pending refresh, clipboard denial,
expiry, platform summaries and permission removal. Fixed the guidance so readers
without an issuance button are not told to use one. Added seven enrollment
regressions; fixed fake-clock testing and an unsupported role query option.
Final inspection found no remaining confirmed issue in these changes.

Verification: all 85 web test files passed (613 tests), including 12 device detail
and 9 device action cases. Shared UI and web TypeScript checks, production build
and git diff --check passed. Existing unrelated CSS build and test act warnings
remain. No API/database changes or database tests were needed for this UI fix.
No live clipboard/browser, desktop enrollment or hosted verification is claimed.
The VM was not updated, per the user's local-only scope.


## Tenant-admin device-type enrollment verification - 2026-10-07

Tenant administrators have org.devices.manage in the current role catalog.
DeviceOperations, issueEnrollment and enrollment_issue contain no laptop/manikin
restriction; no platform role is required to issue a token within the accepted
administrator's tenant. The token-copy dialog fix remains in local source.
Active organization/device/department checks, retired-device restrictions,
maintenance protection, tenant scope and management ETags are retained. No API
permission relaxation, schema change or new device-type condition was needed.

Review 1 expanded UI tests to both types and verified issuance responses reach
an org_admin with tenant-only permissions. Added denial for a tenant user without
management permission and checked stale tenant context before API submission.
Parameterized the real API registration/enrollment/heartbeat/revoke/retire test
for both types, with explicit pending/not_issued and enrolled/active assertions.

Broader isolated testing exposed an obsolete fleet assertion expecting removed
profile fields and eight desktop inference fixtures returning plain hello to
compiler 35's fact-selection prompt. Fixed the fleet assertion to require those
fields to be absent. Local and cloud inference mocks now return a source fact ID
and assert the spoken text matches that source. Only inference is mocked; actual
pairing, token single use, tenant/neighbor isolation, department restrictions,
conversation orchestration, history and revocation continue through the API and
disposable PostgreSQL. Preserved the private-details merge regression.

Review 2 checked the final diffs, permissions, type coverage and test failures;
fixed a mock role incompatible with the web session role type and normalized the
changed Python test formatting. No remaining confirmed enrollment issue found.

Verification: 24 affected web tests passed and both UI TypeScript checks passed.
On the dedicated disposable PostgreSQL 17 server at 127.0.0.1:55479, all four
console and eight desktop pairing cases passed after fixes. Both parametrized
registration cases passed again after preserving the metadata merge fixture.
Nine device-management cases also passed during the initial broader run, for 21
unique affected database cases verified. Full API run: 581 passed, 391 database
cases skipped without a DSN; the affected cases above were exercised separately
with the disposable DSN. API ruff check/format and mypy passed. No live cloud,
hardware or hosted testing is claimed. No deployment or publishing was performed.


## Enrollment and Downloads final review/deployment - 2026-10-07

Final pre-deployment review found a shared-error race: late configuration success
could clear an enrollment issuance error or status-refresh warning. Separated
configuration errors from operation errors and added a regression that resolves
configuration after issuance fails. The warning/error remains visible. Rechecked
modal transitions, pending submissions, clipboard fallback, expiry, tenant scope,
role changes and both laptop/manikin enrollment coverage. No further confirmed
finding remained in the final diff review.

Local verification: all 85 web files passed (617 tests), including 14 device-detail
cases. Production UI build, API ruff check/format and mypy passed. Affected API
checks: 34 passed, 15 database-dependent cases skipped without a DSN in this run.
The preceding verification separately exercised 21 unique affected device cases
against disposable PostgreSQL, including laptop/manikin issuance and redemption,
local/cloud pairing, tenant/department isolation and revocation; no live model
calls were used. Existing unrelated CSS and React act warnings remain.

Packaged the reviewed working source and production build in
pms-platform-enrollment-20261007-r1.zip; verified archive integrity and every
manifest digest against local files. A private database backup was verified on
the VM before upgrade. Deployed API/UI/database runtime synchronization using
the managed installer. Active release: 20261007-125237-196896. Schema remains
0046_patient_background; no new migration or data-loss authorization was needed.

Hosted verification passed: all 490 API/UI/DB/shared source hashes match the
package; database/application/model record checks, signing identity and private
download catalog match the baseline. API, web, worker, retention and Nginx are
active; public HTTPS API and web readiness passed. Platform and tenant admins can
open Downloads and access both editions. Desktop App branding and
Desktop-App-GPU.zip / Desktop-App-CPU.zip Content-Disposition names are live.
API and web HEAD, byte-range resume, invalid-range and stale-release checks pass;
anonymous and regular-member access is denied. Tenant-admin management permission
and the enrollment action were verified on an existing hosted manikin without
issuing a replacement token or invalidating its credential. Temporary operator
verification sessions were revoked. Actual laptop/manikin token redemption was
verified on the isolated database, not by changing production device credentials.

The installed workbook parser accepted email hyperlinks and cached formulas and
reported an unsaved formula's specific cell. No production import/user was created.
Existing portable ZIP binaries/catalog remain immutable and unchanged; shorter
internal extraction folders apply when new portable archives are built. Existing
model weights, desktop application state and recordings were not replaced.
No Git commit or publish was requested or performed for this deployment.

## Portable GPU setup diagnostics and bundled models - 2026-10-07
Review 1: screenshots locate failure after local route selection and before GPU/service startup. User confirmed no Qwen or Whisper models present; enrollment is saved before model preparation. Exceptions were swallowed, cleanup reported success, and UI progress overwrote the failure. Fixed with early private logging, real severity, bounded structural traces and stage timings, actionable assigned-model errors, retained enrollment retry and correct failed/cancelled states. HTTP-client cleanup now cannot bypass lock/log release.
Review 2: Qwen installer child failures were reduced to generic installation_failed; completed Qwen installations still attempted runtime downloads. Added a bounded allowlisted diagnostic protocol (certificate/network/HTTP/permissions/disk/integrity), propagated safe codes/frames through both child-process levels, bounded protocol buffers and retained offline verification. Strict model inventory excludes credentials, recordings and history; tightened runtime/speech path depth and checked every model hash. Large quantized weights use ZIP_STORED to avoid costly compression and extraction; checksums remain mandatory. Corrected LLM discovery to use the requested root. Fixed two existing local-LLM test issues: stale default-model expectation and non-atomic process marker.
Verification so far: 226 startup/build tests passed before final added nested-installer regression; affected diagnostics/provisioning suite 34 passed after it. Build packaging/privacy suite 20 passed including uncompressed model entries. Desktop suite 563 passed, 6 skipped; native Tk pairing/retry/offline cancellation smoke passed outside sandbox. Local LLM suite 39 passed plus 39 subtests. Downloads page/proxy suite 15 passed; web production build passed (existing CSS autoprefixer warning). Ruff check passed on changed desktop/installer/build files. Twelve protected startup/installer bytecode files exactly match final source. Protected bundle self-test passed including Qwen CPU/CUDA runtime hashes, Whisper conversion hashes and all Piper voices.
Remaining: extracted-package live local model qualification, private VM artifact publication and hosted download verification. No paid cloud inference or enrollment credential changes performed. Original laptop's Qwen downloader failure cannot be classified retroactively because its old installer discarded the detail.

Portable qualification: final protected GPU archive is 7,015,166,841 bytes (SHA-256 04781c82d4d69166067ccc09b42380aedb6555fb3ed315786c2ff9aa866c52db), root Desktop-App-GPU. Extracted to a different folder with invalid PYTHONHOME/PYTHONPATH. Installed-state checks passed for Qwen 3.5, Whisper large-v3, voices and video; Qwen verify completed with socket network calls forbidden. Live local qualification passed: Piper English and Hindi generated audio; Whisper large-v3 CUDA int8_float16 loaded, warmed and transcribed generated speech (14.55 seconds including startup); Qwen 3.5 CUDA 20-layer server returned a streamed answer in 3.52 seconds after warmup. These are local engine smoke checks, not a physical microphone/camera or full learner-session latency measurement. The original user's laptop remains untested. Qualification generated fresh local credentials only in the separate extracted test folder; the distributed ZIP remains credential-free.
Shared GPU qualification also passed on a 4,094 MiB NVIDIA GPU with Qwen 3.5 using 20 layers and Whisper large-v3 resident simultaneously. The synthetic full streamed answer completed in 5.11 seconds; this does not establish a sub-5-second full voice round trip or the first audible response latency.

Deployment complete: private VM catalog now serves the verified 7,015,166,841-byte GPU bundle as Desktop-App-GPU.zip; CPU artifact preserved. Active platform release 20261007-144101-199603 contains the Downloads instructions for included Qwen/Whisper/Piper models. Linux deployment completed its backup/migration/readiness flow; no new schema migration was required for this task. Live platform-admin and tenant-admin catalog/page access, checksum-pinned HEAD, resumed byte ranges, invalid ranges and stale-digest rejection passed for both editions. Anonymous and regular-member access denied. Hosted ZIP root, selected model inventory, 15 native protected modules and exclusion of private state verified. All five services active, API/web readiness successful. No enrollment token issued or device credential changed during verification; temporary verification sessions revoked. TODO completed. Original laptop's Qwen download error remains unclassified because the previous installer discarded its details; included verified models remove that first-run dependency, and future installer failures now expose safe categories and traces.

## Fresh CPU and GPU protected portable release review - 2026-10-08

Review 1: inspected current startup/installer recovery, private-state allowlist, bounded safe logs, native/bytecode protection, included model integrity, hosted API defaults and 20-layer policy. Both builds compile 15 sensitive modules and include the latest 12 setup/installer bytecode files. No new functional finding. Fixed a portable test formatting inconsistency under the project Ruff configuration, then reran all 20 packaging/privacy tests. The initial GPU build required normal build-account access to the private local voice folders; rebuilt with that access without changing distribution permissions. Tests were run separately for scripts/tests and tests because duplicate test module basenames prevent combined default collection.

Verification: 563 desktop tests passed, 6 optional/hardware tests skipped; 207 startup/setup tests passed; 20 portable packaging tests passed; 39 local LLM tests and 39 subtests passed. Ruff checks passed and all 16 inspected changed files passed formatting with the project configuration. Both editions passed their built-in protected/native import, isolated Python, Tcl, installer-entrypoint, recording-spawn, defaults and runtime checks. GPU also verified Qwen 3.5 4B, Whisper large-v3, all six Piper voices and CPU/CUDA native model runtimes. Both final ZIPs extracted at different paths and passed self-tests with system Python absent from PATH and invalid PYTHONHOME/PYTHONPATH.

Review 2: exact shipped bytecode matches current setup/installer source; archive roots remain Desktop-App-CPU/GPU; checked enrollment/history/provider secrets are excluded, with only pinned public voice assets allowed under .local. Transfer reused only byte-identical compressed payloads from previous verified ZIPs; locally reconstructed byte stream and remote full archive SHA-256 match the newly built releases. VM publisher atomically updated both catalog entries, preserving old immutable downloads and application services. Live platform-admin and tenant-admin Downloads page/catalog access, checksum-pinned HEAD, byte-range resume, invalid ranges, stale-hash rejection and short attachment filenames passed for both editions; anonymous/member access denied. Temporary verification sessions revoked, no enrollment token issued. All five services active; API/web ready. No new API/UI/database release or schema change needed for installer publication.

Limits: the CPU ZIP downloads local model weights/voices through setup or uses cloud assignments; the GPU ZIP includes Qwen/Whisper/Piper for matching portal assignments. Fresh extracted self-tests verify dependency and model integrity, not microphone/camera behavior or performance on the user's other computer. The previous release's local GPU inference qualification still applies to unchanged inference source/model assets; no new physical-laptop or full voice latency acceptance claim is made. Packages remain unsigned. Each different computer requires its own enrollment; do not copy enrolled private state between machines.

Published cpu: Human-test-windows-x64-cpu-protected-20261007-144648-252418.zip; bytes=335744211; SHA-256=2a365baf76afd9bdf37c7a6c97dde122c9193546aa6bb3b35af8e4e1a81d5969.

Published cuda: Human-test-windows-x64-cuda-protected-20261008-023519-200886.zip; bytes=7015166620; SHA-256=c536dd98183b2e1d51582b16960d4165d859b4fb80ee948313ecbbb29f629c91.

## VM cleanup review - 2026-10-08

User authorized post-build/deployment cleanup of temporary VM files, folders and database artifacts. Review 1 inventoried the four operator staging folders and checked their individual contents; all were completed upload/deployment archives, patches, checksums and temporary verification/deployment scripts. Database inventory contained only device_platform and postgres; no disposable test database exists to drop. Three revoked operator_download_verification sessions seen on initial inspection had already been removed by the existing account-expiry cleanup before execution. No application/tenant/media data or audit events were targeted.

Removed /home/evaluator/pms-update-20261005, pms-sessions-20261005, pms-update-20261007 and pms-downloads-20261007, including the cleanup scripts themselves. Cleaned the apt download cache under the package manager's lock. Exact absolute staging targets were validated against /home/evaluator before deletion; Linux fd-based shutil.rmtree avoids following child symlinks. Kept /var/lib/pms-downloads (including older immutable ZIPs for existing/resumed downloads), application/rollback releases, private media, configuration/keys, diagnostic journals and database backups. Active systemd private temporary directories were not touched.

Review 2 verified the active release still resolves to 20261007-144101-199603, catalog bytes unchanged (SHA-256 bb13ebb5d962c5614fde46e6a96ba996d755b4666cfea6b24fe001eef4c4a185), both current ZIP device/inode/size/mtime unchanged, and both ZIP roots/native protection manifests readable. All five services active; public API and web readiness passed. Verification-session count zero. Both database sizes unchanged (device_platform 14,358,195 bytes; postgres 7,689,907 bytes); no database/schema deletion or reset performed. Disk use fell from 47,835,488,256 bytes on initial audit to 31,132,372,992 bytes after cleanup, approximately 16.7 GB recovered; available root disk 34,296,664,064 bytes, usage 48%. No further cleanup finding; rollback and retained data deliberately preserved.


## Session assignment device confirmation review - 2026-10-08

The planner previously displayed a small fixed device label and created queued assignments immediately. Adding sessions now opens an explicit review of the destination device name/registration ID, trainees, case, language, duration and order. Change device returns to the draft with a device selector. Selected settings remain intact while the new device's scoped trainee list loads; unavailable trainees must be removed or a different device selected before confirmation.

Review 1 checked target-device identity, authorization scope, input validation, device-change request races, uncertain submission handling and duplicate-submit prevention. The request fingerprint includes the target device; retrying an unchanged submission preserves its key. Saving selects the confirmed device's queue without comparing revisions across different devices, while preserving the existing same-device stale-reply guard. Edit operations retain their original device and opening revision. Review 2 inspected the final diff and browser rendering, including focus on the review heading, pending-action locks, cancellation and mobile overflow. No remaining confirmed finding identified.

Verification: 33 tests passed across start-session, start-session-actions, sessions-experience, session-controls and session-archives; web TypeScript passed. The isolated browser fixture exercised device review, zero writes before confirmation, device change, exactly one confirmed write, selected queue and dialog bounds at 1440x1000 and 390x844, with light/dark themes and zero page errors. Evidence: .test_artifacts/session-device-confirmation-20261008/. All browser actions were mocked; no live session was created. No API/schema changes, hosted deployment, commit or publication. Earlier local LLM changes were preserved.


## Compact starter scenario review - 2026-10-08

The two fictional Alex starters previously duplicated timing and lacked explicit education, family-condition uncertainty and reliever-prescriber detail. Schema-5 documents now separate onset/duration/severity, retain clinical measurements and known history, identify resting measurement timing, and include short fixed food, sleep, education and school-day facts in English/Hindi. A usual meal does not imply yesterday's meal. These are system-authored fictional examples, with no fabricated clinician approval. Existing untouched publications receive version 2; new tenants receive version 1 containing schema 5. The other seven catalog drafts remain at revision 4.

Review 1 checked tenant creation/import readiness, canonical source fingerprints, atomic audit records, quota serialization, immutable provenance and publication history, archived/customized parent profiles, assignment lifecycle, private vitals overrides, and inactive version handling. Migration 0047 locks affected tables, matches frozen predecessor content, uses narrowly bounded owner-only trigger maintenance, restores triggers in the same transaction, preserves queued/live choices, and retires old publications only when no current use requires them. Customized content and historical records are never rewritten. A known 4-to-5 bundled upgrade may retain an already-mapped customized legacy snapshot; unknown source drift remains rejected. Audit expiration follows tenant policy bounded by platform limits.

Review 2 checked final diffs and compiled Windows behavior. Compiler 36 keeps family medical queries on family facts, household queries on household facts, qualification queries on explicit education facts, and yesterday-meal questions on recorded events. Missing facts remain unknown. The download updater accepts exactly three pinned protected conversation modules, verifies the source SHA and every archived member, rebuilds manifests, and validates both full and model-free outputs. Existing model/runtime data and unrelated protected modules are preserved. Other laptops require installation of the new desktop distribution; existing installations do not update themselves.

Verification: the general API suite passed 584 tests and skipped 395 without a database DSN. A dedicated disposable PostgreSQL 17 server on port 55488 ran the supported migration/provisioning/backfill/import group (18 passed), the background/queue group (19 passed), and a final six-test starter rerun including tenant-specific seven-day audit retention. These groups overlap and are not additive totals. API Ruff lint/format and mypy (87 source files) passed; shared-contract Ruff checks passed. Human-test local execution: 24 passed. Desktop updater: 5 passed. The complete protected Windows package qualified offline; final three-module compiled qualification passed for both starters, including family/qualification/missing-meal and same-house family queries.

Native verification used the actual Qwen3.5-4B-Q4_K_M model and llama.cpp CUDA runtime with total context 2,048, thinking disabled, and one slot. Full starter prompts with two recent pairs used 1,191/1,272 tokens; reserving 128 output plus 128 safety left both within the limit. Ten long pairs triggered removal of three complete pairs and fitted at 1,747/1,786 prompt tokens (2,003/2,042 including reserves). Selected family, qualification, prescriber and recorded-vital answers used the stored facts; unrecorded yesterday meals remained unknown. This verifies the tested prompts and native fitting, not unlimited retention of conversation history.

VM verification after authorized migration: Alembic head 0047_compact_starters; both global starters revision 5; both unchanged tenant starters have active publication version 2/schema 5 and inactive historical version 1. Before/after database hashes were equal for all 3 practice sessions, 9 conversations, 10 session archives and 408 archive items. Managed deployment created a PostgreSQL backup under /var/backups/pms-platform before upgrading and public readiness passed. No application/production database was used for destructive tests. Evidence and temporary tooling: .test_artifacts/compact-starters-20261008/ (excluded from Git).

Limitations: broadening isolated DB checks encountered the pre-existing scenario-library lifecycle fixture posting a retired schema-2 authoring document and receiving 422; current writes accept schema 4/5. This fixture was not used to relax supported validation. The 395 skipped general-suite tests are explicitly not claimed as live DB verification. Hindi translations validate, but only English conversation is installed. Microphone/camera/ASR behavior and installation on the user's other laptop were not verified. The recording-sync incident and earlier UI/local-client edits remain separate from this publication.


Final hosted verification: active release /opt/pms-platform/releases/20261008-151857-238576 contains compiler 36, the canonical provisioning fingerprint gate and mapped-legacy compatibility check. All four application services were active and public readiness passed; the protected database hashes above remained unchanged. The first attempt to prepare this final release hit a PyPI hatchling index timeout before replacing the working release. A temporary copy of the managed helper changed only uv sync/npm ci dependency installation to offline mode after successfully qualifying the existing cache; all backup, lifecycle, migration, grant, signing and recovery guards remained intact. The final deployment and post-deployment verification completed successfully.

Final private download catalog: GPU Human-test-windows-x64-cuda-protected-20261008-142000.zip, 6,950,650,298 bytes, SHA-256 18459e5dced68abc764f92109e47187e1f18f94561764345ea15121324adfa75; model-free Human-test-windows-x64-runtime-protected-20261008-142000.zip, 2,278,614,960 bytes, SHA-256 fbbb085719ca45e37a2010ba61e4c154559ee1a61077436888d873f5286f118b. Both archive manifests and actual protected module bytes matched the final qualified three modules. Repacking preserved 13,216 full-archive files and omitted 20 model files only from the smaller distribution. Previously published immutable downloads were retained. The disposable PostgreSQL test server and owned native model test process were stopped after verification.

Implementation publication used the configured helper's dry run and publish: local source 3176f1e3f10ad61839844b8b01247dc67e238dc3 mapped to GitHub main:device-poc at 164e4f1bcd11fb96aaae24b50bc0f8203e56d294. The helper verified preservation of other GitHub entries, including bill-poc. Only this task's changes were committed; the earlier UI/local-client work and its document sections remain unstaged.


## Two-scenario live evaluation and unified session history — 2026-10-09

Actual enrolled Human-test sessions against the VM exposed a chest-relief scope error, unrelated family-condition selection, unnecessary unknown markers, bundled social facts and indirect everyday quantities. Compiler 38 scopes explicit compound questions independently on the host and merges their evidence into one generation. It distinguishes pain intensity from education, retains explicit relief/current-presentation evidence, omits unrelated history for self-contained questions, separates independent authored sentences while preserving qualifiers/pronoun references, and requires actual dated meal evidence. Source selection remains checked against the immutable conversation snapshot; native fitting reserves 128 output and 128 safety tokens inside the total 2,048 context.

Forward migration 0048 refines only the two unchanged stock starters to source revision 6, publishes version 3 for matching existing tenant starters, and provisions correct version-1 publications for new tenants. Clinical measurements and presentation are unchanged; smoking/alcohol/household entries and English/Hindi sleep/work quantities are explicit. Customized sources, archived parents, quotas, selected live/queued versions, private vital overrides and historical publications/results remain protected. Review caught incorrectly stamped drafts and default-field differences in semantically identical publications. Fixed the seed/publication distinction and typed canonical comparison; did not relax publication-forgery checks. Existing migration 0047 is unchanged.

Sessions now has one scoped, paginated history for assigned sessions and standalone captures. Assignment completion, capture integrity, transfer status and saved/expected counts remain distinct. View session combines conversation and private recordings, with authorized archived-turn fallback and bounded pagination when separate text history is empty. Removed the confusing earlier-session entry and the separate Recordings & sync tab; existing captured data is preserved. Review checked tenant/department/learner scope, platform-admin media denial, signed actor/organization-bound cursors, retention, request races, duplicate rows, stale replies, errors/retry and private download authorization. Final visual inspection also fixed a stale help reference and status words wrapping mid-word.

API, laptop Settings and new environment templates default history reporting to true; explicit false remains an opt-out. The current laptop's saved flag and VM flag were enabled without exposing or replacing credentials. Live validation found that an enrolled device in a department could report a null department, producing a legitimate Scope not found rejection. The API now normalizes only omitted device department from authenticated scope before frozen-context validation and canonical idempotency checks. Explicit mismatches, another device, moved department, inactive scope and expired contexts remain rejected. User-report scope behavior is unchanged. The same normalization applies to text-free turn metrics.

Verification: final general API suite 614 passed, 398 skipped without a database DSN; Ruff lint, format (240 files) and mypy (87 source files) passed. Human-test suite 577 passed, 6 opt-in native/speech checks skipped; actual native execution was verified separately. UI sessions/archive/planner group 27 passed, TypeScript passed, and the affected eight session tests passed again after the help-text fix. Isolated PostgreSQL 17 on dedicated disposable port 55488: migration/provisioning group 47 passed, queue/archive group 9 passed, merged-history authorization/pagination regression 1 passed, final device pairing/scope/delayed-upload/idempotency/lifecycle group 8 passed. These groups overlap and are not additive totals. The device fixture now connects the enabled default history worker to its mocked API, waits for durable receipts, and uses its own temporary outbox. Its approximate mock tokenizer is not claimed as native capacity verification.

Broader DB checks are not clean: 32 older local-history/metrics fixture setups still call the removed tenant /llm/connections creation route and fail with 404 before exercising their assertions. The first device rerun also exposed asynchronous history acknowledgements and an inaccurate mock tokenizer estimate; those fixture problems were corrected and all eight device cases rerun successfully. No runtime authorization, context limit or failed assertion was removed to obtain a pass. Older schema-2 scenario fixtures remain a separately recorded modernization task.

Live evidence: the original 44-question baseline and final repeated 44 plus eight additional probes are preserved privately. The user manually ended an intermediate chest session; that interrupted run is excluded from completed evaluation totals. Both subsequent actual sessions ran silently with speaker output disabled, microphone/camera off. All 52 final turns used one native generation, maximum prompt 1,393 tokens (1,649 including reserves) and maximum actual usage 1,397. Manual response review: baseline 36 complete, 6 partial and 2 wrong scope; final 49 complete, 3 partial and no wrong-scope answer. Three compound uncertainties remain vague; wheeze relief repeats consistent evidence. Native generation median rose from 2,062.5 to 2,555 ms, maximum 5,937 ms; no speed improvement or sub-five-second guarantee is claimed. Full actual Q&A and limitations: [evaluation](simulations/patient-background/evaluation-20261009.md).

Authorized VM deployment applied migration 0048 under managed backup/traffic isolation. Release 20261009-024324-257885 preserved all protected rows/hashes at deployment: 5 assignments, 11 conversations, 12 archives and 502 items. Both final silent archives then synced 26/26 conversation items each while the app remained open, with complete final manifests. No desktop portable was built or uploaded during this review; hosted ZIPs/checksums are unchanged. The final API/UI release and text-history recovery are recorded below after live verification. Native ASR inference, physical microphone/camera, Hindi conversations, another laptop and blinded unseen-question accuracy remain unverified. All local live app/model/media processes owned by the harness were closed.

Final hosted verification: release `/opt/pms-platform/releases/20261009-033357-260510` deployed the final API/UI fix successfully with schema head 0048 and both starter publications at version 3. Its managed backup/restart preserved hashes for all 8 assignments, 14 conversations, 15 archives and 597 archive items existing before that deployment. All four services and public readiness passed. The normal background history worker then acknowledged all 74 pending original events, with zero pending/rejected records; both completed final sessions now expose 52 messages each, exactly matching all actual questions and delivered answers. A real authenticated browser verified 16 combined rows, full new conversation, archived baseline conversation, private recording links, no obsolete tabs/earlier-session entry and zero page errors. Screenshots were visually inspected; status text no longer breaks mid-word. Silent capture remains 26/26 per final session; no microphone, camera or output audio was generated. Hosted desktop ZIPs are unchanged. The dedicated disposable PostgreSQL server was stopped after verification.


## Reliable explicit sign-out review - 2026-10-09

API revocation failures previously returned an error without clearing the browser session, and a failed server-action transport displayed "Sign out failed". Explicit logout now reads the current opaque credential, expires the browser session/context cookies with their existing HttpOnly/SameSite/Secure/Path settings, removes the legacy cookie, and attempts API revocation once with a two-second deadline. API errors, missing/invalid credentials and timeouts cannot block returning to sign-in. Normal successful logout still revokes the API credential. The sign-in setup-status lookup also has a two-second deadline; passive session checks continue preserving valid cookies during API outages.

Review 1 checked credential handling, authorization, revocation/audit compatibility, failure handling and mutation replay. Both controls now submit a native POST to /logout, independent of server-action identifiers and client router caches; the rail also works without JavaScript. The route requires the public Origin to match Host and the trusted proxy scheme. Native submissions under the existing no-referrer policy can send null Origin, which requires browser Fetch Metadata declaring same-origin. Untrusted/null-without-metadata, cross-site, sibling-site and forged forwarded-host requests are rejected before any cookie mutation. GET is rejected and the redirect is fixed to /login. Review 2 inspected the final diff, bounded waits, production prefix-cookie expiration, proxy behavior and protected-page redirects. No remaining confirmed finding.

Verification: all 673 tests in 90 web files passed with two workers after the initial unrestricted parallel run timed out in two unrelated start-session/tenant-provision tests. Final affected rerun passed 80 tests, including four additional no-referrer/Fetch Metadata regressions; these groups overlap. Both UI workspaces passed TypeScript. Production build passed with an existing TenantProvisionWizard.module.css autoprefixer warning. An actual local Next/Edge journey against a mocked API passed seven browser checks: healthy logout, API 503, disconnected API, stalled logout/setup, JavaScript-disabled rail logout, cross-site rejection and GET rejection. Each logout removed session/context/legacy cookies and a subsequent protected-page visit returned to sign-in; server-action requests were blocked in the browser to verify independence. Zero page errors. Evidence: .test_artifacts/signout-20261009/results.json and signed-out.png. Owned fixture processes were stopped; generated tsconfig edits were removed.

Limitations: API revocation cannot be confirmed during an outage; a separately copied credential can remain valid until server expiry or another revocation. Clearing HttpOnly cookies requires a reachable web server. API/schema code was unchanged, so no API/database tests or migrations were run. Browser API calls were mocked; no live cloud/hardware verification, hosted deployment, commit or publication was performed. The user explicitly deferred VM deployment.


## Patient background tab layout review - 2026-10-09

The clinical Patient background tab previously stacked full-width fieldsets with repeated instructions, crowded buttons and checkboxes, and disabled inputs for published content. A dedicated shared component now presents five responsive category cards with aligned labels, brief guidance, expandable approved-detail controls and a compact draft preview. Additional background spans the available width. Published scenarios and restricted catalog viewers receive readable text, including saved choices and explicit missing translations, without edit controls. Styles use the existing light/dark/ledger theme tokens and remain scoped to this tab.

Review 1 checked disabled-fieldset enforcement, scenario lifecycle/author permissions, catalog viewer restrictions, language preservation, the three-choice limit, entry IDs and final-choice removal. Existing validation, document upgrade behavior and server authorization are unchanged. Review 2 inspected the final diff and browser rendering, including collapsed initial controls, mobile wrapping, expanded editing controls, published/reviewer layouts and 200% text sizing. No remaining confirmed finding identified.

Verification: 27 tests passed across patient-background, scenario-library-workflow, scenario-starters, catalog-editor and app-css. Both UI workspaces passed TypeScript. The production build passed with the existing unrelated TenantProvisionWizard.module.css autoprefixer warning. Local Edge browser checks passed 36 combinations of draft/published/reviewer views, widths 320/390/768/1440 and light/dark/ledger themes, with no checked control overflow or page errors. Adding/enabling/saving a detail, switching English/Hindi and 200% text sizing passed. Initial and expanded desktop/mobile screenshots were inspected. Evidence: .test_artifacts/patient-background-20261009/results.json and draft-default-1440-light.png.

Limitations: browser API/actions were mocked; no live cloud, hardware or hosted deployment was performed. API/schema code is unchanged, so no API/database tests or migrations were required. VM deployment remains deferred.


## Shared local model service design note - 2026-10-09

Recorded the user's requested future direction in [local-model-service-plan.md](local-model-service-plan.md): independently installed background services on the GPU laptop centralize approved model assets, downloads, inference, lifecycle and diagnostics; Human-test and a later Pi client use the same contracts. The hosted platform remains authoritative for identity, assignments, sessions and private history. Current local LLM/audio/video packages already separate some engines; Human-test speech and companion orchestration are extraction candidates. The note distinguishes model/service installation from loading/readiness, keeps physical capture/playback in clients, preserves independent service lifetime, separates video recording from future analysis, and records host-binding, authorization, GPU admission and context isolation work.

Documentation review checked the current Human-test/API boundary, standalone media services, native LLM setup, shared conversation imports and direct model assignment guide. A second inspection checked relative links, proposed-versus-implemented labels and the final documentation diff. The existing caller-only/loopback route is explicitly insufficient for a Pi using another host; the note requires future contracts rather than claiming the complete integration works. No remaining confirmed documentation finding. Runtime files, dependencies, models, credentials, services, databases, VM and Pi were not changed. Documentation-only verification used inspection; no runtime tests, live provider calls or hardware checks were needed or claimed. No commit or publication was performed for this note.


## Local model directory rename review - 2026-10-09

Renamed the complete local-llm folder to local-models, preserving installed models, native runtimes, download caches, private state and configuration. Before/after metadata matched for all 1,034 installed/private asset files; default Qwen and CUDA runtime passed existing pinned size/hash checks. Updated managed-launcher imports, credential/runtime lookup paths, offline installation, benchmark/qualification scripts, source/assets/protection/interpreter packaging paths, fixtures, help text and documentation links. Generated local virtual-environment activation paths were repaired without dependency installation. Existing Python module names, API identifiers, database migrations and historical .test_artifacts evidence locations retain their names.

Review 1 checked launcher and private-state boundaries, relocation of every tracked package file, asset privacy exclusions and source packaging paths. Review found the protected archive refresh helper must continue recognizing immutable releases containing the old folder name. It now supports both layouts without rewriting source archives, with a regression checking model-free output and preserved runtime inventory for each layout. Review 2 checked final diffs, current-path references, installed integrity, relative links, generated environment relocation and shared-service scope. Background-service implementation and Pi integration remain deferred.

Verification: 40 local model unit tests passed. The broad launcher/start group initially passed 277 tests and 13 subtests, skipped one opt-in deployment-database test, and failed three unrelated platform tests because the Human-test interpreter lacks pms_api. Rerunning the two affected platform test files with the API interpreter passed all 34 tests and 13 subtests. Final changed-path launcher/model-inventory/installer/portable/archive group passed 77 tests; these groups overlap. Batch model setup/run help, desktop launcher help and offline installer help passed without starting inference or downloading models. Nine API device-pairing/native-history tests were skipped without a disposable database DSN/native opt-in. No destructive test used an application or hosted database. API Ruff lint/format (240 files) and mypy (87 source files) passed; local-models Ruff lint/format passed. Core syntax/error lint passed across model/start/launcher code. Broader style checks retain existing import-order/format findings; comparing changed Python files against HEAD confirmed no new style findings after adjusting line wraps for the longer directory name. Evidence: .test_artifacts/rename-local-models-20261009/.

Limitations: no real inference generation, microphone/camera, Raspberry Pi, live cloud provider, desktop release build/upload or VM deployment was performed. The native check verified installed file integrity only. Earlier shared-service design documentation remains present. No commit or publication was performed.


## Manage Local Models desktop UI review - 2026-10-09

Created a separate Python Tk/ttk desktop interface in local-models/desktop, launched with manage-local-models.bat or manage_local_models.py. The application is named Manage Local Models. Overview, Models, Services, Logs and Settings share a navy/teal palette, locally drawn outline/title-bar icons, persistent navigation, scrollable pages and responsive model/service cards. Navigation, category/search/sample-log filtering and model/download, service-status and provisioning preview dialogs are presentation-only. All operational download/provision/start/stop/export/save controls are disabled. Hardware, installation/readiness states and logs are explicitly labelled sample data; video analysis remains planned and recording is identified as model-free.

Review 1 checked scope, dependencies, process/file/network boundaries, sample-versus-live labels and UI interaction. The app imports no installers, inference engines, Human-test, platform clients or supervisors, and does not read private state or change model/service configuration. Review found and fixed a stale resize callback after category changes, unused second-column spacing in narrow layouts and a temporary Tk variable leaving the preview capability blank. Review 2 checked final layouts, disabled operations, independent window lifetime, native icons and documentation. No remaining confirmed finding.

Verification: 42 native UI checks passed across 1280x820, 1040x700 and 1600x1000, covering every page, model categories/search, filtered read-only logs, category changes followed by resize, full-width single-column cards, compact dialogs and disabled operations. Existing 40 local-model unit tests passed. Ruff lint and format checks passed for all 23 Python files in local-models; git diff --check passed. Native GUI verification required execution outside the sandbox because it could not access installed Tcl/Tk libraries. Initial native screenshots were inspected; subsequent Windows DPI/compositing capture attempts were inconsistent or stalled, so optional screenshot capture was removed from the reusable test. Final verification uses direct native geometry/navigation checks. Evidence and capture-attempt notes are under .test_artifacts/local-models-ui-20261009/.

Limitations: this verifies the native presentation, not live hardware inventory, downloads, background-service provisioning/lifecycle, actual inference, logs, platform connectivity or Raspberry Pi support. API/database/schema code is unchanged, so API/database tests were not required. No service/model installation, cloud call, hosted deployment, desktop release build, commit or publication was performed. Earlier folder-rename and design-note work remains present and uncommitted.


## Manage Local Models operational implementation review - 2026-10-09

Implemented the independent operator manager and live desktop controls in phases: private atomic metadata/contracts and approved inventory; verified downloads/isolated runtimes and owned resident model adapters; then asynchronous desktop wiring, filtered operational logs/export, revisions/defaults, diagnostics and remove-configuration controls. Model installation remains distinct from provisioning and start/readiness. The UI defaults to live data; --preview is explicit. The manager is a detached operator process, not an installed Windows service. The user queued genuine service registration and reboot auto-start next, so boot controls remain disabled and the backend rejects start_at_boot=true.

Review 1 inspected authentication, filesystem/credential boundaries, approved source IDs and hashes, idempotency/concurrency, process ownership and native adapter compatibility. Fixed nested Vosk manifests and required files, the incorrect QwenMedic installer entry point, cached source validation, private library/cache permissions, isolated optional conversion dependencies, duplicate-manager locking, worker-guard failure cleanup and bounded slow input. Runtime preparation cannot replace a manager-owned running capability's environment; shared LLM preparation takes the existing installer lock.

Review 2 inspected real desktop events, UI/backend separation, errors/reconnection, startup failure/readiness, native child death, stop/drain semantics, shutdown races and persistence failure. Fixed status reporting for failed starts/native children, wrapper release before reprovisioning, shutdown admission, restoring active operation visibility after reconnect, bounded connection startup, operator permission errors, atomic write rollback and read-only mutation handling after persistence failure. The native fixture's final teardown originally observed port closure before its process released the lock; it now waits for the owned process to exit. An empty-body regression exposed an ambiguous status code, corrected to 400 independently of oversized-body 413. Affected regressions were rerun after fixes.

Verification: 72 local-model unit/regression tests passed, including the existing 40 and 32 new manager tests. Native preview layout passed 42 checks; live desktop against authenticated HTTP and fixture engines passed 23 checks across all pages and three sizes, including provisioning, start/stop, filtered export, settings and UI closure. Separate opt-in native tests loaded existing verified Qwen3 1.7B, Piper English and Whisper large-v3 on CPU; all three answered through the detached manager and stopped. Actual Tk desktop closure was followed by successful inference from a new client using the same resident LLM. The final native run exited successfully and stopped its isolated manager/workers. Native GPU, live publisher downloads/conversions, microphone/camera/Pi, LAN pairing and cloud/hosted deployment were not verified. Existing model files were reused; no model downloads occurred during native checks. Ruff lint and formatting passed for the local-model package. No platform API/schema code was changed by this operational phase, so API/database integration tests and migrations were not applicable. Preserve earlier rename verification and unrelated concurrent API/UI edits.

Reconciliation: current desktop controls and local model APIs are implemented; Windows SCM installation/uninstallation and reboot auto-start remain the next queued phase; Human-test migration, scoped clinical execution, TLS/LAN pairing and Pi/video analysis remain separate future work. See [the detailed reconciliation](../local-models/manager-review.md) and [control reference](../local-models/desktop/README.md). No VM update, commit or publication was performed.


## Manage Local Models final review and fixes - 2026-10-09

Final review inspected desktop configuration round trips, disconnect/error behavior, real readiness/device execution, installation integrity/recovery, process ownership/cleanup, port conflicts, export destinations and current control restrictions. Fixed configuration resetting saved GPU/port/options; false-ready repeated starts; duplicate model disk-space gates on verified reuse; non-atomic source/manifest writes and incomplete cached HF metadata; interrupted conversion publication; legacy voice SystemExit escaping the operation thread; installer guard release on termination failure; installer import races; manager/native-port collisions; and log export overwriting private metadata or managed assets. The final desktop inspection also fixed Refresh Status closing its dialog and the hard-coded default inference port. Current status updates configure/remove availability; disconnected/invalid forms preserve entered values. Affected checks were rerun, followed by a second inspection. No remaining confirmed finding was identified in reviewed paths.

Verification: 83 local-model unit/regression tests passed (11 additional backend regressions); 27 native live desktop checks passed against real authenticated HTTP and fixture engines; 42 native preview layout checks passed after the shared field change. Independent native CPU and GPU runs reused verified Qwen3 1.7B, Piper English and Whisper large-v3. All three inferred on CPU; Qwen/Whisper separately reported CUDA and inferred, while Piper remained CPU. GPU hardware was NVIDIA RTX 500 Ada Generation Laptop GPU (4094 MiB), with 16 LLM layers requested. These are sequential functional checks, not concurrent GPU capacity or performance qualification. Both native runs closed the actual Tk desktop and confirmed inference from a new client through the same resident LLM, then stopped their isolated workers/managers. Existing Qwen/CPU runtime reuse passed with network fetch blocked. No weights were downloaded. Ruff lint/format passed for 42 Python files, Git whitespace check passed, and private manager/model/runtime paths remain ignored.

Download/installer failure regressions use fixture assets/mocked publisher calls; live publisher downloads/conversions remain unverified. Genuine Windows SCM installation/removal, dedicated service identity and reboot auto-start remain the next queued phase. The detached manager already survives UI closure. Journal archive maintenance remains necessary before the documented 2000-operation limit; shared clinical clients, scoped session/LAN authorization, Pi/video adapters and cloud/hardware integration remain separate. This review changed no platform API/schema, so no API/database tests or migrations applied. Earlier rename checks/skips and unrelated concurrent API/UI work remain intact. No VM update, commit or publication occurred. Detailed reconciliation: [manager-review.md](../local-models/manager-review.md).


## Human-test centralized inference migration - 2026-10-09

Human-test is now a consumer of the local-models gateway. The scope covers desktop
routing/readiness, recognition and physical playback, setup/launch scripts,
portable packaging, central model credentials/voice ownership, and the relevant
qualification tools. Platform API/schema and unrelated concurrent work were not
changed by this migration.

| Requirement | Reconciliation |
| --- | --- |
| One implementation for local inference | Shared local-model-client package in local-models/client; manager owns LLM/ASR/TTS engines. |
| Models/access from the central manager | Verified inventory/aliases/voices and live service readiness; inference-only credential excludes management, logs and shutdown. |
| No model management in Human-test | Removed offline tab/installers, local catalog, native loaders, model launch/cleanup, GPU selection and restart supervisor. |
| Startup connects only | Prepared-child handover and read-only platform/manager readiness; cloud startup remains usable with the manager unavailable. |
| Central synthesis assets/runtime | Voice locks/installers and existing private weights moved intact to local-models; Piper removed from Human-test dependencies. |
| Physical devices stay in the client | Microphone, speaker, camera, bounded recording, UI/session handling and durable playback gates retained. |
| Model-free client builds | One desktop environment plus SDK; native engines, weights, runtime installers and manager keys excluded. |
| Future consumers | Shared inference contract prepared; Pi code and authenticated LAN/TLS pairing deferred. |

Both reviews were performed by the same agent. Review 1 checked the extraction,
model ownership, route/model pinning, clinical context/fact validation, credential
separation, private media/history preservation, client packaging and request replay.
Findings fixed included empty metadata breaking cloud UI startup, stale native
transport/test fixtures, a voice installer still called by setup, and central
runtime/model paths still rooted in Human-test. Affected regressions were rerun.

Review 2 checked the final startup/window lifetime, native engine calls, live
readiness, metadata refresh, playback caches, Windows HTTP rejection and source
imports. Fixes covered the prepared-child flag causing recursive launcher startup,
obsolete compute/process fields in launcher status/monitoring, stale monitor data
being used for synthesis readiness, cached audio losing its actual sample rate,
unread denied POST bodies aborting the Windows response, malformed metadata/error
codes, and simulation imports of removed Human-test modules. Explicit regressions
cover these findings. Final inspection found no remaining confirmed issue in the
reviewed paths.

Verification:

- Human-test full suite: 674 passed, 2 skipped. The two skipped tests opt into a separately
  running Qwen clinical fixture; this migration instead qualified isolated native
  CPU and GPU workers through the real shared client. Final affected launcher
  suite: 112 passed after the last status/monitoring/port-policy fixes.
- Central manager, shared-client security and portable-package suite: 144 passed,
  plus 41 subtests. This includes credential permissions, one-attempt inference,
  malformed inputs, model pinning, live readiness and model/private-data exclusions.
- Actual Tk checks: pairing/reconnect/reset/cancellation, read-only Models and
  Practice action layout passed. No real platform enrollment was performed.
- Native CPU: verified Qwen3 1.7B, Whisper large-v3 and Piper English inferred
  through the SDK. Native GPU: Qwen/Whisper reported CUDA and inferred; Piper
  remained on CPU. Runs were sequential on the existing installed weights, with
  16 LLM GPU layers; they do not qualify simultaneous GPU capacity or performance.
- Both native runs closed the actual manager desktop, then confirmed inference
  from a new client through the resident LLM. Client disconnection has no stop or
  shutdown request. Isolated managers/workers were stopped by their test owner.
- Frozen dependency sync and CLI help/import checks passed; Ruff lint/format passed
  for 165 Python files and Git whitespace checks passed. No weights were downloaded.

Private evidence is under .test_artifacts/human-central-models-20261009/:
human-final-pass.txt, launcher-final-pass.txt, central-complete.txt, native-cpu.txt,
native-gpu.txt, connection-window.txt, setup-layout.txt and CLI help output.

Windows SCM installation/removal and reboot auto-start remain queued. The manager
is currently detached under the Windows operator. Pi networking/hardware, video AI,
physical microphone/camera quality, live cloud and publisher downloads remain
unverified/deferred. No API/database tests or migrations were needed for this
client/manager-only change. No VM update, hosted-download replacement, commit or
publication was performed. Run instructions and remaining boundaries are in
[local-model-client-migration.md](local-model-client-migration.md).


## Human-test portable packaging scope cleanup - 2026-10-09

Human-test now has one desktop/runtime build and no model/GPU bundling or protection
options. Removed the GPU batch wrapper and the archive-refresh helper that rebuilt
model-containing releases. The publication helper accepts a single protected
`--client` ZIP; its `desktop-runtime` ID/filename convention remains compatible with
the unchanged platform download API. No hosted files or catalogs were updated.

The package contains Human-test UI/physical capture/session code, private Python/Tcl,
its locked desktop dependencies and two ordinary shared client libraries. Shared
clinical contracts and the central HTTP client are installed in that runtime's
site-packages; no Local Models app/source tree ships. Native protection covers only
eight Human-test modules. SDK/contracts are not part of this Cython/bytecode pass.
Benchmarks, repository setup metadata, model installers/services, weights, inference
runtimes and private state are excluded. Shared build/self-test/publication checks
reject unexpected layout, known engine dependencies, model assets and credentials.
Runtime metadata explicitly declares version 2/application human-test/role client.

Review 1 removed the deprecated parser flags, dead CUDA/model ZIP branches, generic
model runtime/protection paths and legacy publishing/refresh choices. Review 2
checked relative paths, runtime dependency imports, native protection inventory,
archive scope/hashes, atomic immutable publication and failures. It fixed malformed
metadata/protection validation and centralized the exact protected module list.
Both inspections were performed by the same agent; confirmed findings were fixed
and affected checks rerun.

Verification: 56 packaging/publication regressions passed. Ruff lint/format passed
for all 8 changed Python files, and Git whitespace checks passed. The actual Windows x64 protected build produced a 115,917,636-byte ZIP with 4,039 files. Its ZIP sidecar and every manifest hash passed the strict publication verifier. Human-test.exe --self-test returned 0 from both the release folder and a freshly extracted directory with spaces in its name, verifying 8 native modules, private runtime imports/paths, Tcl and recording-process startup. The build batch now merges dependency-tool informational stderr for PowerShell and correctly returns 0 for help and 2 for removed options; an executable batch regression covers these exits.
The first build passed its executable self-test but final validation failed because
a helper was edited during that build; final verification used a fresh process
against finished source definitions. No model weights were downloaded or inferred,
and no central manager or cloud service was contacted.

API/schema/business logic were unchanged, so platform/database tests were not run.
Physical microphone/camera quality remains outside package checks. Separate Local
Models portable packaging/downloads and Windows SCM/reboot startup are later phases.
Unrelated workspace changes remain intact; no VM update, commit or publication.
Run/build details: [human-test-portable.md](human-test-portable.md).


## Human-test requirements cleanup review - 2026-10-09

Review 1 inspected static/dynamic import paths and the runtime dependency graph. Human-test has no current WebSocket client usage: local/cloud audio and inference use HTTP. Removed `websockets`; made directly used Pydantic explicit without adding a new installed package. Retained SoundDevice/CFFI for microphone/playback, OpenCV/NumPy and PyAV for camera/recording, HTTPX and settings dependencies, training contracts and the thin local-model client. The graph contains no inference engines or model-management packages.

Review 2 checked frozen lock/export consistency, setup and launcher behavior, development separation and the actual installed environment. Normal setup now performs an exact `uv sync --frozen --no-dev`, removing obsolete WebSockets and 12 development/tool dependencies from this Human-test virtual environment. Development requirements remain available through `uv sync --frozen`; batch launchers use the existing environment.

Verification: 731 tests passed, with 2 explicitly opt-in resident Qwen checks skipped. Actual `human-test/setup.bat` returned 0; the final environment contains exactly the 19 exported registry packages plus Human-test, local-model-client and training-contracts. All 27 Human-test modules import and Tcl initializes. `uv pip check` reports all 22 installed packages compatible; offline lock check and Git whitespace check pass. The restricted Tcl smoke initially could not read Python's installed init.tcl; rerunning with approved access passed. No physical capture, model inference or cloud integration was performed.

No Python business logic/API/schema changed, so platform/database tests were not run. Existing portable archives were preserved; the next build will consume the cleaned lock. Unrelated work remains intact. No VM update, commit or publication.


## Local Models loading/preferences and reported desktop launch failure - 2026-10-09

Implemented an animated loading card on all five management pages before connection/inventory verification. The manager reports loading/ready/failed initialization, and failed checks present Try again. Initial polling waits for connection completion to avoid an unavailable flash while a manager starts. No model/service mutation form is available during loading. Retry reconnects or requests an inventory refresh; it does not replay or start inference.

New supported model/runtime selections prefer GPU; CPU-only adapters remain CPU. New LLM forms prefer installed qwen3.5-4b over catalog order. Factory GPU layers are 20. Legacy factory defaults move from 16 only when no operator settings action/custom preference is present; existing service options remain intact. Saved services, explicit model-card choices and custom CPU selection take precedence. Revisions advance once on persisted default migration. The UI also understands snapshots from a running older manager without stopping its workers.

The user's actual private operational log located the Human-test TypeError at Demo.launch -> Windows CreateProcess, before the child window existed. HUMAN_LOCAL_MODELS_PORT was an integer. Startup now writes a string port and the desktop environment boundary serializes typed values, omits absent optional values and retains backend credential filtering. Regression checks launch a real subprocess with numeric and string port inputs, path/bool options and redacted backend test credentials.

Review 1 checked initialization/failure transitions, device/model/default precedence, old-state compatibility and persisted preference intent. Review 2 checked dialog preservation, reconnection concurrency, progress timer cleanup, private logging/environment filtering and inference ownership. It fixed a retry that entered loading after metadata restrictions refused refresh; native regression now verifies that rejected refresh leaves the error/retry screen visible. Confirmed fixes were checked again.

Verification: 94 manager/runtime unittest checks, 27 inference-client pytest checks and 65 Human-test startup regressions passed. Native Tk checks passed: 42 preview layout checks, 27 isolated HTTP-manager/live-control checks, and 14 delayed loading/default-selection/retry checks. Human-test setup geometry passed at three sizes with mocked platform data. Ruff lint and formatting passed for all 12 changed Python files; whitespace checks passed. Early discovery with system Python lacked thin-client dependencies; the final unit suite used the Human-test project environment. Human-test was restored to runtime-only dependencies after verification.

No actual model inference, asset download, live cloud/hardware quality check or production manager mutation was performed. Platform API/schema/business logic were unchanged; platform/database tests were not run. Existing portable archives were preserved and require rebuilding to pick up these source fixes. Windows SCM/reboot startup and Raspberry Pi work remain queued. No VM update, commit or publication.


## Local Models capability-specific provisioning options - 2026-10-10

Provisioning now derives visible options from the selected capability, execution mode and supported adapter. LLM shows CPU threads, context size and output limit, plus GPU device/layers only in GPU mode. Recognition shows CPU threads for Whisper/Nemotron and GPU device selection when supported; Vosk has no effective thread tuning. Current Piper synthesis exposes service timeouts only because its thread count is controlled internally. Startup/drain timeouts apply to all capabilities. Global Settings remains a complete defaults form.

Runtime drafts are separate per capability and survive capability/device/model changes. Only visible fields are parsed; unchanged hidden legacy values are retained in the existing complete worker option shape. This keeps old saved configurations and a running older manager compatible. GPU/Qwen/20-layer defaults, revision/ownership checks and language context/output validation are preserved. No native worker lifecycle or API/database behavior changed.

Review 1 compared each control with the actual LLM, Whisper/Nemotron/Vosk and Piper implementation and checked compatibility of partial incoming options with complete saved worker options. Review 2 checked capability switches, draft preservation, hidden invalid GPU/LLM inputs, CPU-only adapters and context-budget enforcement; regression checks passed with no unresolved findings.

Verification: 131 local-models pytest tests and 50 subtests passed. Native Tk fixture checks passed: 13 capability-option checks, 14 loading/default-selection checks and 27 isolated HTTP manager/desktop checks. Lint and formatting passed for the 6 touched Python files and whitespace checks passed. Human-test development tools installed for checks were removed again; its final runtime-only imports and dependency compatibility passed. No live model inference/download, cloud or hardware quality check was performed. Platform/schema/business rules were unchanged, so platform/database tests were not run. Existing portable archives were not rebuilt. No production service restart, VM update, commit or publication.


## Publication review of central model migration - 2026-10-10

The final all-changes review found two API test fixtures still coupled to Human-test's removed local model implementation. Device pairing now supplies central inventory, uses the inference client key setting and mocks the manager capabilities/inspection/inference contract. Local/cloud parity now imports the shared client and exercises the same central contract while preserving comparisons of prompts, answers and safe telemetry. These are fixture updates; production API authorization and inference behavior are unchanged.

Verification: final broad API run 614 passed, 406 database/opt-in tests skipped without a test DSN. Separately, 33 device pairing, model review, console and management tests passed against the dedicated disposable PostgreSQL 17 server at loopback port 55589, using per-test databases, forward migrations and runtime grants. No application database was used. Three corrected parity tests also passed separately. API Ruff lint, formatting (240 files) and mypy (87 source files), both UI TypeScript checks and 25 affected UI tests passed. Earlier Local Models 131-test/50-subtest results and native desktop evidence remain recorded above; those checks were not repeated for publication. Existing test-client and workbook warnings remain.

Second review checked the final fixture contracts, staged diff, whitespace, file sizes and credential/private-artifact exclusions. Model weights, manager state/keys, local environments, recordings and generated portable archives remain ignored. This publishes committed source; it does not rebuild or replace earlier immutable desktop archives, deploy the VM, contact a live model provider or verify Raspberry Pi hardware. Windows SCM/reboot auto-start and authenticated LAN/Pi support retain their documented queued status. Evidence: .test_artifacts/publish-api-tests-final-20261010.txt, publish-db-tests-20261010.txt, publish-ui-tests-20261010.txt and publish-ui-types-20261010.txt.


## Local tenant and real desktop inference review - 2026-10-10

Started the local API after a private verified database backup and existing 0046-to-0048 migration/runtime-grant upgrade. Provisioned a new local tenant, administrator and enrolled laptop through authorized API operations; assigned Qwen 3.5 and Whisper. Preserved the previous hosted enrollment privately. API endpoint, database model and migration source were unchanged.

Review 1 exercised actual Tk desktop windows and resident Qwen/Whisper/Piper services, comparing fictional answers to the published cases. It found an emotional question answering with a pain score and an intake wording missing presentation scope. The shared evidence selector now restricts emotional answers to emotional facts and recognizes equivalent intake wording; compiler version is 39. Review 2 found mixed clinical questions could drop known emotional background, fixed the source-domain vocabulary, and added/ran all ten regressions. It also checked immutable facts, context compatibility, credentials, authorization boundaries, startup and service ownership. Corrected stale Human-test migration wording in manager Settings. No unresolved confirmed code finding remains from these checks.

Final native run: nine typed questions and one synthesized-speech question across chest/wheeze scenarios, matched clinical/background/general answers, safe missing-detail response, no instruction disclosure, distinct conversations and ten completed API history records. Real speaker playback was confirmed audible by the user. Actual manager Stop/Start/status/Configure/Logs controls passed; SDK saw stopped TTS without starting it. Closing either UI left all three services Ready; Qwen reports 20 offloaded CUDA layers, Whisper CUDA and Piper CPU. Canonical reconnect and real Human-test child launch succeeded. Inference-only management access returned 403, anonymous capabilities 401 and another-organization device access 404. Final window-only captures were inspected. Physical microphone check returned digital silence despite Windows consent Allow, so live spoken microphone quality is not claimed.

Verification: API 614 passed/406 skipped (no disposable DB DSN), affected final conversation/parity 165 passed/2 skipped, Human-test broad 572 passed/2 skipped and final affected 62 passed/2 skipped (including ten new regressions), Local Models 132 passed plus 50 subtests. API lint/format/mypy, touched Python lint/format and whitespace checks passed. The application database was not used for destructive tests. Native inference is separate from unit mocks; no cloud, camera/Pi quality, reboot/SCM, VM or portable artifact verification was performed. Existing warnings remain. Both review passes were performed by the same agent.

Full reconciliation and ignored evidence locations: [local-practice-review-20261010.md](local-practice-review-20261010.md). Apps and API are left running on the new local pairing; speaker output stays enabled. Verification was completed before the subsequent commit/publication request; publication is authorized separately. Final publication review checked all pending source, examples and review evidence, with private runtime data excluded.


## Shared client extraction - 2026-10-10

Shared training-client extraction and Human-test cleanup are complete. Two review passes, fixes and verification are recorded in [shared-client-review.md](shared-client-review.md): broad desktop/shared tests 703 passed/2 skipped, final ownership regressions 75 passed, packaging/inference checks 83 passed, and API 614 passed/406 skipped (no disposable database). Lint/format/types, synthetic native UI checks, standalone wheel and protected desktop self-test passed. No API schema change, live hardware/cloud verification, deployment or publication. Raspberry Pi and remote GPU transport remain the next phase.


## Shared client follow-up review - 2026-10-10

Reviewed and fixed common/runtime and Human-test lifecycle boundaries, including cancelled poll supervision, headless playback interruption, rejection of audio fragments, guarded model/reset operations, closed-runtime startup, forced camera termination, native module path validation and Tk shutdown callbacks. Regression failures were reproduced before the relevant fixes. Final broad client suite: 720 passed/2 opt-in native checks skipped; packaging/inference: 84 passed; API: 614 passed/406 database-dependent checks skipped, with no disposable database configured. Lint/format/types, native synthetic UI flows, standalone wheel and final protected desktop self-test passed. No live cloud, physical hardware, deployment or publication. Details and limitations: [shared-client-review.md](shared-client-review.md).

## Shared client live local verification - 2026-10-10

Started Local Models, local API and Human-test using the existing test tenant. Real Qwen/Whisper/Piper runs passed the chest-discomfort and wheeze scenarios: eight typed and two synthesized-speech questions, separate conversations, ten completed API history records and two complete synchronized audio archives. Native inspection found an idle microphone pause incorrectly telling the user to repeat a completed question. Fixed only the desktop cancellation presentation and added three regression cases; 64 affected tests, lint/format and desktop mypy passed. Both complete live scenarios were repeated after the fix, including assertions for the corrected pause message. Normal saved-device startup passed and applications remain running.

No API implementation/schema change or database migration was needed. The application database was accessed through normal APIs only; destructive database integration suites were not run. Physical microphone probing reports digital silence; ASR verification used synthesized PCM through the real shared Listener. Cloud, camera, Pi/LAN, hosted deployment and portable rebuild remain outside this run. Full evidence and limits: [shared-client-live-review-20261010.md](shared-client-live-review-20261010.md).


## Raspberry Pi framework and two reviews - 2026-10-11

Implemented pi-test as an idle-on-boot headless service reusing training-client. Added private local control, enrollment/diagnostics, systemd lifecycle, ALSA/USB/CSI adapters, independent bounded media transport and cloud synthesis through existing processing. Remote local inference runs on a separate GPU gateway with TLS, platform-signed device/host/model/body grants, durable replay prevention, admission limits and status receipts. Platform changes are limited to optional validated device details.inference plus binding/grant endpoints; existing JSON storage and tenant/device/conversation/session checks are reused, with no migration.

Review 1 fixed service ownership/shutdown, finishing barriers, host-specific caches, unknown-request journals, signed output/duration budgets, bounded grant reads, lifecycle revalidation and release validation. Review 2 fixed concurrent status/shutdown responsiveness, listening state, redacted stream failures, atomic admission limits, malformed grants, cloud cancellation/deadlines and supervised GPU startup failures. Both passes and affected reruns are complete; no confirmed finding remains unresolved.

Verification: Human-test/shared 623 passed and 2 opt-in skips; final Pi/shared/manager/client 126 passed with 2 subtests; gateway 14 passed plus a separate real TLS/WSS transport check. API broad run 620 passed and 408 database/opt-in skips. Dedicated disposable PostgreSQL on port 55459 passed all 20 selected inference, two-scenario Pi, session and device-management checks using per-test databases, forward migrations and runtime grants. API lint/format/mypy and client/gateway lint/format/types passed. All deployment scripts parsed. Built 24 pinned CPython 3.13 ARM64 wheels and the gateway wheel; offline hash-checked cross-platform installation dry-run passed.

No physical Pi, Linux/systemd execution, real GPU over LAN, paid cloud or hosted deployment is claimed. WSS ASR sends completed utterances; video ingress is transport only and explicitly reports vision inference unsupported. The application DB and services were preserved. Full findings, evidence and final artifact locations: [Pi review](../pi-test/docs/review.md), [operations](../pi-test/docs/operations.md), [hardware acceptance](../pi-test/docs/compatibility.md). No commit or publication.


## Raspberry Pi completion review - 2026-10-11

Completed software phases and two distinct review/fix passes. Fixed remote ASR preflight's desktop-key requirement, cloud output execution_mode handling, device heartbeat identity, duplicate WSS timestamps, JPEG allocation bounds, capture/result cancellation, optional GPU readiness and probe/capture sample-rate mismatch. Added independent camera processing, durable private request inspection, native qualification automation and upgrade/rollback safeguards.

Verification: Pi/shared 73 passed; gateway 18 passed with real loopback TLS/WSS and mocked model/provider execution; Human-test/shared 632 passed and 2 GUI skips; affected desktop preflight/readiness/local execution 136 passed, final capture/listening 66 passed; manager/client 76 passed plus 2 subtests. API full run 620 passed and 410 DB-dependent skips; separate disposable PostgreSQL run 11 passed, plus final two-scenario text/ASR journey rerun passed. Ruff, format, mypy and whitespace checks passed. Built 24 hash-locked ARM64 wheels and gateway 0.2.0; offline dry-run and exact source/wheel comparison passed.

[Detailed findings and evidence](../pi-test/docs/completion-review.md). Native Linux/systemd/ARM, physical hardware, live cloud and real GPU over LAN remain unverified. The native qualification runner correctly refused this Windows/AMD64 host. All user-requested application services remain stopped and the test PostgreSQL server was stopped; application DB unchanged. No commit/publication/deployment.


## Human-test, Pi-test and shared client end-to-end review - 2026-10-11

Completed two review/fix passes plus final inspection. Fixed shared video HTTP 202 acceptance, Pi video cancellation before finish acknowledgement, a persistent standalone finish barrier, common private-media URL validation and cookie isolation, output stream reopening on speaker change and voice preference application after metadata discovery. No platform API implementation change was required; stale desktop integration fixtures were updated to current contracts.

Verification: Human-test/shared 638 passed and 2 opt-in skips; sandbox-blocked native Tk camera test passed separately outside the sandbox. Final Pi/shared 84 passed; manager/client/desktop packaging 90 passed plus 2 subtests; gateway 18 passed including fixture TLS/WSS. API broad suite 620 passed and 411 database-dependent skips. All 23 selected database-backed tests passed across targeted runs after stale fixture corrections, including both desktop modes, Pi's two scenarios with text/ASR, actual shared video processing, permissions, lifecycle, grants and archive recovery. Ruff/format and mypy passed; final 24-wheel ARM64 bundle matched source and passed offline hash-checked installation dry-run.

[Detailed findings, initial failures and final evidence](client-e2e-review-20261011.md). Physical Pi, Linux/systemd/ARM execution, live cloud, real GPU/LAN and endurance remain unverified. The disposable PostgreSQL server was stopped; user application services remain stopped. No application database mutation, commit, publication or hosted deployment. Existing desktop portable binaries were not rebuilt.


## Pi-test final review and fixes - 2026-10-11

Reproduced four regressions before changing code: pending control commands delayed shutdown, queued/new commands could be admitted after shutdown, JSON escaping rejected valid Unicode input, and the CLI could submit truncated oversized stdin. Fixed cancellation/cleanup order, stopping-state admission, bounded UTF-8 framing and pre-trim input limits with optional terminal newline handling. Installer now refuses to switch releases after service-stop failure and rejects dangling release symlinks; Pi deployment Git attributes preserve LF. Second inspection completed with no unresolved confirmed finding. No API/shared runtime implementation changed in this pass.

Pi/shared 91 passed; Pi lint/format (24 files) and mypy (10 files) passed. API broad suite 620 passed and 411 skipped without a database DSN; API lint/format/mypy passed. All three Pi deployment shell syntax checks passed; real systemd execution remains unverified. Rebuilt 24 hash-pinned CPython 3.13 ARM64 wheels, verified offline installation dry-run and exact match of all 69 application Python sources. Physical hardware, real GPU/LAN, live cloud and endurance remain unverified.

[Complete findings, evidence and release location](../pi-test/docs/final-review.md). Application services and test PostgreSQL remain stopped. No commit/publication/deployment.
