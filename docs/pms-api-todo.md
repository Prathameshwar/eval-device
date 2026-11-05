# PMS API implementation TODO

## Device list required model action - 2026-10-09

- [x] Add a platform-only model selection status using one bounded query per page.
- [x] Show Configure Model immediately after View with a subtle gray row and Model required when no model is selected.
- [x] Preserve lifecycle/permission checks and refresh status/focus after saving.
- [x] Complete isolated PostgreSQL verification and record final review evidence.

## Human-test menu, local replies and download refresh - 2026-10-08

- [x] Reproduce the hidden three-dot menu at short heights/high display scaling;
  anchor the menu to the top and clip the camera preview below its header.
- [x] Verify 240 native layout cases across 100%, 150% and 200% display scaling,
  including the protected portable interpreter at 200%.
- [x] Inspect authorized synced history and reproduce invalid local replies across
  multiple question wordings, cases and history lengths; preserve private evidence.
- [x] Constrain local fact-ID decoding without relaxing evidence checks or retrying
  generation; qualify the single rebuilt native module and portable executable.
- [x] Replace the CPU download choice with executable/app/CPU+NVIDIA runtimes
  without models; retain the GPU bundle with Qwen, Whisper and Piper included.
- [x] Verify source, API, frontend, publishing and portable regression checks;
  deploy the compatible web/API release with an unchanged schema and backup.
- [x] Publish both verified ZIPs from existing VM assets and verify authenticated
  downloads, range/resume behavior and responsive rendered content.
- [x] Finish review evidence and prepare the authorized mapped GitHub publication.

## AI Evaluator public landing layout - 2026-10-08

- [x] Record the seven-section landing plan and independent CSS/layout specification.
- [x] Implement the public homepage, scoped light palette, responsive navigation,
  existing branding, ten content icons, FAQ and footer; preserve login and console
  access. Initial CSS illustrations reserved the image areas; final assets replace them.
- [x] Complete one review and fixes, frontend checks and mocked browser verification;
  see the review record. Correct decorative hero overflow on narrow screens.
- [x] Complete the subsequently authorized asset/content phases: two consistent Alex
  images, responsive WebP variants, actual fictional-data UI preview and final copy.
- [x] Wire approved company/email/origin, local privacy/terms pages and social metadata.
  Keep noindex by default with documented explicit opt-in.
- [x] Complete final review/fixes, 91 distinct affected frontend tests, typecheck,
  production build and browser review; see the completion review record.
- [x] Follow-up self-review: fix enlarged-text/header/grid overflow, clarify copy,
  verify 36 public-route reflow cases and short landscape menus, and inspect final render.
- [x] Deploy the reviewed landing page when requested: retain the previous managed
  release and private database backup; verify HTTPS/browser rendering, Login,
  readiness, protected access, unchanged configuration and six retained data tables.
- [x] GitHub publication authorized: review and commit all landing source, assets,
  tests and documentation, then use the mapped publishing helper.

## Hosted training configuration - 2026-10-05

- [x] Repair missing hosted training signing-key configuration and verify the public-key endpoint over HTTPS; preserve unrelated settings. See the review record. Authenticated session execution and device public-key trust remain unverified.

## Consolidated tenant scenarios and practice - 2026-10-03

- [x] Synchronize local database to the current migration head; verify ORM columns, grants, initializer/deploy scripts and update database runbooks.

- [x] Final integration review: published Practice through human-test, desktop recovery and optional patient fields, real API/PostgreSQL journeys, regression checks and evidence.

- [x] Usability follow-up: review language and save controls, published read view, Practice selection and validation, responsive browser checks, regression tests and final review.

- [x] Stage 1: forward tenant-scoped scenario metadata and defaults; preserve existing clinical and practice history; verify isolated PostgreSQL upgrade and grants.
- [x] Stage 2: one draft/review/publish lifecycle and direct published-scenario Practice selection with immutable session snapshots and device compatibility; test authorization, review separation, revisions and concurrency.
- [x] Stage 3: consolidate navigation, guided editor, reusable UI components and responsive styles; redirect old URLs, review and fix findings, run checks and record evidence.

## Manual tenant subscription management - 2026-09-24

- [x] Confirm tracking-only status/dates with no processing restriction or payment integration.
- [x] Add forward 0025 migration preserving existing assignments, with term constraints and database-managed versions.
- [x] Implement central manual edits, subscription directory/history and tenant read-only access.
- [x] Replace the license placeholder with plan editing, renewals, status controls, private notes and direct details.
- [x] Preserve server-side seat quotas, atomic audits, tenant boundaries and stale-edit guards.
- [x] Pass seven real local browser/API/PostgreSQL journeys and both forward/baseline-adoption upgrade checks.
- [x] Review twice; fix timestamp precision, invalid plan text and legacy-history display findings.
- [x] Finish final focused checks/build and record verification evidence.


## Web device and tenant association management - 2026-09-24

- [x] Confirm platform administrators control cross-tenant moves; tenant administrators manage their own tenant.
- [x] Add limited central registration, public edits, activation/deactivation, credential revoke and terminal removal APIs.
- [x] Make transfer atomic: preserve source ownership/history, revoke old credentials and require fresh destination enrollment.
- [x] Connect context/version-guarded web forms, confirmations, association details and current/retired filters.
- [x] Cover runtime-role authorization, quota rollback, conflicting transfers and unavailable assignments.
- [x] Exercise seven real local browser/API/PostgreSQL journeys including desktop/mobile views.
- [x] Complete final broader checks, second review and verification record.

## Web activity logs - 2026-09-24

- [x] Replace preview records with scoped platform audit and tenant activity APIs.
- [x] Add retained list/detail reads, metadata search, date/severity/actor/ID filters and cursor pagination.
- [x] Connect the web directory/details, permissions, refresh, deep links and recovery states.
- [x] Remove production fixtures; keep credentials, media and conversation payloads out of log projections.
- [x] Align the UI/API severity contract with persisted info/warning/error values.
- [x] Complete both reviews, final local browser/database checks and production build.

## Web user and member management - 2026-09-24

- [x] Replace mock platform users and tenant members with authenticated, persisted web CRUD.
- [x] Add invitations/acceptance, setup resend, role/department editing, archive/restore and activation controls.
- [x] Enforce tenant scope, version fences, accepted account lifecycle, quotas and existing administrator guards.
- [x] Remove obsolete preview components and replace mock-only tests with server-action/component regressions.
- [x] Review twice; fix identity, invitation, invalid-text, concurrency and misleading-preview findings.
- [x] Complete real browser/API/PostgreSQL journey, production build and verification record.
- [ ] Live SMTP/OIDC delivery remains deferred; local tests do not certify external services.

## Development snapshot - 2026-09-24

Current language/conversation implementation, model UI, input filtering and manikin
changes are included in the requested development publication. The phase checklist
below remains a qualification checklist: unfinished live answer-quality and isolated
database gates are not completed by committing this snapshot. Current verification
is recorded in [review evidence](pms-api-reviews.md).

## Input ignore dictionary - 2026-09-24

- [x] Editable per-language literal filler, acknowledgement and gratitude lists.
- [x] Whole-input filtering before local/cloud answer generation for text and ASR results.
- [x] No reply/TTS/history/archive for ignored input; preserve meaningful questions.
- [x] Reload edits on the next input; validate size/schema and report invalid files.
- [x] Two scoped reviews, regressions and package-data verification.
- [ ] Finish the separate broader English model-quality and architecture qualification.

## Pluggable conversation language architecture - 2026-09-24

- [x] Inspect existing language catalog, bilingual case fields, runtime prompts, speech selection, and history isolation.
- [x] Document the [architecture](language-conversation-architecture-plan.md) and [detailed phase plan](language-conversation-phased-implementation-plan.md), including dependencies, code/storage changes, tests, and exit gates.
- [ ] Phase 0: account for current work, reproduce the baseline, and freeze evaluation contracts/held-out fixtures.
- [ ] Phase 1: implement trusted language packs, shared types, English resources, and synthetic second-pack tests.
- [ ] Phase 2: implement generic localized case data, source/review invalidation, conversion, and database constraints.
- [ ] Phase 3: implement scoped conversation lifecycle, immutable context, bounded state/history, idempotency, and retention.
- [ ] Phase 4: implement the shared one-generation engine, factual precedence, exact prompt fitting, and failure handling.
- [ ] Phase 5: integrate desktop/platform capabilities, explicit language selection, history/outbox, and reset isolation.
- [ ] Phase 6: complete English recognition, pronunciation, synthesis, playback, and timing instrumentation.
- [ ] Phase 7: pass 45 live English questions, at least 216 broader turns, held-out scoring, speech checks, and latency qualification.
- [ ] Phase 8: fix review findings, pass required checks, activate the development install, and record final evidence.
- [ ] Phase 9 (later): qualify Hindi and each further language through packs, reviewed content, execution capabilities, and evaluations.

Planning only at this point. Prior single-call changes remain incomplete; this phase plan does not mark runtime work complete or resume its execution.

## Patient conversation replacement - 2026-09-24

Implementation has started but is incomplete. The revised language plan above takes precedence; runtime changes are paused for its review.


- [x] Inspect retained dialogue failures and measure a draft full-case prompt with the installed local tokenizer.
- [x] Document the selected one-generation design and direct development replacement in the [implementation plan](patient-conversation-implementation-plan.md).
- [ ] Build fictional regression fixtures, held-out dialogue cases, and a repeatable baseline/evaluation runner.
- [ ] Implement the shared permitted-case compiler, conversation prompt, and token-bounded recent history.
- [ ] Replace routing/review execution in both hosts; simplify configuration and one-call quota accounting.
- [ ] Align event schemas, history/outbox handling, and database checks with one-call patient conversation results.
- [ ] Pass runtime, isolated database, quality, naturalness, and latency checks; review the final changes.
- [ ] Update the development installation and record measured results. No production compatibility layer or backup prerequisite is planned.

## Login and account lifecycle review — 2026-09-23

- [x] Trace login, sessions, local/OIDC API, password/email actions and access boundaries; record [review findings](login-review-20260923.md).
- [x] Run focused UI/API checks and disposable PostgreSQL probes; distinguish broken fresh migration from supplemental runtime evidence.
- [x] L01/L02: reconcile the invalid baseline administrator seed and remove shared administrator credential provisioning.
- [x] L03/L04: prevent login rehash from overwriting password changes and stale email-change requests from surviving credential revocation; add concurrent regressions.
- [x] L05/L06: connect the web application to verified API sessions and current authorization; replace the unsigned demo identity boundary before loading real data.
- [x] L07/L08: implement setup/reset/email-confirmation pages and recover the login form after rejected requests.
- [x] Add browser-to-API login/recovery/logout coverage and committed refresh, lifecycle, purpose/reuse and concurrency regressions; review shared abuse controls.

- [x] Synchronize the configured local database, SQL scripts, migration head, models and runtime grants through 0022; verify private backup/restore and preservation of all 1,765 rows.
- [ ] Configure the web/API/SMTP account URLs; live SMTP, external SSO and hosted verification remain deferred. Rotate any administrator created from an earlier shared seed.
- [ ] Resolve the Windows reservation of the configured local database port 55444 before normal application startup; temporary maintenance used 56324 and left application settings unchanged.

## Live database, scripts and model synchronization - 2026-09-22

- [x] Inspect live database revisions and compare structural catalogs with migrations and ORM metadata.
- [x] Verify upgrades, runtime grants and focused regression coverage on a dedicated disposable PostgreSQL server; fix verifier, upgrade/restore assertions and local credential insertion order.
- [x] Back up and apply migration 0020 and current runtime grants to the idle configured local application database; verify all 1,866 existing records preserved.
- [x] Recheck live schema, model mappings, scripts and data preservation; follow-up on 2026-09-23 verifies migration 0022, 31 tables/545 columns, current grants and all 1,765 then-existing records.

## Tenant View back navigation - 2026-09-22

- [x] Add a visible top Back to tenants link with the shared left-chevron icon; retain the footer link and directory state.
- [x] Review mobile rendering and navigation: 11 focused app tests, app type checking and six browser checks passed, including exact scroll restoration and no runtime errors.

## Tenant View page - 2026-09-22

Scope: replace the View drawer with a dedicated, responsive tenant detail page; retain local Create/Edit data and list navigation without API integration.

- [x] Phase 1: inspect existing tenant data, forms, permissions and shared layout controls.
- [x] Phase 2: add guarded detail routing and a tenant-scoped in-memory workspace for list/detail navigation.
- [x] Phase 3: build the overview, contact and record cards; connect Edit, Copy ID and confirmed Delete.
- [x] Phase 4: reviewed navigation, permissions, empty/archived states and responsive themes; polished route-focus and wrapped actions. All 156 app tests, app type checking, production build, 40 browser checks in each mode, five additional production navigation checks and 15 direct-route checks passed. See the Tenant View review record.

## Tenant Create/Edit preview - 2026-09-22

Scope: build local-only Create/Edit flows using the existing drawer, field, confirmation and notification controls. Preserve list context; align fields with the API without calling it.

- [x] Phase 1: inspect API contracts and shared form/navigation controls; define field and lifecycle behavior.
- [x] Phase 2: implement grouped Create/Edit forms, validation, unsaved-change handling and accessible controls.
- [x] Phase 3: wire local saves, list feedback, permission/lifecycle checks and focus restoration.
- [x] Phase 4: reviewed and fixed premature validation on mount and contact-control alignment. All 138 app tests, app type checking, production build, 46 browser checks in each mode, 18 additional production layout/dismissal checks and five direct-route checks passed. See the Tenant Create/Edit review record.

## Settings hub - 2026-09-22

Scope: build the card-based Settings hub, move Models/Licenses/Administrators out of the platform rail, and move tenant-admin Models into tenant Settings. Reuse existing styles/icons and keep destination screens as previews without API integration.

- [x] Phase 1: inspect routes, role grants and shared cards; define one category catalogue for navigation and access checks.
- [x] Phase 2: build responsive, accessible Settings cards using shared theme tokens and icons.
- [x] Phase 3: update sidebar destinations, section highlighting, breadcrumbs and server route guards.
- [x] Phase 4: test permissions/navigation, inspect themes and responsive layouts, fix findings, and record review evidence. All 121 app tests, type checking, production build, 59 browser checks in each build mode and 20 direct-route checks passed. See the Settings hub review record.

- [x] Follow-up review: fixed the mobile drawer remaining over Settings after navigation; added five regression cases. All 1,699 UI tests, both workspace type checks, production build, 18 additional browser checks in each mode, 59 production layout/theme checks and 20 direct-route checks passed. See the follow-up review record.

## Tenant list preview - 2026-09-22

Scope: the existing Tenants navigation opens `/tenants`; use fictional records and shared UI styles. No API calls. Create/Edit remain demo entry points in this list-only phase.

- [x] Phase 1: inspect tenant API fields, permissions, lifecycle and reusable UI contracts; agree the list design.
- [x] Phase 2: add deterministic fictional tenants and API-aligned search, filters, sort and paging.
- [x] Phase 3: replace the placeholder with the shared table, controls, badges, icons and responsive layout. Search/Status/Records/Sort share one desktop row; count and pagination sit below the table.
- [x] Phase 4: wire View preview, Edit/Create notices, confirmed local archive, Copy ID and permission gates.
- [x] Phase 5: test interactions and edge cases, review desktop/narrow and light/dark rendering, fix findings, and record evidence. Fixed saved-theme/toast hydration, extra document/table scrollbars, compact footer spacing and production CSS precedence. All 1,664 UI tests, workspace type checks, production build and local browser checks passed; see the [review record](pms-api-reviews.md#tenant-list-preview-and-console-rendering-fixes---2026-09-22).

## API management completion plan - 2026-09-22

API-only implementation completed; no UI work is part of this change. See the [phase plan and acceptance criteria](pms-api-management-plan.md) and [review evidence](pms-api-reviews.md#pms-management-api-phases-1-7--2026-09-22).

Confirmed identity direction: external OIDC users manage passwords at their provider; platform-created local users receive PMS login, setup/change/recovery/reset, and session APIs. Local passwords will use salted one-way hashes. This extends the earlier OIDC-only design; existing external accounts and clients remain supported.

- [x] Inspect current routes/schema and document the gaps, phase order, compatibility rules, and verification gates.
- [x] Expand the plan into work packages, target endpoint coverage, per-resource list fields, schema sequencing, and completion records; the implementation now follows those contracts.
- [x] Consolidate all seven phases, including the expanded multi-model/provider scope, into the primary plan with shared contracts, dependencies, migration groups, and completion gates.
- [x] Phase 1: endpoint/permission contracts, compatible identity schema, shared pagination/filter/sort/search.
- [x] Phase 2: local authentication/password/session APIs alongside existing OIDC and device authentication.
- [x] Phase 3: complete user and membership management, including local account setup and explicit archive behavior.
- [x] Phase 4: complete organization/department lifecycle, administrator onboarding, and subscription boundaries.
- [x] Phase 5: complete device management contracts, lifecycle, and collection queries.
- [x] Phase 6: [multiple model types/providers](pms-api-model-management-plan.md), tenant connections/bindings, typed capability validation, profiles, and consistent administrative lists; deliver steps 6.1-6.8.
- [x] Phase 7: local automated verification, grants/package checks, implementation reviews, fixes, and documentation. The final review aligned local-account setup with database administrator-availability guards and narrowed credential-table privileges. Disposable PostgreSQL integration tests were skipped because `PMS_TEST_ADMIN_DSN` was not set; live services and hardware remain deferred.

## AI Evaluator console shell and dashboards — 2026-09-22

Presentation only, by request: no API binding in this phase. Roles and permission keys come from the real catalogue in [`platform/db/sql/006_role_catalog.sql`](../platform/db/sql/006_role_catalog.sql); the UI says "tenant" where the schema says "organization", mapped in one module. The hardcoded sign-in is shaped like the local session API planned in [the management plan](pms-api-management-plan.md#phase-2), so wiring it later replaces one server action.

- [x] Phase 1 — demo session: three hardcoded accounts (platform admin, tenant admin, tenant user), server-action credential check, httpOnly id-only cookie, guarded `(console)` route group, `PermissionProvider` seeded from the role's catalogue keys, working sign-out. "Keep me signed in" chooses between an eight-hour and a thirty-day cookie.
- [x] Phase 2 — six product icons the design system does not ship: tenant, device, model, pulse, licence, session — drawn to the package's 24px/1.8-stroke/`currentColor` convention.
- [x] Phase 3 — console shell: `AppShell` + `Rail` (brand, tenant switcher, Overview, the role's sections, Settings, pinned sign-out) and `TopBar` (tenant chip, role chip, demo badge, theme switcher, notification bell, account menu showing name/email/role with change password and sign-out), plus the change-password dialog. Added an optional `email` to the package's `UserMenu` and an optional `as` to `RailItem`.
- [x] Phase 4 — dashboards: four stat cards per role from one static data module, plus a split band (devices-by-tenant chart, device-health meters, recent activity, start-a-session).
- [x] Phase 5 — role matrices: one permission-keyed navigation table filtered by `useGranted()`, a dashboard per role, and twelve placeholder pages so no menu item 404s.
- [x] Phase 6 — responsive/theme/keyboard pass, screenshots per role in light and dark, documentation, review and fixes. See [review evidence](pms-api-reviews.md#ai-evaluator-console-shell-and-dashboards--2026-09-22).
- [ ] Deferred: real authentication, the management screens themselves (tenants, devices, models, logs, settings), and any API call.
- [ ] Deferred: persisting the rail's collapsed state, which needs the same pre-paint treatment as the theme, and a real notification feed behind the bell.

## AI Evaluator login page — 2026-09-21

Presentation only, by request: no API binding in this task.

- [x] Add `platform/ui/apps/web` (`@pms/web`, Next.js 15 App Router, React 19) to the existing `platform/ui` npm workspace; `transpilePackages: ['@pms/ui']` because the package ships TypeScript source.
- [x] Build `/login` and `/forgot-password` on a shared `(auth)` split-screen layout: brand panel plus form column, with the root layout importing `@pms/ui/styles.css` once and running `themeScript` before first paint.
- [x] Reuse `EmailField`, `PasswordField`, `Checkbox`, `Button`, `Notice`, `Badge`, `ThemeSwitcher` and the package tokens; add only the product identity (`brand.css`) and the split-screen (`auth.css`), which `shell.css` states belong to the consuming app.
- [x] Create the AI Evaluator mark, wordmark and favicon — a tick with a spark, on a tile painted by `--pms-grad-action` so the logo is identical in all three palettes.
- [x] Keep sign-in unbound and say so on screen: local validation only, a simulated pending state, and a notice that no server was reached. No token, session or storage write.
- [x] Add 24 app tests, including a stylesheet guard that forbids colour literals and `z-index` in the app CSS and rejects any class the app emits but nothing styles.
- [x] Verify: 1565 package tests and 24 app tests pass, both workspaces typecheck, `next build` succeeds, and all four routes answer. Screens captured at 1440/760/390 and in the dark palette. See [review evidence](pms-api-reviews.md#ai-evaluator-login-page--2026-09-21).
- [ ] Bind sign-in to the identity provider: replace `onSubmit` with the OIDC redirect, add the callback route and server-side session handling, then re-review. The API has no password endpoint by design.
- [ ] Decide whether Google and Microsoft are real providers for this deployment; today both buttons state that they are not configured.
- [ ] Add the authenticated console shell (`AppShell`) and make `/` choose between it and `/login` on a real session check.

## Authorized live audio baseline - 2026-09-20

- [x] Add a reusable 25-question audio suite, inputs, batch entry point, offline checks and timestamped evidence under [docs/simulations/alex-cardiology](simulations/alex-cardiology/README.md).
- [x] Complete one uninterrupted live online attempt of all 25 questions: 5 correct answers, 13 LLM daily-limit failures, 6 speech retry exhaustions and 1 readiness failure; 60 speech retries, 18 correct transcripts.
- [x] Review the evidence and verify five offline grading tests, lint/format, batch help and native window capture. See [findings](simulations/alex-cardiology/findings-2026-09-20.md).
- [ ] Review quota/reservation accounting and actionable daily-capacity feedback; no capacity changes were made in this baseline.
- [ ] Review Azure speech rate/capacity handling and the shared `llm_busy` error label; retain upstream retry metadata without secrets.
- [ ] Isolate intermittent readiness failure and rerun full answer correctness after capacity is available.


## Desktop camera preview and dated local video — 2026-09-20

- [x] Add an explicit camera checkbox, preview, camera index and visible local save path; stop/finalize on uncheck, new conversation, patient setup and close.
- [x] Save private, bounded video in year/month/day/time session folders, with exclusive recording ownership, one-minute segments, quota/free-space/duration limits and completion receipts.
- [x] Prioritize conversation responsiveness with a low-priority process, one encoding thread, 10 FPS capture ceiling and a bounded latest-frame 5 FPS preview; verify generated-frame playback and native Tk lifecycle.
- [x] Measure synthetic recording overhead with resident local speech synthesis; document actual evidence and limits in [desktop video review](desktop-video-review.md).
- [ ] Verify physical webcam performance alongside the selected ASR/LLM and speech playback on the laptop.
- [ ] Connect the existing Pi training stream to the desktop preview/date-organized recorder, preserving compressed frames for saving; verify Pi camera/Wi-Fi/TLS on hardware when requested.

## One-click local stack launcher (2026-09-19)

Robustness follow-up:

- [x] GPU-first audio correction: automatic compatible CUDA detection, CPU fallback, matching desktop/readiness configuration, shared GPU memory budget, regressions and native full-stack verification. 47 launcher + 163 audio + 20 desktop + 33 local-LLM tests passed. Actual CUDA ASR finalization was 1.047/0.890 seconds on the existing English fixture; full batch `--check` passed. See [GPU audit](start-launcher-audit.md#automatic-gpu-selection-correction).
- [x] Increase owned-service startup budgets to five attempts with 1/2/4/8-second backoff; verify fifth-attempt success, exhaustion, cleanup and duplicate-launch wait coverage. Follow-up: 32 launcher tests, 20 desktop tests and static checks passed.
- [x] Diagnose the reported interrupted launch and print the batch exit code with interruption guidance.
- [x] Add bounded service retries, confirmed owned-process cleanup, ongoing health monitoring and recovery budgets.
- [x] Add private rotating operational logs and safe categorized child diagnostics.
- [x] Verify real owned-service crash recovery, finish final review and record evidence.

Recovery verification: 29 launcher/supervisor tests and 20 desktop tests passed. A deliberately terminated owned audio process recovered in 28.618 seconds while Qwen/PMS/video/PostgreSQL PIDs stayed unchanged; a subsequent real patient request succeeded. Logs were checked for credential/content leakage and private Windows ACLs. See the robustness follow-up in [launcher audit](start-launcher-audit.md).

- [x] Add `start/start-human-test.bat` using the shared demo lifecycle, clear messages and verified service reuse.
- [x] Include the video recording API, duplicate-launch locking and owned-process cleanup.
- [x] Test actual batch cold startup, repeated launch, compatible model reuse, conflicting service rejection and GUI lifecycle.
- [x] Review twice, fix findings and record final audit evidence.

Verified: 15 launcher tests, 20 desktop tests, Ruff/format and PMS mypy; native batch cold check, concurrent/repeated launches with unchanged listener PIDs, one GUI window, real PMS/Qwen patient answer, conflict rejection and cleanup preserving independently started Qwen. Final test-owned listeners were closed. See [launcher audit](start-launcher-audit.md).

## Previous implementation

Status: subscription extension implemented, reviewed and locally verified; previous implementation/reviews remain complete. The standalone local laptop audio receiver is implemented separately; Pi hardware and PMS integration remain future work below. Live external verification remains deferred by the user.

- [x] Phase 1: architecture, contracts and package structure
- [x] Phase 2: runtime, configuration, health, errors and logging
- [x] Phase 3: SQLAlchemy models, Alembic baseline and verified adoption
- [x] Phase 4: OIDC/device authentication and six-role authorization
- [x] Phase 5: strict API contracts, pagination and transaction/error conventions
- [x] Phase 6: platform administration and atomic audit
- [x] Phase 7: organizations, departments, memberships and invitations
- [x] Phase 8: device enrollment, credentials, heartbeat, telemetry and events
- [x] Phase 9: connections, secrets, validation, profiles and effective configuration
- [x] Phase 10: idempotent runs, quotas, media and playback contracts
- [x] Phase 11: durable worker, AWS/Azure adapters, reconciliation and retention
- [x] Phase 12: deployment, local tooling, operational documentation and CI
- [x] Review 1: correctness/security review, findings, fixes and regression tests
- [x] Review 2: independent second pass over final implementation, fixes and verification
- [x] Additional requested review: fixed retention progress, profile capture enforcement and AWS transport retries; verified enrollment lifecycle and broadened package checks

- [x] Database/API end-to-end review: schema migrations and grants, lifecycle/queue boundaries, provider preflight, fixes and complete verification.

- [x] Subscription plans: schema/backfill, mandatory organization selection, editable catalog, capacity limits, review and verification.

## Confirmed scope update

User requested encrypted provider credentials in PostgreSQL. Add a reviewed Alembic migration and authenticated encryption; encryption keys remain deployment configuration outside the database. All live external integration/testing is deferred by the user.

## Pi input/output and laptop transcription follow-up

Confirmed on 2026-09-17, followed by the user's request to implement a standalone audio API, reuse its model across calls, and save audio/text without waiting for disk on the transcription path. See the [execution plan](platform-service-plan.md#71-how-the-raspberry-pi-will-work).

- [x] Record Pi microphone/camera input and speaker/video-display output in both modes; local OSS transcription executes on the connected laptop; cloud requests go directly from Pi to platform API and server-side provider workers.
- [x] Record local Wi-Fi as preferred transport, Windows/16 GB RAM/CPU laptop target, configurable OSS model choice and Hindi/English requirements. Whisper `large-v3` INT8 is a candidate pending benchmarks; mixed-language accuracy and live latency are not verified.
- [x] Implement the standalone laptop audio API in `device/audio-process`: authenticated bounded PCM streams, one startup-loaded/warmed CPU INT8 model, configurable multilingual Whisper choices, responsive async reception, queue limits and cancellation-safe serialized inference.
- [x] Print text to the laptop console and return stream events; keep the optional fixed POST receiver disabled. No PMS API, database or cloud-provider integration exists in this service.
- [x] Implement private background WAV/UTF-8 transcript storage, bounded byte/event queues and pending sessions, 1 GB/1,000-session/seven-day limits, owner-scoped recording status, incomplete-file recovery and bounded storage lifecycle waits. Keep ASR responsive under disk overload/failure.
- [x] Cover model reuse, Unicode text, invalid input, authorization, native-call cancellation, bounded queues, callback failure/no-retry behavior and real loopback HTTP/WebSocket transport with tests.
- [x] Verify recording with the installed large model: one load across four off/on/on/off streams, exact stored audio/text, and separate saved receipts. Completion averaged 51.51 seconds off versus 52.40 seconds on for an 8.55-second English clip; this small sample does not establish zero overhead or real-time performance.
- [x] Add bounded retries for safe local file operations and pre-submission callback failures, preserve exact data across partial writes, keep independent audio/text fallback within existing quotas, and expose finalization/completeness and retry counters. Regression-test duplicate prevention, permanent errors, fallback recovery and total delivery deadlines; perform a final correctness/security review.
- [ ] Connect the standalone receiver to the Pi's authorized platform workflow when requested. Preserve tenant/device/configuration binding, lifecycle/offline expiry, retention and disconnect handling; local tokens and stream IDs are not platform identities. No implicit cloud fallback.
- [ ] Extend the validated engine/model registry, profile/capability contracts and configuration acknowledgments for laptop transcription; keep unsupported models disabled and preserve device-seat semantics.
- [ ] Implement Pi microphone/camera capture and speaker/display output adapters, including the video-display delivery/control contract and output acknowledgments. Keep video analysis and synthesis independently configurable.
- [x] Provision/checksum-verify official `large-v3`, convert CPU INT8 locally, and verify real English streaming/console output with one load per process. Four/eight-thread trials on this 64 GB host are recorded in review evidence; they are not real-time and do not establish 16 GB or Hindi/mixed-speech suitability.
- [ ] Benchmark candidate OSS models on the actual laptop CPU using Hindi, English and mixed recordings; measure accuracy, response delay, memory and sustained processing throughput.
- [ ] Verify Pi local/cloud routing, Wi-Fi reconnects and concurrent audio/video input/output on hardware when requested. Verify cloud mode works without the laptop using mocked providers first; live cloud verification remains separately deferred.

## External verification

- [ ] Live OIDC: issuer/audience and identity-provider configuration required; deferred by user.
- [ ] Live AWS: approved identity, region and staging bucket required; deferred by user.
- [ ] Live Azure: Speech/Video Indexer resources and approved identity required; deferred by user.
- [ ] Hosted deployment: target hosting configuration required; deferred by user.

External checks are tracked separately from executable implementation and local tests.

Device language update: optional preference; English fallback and seeded Hindi; extensible platform catalog implemented and covered by PostgreSQL/API tests.

## Verification at migration 0005 (prior run)

- 37 tests passed against PostgreSQL 17 with mocked external providers, including subscription registration, prices, authorization, invitation reservations, reactivation/admin assignments, upgrades/downgrades, concurrent direct SQL and exact price audit history.
- The review fixed deferred-trigger ordering during existing-organization backfill. Three follow-up checks passed before the full suite; the concurrency check observes an actual lock wait while the last device slot is uncommitted.
- Unprivileged baseline adoption/migrations preserve an existing organization above the initial cap, then prevent further capacity increases. Schema mappings match 13 domain tables and 241 columns.
- Current-head backup/restore followed by API readiness/authorized reads passed, preserving encrypted credentials and Hindi preference. The frozen SQL baseline remains unchanged.
- Ruff lint/format passed for all 53 package Python files; mypy passed for 36 source files; dependency lock check passed.
- Source distribution and wheel builds passed. Packaged migration 0005, role catalog, baseline signature, exact reviewed implementation and self-contained atomic runtime grants were verified.
- Real Windows HTTP startup/readiness/authentication and processing/retention worker CLI checks passed at schema head 0005.
- Disposable test databases/roles were removed, and the dedicated local PostgreSQL instance was stopped.
- Docker/CI execution, live OIDC/AWS/Azure, hosted deployment and Raspberry Pi hardware remain outside the verified local scope.

## Confirmed plan limits and repository instructions

- Confirmed configurable defaults: Standard 200 users/1 device; Advanced 500 users/3 devices. Prices are INR 350,000/500,000; billing period is unspecified pending confirmation. The platform supports explicitly configured USD prices without conversion or payment processing.

- [x] Add concise root AGENTS.md covering security, review, meaningful tests and project conventions.
- [x] Add forward migration 0006 for confirmed limits, preserving customized plans and existing records; align API readiness and documentation.
- [x] Verify fresh plan boundaries and existing-database upgrades on isolated PostgreSQL: 7 focused tests passed.
- [x] Complete two review passes; no outstanding findings. Ruff lint/format, mypy, source/wheel builds and packaged migration/readiness checks passed.


## Separate local video recording API

Confirmed 2026-09-17: `device/video-process` receives and saves video only. No detection or live image analysis; image extraction belongs in an offline batch path.

- [x] Implement separate authenticated bounded WebSocket receiver, owner-scoped save receipts and independent port/configuration.
- [x] Preserve compressed JPEGs in playable video segments, using a bounded background writer, safe retries, quotas, private storage and incomplete-session recovery.
- [x] Add separate offline JPEG extraction with hashes, output limits and an exclusive store lock; keep it outside live recording.
- [x] Document the protocol, local/cloud boundaries, operating limits and deferred Pi/platform integration.
- [x] Complete final correctness/security review, native transport verification and package checks: 56 tests passed with no skips; Ruff, mypy, lock/build and archive-content checks passed. See review evidence dated 2026-09-18.
- [ ] Implement and verify Pi camera capture and Wi-Fi/TLS transport on hardware when requested.
- [ ] Benchmark actual camera traffic with concurrent audio transcription on the intended 16 GB laptop.
- [ ] Add another stream codec/transport or scheduled bulk processing only when requested.


## Local TCP transport assessment (2026-09-18)

- [x] Review existing media transports and primary protocol documentation: WebSocket already provides TCP; retain separate TLS-protected audio/video connections without adding a redundant raw TCP API.
- [x] Remove the video sender's one-frame-at-a-time reply wait using a bounded concurrent window; add strict acknowledgment/completion checks, deadlines, lag limits and direct connections without environment proxies.
- [x] Compare one/four outstanding frames with actual local recording and ordered simulated receipt delay; preserve all stored frame bytes. Record limitations and reconnect semantics.
- [x] Complete final sender regressions, full video checks, package verification and review evidence: 81 tests passed with no skips; Ruff, mypy, lock/build and archive-content checks passed.
- [ ] Evaluate real Pi/Wi-Fi/TLS and concurrent audio/video behavior on the target laptop when requested; any future durable spool/resume needs a separate idempotent application design.


## Combined audio/video final review (2026-09-18)

- [x] Inspect both complete implementations, security/lifecycle boundaries, native work, senders, recording/recovery and compatibility; baseline suites passed (audio 89, video 81).
- [x] Fix confirmed audio native lifecycle/console blocking, initial credential file permissions, abandoned initial recording recovery and sender completion handling; add targeted regressions.
- [x] Fix video capacity cleanup after final-reply cancellation and bound audio/video opening and closing handshakes; add targeted regressions.
- [x] Run final checks, local native-model verification, package inspection and the second review: audio 104 tests, video 84 tests, no skips; Ruff, mypy, locks, builds and archive checks passed. Record findings and remaining hardware/performance limits in review evidence.


## Patient interview pilot implementation (2026-09-18)

Authorized: implement the nine agreed phases, continue through two final reviews. Reuse the existing media APIs; no live video analysis, cloud fallback, custom model training or broad course-management scope.

- [x] Phase 1: pilot contracts, fictional bilingual scenario, educator approval boundary, session lifecycle and acceptance criteria.
- [x] Phase 2: provision and measure local dialogue/TTS options; record ASR and whole-pipeline latency, memory and target-hardware limits.
- [x] Phase 3: forward training migration, grants/readiness, scenario/session/feedback endpoints, scoped authorization and isolated PostgreSQL tests.
- [x] Phase 4: bounded laptop training coordinator, local dialogue/TTS adapters, patient consistency, turn/playback lifecycle and cancellation.
- [x] Phase 5: Pi microphone/camera/speaker agent, WSS media integration, self-check, fixture mode, failure handling and explicit playback acknowledgments.
- [x] Phase 6: private synchronized artifacts, minimal instructor UI, replay and manual rubric/feedback.
- [x] Phase 7: integration/fault tests, runnable setup, dependency/package checks and evidence; separate simulated, native, hardware and educator validation.
- [x] Phase 8: correctness/security review; fix findings and rerun affected checks.
- [x] Phase 9: fresh final review, complete checks, consistent documentation and final limitations.

External acceptance remains explicit: actual Pi/camera/microphone/speaker access, actual 16 GB CPU measurements, and clinical educator approval cannot be claimed from local mocks or synthetic cases. The supplied sample is development-only until reviewed by an authorized educator.

### Pilot implementation verification

- Native feasibility: actual Qwen/eSpeak text-input check 10/10; synthetic ASR/dialogue/TTS 3/4, 3.7-5.9 seconds. Cold service warmup exceeded 30 seconds on a later check; a warm authenticated repeat passed. The latency/accuracy gate is **not met**.
- Real loopback fixture: Pi client -> coordinator -> audio protocol double + actual video API/store -> simulated platform receipt; private artifacts and bulk replay verified. Fixture playback is explicitly simulated.
- Automated regressions: platform 45, audio 104, video 85, training 12 passed (246 total), with no skips. Chrome page-load/clear-access smoke check and package inspection passed. Full instructor/OIDC acceptance remains external.
- Packaging excludes secrets, private media and weights. The shared contract wheel must accompany the platform/training wheels.
- [ ] External acceptance: actual Pi/camera/microphone/speaker, Wi-Fi/TLS installation, human Hindi/English/mixed-language accuracy, acoustic timing, full instructor workflow with deployed identity, target 16 GB RAM/CPU, educator approval.
- [ ] Docker image build/run (Docker is unavailable here); live cloud services and hosted deployment remain deferred.

## Patient Scenario Library feature baseline (2026-09-18)

- [x] Record the agreed manikin-as-patient concept, terminology, feature list, component ownership, physical capability limits, and future priorities in [Patient Scenario Library](patient-scenario-library.md); link it from the pilot and service plan.
- [x] Prepare the [practical phase-wise plan](patient-scenario-implementation-plan.md) against existing scenario/session contracts: structured data, approved answers, authoring/versioning, assignment/readiness, interview/review controls, verification, and two final reviews. Fixed vitals are the first delivery; live state changes are deferred. No implementation phase is complete merely because the plan is recorded.
- [ ] Design generated answering, dynamic physiology, physical effects, and assisted assessment in later increments; retain existing hardware, language, performance, and educator acceptance gates.

### Patient Scenario Library next implementation

- [x] Phase 1: platform/shared scenario contract, disclosure projections, and version-1 compatibility under the revised API scope; extended runtime remains Phase 4.
- [x] Phase 2: scoped drafts, atomic approved publication, library API, migration/grants, and PostgreSQL tests.
- [x] Phase 3: instructor authoring, preview, copy, approval, and retirement UI.
- [ ] Phase 4: extended cases with existing approved-answer selection, deterministic rendering, and session isolation.
- [x] Phase 5: load/readiness/version checks and explicit authorized Start.
- [x] Phase 6: fixed-state interview controls, case snapshot, media review, and manual feedback.
- [x] Phase 7: combined workflow/failure tests and language/performance evidence.
- [ ] Phase 8: first final review, fixes, and affected regressions.
- [ ] Phase 9: fresh final review, final checks, runbooks, and acceptance report.
- [ ] External acceptance: actual Pi/Wi-Fi/16 GB laptop, human speech, identity workflow, and educator approval; separate from software completion.


## Patient Scenario Library: database-only delivery (2026-09-18)

Historical database-only scope: migration, deployment/verification scripts, database mappings/readiness compatibility, tests, review, and fixes. The subsequent authorized API/shared-contract delivery is tracked below; UI and version-2 runtime remain separate.

- [x] Add forward migration 0008 for bounded private drafts and immutable publication provenance; preserve all existing cases/sessions and the frozen baseline.
- [x] Align database mappings, readiness revision, least-privilege grants, and a read-only installation verifier.
- [x] Verify fresh install, 0007 upgrade with retained data, real concurrency, malformed data, permissions, and populated backup/restore on disposable PostgreSQL.
- [x] Complete database review 1, fix findings, and rerun affected checks.
- [x] Complete database review 2 and final checks; record evidence and hand over for API authorization.

Verification: 55 platform tests passed with no skips; both reproduced review regressions passed after fixes. Ruff, format, mypy, lock/build and final package inspection passed. The dedicated test cluster was stopped and application databases were untouched. This was the database-only handover; the subsequent API/shared-contract delivery is tracked below. UI and version-2 runtime remain pending.


## Patient Scenario Library: revised API plan (2026-09-18)

- [x] Prepare revision 2 of the [API-only plan](patient-scenario-api-plan.md): early compatibility/security checks, concrete request/retry contracts, phase deliverables, tests, and completion gates. Database and API implementation are complete; final delivery verification is recorded below.
- [x] API-1: shared contracts, permissions, and safe response models.
- [x] API-2: safe listing/detail, pagination/filtering, and early rejection of unsupported version-2 sessions.
- [x] API-3: draft create/copy/read/save/archive/restore with revision/audit guarantees.
- [x] API-4: complete-case validation and explicit-revision patient preview.
- [x] API-5: atomic publication, complete idempotency handling, and retirement.
- [x] API-6: complete workflows, security/concurrency/fault tests, package checks, and client examples.
- [x] API-7: first API review, fixes, and affected checks.
- [x] API-8: fresh final review and API delivery evidence; UI/runtime remain separate.

Final verification: 105 platform tests passed with no skips, plus 12 companion tests. Platform/shared Ruff and format checks, mypy (39 source files), and consumer dependency-lock checks passed. Both reviews reproduced and fixed four findings in total; review regressions are included in the final count. API/shared wheel and source builds passed; archive inspection verified the final code, migrations, tests, runbook and Hindi/English examples. No private environment/key files were included. The disposable server had zero remaining test databases/roles and was stopped. No application database migration, live provider call, or Pi hardware verification was performed.


## Patient Scenario Library: planned-versus-implemented audit (2026-09-18)

See the [audit report](patient-scenario-api-audit.md). The API feature checklist above records implemented deliverables and the two completed reviews. The initial audit qualified acceptance coverage with two follow-ups, now closed below; the original unqualified all-phases-complete statement preceded that verification.

- [x] Compare revision-2 API requirements with source, test cases and recorded delivery evidence; verify all four package hashes and 111 Python source comparisons against current files.
- [x] A-01 (API-5 verification): four coordinated overlap tests now cover retirement versus device/control validation and subsequent renewal rejection.
- [x] A-02 (API-6 verification): complete authenticated kidney lifecycle now covers edit/preview/publication, bilingual snapshot, safe/private retrieval and retirement.

No functional defect was established by these two coverage observations. The initial audit changed documentation only; follow-up closure ran the full platform suite (110 passed, no skips). Version-2 UI/runtime, live services, hardware, performance and clinical acceptance remain outside the delivered API scope.

## Audio implementation and latency deep review (2026-09-18)

- [x] Close API audit acceptance items A-01/A-02 with isolated PostgreSQL tests (110 passed, no skips).
- [x] Review capture, WebSocket/TCP transport, segmentation, resident inference, recording/callbacks, training response and playback.
- [x] Reproduce and fix confirmed correctness/latency findings with regression coverage.
- [x] Measure feasible local latency and document hardware/model limitations.
- [x] Run relevant checks, complete a fresh final review and record evidence.

A-01/A-02 were closed on 2026-09-19; see the appended [audit closure](patient-scenario-api-audit.md#audit-follow-up-closure-2026-09-19). The original observations above are historical.

Audio review completed 2026-09-19: [findings and measurements](audio-latency-review.md). Nine findings fixed; 106 audio and 21 training tests passed, in addition to 110 platform tests. Ruff/format/mypy, lock checks and six package archives passed (215 source comparisons). Two native models each loaded once across eight paced synthetic loopback streams. Interactive latency/accuracy acceptance remains open; Pi, Wi-Fi and the target 16 GB machine were not tested. The isolated PostgreSQL server was cleaned and stopped.

## Whisper turbo/medium practical comparison (2026-09-19)

- [x] Download and verify local multilingual turbo/medium assets without changing service defaults.
- [x] Prepare shared Hindi/English reference clips and explicit quality scoring.
- [x] Benchmark current CPU INT8 service using small, medium, turbo and large-v3 with one resident model at a time.
- [x] Review raw transcripts, failure cases, latency and memory; document a practical recommendation and evidence limits. See [comparison](whisper-model-comparison.md): 92 whole-clip checks, 16 API streams and 16 exact recording/transcript matches.

Future acceptance, outside the completed model comparison:

- [ ] Validate natural interview Hindi/English/Hinglish and utterance-boundary sensitivity on the actual microphone/Pi and 16 GB laptop, with video recording active; measure complete audible-response latency before accepting a live model profile.

## Three-audio demonstration per model (2026-09-19)

- [x] Run the same three audio clips sequentially through each installed model and retain fresh timings/transcripts.
- [x] Provide playable input audio, per-test reference/transcript/quality comparison and final integrity review. See [three-audio results](whisper-three-audio-tests.md): 12 final API tests, exact recordings, three embedded WAV players.

## Selectable Nemotron CPU streaming (2026-09-19)

- [x] Download and checksum the multilingual 560 ms INT8 model; preserve installed Whisper assets.
- [x] Add model-based engine selection, resident model reuse and isolated incremental stream state.
- [x] Preserve protocol, recording, callbacks, authentication, bounded queues and cancellation behavior.
- [x] Test Hindi/English audio through the real API; document selection and measured limitations.
- [x] Review, fix findings, run relevant checks and complete a second review.

Completed: [Nemotron integration, measurements and reviews](nemotron-integration.md). 124 audio + 21 training + 42 platform tests passed; 68 database integration tests skipped (no disposable DSN). Seven real Nemotron streams and one Whisper compatibility stream had exact recordings. Existing model selection remains operator-controlled.

## Optional Whisper GPU execution (2026-09-19)

- [x] Add an explicit GPU on/off flag, retain CPU defaults and expose the execution device.
- [x] Install project-local CUDA libraries and verify Whisper Large-v3 GPU startup without CPU fallback.
- [x] Run the same three audio clips with GPU telemetry and exact recording checks.
- [x] Review, fix findings, run regression/static/package checks and document actual results.

Completed: [GPU configuration and measured results](whisper-gpu-validation.md). Native CUDA execution verified, 3/3 exact recordings, 135 audio and 21 training tests passed. CPU default and operator model selection remain preserved.

## Vosk CPU evaluation and GPU capability check (2026-09-19)

- [x] Verify the installed Vosk GPU API and local build prerequisites; report genuine support.
- [x] Add optional Vosk selection with persistent models, language validation and bounded streaming.
- [ ] Deferred by user: download small English/Hindi models and compare reference audio with exact recordings. Original host/direct Hugging Face mirrors were blocked; the additional Hugging Face client attempt also failed.
- [x] Run regression/static/package checks, review findings, fix and review the final result.

See [Vosk status](vosk-validation.md): 152 audio + 21 training tests passed. CPU recognition/quality/latency remains unmeasured; installed Windows Vosk has no working CUDA decoder.

## Standalone local Qwen3 4B inference (2026-09-19)

- [x] Download and verify pinned Qwen3 4B Q4_K_M and Windows llama.cpp CUDA assets.
- [x] Create isolated local-llm setup/configuration and double-click batch launcher.
- [x] Run native English/Hindi inference, verify GPU execution, startup/shutdown and model reuse.
- [x] Review, fix findings, run relevant checks and record final evidence.

Local LLM complete: [launcher and instructions](../local-models/README.md), [native results and final review](../local-models/validation.md). Qwen3 4B Q4_K_M installed and checksum-verified, 37/37 layers on GPU, explicit CPU mode verified, 14 unit/regression tests passed. Actual start-llm.bat and chat.bat inference passed; native processes released after normal and abrupt launcher exit.


## Local LLM follow-up review (2026-09-19)

- [x] Review local setup, credential creation, configuration, streaming and process ownership; fix confirmed failures.
- [x] Add failure-path regressions and run relevant tests/static checks.
- [x] Rerun native GPU/CPU, API authentication, batch entry points and process cleanup.
- [x] Perform a final review after fixes and record evidence and limits.

Completed: [follow-up review](../local-models/review.md). 25 tests/static checks passed; native full GPU (37/37), partial GPU (17/37), CPU, all batch entry points, authentication, resident model reuse and cleanup passed. Repaired legacy public-runtime permissions and verified private credential ACLs plus launchers under the interactive Windows account.


## Human microphone test through PMS LLM (2026-09-19)

- [x] Phase 1: LLM connection/request storage, migration, permissions, limits and encrypted credentials.
- [x] Phase 2: asynchronous complete/stream client, cancellation and bounded transport.
- [x] Phase 3: authenticated PMS routes, idempotency and backend checks.
- [x] Phase 4: human-test desktop screen, microphone and turn assembly.
- [x] Phase 5: launch/setup, native integration and latency measurements.
- [x] Phase 6: first review, confirmed fixes and regressions.
- [x] Phase 7: final review, required checks and completion evidence.

Completed: [desktop launch instructions](../human-test/README.md), [planned-versus-implemented report and two reviews](../human-test/validation.md), [PMS LLM API](../platform/api/deploy/local-llm.md). **436 tests passed** across PMS (141, zero skipped), human-test (12), audio (152), video (85), training (21) and local-llm (25). Native English/Hindi, multi-chunk, silence, JSON/SSE cancellation, GUI and batch checks passed. All owned services were stopped. Actual human-spoken answer acceptance, clinical grounding and Pi/cloud hardware work remain separate.

## OpenAI and compatible LLM follow-up (2026-09-19)

- [x] Phase 1: forward migration and explicit provider configuration, retaining local Qwen defaults.
- [x] Phase 2: guarded remote transport, provider-specific JSON/SSE payloads and usage parsing.
- [x] Phase 3: credential, token expiry, quota, provider and upgrade regression checks.
- [x] Phase 4: native local compatibility check and deployment documentation.
- [x] Review 1: inspect authorization, endpoint security, token accounting and cancellation; fix findings.
- [x] Review 2: rerun affected/full checks and record actual evidence and limitations.

Completed provider follow-up: **207 PMS tests, zero skips**, including isolated PostgreSQL and real Qwen JSON/SSE; **14 desktop tests**. Ruff, formatting, mypy and both package builds passed. Both reviews and fixes are recorded in [review evidence](pms-api-reviews.md); [provider/token setup](../platform/api/deploy/llm-providers.md) documents OpenAI and compatible endpoints. Local models remain supported. Live cloud calls were mocked, and owned native/test-database services were stopped.


## Optional medical models (2026-09-19)

- [x] Phase 1: explicit QwenMedic and English-only Whisper Medical selections; retain existing defaults.
- [x] Phase 2: verified download/quantization/conversion scripts and isolated converter dependencies installed.
- [x] Phase 3: optional medical human-test profile through the existing authenticated PMS client.
- [x] Phase 4a: 160 audio + 31 local LLM + 17 desktop tests, lint/types/builds, native converter fixture and existing English/Hindi end-to-end checks.
- [ ] Phase 4b BLOCKED: download both actual medical checkpoints and measure their real inference, quality, latency and GPU usage. Corporate filter returns HTTP 403 for both; SSL-disabled diagnostic has the same result.
- [x] Review 1: inspect model isolation, integrity, language restrictions and failure behavior; fix findings.
- [x] Review 2: rerun affected checks and document actual evidence and outstanding download restrictions.

See [medical models](medical-models.md). Model support and launchers are implemented; **medical model download and native verification are incomplete**. No default was replaced and no medical quality/speed claim is made. Owned baseline test services were stopped. Both required setup scripts can be rerun when the network allows the publisher requests.


## Patient scenario category defaults (2026-09-19)

- [x] Add a forward migration, catalog mapping and three defaults: Cardiology, Nephrology, Respiratory Medicine.
- [x] Add repeatable database initialization (create if missing, then migrate); preserve existing records and frozen SQL baseline.
- [x] Align readiness, deployment grants, schema verifier and documentation.
- [x] Test fresh initialization, upgrades, constraints, privileges and concurrent/repeated initialization on disposable PostgreSQL.
- [x] Apply to the existing local PMS demo database and verify the three stored categories.
- [x] Set Qwen3 4B and Whisper large-v3 as standard defaults; verify installed assets, preserve optional model profiles and unrelated private settings.
- [x] Review, fix findings, rerun affected checks and record final evidence.

Completed: three category records in the existing `human_test_demo` database, repeatable `platform/db/init.bat`, and current schema `0011_scenario_categories`. Final checks: 218 PMS tests (zero skipped), 17 desktop tests, 31 local LLM tests; static checks and PMS/desktop builds passed. See the category entry in [review evidence](pms-api-reviews.md). Scenario records and category HTTP selection remain later steps.

## Fictional patient identity: Alex (2026-09-19)

- [x] Add a forward migration, validated identity storage, ORM mapping and one fictional Alex default.
- [x] Align initialization, readiness, runtime read-only grants and schema documentation.
- [x] Verify fresh install, upgrades, audit rollback/retry, preservation, constraints and permissions on disposable PostgreSQL.
- [x] Insert and verify Alex in the local PMS database, preserving existing categories and records.
- [x] Complete two review passes, fix findings and record final checks.

## Alex setup and grounded desktop practice (2026-09-19)

Plan: [patient workflow phases](human-test-patient-workflow-plan.md).

- [x] Phase 1: nine complete fictional templates, one Alex identity, migration and repeatable seeds.
- [x] Phase 2: authorized PMS catalog/setup APIs, validation, revisioned save, snapshots and audit.
- [x] Phase 3: selected-case context on each call, scripted answer routing, token budget/history handling and request fencing.
- [x] Phase 4: redesigned Setup → Conversation desktop with PMS persistence, icons and clear capture controls.
- [x] Add centered skin-toned virtual manikin, left/right question/answer panels and saved observations; verify rendered layout and status transitions.
- [x] Animate lips and blinking on displayed answers; keep capture independent and clean up timers on cancellation, setup changes and close.
- [x] Review 1: security/data/context review, regression tests and fixes.
- [x] Review 2: native end-to-end, visual review, full checks, fixes and final audit table.

Completed software checks: 228 full PMS tests (zero skips), then 85 targeted regressions after final fixes; 20 desktop tests; static checks and package builds. Real Qwen answered all nine selected cases and an edited observation; native desktop save/restore/conversation passed. Whisper large CPU finalization took 16.39–16.91 seconds for two synthetic clips; Hindi recognition was incorrect and correctly led to clarification. Typed Hindi passed. This quality/latency limitation remains explicit in the [final audit](human-test-patient-workflow-audit.md); no real-time or clinical acceptance claim is made.

## Everyday-question patient answering: routing and speaking (2026-09-19)

Reported problem: the patient returned "I am not sure about that. Could you ask me about my symptoms or history?" for anything outside the 22 seeded clinical topics, including "what did you eat yesterday", "when did you sleep", "turn to your left side" and "hmm". No refusal, safety filter or content block was involved; single-call routing mapped every unmatched utterance to the one clarification string. Design: [architecture](pms-api-architecture.md#patient-practice-turn-routing-then-speaking-2026-09-19).

- [x] Classify the utterance instead of only matching topics: `kind` of `topic`, `backchannel`, `command`, `boundary` or `unknown`, fail-closed on any malformed routing object.
- [x] Add authored `dialogue.backchannel`, `command_ack` and `boundary` replies to the contract, publication reference checks and the runtime projection; optional, falling back to `clarification`.
- [x] Answer the non-topic kinds from authored text with no second model call.
- [x] Speak matched topics through a second bounded call carrying only persona facts, the selected answers and the routed `presentation`/`history` sections; exclude instructor content and `never` disclosures.
- [x] Guard generated wording: reject invented numbers (Latin or Devanagari), over-length output and `length` truncation, falling back to the literal authored answer.
- [x] Drop topic answers from the routing prompt and carry `id|intent` only, keeping 32 topics inside the 2,048-token window; fit and report both prompts separately.
- [x] Reserve both completions against the daily quota; keep remote allowances whole and the connection's instruction role on both prompts.
- [x] Separate `routing_invalid` from `case_clarification` so a model failure is no longer indistinguishable from a coverage gap.
- [x] Add ten everyday topics (diet, sleep, appetite, routine, exercise, mood, bowel/bladder, home, travel, vaccination) to all nine cases with per-case overrides where the complaint interacts, plus wider routing intents and in-character clarification text.
- [x] Forward migration `0014_patient_dialogue` with a rerunnable authoring generator; align readiness revision, deployment verifier and schema documentation.
- [ ] Decide manikin physical capability so `command_ack` can state what the body can actually do instead of only acknowledging.
- [x] Verify the two-call turn against the resident local Qwen server and record latency; completed in the [offline final review](offline-models-final-review.md), including eight native patient cases and both real audio response modes.

Original implementation checks: 227 PMS tests passed against a disposable PostgreSQL 17 cluster with the 6 revision-pin failures fixed; API Ruff, formatting and mypy (49 sources) passed. Native Qwen was not running during those checks. The later [offline final review](offline-models-final-review.md) now records real two-call patient results and latency.


## Local/cloud model integration (2026-09-19)

Plan: [cloud models](cloud-models-plan.md). Concurrent workspace edits must be preserved.

- [x] Phase 1: effective profile contracts and model selection.
- [x] Phase 2: forward migration and complete token accounting.
- [x] Phase 3: Azure/OpenAI LLM parameters, readiness and concurrency.
- [x] Phase 4: interactive Azure Whisper, recording and retention.
- [x] Phase 5: PMS-driven Human-test selection and routing.
- [x] Phase 6: conditional startup and documentation.
- [x] Review 1: security/correctness, fixes and affected checks.
- [x] Review 2: end-to-end/latency, fixes and final evidence.

Implementation and both review/fix passes are complete. Evidence: [cloud audit](cloud-models-audit.md). Live provider calls remain deferred. The audit separately records intermittent Tk initialization failures in the new parallel speech-output tests; the cloud/client tests and Models-dialog smoke pass.

## Final online enablement review (2026-09-19)

- [x] Recheck official Azure/OpenAI protocol, operator enablement and model selection.
- [x] Fix confirmed configuration, draft-preservation, client and launcher findings; add regressions.
- [x] Run isolated PostgreSQL/API, client and launcher checks; inspect the final changes again.
- [x] Record verified behavior, remaining live-cloud prerequisites and an audit table.

Final evidence: 263 API tests passed with two opt-in native-model skips; 43 desktop
tests passed with one opt-in native-voice skip; 68 launcher tests passed. Static
checks and package builds passed. See the [final online review](online-enablement-final-review.md).

## Offline models and processing final review (2026-09-19)

- [x] Inspect installed assets, offline routing, resident models, GPU/CPU selection and failure handling.
- [x] Fix confirmed findings and add regression coverage while preserving parallel work.
- [x] Run audio, local-LLM, client and launcher checks plus native inference on installed models.
- [x] Review the final changes again and record measured results and remaining limitations.

Final evidence: 263 broad API tests passed; three native tests were skipped there
and all three passed separately with real local models. Audio 163, desktop 49
(including native English voice), launcher 68, local-LLM 33 and video 85 tests
passed. Thirty real ASR streams and CPU/GPU Qwen inference passed their functional
checks. Both review passes are complete; see the [offline audit](offline-models-final-review.md)
for latency, transcription-quality limitations and incomplete optional model assets.

## Consolidated correctness review (2026-09-19)

- [x] Review previous changes and reproduce remaining client failure cases.
- [x] Fix confirmed findings and run affected regression/static/package checks.
- [x] Reinspect the final changes and record verification boundaries.

Evidence: [consolidated correctness review](final-correctness-review.md). The final
desktop suite passed 67 tests, launcher 68 and PMS provider/client contracts 80;
static and package checks passed. API source and migrations remain unchanged
since the preceding full database/native verification.

## Larger desktop manikin (2026-09-19)

- [x] Give the patient most of the conversation area and group existing controls on the right.
- [x] Review minimum-size layout, long text and Hindi; add visible text scrollbars.
- [x] Rerun desktop regression/static checks and review the final changes.

Evidence: [desktop layout validation](../human-test/validation.md#larger-manikin-layout-2026-09-19).

## Local model selection and activation (2026-09-19)

- [x] Discover complete supported speech/LLM installations and expose selectable local models.
- [x] Add authenticated launcher-owned switching, confirmed process release, readiness and rollback.
- [x] Connect Models selection to activation and PMS persistence without closing Human-test.
- [x] Verify restart compatibility, failures, permissions and real local model switching.
- [x] Review, fix findings, rerun affected checks and record the final review.

Evidence: [local model activation audit](local-model-activation-review.md).

## Online model selection review (2026-09-19)

- [x] Verify supported interactive speech/LLM and separate platform media options.
- [x] Check candidate online connections before applying changes; fence stale selections.
- [x] Improve model/deployment labels, failure messages and runtime switching in Models.
- [x] Test cloud switches and platform video/output configuration using mocks and disposable PostgreSQL.
- [x] Review twice, fix findings and record verification and live-service limitations.

Evidence: [online model switching audit](online-model-switching-review.md).

## Patient voice selection (2026-09-19)

- [x] Select output voice from the saved PMS patient sex; default to male.
- [x] Install and pin a male English voice while preserving the existing female voice.
- [x] Verify voice selection, fallback, caching, synthesis and existing desktop behavior.
- [x] Review, fix findings and record results and language limitations.

Evidence: [patient voice selection audit](patient-voice-review.md).

## Patient LLM latency optimization (2026-09-19)

- [x] Measure routing, prompt budgeting, generation and full patient-turn latency on local Qwen.
- [x] Implement measured improvements without weakening patient context, authorization or answer checks.
- [x] Verify English/Hindi behavior, token limits, failure handling and local/cloud compatibility.
- [x] Review twice, fix findings and publish before/after evidence and operating limits.

Evidence: [LLM latency review](llm-latency-review.md). The interrupted broad API run
was completed through remaining modules and focused reruns; the audit records
the exact parts and the deferred ASR integration check.

## Hindi patient speech output (2026-09-19)

- [x] Locate and download pinned Hindi Piper voices through an available official distribution.
- [x] Install male/female Hindi voices and preserve the existing English selection and fallback.
- [x] Verify real Hindi synthesis, playback integration, installer retries and integrity checks.
- [x] Review twice, fix confirmed issues and record results.

Evidence: [Hindi speech installation audit](hindi-voice-review.md).

## Repeated setup navigation and answer latency (2026-09-20)

- [x] Check repeated setup/conversation transitions for task, timer, history and voice accumulation.
- [x] Measure repeated fresh patient requests and voice warmup costs with installed local models.
- [x] Fix confirmed causes within scope, preserve parallel voice changes and review regression evidence.

Evidence: [navigation and answer-latency review](navigation-answer-latency-review.md).

## Smaller local Qwen option (2026-09-20)

- [x] Pin and install Qwen3 1.7B without replacing the default 4B model.
- [x] Support installation, discovery, activation and restart of the new local option.
- [x] Compare native English/Hindi patient answers and timing with the current model.
- [x] Review compatibility, run relevant checks and document selection and quality limits.

Evidence: [smaller Qwen installation and switching audit](smaller-qwen-review.md).
1.7B is available for comparison; 4B stays the default because the new model
misrouted two Hindi question types in the native patient fixture.


## Online Nemotron default (2026-09-20)

- [x] Save the requested compatible endpoint/model and explicit launcher defaults.
- [x] Verify HTTPS with existing PMS trust and retain certificate/hostname checks.
- [x] Test operator-setting validation, environment precedence and launcher regressions.
- [x] Receive the key through masked input, test JSON/SSE and publish the PMS default.
- [x] Verify a fresh startup restores the online default and completes patient identity/complaint turns.

Evidence: [online Nemotron review](nemotron-online-review.md).


## Azure Whisper cloud default (2026-09-20)

- [x] Configure Azure `whisper-audio-to-text` and retain online Nemotron responses.
- [x] Collect the Azure key in masked input and retain encrypted PMS storage.
- [x] Support the explicit `2024-06-01` transcription route and bounded Azure catalog checks.
- [x] Fix speech readiness identity reload after rollback while retaining revocation checks.
- [x] Verify live English/Hindi speech, transcription-to-patient response and fresh cloud startup.
- [x] Complete corrected isolated readiness regression fixtures and final review.

Evidence: [Azure Whisper review](azure-whisper-online-review.md).

## Online speech and response final review (2026-09-20)

- [x] Review the actual Human-test controller, Azure transcription, Nemotron response and recovery path.
- [x] Reproduce and fix cached speech access after department reassignment for staff and devices.
- [x] Clear both speech and response recovery references on a new conversation.
- [x] Preserve completed Nemotron answers when optional reasoning-token metadata exceeds its parent count.
- [x] Queue the current utterance and retry explicit busy rejections after 1, 2 and 3 seconds; keep cancellation and unknown-outcome protection.
- [x] Verify the focused PostgreSQL suite in a disposable cluster and complete API checks.
- [x] Finish remaining live complaint turns and record the final review evidence.

Evidence: [online speech and response review](online-speech-response-final-review.md).

## Local speech and response final review (2026-09-20)

- [x] Exercise all installed local speech choices and both Qwen sizes through the real desktop/PMS flow in isolated databases.
- [x] Verify model replacement, residency, saved-result recovery and CPU-only Qwen calls.
- [x] Fix Whisper Auto selecting an unsupported language for a Hindi question and add regression coverage.
- [x] Repeat English/Hindi end to end after the fix and run the relevant suites and static checks.
- [x] Record remaining Nemotron recognition and smaller-Qwen quality limits, preserve Cloud defaults, and stop test-owned services.

Evidence: [local speech and response review](local-speech-response-final-review.md).


## Local model execution stays on the laptop (2026-09-20)

- [x] Extract the two-call patient turn (routing, fact guard, budget, event) into shared `training-contracts` so the platform and the laptop build a turn identically.
- [x] Publish `llm.execution`, `local_port` and `local_context_tokens` in the effective route, and execute a published local model from human-test without PMS on the data path.
- [x] Add the metadata-only `POST /organizations/{org}/llm/local-turns` endpoint, `local_turns` model and forward migration `0016_local_turns`; human-test reports a turn after the answer is delivered.
- [x] Refuse platform-executed local turns at admission, readiness, transport and endpoint configuration; remove PMS's ability to dial loopback.
- [x] Drop cloud-only machinery (request rows, recovery, quota reservation) from the local path; keep the local model's key out of PMS responses.
- [x] Add parity, rejection, laptop stub-server, turn-event and opt-in resident-model tests; move the latency benchmark to the laptop path and document the boundary.
- [x] Review the finished implementation again: fixed the report schema refusing the fact guard's own outcome, the launcher never exporting `HUMAN_LOCAL_LLM_KEY`, and a forward laptop clock discarding records; added the pipeline/report contract tests.
- [x] Export the local model key from the startup path the launcher really takes (`model_startup.start`), guarded by the published LLM mode; delete the 190-line dead `Demo.start()` body so one path cannot be fixed while the other runs.
- [ ] Run `start\start-human-test.bat --check` for a local and a cloud profile, plus one real local question, from a normal (non-elevated) console. Attempted here and refused at the first step: `postgres.exe` will not run under an administrator token.

Evidence: [local execution boundary](local-execution-boundary.md), review findings in
[review evidence](pms-api-reviews.md). Final checks: 335 PMS tests passed with 1 skip,
184 human-test passed with 6 skips, 103 launcher passed; lint, formatting and mypy clean.

## Human-test camera layout (2026-09-20)

- [x] Add a full-width control bar above larger-left and compact-right panels.
- [x] Keep the manikin and instructions on the left; move camera capture to the right.
- [x] Place the recording path below the capture controls and above the preview.
- [x] Verify three native window sizes, actual webcam capture, playable recordings and cleanup.
- [x] Run desktop checks and record the final visual review.

Evidence: [camera layout review](human-test-camera-layout-review.md).

## Five busy retries with retained input (2026-09-20)

- [x] Increase speech/response capacity retries to five waits of 1, 2, 3, 4 and 5 seconds.
- [x] Retain the captured audio and transcript; close capture before submitting and pause playback during retries.
- [x] Show waiting/in-progress status and allow cancellation of spoken or typed queued questions.
- [x] Preserve unknown-outcome/partial-output protection and restore controls after exhaustion.
- [x] Verify regression cases, the native desktop flow with real delays, and static checks; update operator documentation.

Evidence: [five-retry review](online-busy-retry-review.md).

## Concise patient clarification (2026-09-20)

- [x] Shorten the stock English/Hindi fallback in the shared local/cloud reply path, including saved cases.
- [x] Preserve custom authored replies, stored snapshots, routing guards and single-call fallback behavior.
- [x] Verify all nine seeded cases, explicit/automatic language choice, invalid routing and custom text; run API and desktop flow checks.

Evidence: [review notes](pms-api-reviews.md). Database integration tests remain
unverified in this run because no disposable test DSN was configured.

## Occasional patient gestures (2026-09-20)

- [x] Add rare, bounded wrist or index-finger motion during actual patient speech.
- [x] Keep the next spoken reply still and clear motion on playback stops/stalls.
- [x] Reuse the existing animation timer and shapes; preserve mouth and blink behavior.
- [x] Verify controller behavior, native canvas isolation and desktop regressions.

Evidence: [patient gesture review](patient-gesture-review.md).

## Microphone input reliability (2026-09-20)

- [x] Make the desktop speech gate adapt to the room instead of trusting one fixed energy threshold.
- [x] Stop isolated coughs and clicks from arming the endpoint, and report per-turn input quality.
- [x] Lose the oldest block rather than the whole question when the event loop stalls, within a budget.
- [x] Add a neural voice detector to the audio service behind the existing detector protocol, and make it the default.
- [x] Measure both detectors through the real segmenter across a rising noise floor before changing the default.

Evidence: [VAD engine comparison](vad-engine-comparison.md), `.test_artifacts/vad-engine/{measure.py,results.json}`.
Real-microphone and real-room verification remain open; the measurement used synthesised speech and synthetic noise.

## Organization-wide online LLM quota follow-up - 2026-09-20

- [x] Default online allowance: 5,000 accepted requests and 5,000,000 combined input/output tokens per organization per UTC day; local model turns are exempt.
- [x] Reserve combined capacity under the organization lock, settle complete provider usage across both patient calls, preserve unknown usage reservations, and keep cached replays uncharged.
- [x] Add forward migration `0017_llm_total_quota`, preserve historical fields, update readiness/configuration/docs, and show distinct actionable request/token-limit messages.
- [x] Update reusable simulation snapshots and retain safe API error codes for rejected admissions; preserve the original live baseline and the user's recent app/audio/VAD work.
- [x] Verify populated upgrades, permissions, concurrency, UTC reset, replay and local exemption with disposable PostgreSQL and mocked cloud calls. Final API coverage after the corrected fixture rerun: 366 passed, 1 opt-in native test skipped; desktop 31, launcher 34 and simulation 8 passed. See [review evidence](pms-api-reviews.md).
- [x] Confirm the independently running demo already has the new schema/defaults and healthy API through read-only inspection; do not restart its owner.
- [ ] Implement the remaining provider-aware speech cooldown, quota precheck, readiness diagnostics, latency and playback work in the [fix plan](simulations/alex-cardiology/fix-plan-2026-09-20.md), then repeat the 25-question live correctness run.

## Readiness resilience (2026-09-20)

- [x] Retry a provider readiness probe, and only the code that a second attempt can change.
- [x] Keep decided answers single-attempt so a rejected key is never asked twice.
- [x] Let an unanswered probe warn instead of refusing the question before any audio is recorded.
- [x] Stop caching a degraded check so a recovered provider is noticed on the next question.
- [x] Give `llm_unavailable` a sentence instead of printing the raw code.

Evidence: [readiness resilience](readiness-resilience.md). Submissions are still never resent on an
unknown outcome. No live provider or PMS deployment was called; the network cause of the original
intermittent failure remains unverified.

## Speech retry rounds and visible waiting state (2026-09-20)

- [x] Retain one recording for ten rounds of five speech retries, with a three-second pause between rounds (51 submissions maximum); preserve five response retries.
- [x] Stop on success/cancellation, and never retry quotas, authorization failures, partial answers or unknown submission outcomes.
- [x] Show a centered bordered panel with an animated clock, countdown, elapsed wait, round/retry progress and cancellation; clear it on every terminal outcome.
- [x] Extend the reusable simulation deadline and retain structured retry evidence; document offline and native UI reruns.
- [x] Verify 267 desktop tests (six opt-in model/voice checks skipped), nine offline simulation checks, and native UI recovery/exhaustion/cancellation with mocked services. Lint/format/type checks passed. See [review evidence](pms-api-reviews.md).
- [ ] Validate live provider recovery with a fresh 25-question run; provider-aware cooldown and other work remain in the [fix plan](simulations/alex-cardiology/fix-plan-2026-09-20.md).

## Azure Realtime Whisper compatibility (2026-09-20)

- [x] On explicit user request, verify the supplied deployment with the existing encrypted resource key: three live synthetic English questions transcribed correctly using `intent=transcription` and a transcription session; the supplied `model=` conversation URL returned HTTP 400.
- [x] Save a reusable bounded probe, redacted event results, measured timings and [integration notes](simulations/azure-realtime-whisper/README.md); preserve the active profile and production code.
- [x] Add a separate selectable Realtime Whisper connection and a bounded PMS-to-Azure WebSocket adapter behind the existing admitted recorded-question API; preserve the original Whisper connection and active profile. Both adapters passed live synthetic English checks.
- [ ] Extend to live partial microphone captions/persistent sessions if requested; validate Hindi/medical accuracy and sustained recovery with the full interview.

## Continuous listening and launcher recovery (2026-09-20)

- [x] Keep continuous listening active after ordinary turn errors, including unknown speech/response outcomes; show a bordered warning and resume fresh capture after three seconds without replaying the failed input.
- [x] Preserve request recovery references, respect manual stop/cancel/close, and retain the existing busy retry exhaustion policy. Ensure display backlog cannot lose a terminal event and strand controls.
- [x] Diagnose startup readiness by stage and safe code; open with a warning after temporary cloud probe failures while retaining credential, configuration, policy and patient access checks.
- [x] Add a repeatable native [recovery simulation](simulations/continuous-listening/README.md) with timestamped results; verify fresh captures, eventual spoken success and manual pause.
- [x] Register and validate **Azure GPT Realtime Whisper** in the existing demo without changing its active Whisper selection. Restart the running app/launcher to load the updated code.
- [x] Verify 408 distinct API tests across the full suite/final targeted run (one opt-in native test skipped), 281 desktop tests (six opt-in checks skipped), 114 launcher tests and nine simulation checks, plus native recovery/retry windows and four live adapter transcriptions. See [review evidence](pms-api-reviews.md#continuous-listening-startup-recovery-and-selectable-realtime-whisper---2026-09-20).

## Cloud/local switching and local service cleanup (2026-09-20)

- [x] Diagnose the occupied local LLM port before model loading; reuse authenticated compatible listeners and report incompatible services before stopping anything.
- [x] Provide the installed laptop model key to a cloud-started desktop for later local activation; verify repeated cloud/local switches use direct laptop inference for local models.
- [x] Add the Models popup cleanup action with organization-admin and loopback capability checks, fixed LLM/audio/video ports, shared operation serialization, idempotent status recovery, recording guards and suspended supervision.
- [x] Preserve saved PMS choices, installed models and recordings; restart cleaned services on local activation and retain failed-switch rollback.
- [x] Verify 135 launcher, 283 desktop and 84 API boundary/provider tests, plus the native popup and Windows listener-release checks. Six desktop opt-in model/voice tests were skipped. See [review](model-switch-cleanup-review.md).

## Patient routing quality, budgets and thinking control (2026-09-20)

- [x] Diagnose in-scope questions answered with the out-of-case clarification: provider non-determinism at `temperature: 0` (9/10 vs 1/10 on identical input) and refused turns in the conversation teaching the router to keep refusing.
- [x] Build a repeatable three-session, 150-turn [routing simulation](patient-routing-quality-review.md) scoring in-scope recall and guard behaviour separately, with a held-out session.
- [x] Revise the shared routing rules for speech transcripts, explicit boundary-first ordering, closest-topic preference and per-message classification. Verified +6 of 111 at every history depth on the deterministic local model and 93.7% against 92.5% over three cloud repeats, with no boundary leak in any arm.
- [x] Budget the routing and spoken calls separately through configuration for local and remote execution; two-call quota reservation drops from 8192 to 4608 and an authored turn from 4096 to 512.
- [x] Apply one history policy on both hosts so a caller cannot widen the routing window; 2 messages local, 12 remote.
- [x] Add `model_options.disable_thinking` for OpenAI-compatible deployments, defaulting to off: measured three times faster and 4.5% accurate on the configured reasoning model.
- [x] Verify the routing prompt against llama.cpp's own tokenizer: worst case 1194 of the 2048-token local window, no truncation or overflow.
- [ ] Route on a small fast model and speak on the large one: the 4B laptop model routes more accurately and about four times faster than the 120B reasoning model. Needs a separate routing connection binding.
- [ ] Re-measure the cloud gain with more repeats, or with a deterministic endpoint; three repeats do not separate 1.2 points from noise.
- [ ] `human-test/scripts/demo.py` imports PyJWT, which is declared in neither the runtime dependencies nor the dev group, so `scripts/tests` cannot run in that virtual environment.

## Continuous listening and truthful status (2026-09-21)

- [x] Diagnose the microphone switching between Listening and Ready while idle: capture gave up after `no_speech_seconds`, the app reopened it 400 ms later, and the device was also closed for the whole of transcription, answering and playback.
- [x] Make the patient's status badge a phase rather than an echo of the status line, so prose can no longer relabel a working machine as Ready; add Transcribing and queue phases and colour work as active.
- [x] Hold one microphone stream open for a whole interview with a 500 ms pre-roll, a per-question duration limit, and no request or reopening while idle.
- [x] Separate capture from processing: a reader task that owns the device and one worker that does not, taking spoken and typed questions in order through a bounded queue whose saturation is reported out loud.
- [x] Report the microphone and the processing pipeline on separate surfaces.
- [x] Keep a failed question from ending the session, charge driver overrun to the question it happened in, and stop a cosmetic status refresh from being able to tear down listening.
- [x] Preserve the playback guarantees through muting rather than closing: the patient's answer is never captured back, and a stalled device releases the microphone instead of stranding input.
- [x] Verify with 296 desktop and 135 launcher tests, including eleven new listener tests over a scripted device: two minutes of silence, speech long after the old cutoff, pre-roll onset, endpoint, refusal, send-now, playback muting, queue saturation, device failure and per-question loss. See [review](continuous-listening-review.md).
- [ ] Capture speech during playback. This needs tested echo cancellation or a verified headset mode; leaving the microphone open during playback would make the patient answer itself.
- [ ] Retire `capture.microphone`: it is now used only by tests and benchmarks and duplicates the endpoint loop. Eighteen of thirty tests in `test_capture_quality.py` pin it, so it was left in place rather than rewritten alongside this change.
- [ ] Measure interview latency end to end after continuous listening; the gaps removed here are structural and were not re-timed.
- [ ] `test_video.py::test_recording_dates_unique_names_private_playable_and_preview` fails when the minute rolls over mid-test; it compares a recording name against a timestamp taken earlier in the test.


## GitHub device-poc import (2026-09-21)

- [x] Configure the standalone workspace for the billing repository's existing GitHub SSH connection.
- [x] Exclude credentials, private JSON overrides, dependencies, generated artifacts, models, recordings, and runtime databases while preserving source JSON, examples, locks, and required assets.
- [x] Add and verify the `git publish` folder mapping into `main:device-poc/`, preserving all unrelated repository contents and refusing unexpected remote changes.
- [x] Document the workflow and validate six isolated publishing scenarios, source JSON, ignore rules, and publisher lint/format. See [publishing instructions](github-publishing.md).

## Local conversation history — implementation 2026-09-21

- [x] Add forward archive migration, scoped API, idempotency, storage caps and retention.
- [x] Add private bounded outbox, independent disk/upload workers and background metrics.
- [x] Capture local completed/failed/cancelled exchanges without awaiting persistence.
- [x] Add recent-pair history view and recording status; preserve local execution.
- [x] Complete broad suites and corrective reruns, final review/fixes and private demo rollout; see review evidence for exact results and native-audio skips.

## Patient turn recovery — implementation 2026-09-21

Objective: use the model where it helps and stop losing answers the case can already give. An
unusable routing object, an unheard question and a truncated spoken reply each produced a stock
line, and a published spoken allowance was silently ignored.

- [x] Wire the spoken allowance on both hosts. `turn_budget`'s `voice_cap` existed and was never
      passed, so a local spoken call used the shared default; `patient_voice_tokens_local` (256)
      and `patient_voice_tokens_remote` (unset) are now published on the route.
- [x] Retry an `invalid` routing object exactly once, with the conversation dropped to the
      current question and the spoken allowance as its ceiling. Report `routing_attempts` and
      `routing_repaired_from`.
- [x] Optional in-character deflection for `unknown` (`model_options.patient_deflection_mode`),
      carrying topic labels only and reusing the spoken guard. Off by default.
- [x] Answer an unrecognized utterance with an in-character request to repeat instead of a
      transcription status line; no provider call and no history entry.
- [x] Forward migration 0019 for the third call and `patient_deflection`; reservations now cover
      every completion a turn may make.
- [x] `scripts/audit_patient_index.py` reports unaskable topics and every prompt against the
      window that binds it.
- [ ] Confirm the deployment's real context window before raising `context_tokens` in
      `start/cloud-models.json` from 8192. The audit reports 4,964 as the minimum for a shipped
      32-topic case with a full conversation, so 8192 works but leaves about 3,200 bytes for
      conversation text; the value was left unchanged rather than guessed.
- [ ] Measure routing accuracy on captured transcripts before tuning prompts further. The repair
      retry addresses malformed and truncated objects; a confidently wrong topic is a separate
      problem and no confidence signal exists (no `logprobs` is requested anywhere).
- [ ] Consider reporting `routing_attempts` in the local-turn record. It is currently derivable
      from `provider_calls` and `answer_source`, which avoided a new column but is indirect.


## Shared UI import cleanup — 2026-09-21

- [x] Keep only reusable components and utilities under `platform/ui/packages/ui`, as requested.
- [x] Remove copied auth/console apps, duplicate app tree, catalog-specific adapters, source branding, and generated artifacts.
- [x] Add a standalone npm workspace, lockfile, neutral package/style names, and usage documentation.
- [x] Verify types, all 1,541 retained tests, 260 affected stylesheet/theme tests, and public JavaScript/CSS package entries. See review evidence.


## Shared common control review — 2026-09-21

- [x] Review common field, button, navigation, tab and overlay composition in `platform/ui/packages/ui`.
- [x] Fix unintended form submission, missing field descriptions, loading-select form ownership, unsafe footer/rail links, duplicate tab ids and keyboard reachability.
- [x] Fix dialog fallback focus, hidden/disabled tab stops, nested Escape handling, overlapping scroll locks and focus restoration; verify search-select Escape composition.
- [x] Add 24 regression cases, review the final diff, and pass all 1,565 UI tests, TypeScript and package/export/bundle checks.
- [x] Document explicit submit buttons and scoped tab-panel labels in `platform/ui/README.md`. Browser layout, screen-reader and React 18 runtime verification remain outside the automated evidence.


## Local audio investigation - 2026-09-21

- [x] Reproduce the intermittent Transcribing display: empty-recognition timing exception, stale failure badge and stranded frames after reader failure.
- [x] Fix all three confirmed desktop defects and pass four new regression cases, 88 targeted tests and the full 326-test desktop suite.
- [x] Simulate 12 generated spoken questions in each of cardiology and respiratory cases through real local Whisper/Qwen and the desktop; record 24 exact transcripts, timings, input conditions and actual answers.
- [x] Verify silence causes no submission and empty recognition does not prevent the next question or UI update.
- [x] Distinguish audio accuracy from model-topic accuracy; reproduce 22/24 expected topics with the saved profile and evaluate additional phrasings without deploying unreliable prompt experiments.
- [ ] Improve local routing of additional/associated symptoms, including follow-ups after symptom-details answers and symptom-presence questions versus measured vital signs. Recheck broad phrasings and Hindi before accepting a prompt/model change.
- [ ] Verify physical microphone/room acoustics and speaker playback; generated PCM tests do not measure these. See [evidence](local-audio-verification-20260921.md).

## Expanded local interview - 2026-09-21

- [x] Prepare and execute 50 spoken questions, 25 per category, covering all 32 available case topics; retain every actual transcript and answer in [Markdown](local-audio-50-questions-20260921.md) and [CSV](local-audio-50-questions-20260921.csv).
- [x] Preserve production routing and saved authored-answer settings; keep expected topics solely in simulation evaluation. Confirm 50 completed turns, zero dropped blocks/UI callback errors, and empty-recognition recovery.
- [x] Review 42/50 matching selections (cardiology 23/25, respiratory 19/25); explain numeral/spelling transcript differences and the punctuation change on the paused treatment question.
- [ ] Address the observed associated-symptom, treatment, contextual follow-up and sleep-routing failures with a general solution. Isolate pause-generated punctuation and the preceding wrong answer before attributing all failures to model routing. No question-specific workaround was introduced.

## Nephrology local interview - 2026-09-21

- [x] Change to flank pain and kidney-condition follow-up; prepare and execute 50 new spoken questions, 25 per case, without repeating the preceding question phrasings.
- [x] Record and review every actual answer, transcript, timing, routing status/source and model-call count in [Markdown](local-audio-50-nephrology-20260921.md) and [CSV](local-audio-50-nephrology-20260921.csv).
- [x] Verify 43/50 exact topic sets, 50 Complete UI states, zero dropped/status blocks or UI callback errors, and empty-recognition recovery. Confirm 37 monitored production/configuration files unchanged by SHA-256 and both owned model ports closed.
- [ ] Investigate the additional routing failures: duration/associated-symptom confusion, invalid routing despite repair, dialysis history misclassified as a command, and an unsolicited allergy topic on a fluid/salt question. Review authored conversational references such as `as I mentioned`. No production workaround was introduced.

## Home, Tenants and Devices API binding (2026-09-23)

- [x] Home � Complete: live API binding, lifecycle/scoping/retention fixes; five PostgreSQL cases, three UI tests and production browser verification.
- [x] Tenants � Complete (38 UI tests, tenant API regressions, seven browser flows): directory/details, creation, updates and lifecycle actions.
- [ ] Devices � In progress: scoped directory/details, registration, configuration and lifecycle actions.
- [ ] Final review, regression checks and DB/model/script consistency.


## Web LLM connection management - 2026-09-24

- [x] Add tenant Settings > LLM connections with API-backed create/read/edit, encrypted key replacement, enable/disable, archive/restore, provider and state filters, and cursor paging.
- [x] Preserve the processing picker contract; add a permission-gated management directory, configuration options and stale-archive revision checks.
- [x] Review authorization, tenant switching, credential redaction, input validation, published-profile dependencies and concurrent edits. Serialize profile publication with connection archival.
- [x] Review the final UI and fix token formatting, responsive actions, missing styles, stale status results and provider error messages. Verify real browser/server-action/HTTP/PostgreSQL flows on a disposable database without cloud calls.
- [ ] Resolve the broader conversation-test setup and language-validator PUBLIC execution-grant failures before claiming a fully passing database suite. These are recorded in the review evidence; this increment does not change the conversation protocol or language migrations.


## 2026-09-24 - Tenant Excel member imports

- [x] Role-specific workbook template, bounded parser and row validation.
- [x] Atomic per-row invitations with saved, idempotent batch results and encrypted delivery queue.
- [x] Tenant-only four-step wizard, refresh/history, error/result Excel downloads.
- [x] Complete two reviews with fixes, upgrade/runtime/concurrency and real browser verification.


## 2026-09-24 - Existing web management screens

- [x] Platform category, fictional patient profile and embedded case Q&A management.
- [x] Explicit language/platform options and tenant patient practice setup.
- [x] Tenant scenario drafts, validation, language review, publication and retirement.
- [x] Provider connections, processing profile revisions and real department CRUD.
- [x] Session history/start/stop/feedback, scoped reports/recordings and personal settings.
- [x] Forward catalog version migration and least-privilege grants; no new entity.
- [x] Two reviews with fixes, isolated PostgreSQL checks and eleven real browser journeys.
- [ ] Deployment operator: apply migration 0027 and refreshed runtime grants to the configured application database; cloud/hardware verification remains deferred.


## 2026-09-24 - Windows platform startup

- [x] Add start/start-platform.bat for API readiness followed by web UI startup, with owned-process cleanup and actionable diagnostics.
- [x] Verify eleven launcher checks and actual Next.js readiness/cleanup.
- [ ] Configure/reach application PostgreSQL and apply runtime grants before the combined launcher can report API readiness.


## 2026-09-24 - Shared API client boundary

- [x] Remove private database/API provisioning and retention startup from all Human-test launcher paths.
- [x] Read published profiles through the configured shared API; retain local companion startup, supervision and model switching.
- [x] Strip inherited backend database credentials from all client child environments and test the API-only boundary.
- [x] Update shared-API startup instructions; preserve unused legacy demo files.
- [ ] Existing unrelated check: reconcile test_devices.py expectations (16 GPU layers) with committed devices.py policy (18), without changing GPU policy as part of this task.


## 2026-09-24 - Human-test central API boundary follow-up

- [x] Remove remaining private-demo bootstrap helpers and client-side backend/cloud provisioning settings.
- [x] Restrict local serving to model/media engines and a capability-authenticated companion-control mailbox; platform data remains on the central API.
- [x] Fix history preference, child credential isolation, model-port validation, stale profile reuse, login/department binding and explicit department handover.
- [x] Review twice, fix findings, and verify 169 launcher + 453 desktop tests; 6 optional native-model/voice tests skipped. No backend schema/runtime changes or live cloud/hardware claims.
- [x] Document current setup and verification in human-test-api-boundary.md and pms-api-reviews.md.


## 2026-09-24 - Human-test end-to-end review

- [x] Review launch/setup/conversation/history/model recovery/native UI/shutdown and fix confirmed findings in two passes.
- [x] Follow configured patient identities; preserve duplicate case choices; clear stale patient/vital state; allow typing during continuous listening.
- [x] Bound API shutdown independently from local history flush; reject incomplete answers; require refresh after uncertain or unapplied model publications.
- [x] Verify full desktop/launcher suites, four native UI smokes and a real central-API/disposable-PostgreSQL journey across three clinical categories; document exact counts and mocks in pms-api-reviews.md.
- [ ] Operator setup: configure HUMAN_PMS_TOKEN and HUMAN_ORGANIZATION_ID in human-test/.env, with a running central API and a published patient conversation profile.
- [ ] Real model answer quality/latency and microphone/camera validation remain unverified; optional resident-Qwen/installed-voice tests were skipped.


## 2026-09-26 - Database/scripts/models synchronization

- [x] Match fresh and adopted PostgreSQL schemas to all 34 ORM tables / 594 columns, including types, nullability and primary keys.
- [x] Add forward 0028 language-validator ACL repair; align runtime grants and exact single-head API/worker readiness.
- [x] Fix stale SQL verifier, grant-test expectations and deployment revision guidance; preserve frozen SQL and existing migrations.
- [x] Verify 67 distinct focused tests, upgrade preservation/concurrency, backup/restore, built wheel contents, initialization wrapper and local Qwen 3.5 asset checksums. One optional running-browser test skipped.
- [ ] Application deployment: restore the configured PostgreSQL connection, configure PMS_MIGRATION_DATABASE_URL, upgrade to 0028 and reapply API/worker/retention grants. Application database and published tenant model configuration remain unverified until reachable.


## 2026-09-26: Local central API and Human-test setup

- [x] Initialize the central device_platform database and current schema using the API-owned initializer; apply separate runtime grants and keep credentials in private backend configuration.
- [x] Support an audited, local-only first-admin password bootstrap without SMTP; verify atomic rollback, environment/approval/password guards, login and repeat-bootstrap rejection.
- [x] Configure a tenant, publish Qwen3.5-4B via the authenticated central API, and save the API-issued client session in human-test/.env.
- [x] Isolate PostgreSQL fixtures from developer migration credentials and accept blank optional desktop UUID selections from the editable .env example.
- [x] Pass 34 API and 46 Human-test regression tests, API static checks, real API/login/configuration checks and the full local companion startup check. See the matching review entry for limits and rerun evidence.


## 2026-09-26: First-run web administrator setup

- [x] Replace proposed automatic password seeding with an installation-key-protected web wizard for name, email, password confirmation, review and completion.
- [x] Create the first Argon2id local administrator and audit atomically through the least-privilege central API; serialize concurrent setup and close setup for every existing identity.
- [x] Generate only an independent installation key in init-local; keep administrator passwords out of environment files, logs and browser persistence.
- [x] Verify 54 relevant API tests, 431 distinct web tests, API static checks, web typecheck/build, and a real browser-to-API-to-disposable-PostgreSQL setup/login journey. Complete two reviews and fixes; see review evidence.


## 2026-09-26: Follow-up setup review

- [x] Validate bootstrap identity with the existing account schema before hashing/database work; reject malformed setup text safely and keep key errors on the correct wizard step.
- [x] Verify the configured administrator and current schema read-only; complete 597 relevant tests, static checks, production build and actual launcher readiness/cleanup; re-review fixes with no remaining blocking findings.


## 2026-09-28: Tenant administration popup

- [x] Move tenant administration from the bottom of tenant details to a top-right button and the existing shared modal.
- [x] Separate Subscription and Administrators tabs; explain plan capacity, subscription dates/status, existing-account search and tenant-wide administrator assignment.
- [x] Preserve read/manage permissions, archived restoration, confirmations, server validation and record-version checks. Clear stale account selections and handle failed searches/load retries.
- [x] Verify 50 tenant web tests, web typecheck and the live local popup at desktop/mobile sizes. No API/schema changes; database suites and mutating browser fixture were not rerun for this UI change.


## 2026-09-28: Administrator management and UI responsiveness

- [x] Create platform or selected-tenant administrators from the existing users UI/API with atomic setup, invitation, quota and audit handling.
- [x] Block platform self-disable/archive in the API, server actions and directory/detail controls; test with another active administrator present.
- [x] Review inactive-tenant first-admin bootstrap, scoped access, archived tenants, duplicate identities, concurrent seats and rollback.
- [x] Repair missing page JavaScript by isolating development/review/production output; use Turbopack, route loading feedback and bounded directory loading with Retry.
- [x] Pass relevant API regressions, 452 web tests, 21 launcher tests, static checks, production build and the full local browser journey; verify running UI survives a production build and record navigation timings.
- [x] Remove temporary review services and the interrupted fixture database; leave application API/UI running. See review evidence for details and limitations.


## 2026-09-28: Tenant user and device association popup

- [x] Add Administrator immediately after View on /tenants, opening the selected tenant in the shared responsive modal with Users and Devices tabs.
- [x] Implement bounded existing-account search, role association, membership editing, disable/enable, removal and disabled restoration with tenant scope, permission, version, quota and audit enforcement.
- [x] Reuse fleet registration, search, transfer, rename, activation/deactivation and removal, preserving original-tenant history and requiring fresh enrollment after transfer.
- [x] Complete two reviews and fixes, relevant disposable PostgreSQL tests, all 467 web tests, static checks, production build and the real desktop/mobile browser journey.
- [x] Clean temporary review services and interrupted test data; restart application API/UI and verify both tabs read-only against the running application.

## 2026-10-01: Single-VM Ubuntu deployment

- [x] Build a Windows transfer zip with checked UI/API artifacts, lockfiles and migrations, excluding local secrets.
- [x] Add Ubuntu setup for database roles, private configuration, Linux dependencies, HTTPS, systemd, readiness and rollback.
- [x] Add no-edit VM-local production configuration with password sign-in, bounded private storage and fail-closed email/OIDC actions.
- [x] Deploy the corrected archive on the target Azure VM; verify HTTPS, API/web readiness, all four services, a private PostgreSQL backup and read-only tenant inventory.
- [ ] Verify certificate renewal and a safe rollback drill on the target Azure VM after a healthy prior release exists.
- [x] Verify bootstrap SQL, migrations, grants, dump and restore against a disposable PostgreSQL 17 cluster.

## 2026-10-01: Tenant-owned clinical content and training

- [x] Record the phase-wise product, file, migration, verification and review plan in [tenant clinical ownership](tenant-clinical-ownership-plan.md). Subsequent local implementation and reviews are recorded below.
- [ ] Phase 0: confirm tenant content, staff capability, reviewer and starter-import policy; inventory current global catalog references and active usage.
- [x] Phase 0: record the implementation defaults and source dependency review, and run a read-only local database inventory; see [Phase 0 review](tenant-clinical-phase-0-review.md).
- [ ] Before Phase 1 cutover: run the read-only inventory against the target VM, review its tenant counts, and record product-owner approval of the capability/publication defaults.
- [x] Phase 1 local implementation: add tenant-owned catalog storage and safe forward/backfill migration tooling, preserving practice snapshots and approved scenario/session history. Disposable PostgreSQL verification complete; the application and VM databases were not migrated.
- [x] Phase 2 local implementation: enforce audited tenant capability assignments and tenant-scoped catalog API; remove platform clinical-content routes and API write grants to global clinical tables. Disposable PostgreSQL verification and review are recorded in tenant-clinical-phase-2-review.md.
- [x] Phase 3 local: connect tenant cases to private rehearsal and revision-pinned scenario drafts; enforce separate author/reviewer and instructor capabilities; compile reviewed bilingual version 3 cases for the signed device runtime.
- [x] Phase 4 local: replace retired platform catalog calls with tenant screens, effective-permission menus, direct-route checks and capability assignment controls.
- [x] Phase 5 local software: pin source/runtime hashes at assignment, recheck on device lease, and prove two fictional cases on one device fixture keep answers, memory, state and media labels separate.
- [ ] Phase 5 physical gate: verify an attestable identity and wipe procedure for serial-less devices before cross-tenant hardware reassignment.
- [x] Phase 6-7 local: full disposable PostgreSQL/API/UI/build/artifact checks and second review passed; see [combined review](tenant-clinical-phases-3-7-review.md). The VM, clinical review, and physical-device gates below remain open.
- [ ] Phase 7 VM: run target inventory, obtain tenant clinical approval, take a verified backup, stop all old writers, deploy and backfill, then record HTTPS/readiness, two-tenant smoke and rollback evidence using the [rollout checklist](tenant-clinical-rollout.md).

## 2026-10-01: Human-test tenant clinical compatibility

- [x] Filter the desktop case picker by the tenant's active specialty and patient profile, and show the current profile identity in preview.
- [x] Explain empty tenant catalogs, legacy global selections and changed cases; require a new tenant selection before another interview.
- [x] Correct desktop permission guidance and setup documentation; add workflow regressions and complete a final review.
- [ ] Verify the desktop against the deployed tenant API and an approved tenant-authored case on the target environment.

## 2026-10-01: Human-test end-to-end follow-up

- [x] Handle active tenant cases with source-language-only complaint, optional onset and blank initial observations in desktop setup.
- [x] Return a structured 422 when a changed tenant profile lacks the selected rehearsal language; preserve selection and audit state.
- [x] Run desktop suite and disposable PostgreSQL API/client journey; correct current API and patient-practice documentation.
- [x] Rebuild and verify the Ubuntu transfer archive after the API correction; refresh the rollout checksum and client smoke step.
- [ ] Record the hosted VM and staff-laptop client smoke results after manual rollout.

## 2026-10-01: Final tenant clinical web and release follow-up

- [x] Resolve historical-selection, context/reload, in-flight case/save, empty-catalog, failed-load, specialty-without-cases, vital-clearing and tenant-author guidance findings in Patient setup.
- [x] Explain incomplete localization and case/profile mismatch errors; add focused web regressions.
- [x] Pass the full 482-test web suite with bounded test concurrency, TypeScript, production build, API static checks and transfer archive integrity/source checks.
- [x] Update the manual Ubuntu rollout commands and checksum for the final archive.
- [ ] Record the target Ubuntu, hosted two-tenant, staff-laptop Human-test and physical-device verification after the operator runs the rollout.

## 2026-10-01: Hosted Users page fix

- [x] Move clinical capability labels out of the Next.js use server action module and add an export regression.
- [x] Build and test the web release, back up the populated VM database, redeploy, and confirm the signed-in Users list loads with administrator and tenant records preserved.

## 2026-10-01: VM local user provisioning

- [x] Fix Create user 503 in VM local mode and show private one-time setup and tenant invitation links.
- [x] Verify the affected flow against disposable PostgreSQL, run API and web checks, build and deploy the source-matched archive, and confirm hosted readiness and preserved records.
- [x] Confirm the administrator created the intended account, received both links, and completed password setup on the hosted VM.

See [review evidence](vm-local-user-provisioning-review.md).

## 2026-10-01: Unified tenant administration

- [x] Use one tenant administration dialog from the tenant list and detail page, with Subscription, Administrators, Users and Devices sections.
- [x] Preserve role and tenant scope, confirm association changes, refresh administrator and tenant state, and pass focused and full web checks.
- [x] Leave the hosted VM unchanged as requested.

See [review evidence](tenant-administration-unification-review.md).

## 2026-10-01: Tenant LLM connection availability

- [x] Explicitly enable LLM connection management in new VM-local configuration, preserving the separate cloud-call gate.
- [x] Show one clear disabled state on the tenant page and cover the deployment setting and UI regression.
- [x] Document the operator-controlled setting required by existing VMs; leave the hosted VM unchanged.

See [review evidence](tenant-administration-unification-review.md).

## 2026-10-01: Tenant administrator clinical default and cards

- [x] Grant clinical author access to tenant administrators from the current membership role, without a stored assignment or schema migration.
- [x] Keep staff assignments, tenant boundaries, and platform administrator isolation enforced by the API.
- [x] Show only Clinical specialties, Patient profiles, and Cases & Q&A cards on tenant administrator Home and Settings while retaining authorized direct routes.
- [x] Review and test the role and UI changes without deploying to the VM.

See [review evidence](tenant-admin-clinical-default-review.md).

## 2026-10-02: Platform device model profile assignment

- [x] Let Platform Admin choose an active published same-tenant processing profile during device registration/edit and from the device list actions.
- [x] Show only published per-operation Local/Cloud model metadata; retain tenant-owned drafts, prompts, credentials, and media behind tenant access.
- [x] Revalidate the selected profile on the server, preserve transfer isolation, and verify effective device configuration changes.
- [x] Run local tests and review; do not create a deployment build or update the hosted VM.

See [review evidence](device-model-profile-assignment-review.md).

## 2026-10-02: Tenant onboarding, devices, and import history

- [x] Replace tenant creation popup with a page wizard that provisions an active tenant, one new or transferred device, and a new or existing administrator atomically.
- [x] Allow only Platform Admin to register devices, select published device profiles, and manage model catalog/LLM connections; keep tenant private device edits and enrollment scoped.
- [x] Use Manikin (Physical) and Laptop (Software) for new devices, preserving legacy records through forward migration 0032.
- [x] Put Departments under tenant Settings and return to the department list with a success message after save.
- [x] Add optional imported local passwords, generated blanks, encrypted 30-day history, audited reveal/download, and the Import History page.
- [x] Run final local API, migration, and web unit checks; fix findings and record review evidence. Do not build or deploy.

## 2026-10-02: Tenant onboarding and import follow-up

- [x] Recover wizard searches and import history loading errors; delay initial tenant field errors, improve narrow-screen history actions, and clarify external sign-in password instructions.
- [x] Enforce the 512 KiB import upload bound before parsing; confirm administrator rollback and password-history tenant/expiry guards.
- [x] Run focused disposable PostgreSQL and web tests, static checks, and final review; leave build and VM unchanged.

## 2026-10-02: Clinical catalog and Q&A follow-up

- [x] Review tenant clinical specialty, patient profile, case Q&A, scenario, and practice permissions and data flow.
- [x] Keep active case parents active across both archive and edit paths; cover this with disposable PostgreSQL regression tests.
- [x] Let authors and readers open incomplete case drafts whose optional sections are absent; cover the Q&A editor and align lifecycle errors with API codes.
- [x] Complete final local verification and record the results; do not build or deploy.

## 2026-10-02: Device model picker and human-test binding

- [x] Show published Local, Cloud, and mixed profile model routes by operation in the platform device editor, including the tenant default.
- [x] Keep installed local model discovery on the authenticated human-test launcher; distinguish published names from installed files and CPU/GPU support.
- [x] Allow an optional active, enrolled device ID to bind human-test model reads to that tenant device's assigned profile, with department scope and read-only options.
- [x] Cover assignment changes, invalid overrides, incomplete desktop profiles, and local client configuration in focused tests.

## 2026-10-02: Platform administrator role review

- [x] Trace platform navigation, direct routes, API grants, and tenant-content boundaries across tenants, users, devices, models, LLM, subscriptions, health, and audit.
- [x] Fix existing-member administrator promotion versioning, duplicate pending-email invitations, and verified-account requirement.
- [x] Keep platform default tenant policy within policy limits so new tenants remain provisionable.
- [x] Run disposable PostgreSQL role regressions, full local API/web suites, static checks, and final review without build or VM deployment.

## 2026-10-02: Tenant administrator role review

- [x] Trace Tenant Admin grants and membership scoping through clinical catalog, members/imports, departments, devices, and platform-only LLM/model controls.
- [x] Reject self-disable and self-archive through shared tenant membership mutations; disable the same actions in the Members list and detail UI.
- [x] Cover Tenant Admin and ordinary user self-actions with disposable PostgreSQL tests, plus direct and list UI regressions.
- [x] Run related database role tests, full local API/web suites, lint, type checks, and final review without build or VM deployment.

## 2026-10-02: Browser session lifetime and expiry

- [x] Make browser session lifetime configurable with a 24-hour default and keep the remember checkbox limited to cookie persistence.
- [x] Revalidate open console sessions on a timer and focus; clear revoked/expired cookies and return to login without treating API outages as expiry.
- [x] Cover configuration, expiry, logout, outage, and open-tab behavior with database and web tests; run full local checks without build or VM deployment.

## 2026-10-02: Default tenant patient profile

- [x] Seed one independent, inactive fictional patient profile in all three tenant creation paths, within the tenant creation transaction.
- [x] Show the automatic profile in the tenant wizard review and completion copy without exposing tenant clinical data to Platform Admin.
- [x] Verify tenant isolation, failure rollback, starter import behavior, and patient practice compatibility with disposable PostgreSQL tests.
- [x] Run local API/web suites, static checks, and final review without a build or VM deployment.

## 2026-10-02: Default tenant clinical specialties

- [x] Seed Cardiology, Nephrology, and Respiratory Medicine as independent inactive tenant specialties in all three creation paths, together with the starter patient profile.
- [x] Show the three specialties in wizard review and completion; the later case-draft phase adds two inactive QnA cases.
- [x] Verify tenant isolation, editing, transfer rollback, catalog import idempotency, and the specialty cap against disposable PostgreSQL.
- [x] Run local API/web suites and static checks; review final changes without a build or VM deployment.

## 2026-10-02: Default tenant case drafts

- [x] Select chest-discomfort and wheeze interview drafts from the existing bilingual starter catalog, and review clinical plausibility against AHA, NICE, and NIH NHLBI guidance.
- [x] Seed two inactive tenant-owned case copies with tenant-specific specialty/profile IDs, instructor criteria, source provenance, and audit events in all three creation paths.
- [x] Describe Details, Presentation, History, Vitals and disclosure, Questions and answers, and Instructor values; show the drafts and activation requirement in wizard review.
- [x] Verify tenant isolation, rollback, import idempotency, backfill compatibility, and local API/web checks without a build or VM deployment.

## 2026-10-02: Final clinical starter review

- [x] Trace all three tenant creation paths and verify tenant-owned specialties, Alex profile, and case drafts remain inactive until review.
- [x] Reject changed global starter revisions during automatic tenant provisioning and verify atomic rollback.
- [x] Verify activation into patient practice, permissions, catalog UI, and local API/web checks without build or VM update.


## 2026-10-02: Published tenant starters and Patient setup

- [x] Provision two clearly labeled published system scenario snapshots and one tenant-wide Patient setup suggestion with each new tenant.
- [x] Enforce same-tenant references, role and lifecycle checks, source integrity, revision guards, and atomic audit events.
- [x] Verify disposable PostgreSQL provisioning and permissions, full local API and web suites, static checks, and final review without build or VM deployment.


## 2026-10-02: Tenant default Case QnA review

- [x] Trace bilingual source questions through tenant provisioning, scoped case detail, editor, and published runtime snapshot.
- [x] Replace three general topics per default case with case-specific assessment questions while preserving 32 topics and the frozen source.
- [x] Verify QnA values, role and tenant scope, snapshot immutability, UI editing, disposable PostgreSQL tests, and local API/web checks.

## 2026-10-02: Platform model consolidation

- [x] Consolidate Platform Admin cloud setup, local laptop inventory, device assignment, media connections, profiles, and catalog into one Models page; redirect legacy routes.
- [x] Encrypt platform credentials, test before use, support Anthropic Messages, and propagate retests to managed tenant bindings.
- [x] Report supported local models with the enrolled laptop credential; reject stale/spoofed reports and incompatible audio routes.
- [x] Publish device-specific assignments atomically, reuse a tenant/model binding, and enforce tenant connection limits.
- [x] Remove tenant administrator model/connection/profile grants while keeping clinical responsibilities intact.
- [x] Verify isolated PostgreSQL migration and grants, assignment/retest, Human-test reporting, API/web suites, and static checks without a build or VM update.

## List-page UI standardization - 2026-10-03

- [x] Complete the six phases and final review in [the list-page UI checklist](list-page-ui-plan.md); keep changes scoped to list filters.


## Unified page back navigation - 2026-10-03

- [x] Complete [the back-navigation checklist](back-navigation-todo.md), preserve editor guards and verify parent destinations.


## 2026-10-03: VM API, UI, and database upgrade

- [x] Build and verify the current release archive in an isolated checkout.
- [x] Reproduce and fix cross-revision database recovery with an atomic schema restore; test recovery failures as well as successful restores.
- [x] Verify fresh database bootstrap/grants, existing-data migration, affected model/scenario tests, full API unit and UI suites, and static checks.
- [x] Complete the authorized VM deployment and verify schema, grants, retained records, services, HTTPS, and backup.

- [x] 2026-10-03: Redesign local tenant administration tabs with a wider scoped dialog, responsive navigation/cards, aligned forms, filters and table actions. Preserve permission and confirmation behavior; verify 30 component tests, web typecheck and five-width browser layouts.

- [x] 2026-10-03: Replace combined tenant user/device action screens with focused task flows: find account, choose access and review; device details and review; transfer search and review. Hide unrelated controls, preserve drafts when returning from review, and restore list focus on exit.


### 2026-10-03 - Focused Models management: completed

Models now contains only model management and relevant filters/actions. Device assignment, provider connections and processing profiles have separate pages. See the [completed TODO](model-workspace-todo.md) and [planned/implemented reconciliation and review](model-workspace-review.md). Verification: web suite 566 passed; final affected rerun 32 passed; API suite 386 passed/333 skipped; isolated PostgreSQL 21 passed; local authenticated browser scenario 1 passed; Ruff, mypy and web typecheck passed. No live provider, application database or hosted deployment was used for this work. Rollout requires migration 0036 and updated runtime grants.


### 2026-10-03 - Models UI clarity follow-up: complete

Reworked header/list grouping, visible Edit, removable applied filters, status presentation, grouped wider editors and responsive spacing. Kept CSS scoped to Models; no API/database changes. Review fixed mobile row spacing and a shared CSS specificity conflict. Verification: 39 affected UI tests plus final 9-test rerun, web TypeScript check, authenticated fixture CRUD and 60 light/dark layout checks at five widths; representative screenshots inspected. [Reconciliation and evidence](model-workspace-review.md#ui-clarity-follow-up). Local work only; no hosted deployment or live cloud calls.


### 2026-10-03 - Devices Configure models popup: complete

Replaced navigation from the device action menu with a focused modal. Fixed device/tenant context, current setup, conditional local speech controls, optional media changes, guarded saves and draft protection. List filters persist; focus returns after close/save. Removed the old assignment component and bulk-device choices loader; old links redirect to the popup. Review fixed deep-link hydration, unchanged-save handling and warning presentation. Verification: 33 focused tests, 586 full web tests, final 9 dialog tests, web TypeScript, 8 isolated API assignment tests, authenticated browser assignment and 20 light/dark layout checks. Disposable database and temporary web server stopped. No API schema changes or deployment. [Reconciliation and evidence](model-workspace-review.md#devices-popup-follow-up).

- [x] 2026-10-03: Second tenant UX review: keep add/register/transfer review inside the original popup; add structured summaries, compact task widths, responsive progress, preserved drafts and Escape-to-edit. Verify live React browser interactions with mocked APIs, including short windows, enlarged text, failures and read-only access.


### 2026-10-03 - Direct models rearchitecture

- [x] Complete typed model ownership, direct device selections, migration/runtime compatibility, simplified UI and final review. This supersedes the earlier model workspace/profile/connection workflow. Track detailed progress in [Direct models TODO](direct-models-todo.md); final reconciliation and evidence are in [Direct models review](direct-models-review.md).


## 2026-10-03 - final model-management simplification

- [x] Platform Admin model CRUD and direct device selection only.
- [x] Removed legacy connection/profile management routes, tenant pickers, desktop mutations and unused web components.
- [x] Forward migration 0038 removes obsolete assignment columns and freezes historical configuration; runtime grants updated.
- [x] Reviewed/fixed and verified focused PostgreSQL, API, web, desktop and authenticated browser flows.
- [ ] Port remaining historical database-test fixtures that call retired setup APIs; full database suite is not claimed as verified.

See [reconciliation](direct-models-review.md) for exact results and rollout limitations.


## 2026-10-04 - database, models and scripts synchronization

Completed: local database backed up and upgraded from 0035 to 0038; runtime grants and ORM verified; API readiness 200. Added read-only/apply sync scripts and aligned startup/transfer scripts. Verification: 10 initial disposable checks, 9 expanded schema checks, 379 API passed/336 skipped, 174 launcher tests, 30 platform checks plus 13 subtests, Ruff/mypy passed. See [database synchronization review](database-sync-review.md) for evidence and limitations.


## 2026-10-04 - Three default local models

- [x] Add forward migration 0039: fresh Models page contains Whisper large-v3, qwen3.5-4b-local and eSpeak NG only.
- [x] Preserve configured, tenant-owned, used, disabled, archived and device-assigned models during upgrades; audit starter-model retirement atomically.
- [x] Align readiness and tenant backfill compatibility; document database-only defaults and repeat-deployment behavior.
- [x] Complete isolated PostgreSQL fresh/upgrade regression checks, API/static checks and final review (21 targeted checks passed across runs; 379 non-database tests passed, 339 database tests skipped in the full run; Ruff and mypy passed).


## 2026-10-04 - Device model dropdowns before installation

- [x] Diagnose the configured local database: three active shared local defaults; Manikin demo 2 is a pending manikin without runtime inventory; no configured cloud models.
- [x] Make active configured local/cloud models selectable by type/mode/tenant scope before enrollment or installation; retain role, tenant, lifecycle, kind/mode and revision checks.
- [x] Update Configure model guidance and empty states; preserve runtime installation and cloud execution requirements.
- [x] Verify pending-manikin and stale-laptop assignment, all four cloud model kinds with mock credentials, UI filtering/saves, permission boundaries and concurrent version checks.
- [x] Back up/sync the local database through pending 0039, restart the local platform and verify API/UI readiness; preserve existing device assignments.


## 2026-10-04 - Platform-wide immutable device IDs

- [x] Require a 1-50 character device_unique_id on all creation paths, immutable after creation and case-insensitively unique platform-wide.
- [x] Preserve the physical ID across transfers while retaining tenant registration/history isolation; reserve retired identities permanently.
- [x] Add forward migration 0040 with approved UUID backfill, atomic audits, constraints and least-privilege runtime grants.
- [x] Add required fields to all creation UIs and read-only display/search to device screens.
- [x] Finish migration/concurrency/transfer/onboarding/UI regressions, static checks and final review; back up and update the running local platform. Two pre-existing legacy-profile test limitations are recorded in review evidence.


## 2026-10-04 - Tenant administration scope

- [x] Remove the Users tab from tenant-list/detail administration; open the list action at Administrators and retain Subscription/Devices.
- [x] Verify required device unique ID, 50-character limit, review display and submitted payload; run focused UI regressions and TypeScript.


## 2026-10-04 - Platform options layout

- [x] Replace nested fieldsets/cards with aligned General, Maintenance, Cloud providers and Language options sections and a clear save bar.
- [x] Verify responsive layouts, light/dark themes, save/validation/confirmation/read-only behavior and TypeScript.


## Scenario simplification — 2026-10-04

- [x] Remove Q&A/Instructor/disclosure editors and authoring API fields; retain three clinical sections and eight vitals.
- [x] Add version-4 strict shared contracts and forward migration 0041 for catalogs, drafts, published/private snapshots and historical conversation prompts.
- [x] Keep tenant authorization, independent review, transcript history and audit; reject removed fields at API/database boundaries.
- [x] Adapt local device patient dialogue to clinical facts, without a question bank.
- [x] Verify populated upgrade, current authoring flow, tenant starter creation, UI controls and mocked companion.
- [x] Repair historical training integration fixtures that depended on the retired /profiles API: resolved in the follow-up review below. Live Pi/cloud/model verification remains deferred.

- [x] Apply verified local backup/migration 0041, restart API/UI and verify live v4 schema and cleaned records. Browser preview: 65 layouts/themes/zoom checks passed.


## Scenario follow-up review - 2026-10-04

- [x] Fix training admission to use current local model assignments; migrate historical profile-dependent training fixtures.
- [x] Reject JSON/analysis/partial local replies using the shared output validator.
- [x] Allow an empty symptom to be saved as an incomplete draft.
- [x] Add forward 0042 to preserve current source references across the format-only conversion without discarding author edits.
- [x] Resolve the previously reported 11 training fixture failures: all 11 now pass with current model configuration.
- [x] Complete final verification, backed local migration 0042 and restart for review fixes; API/UI readiness both return 200.


## Tenant onboarding alignment - 2026-10-04

- [x] Align wizard review/completion with active specialties, inactive editable cases/profile, and published system starter availability.
- [x] Remove stale QnA Settings copy and replace obsolete starter documentation with the current v4 lifecycle.
- [x] Verify wizard/Settings UI, TypeScript, and all tenant provisioning routes on disposable PostgreSQL: 23 UI tests and 10 database integration tests passed.


## Desktop-only Practice - 2026-10-04

- [x] Remove web Practice and patient-setup pages, components, server actions, navigation and Settings destination.
- [x] Preserve Practice API/database support and tenant defaults for the desktop app, following the user's clarified scope.
- [x] Let desktop users select published scenarios and languages without web setup; preserve explicit saving and revision checks.
- [x] Verify affected web tests, desktop setup/restore/save flows, TypeScript and desktop static checks.


## Dedicated session start page - 2026-10-04

- [x] Replace the Start session popup with /sessions/new and a responsive form, summary, duration presets and confirmation.
- [x] Preserve tenant context, align start permissions with the API, filter unenrolled devices and handle validation, loading and request failures.
- [x] Verify affected UI/server actions, TypeScript, and desktop/mobile/dark layouts without starting a real device session.


## Tenant and role review - 2026-10-04

- [x] Review tenant provisioning, administrator/member lifecycle, role grants, department scope, device access and session controls; exclude human-test desktop implementation.
- [x] Make trainee device summaries and personal settings reachable with their existing grants.
- [x] Align session stop and feedback UI with instructor capability and session ownership; retain authoritative API checks.
- [x] Allow revoking saved responsibilities after role/scope changes; disable controls until assignments load and offer retry.
- [x] Remove unused TenantUsersPanel and its orphaned web actions/types/tests after the earlier Users-tab removal.
- [x] Exercise real browser login/navigation/routes for all four tenant human roles on disposable PostgreSQL.
- [x] Finish broad database regression review and resolve confirmed failures.

## Cloud model review - 2026-10-04

- [x] Review create/edit/delete, provider/type validation, encrypted credentials, device selection and runtime adapters.
- [x] Add a bounded, authorized, revision-fenced cloud connection check with redacted audit results.
- [x] Preserve provider-specific settings during edits; expose temporary AWS credentials, Whisper API selection, reply limits, speech formats and conversation compatibility controls.
- [x] Correct Azure resource synthesis path and use the speech-recognition service for ASR access checks.
- [x] Verify provider matrix, security/lifecycle guards, adapters, UI/server actions and responsive browser flow with mocked external calls.

## Device model configuration review - 2026-10-04

- [x] Review platform authorization, tenant/department lifecycle, four model slots, local/cloud mode, stale revisions and device runtime configuration.
- [x] Clear stale dialog data on reload/device change and prevent submitting selections for the wrong device.
- [x] Share lifecycle blockers between model choices and saving; display actionable tenant/department/retirement reasons.
- [x] Keep conversation configuration available when optional cloud speech recognition is disabled, while preventing speech execution.
- [x] Finish device isolation, clearing, transfer, concurrent-save, browser and static verification.


## Human-test desktop compatibility review - 2026-10-04

- [x] Align launcher/client handling of disabled and job-only speech; preserve typed conversation access and block unsupported microphone capture.
- [x] Apply model reload on the asyncio worker, refresh scenario/language setup, show all device assignments, and handle stale/failed dialog responses.
- [x] Validate all eight observations against the current contract and accept published scenarios with initially missing vitals for manual entry.
- [x] Remove unused local activation/publication/control code that called retired APIs; update current setup instructions.
- [x] Permit ordinary authorized staff to close their own published-scenario conversations; retain owner, scope, lifecycle and legacy author checks.
- [x] Complete final desktop, launcher, isolated PostgreSQL/API and static verification; record evidence and limitations.


## Human-test final desktop review - 2026-10-04

- [x] Restore model reload controls after cancellation and refresh the main setup after a committed reload even if its dialog closes.
- [x] Cancel and await sibling readiness probes on failure/cancellation; validate local execution before constructing probes.
- [x] Retain the exact conversation-start payload across uncertain retries and clear it on reset/setup changes.
- [x] Verify regressions, full desktop suite, disposable PostgreSQL/API recovery and static checks; record skipped checks and remaining live-verification limits.

## Fresh Ubuntu VM deployment - 2026-10-04

- [x] Verify the VM identity, managed release and exact application database before the authorized reset.
- [x] Build current API/UI sources, verify transfer integrity, take a private recovery backup and recreate device_platform.
- [x] Deploy the current API, web, worker and retention services through the managed Ubuntu script.
- [x] Verify schema 0042, empty tenant/account/device data, three model defaults, runtime privileges, HTTPS and desktop/mobile first-administrator setup.


## 2026-10-04 Device-only Human-test pairing and schema synchronization

- [x] Add responsive device-ID/enrollment-token setup, private atomic credential storage, automatic reconnect, progress, cancellation and actionable errors; no human login required.
- [x] Restrict device Practice to its tenant/department, assigned models and private selections/conversations; preserve human authorization, quotas, revocation and audit attribution.
- [x] Add forward migration 0043_device_practice; align ORM, readiness, deployment backfill compatibility, runtime grants and the database sync checker.
- [x] Back up and synchronize the configured local database; deploy the VM forward without resetting user-created data; verify both databases against ORM/types/nullability/ownership/grants.
- [x] Verify desktop, launcher, disposable PostgreSQL pairing/schema/migration tests and static checks; see review evidence for historical test-fixture limitations.
- [ ] Full legacy PostgreSQL suite still contains fixtures targeting removed /llm/connections APIs; migrate those fixtures separately. No live cloud inference or hardware acceptance claimed.

- [x] 2026-10-04 requested latest VM redeployment: release 20261004-125312-109062; API/UI healthy, schema 0043 verified, private backup and existing-record preservation confirmed.


## 2026-10-04 - Desktop provisioning management and offline downloads

- [x] Add a single icon in the desktop header to reopen provisioning after normal session/owned-service cleanup.
- [x] Add explicit local provisioning reset; remove generated credential files, prevent legacy reconnect, preserve model/media/history data and server registration.
- [x] Add supported Qwen/Whisper/Piper/video-runtime installation UI with automatic locations, CPU default/optional CUDA, progress, cancellation and retry.
- [x] Serialize installation/reset with managed services; bound/redact progress, strip inherited credentials and stage Whisper before a local-only load check.
- [x] Fix CPU-only Qwen startup when repository configuration prefers CUDA; verify launcher, desktop and native Tk behavior.
- Verification limitation: model downloads were mocked; no new multi-GB downloads, live cloud inference or hardware microphone/camera checks were performed for this change.


## 2026-10-04 - Human-test provisioning, downloads and session review

- [x] Acquire the shared app ownership lock before enrollment/resume, retaining ownership through companion startup; reject concurrent setup without sending enrollment requests.
- [x] Stop unsent requests after cancellation while preserving a successfully issued device credential; handle malformed platform errors safely.
- [x] Repair damaged Whisper files through verified staging, restore the old directory if publication fails, and check repair/CUDA disk requirements.
- [x] Show allowlisted actionable installer errors, tolerate invalid local metadata, ignore late UI events on close, and restrict Enter-to-connect to the connection tab.
- [x] Expand real API/disposable PostgreSQL coverage to actual desktop Controller turns, local telemetry, history isolation, conversation reset and device revocation across local/cloud and department scopes.
- [x] Run desktop, launcher, API unit suites, native Tk and isolated database checks; stop disposable PostgreSQL afterward.


## 2026-10-04 - Deployed login recovery after an update

- [x] Diagnose reported generic sign-in connection failure against the hosted services and a fresh browser.
- [x] Detect Next.js unrecognized Server Actions on login; clear the password, block replay, and provide an explicit full-page refresh.
- [x] Test login/session behavior and production compilation, deploy through the standard protected workflow, and verify stale-action recovery against the live HTTPS site.


## 2026-10-04 - Human-test inventory HTTP 422 on manikin enrollment

- [x] Remove obsolete laptop-only restrictions from authenticated inventory reporting and platform inspection; preserve device identity, lifecycle and model-name validation.
- [x] Show bounded, redacted, actionable desktop inventory errors.
- [x] Verify manikin/laptop enrollment, inventory and local/cloud practice with disposable PostgreSQL; deploy the fix and verify the saved desktop credential against the VM.


## Automatic training signing configuration - 2026-10-05

- [x] Provision private Ed25519 signing keys automatically for fresh local setup, local startup and managed VM deployment; preserve existing identities across upgrades and concurrent setup.
- [x] Validate API-account access and startup verification, preserve other settings, fail closed on broken configured keys and restore configuration on deployment failure.
- [x] Verify Windows provisioning, isolated Linux role permissions, API and launcher regressions, packaging exclusions and the local installation; record database-test skips and limits in the review log.
- [x] Add Previous navigation before Complete & Close in human-test and verify the native layout and return to setup.


## 2026-10-05 - Assigned device session queue

- [x] Per-device web queue: batch trainee planning, per-user case/language/duration, edit/remove/reorder, pause/resume, active end and history/results.
- [x] Human-test assigned defaults and trainee identity, explicit Begin, Previous, sequential handoff and web/desktop completion; retain standalone practice without a ready assignment.
- [x] Fixed 24-hour expiry from queue creation for waiting/running sessions, independent of edits/start; server maintenance, database invariants and short runtime leases.
- [x] Scoped API authorization, atomic audits, concurrency/idempotency, forward migration 0044 and least-privilege runtime grants.
- [x] Local unit/integration, native desktop and mocked browser verification; evidence and limitations recorded in pms-api-reviews.md.
- [x] Deploy hosted API/web/migrations/grants together (2026-10-05); verify HTTPS readiness, schema/ORM/grants, preserved records and training signing identity.
- [ ] Update other Human-test installations and verify complete hosted practice/physical-device workflows; deployment health checks do not establish end-to-end hardware behavior.

- [x] Final queue review: fixed stale edit revisions, delayed planning responses, assignment-edit/Begin race, bounded display queue lifecycle recovery and learner-picker/admission scope mismatch; added regression coverage (2026-10-05).


## 2026-10-05 - Session archive synchronization

- [x] Default enrolled-device local/cloud archive identity, immutable selected case/vitals and model context; standalone practice remains unassigned.
- [x] Nonblocking bounded capture, independent durable journal/uploader, foreground pause and upload/hash rate limits; resume after lost acknowledgements, restart and GUI exit.
- [x] Private resumable checksummed API, scoped result access, concurrent capacity limits, completion manifest and policy retention independent of 24-hour assignment expiry.
- [x] Web Recordings & sync tab with paginated history, private streamed media and honest pending/incomplete/expired states; desktop retry action.
- [x] Forward migration 0045, grant/readiness updates, regression tests, performance/failure-path review and operator documentation in [recording sync](session-recording-sync.md).
- [x] Roll out hosted API migration/grants and web (2026-10-05), including authenticated recording proxy checks; current workspace already contains the desktop implementation.
- [ ] Update other desktop installations and validate end-to-end sync, real cloud storage and target hardware before claiming production performance or durability.


## 2026-10-05 - Local database/schema synchronization

- [x] Back up and upgrade the configured local application database from 0043 to 0045; reapply the current runtime grant bundle and independently verify schema/ORM/script alignment.
- [x] Extend the existing database sync script with primary-key matching, API-only queue/archive privileges and enabled lifecycle-trigger checks; enforce private Windows backup-directory access.
- [x] Exercise schema and permission regressions against disposable PostgreSQL; preserve the frozen SQL baseline and existing ORM mappings.


## 2026-10-05 - Plan sessions dialog usability

- [x] Align default/per-trainee controls; add a searchable picker, numbered reorderable session cards, clear empty states and a persistent action footer.
- [x] Preserve settings and request identity; verify responsive themes, long queues, keyboard focus, dismissal and component regressions.
- [x] Deploy the reviewed planner UI to the hosted platform (2026-10-05); production build, HTTPS assets and service health verified.


## 2026-10-05 - Sessions workspace, history and detail UX review

- [x] Unify queue, history and recording views with accessible tabs, responsive rows, lifecycle badges and clear device status.
- [x] Provide immediate session/recording detail dialogs, readable conversations, explicit loading/error/retry/pagination and late-response guards.
- [x] Preserve planner behavior and older-session navigation; verify component regressions, CSS references, responsive themes and keyboard interactions in the browser.
- [x] Deploy the reviewed Sessions UI to hosted release 20261005-131148-135440 (2026-10-05); verify schema/grants, preserved records/key, five services and public Sessions asset checksums.


## 2026-10-05 - Members directory presentation

- [x] Improve member identity, filters, sorting, lifecycle badges, management menus and import navigation.
- [x] Style member details and invitation forms; preserve access restrictions, versions and private link behavior.
- [x] Verify component regressions, responsive/dark layouts, menu keyboard behavior and empty/error states.
- [ ] Deploy the reviewed Members UI when requested; hosted Members remains the preceding version.


## 2026-10-06 - Session sync durability and retry fixes

- [x] Flush server local storage and durably publish blobs before chunk acknowledgement; cover uncertain write/retry and publication failures.
- [x] Wait for detached uploader ownership handoff; recover uploader failures and retry SQLite contention on background workers; reject intake after fatal journal failure.
- [x] Persist fair item/manifest retries and classify quota, expiry, permanent and credential failures; support explicit retry after restored scope access.
- [x] Separate capture completeness, transfer progress and local result-save status; show media/result deadlines while honoring existing tenant retention.
- [x] Add sync regressions, isolated PostgreSQL archive/storage tests, desktop local/cloud compatibility checks and UI coverage; run relevant full suites, lint, format and types.
- [ ] Verify sustained performance and power-loss recovery on target hardware before making production durability guarantees; queued/unflushed capture remains a bounded loss window.
- [ ] Update seven obsolete optional-history integration fixtures using the removed model-creation endpoint before those broader tests can verify business behavior.
- Implementation and verification: see [sync guide](session-recording-sync.md#durability-and-retry-corrections---2026-10-06) and the 2026-10-06 implementation entry in [review evidence](pms-api-reviews.md). Live cloud, hardware and hosted rollout remain deferred.


## 2026-10-06 - Patient background and local-first conversation

- [x] Implement optional version-5 background, bounded author choices and stable session selection; preserve version-4 cases.
- [x] Add forward migration 0046, runtime grants/readiness, review/publication/copy/practice and device/desktop compatibility.
- [x] Add Patient background authoring tab, independent language review and previews; preserve background when refreshing a clinical-only source.
- [x] Compile a compact snapshot once; retain one plain-text generation, 128-token local default, two pairs, exact native fitting and bounded error-invalidated caches.
- [x] Persist private snapshots off the UI thread, reject conflicts/unsafe links, recover queue rejection and preserve durable result sync.
- [x] Export unreviewed starter restoration drafts and add the 20-question matrix; complete focused/full checks and native measurements.
- [ ] Roll out when requested: migration 0046, runtime grants, API/UI/companions and reviewed replacement cases.
- [ ] Qualify additional models/languages, near-limit native cases, explicit clarification behavior and sustained audio/hardware timing; no broad semantic guarantee.
- Evidence: [phased TODO](patient-background-todo.md), [review](patient-background-review-20261006.md), [authoring/benchmark guide](simulations/patient-background/README.md).


## 2026-10-06 - Patient background: two follow-up review passes

- [x] Review 1: fix device session admission on unavailable/stale translations and preserve the last two completed history pairs.
- [x] Review 2: account for retained/partial snapshots in local and recovery quotas; reserve capacity durably and reuse it on retry.
- [x] Review 2: fix immediate disk-failure activation race so begin admission can retry.
- [x] Add regressions, rerun affected and broader checks, inspect the final changes and record limitations.
- Evidence: [two-pass review](patient-background-two-pass-review-20261006.md).


## 2026-10-06 - Native patient-background local-model qualification

- [x] Run real Qwen3.5-4B at a 2,048-token context over known, missing, mixed, follow-up and general questions.
- [x] Fix confirmed grounding, routing, reply-validation and prompt-size findings; repeat four 25-question sets twice.
- [x] Complete two grounding/validation reviews and final compatibility/security review; rerun affected regressions and required checks.
- [x] Record all 200 final answers, actual settings, native budgets and timing limits.
- [ ] Separate qualification: sustained shared-GPU Whisper/TTS/capture timing, other models/languages and target hardware.
- [ ] Separate existing shared schema/registry typing debt: 26 errors reproduced in the committed baseline.
- Evidence: [native qualification](patient-background-local-qualification-20261006.md), [feature TODO](patient-background-todo.md).


### Human-test conversation performance, 2026-10-06

Implementation and qualification: docs/conversation-performance-todo.md.
- [x] Add privacy-safe stage timings and a fictional combined local benchmark.
- [x] Fix ASR runtime GPU allocation and overlap durable saving with gated speech.
- [x] Add bounded synthesis/playback overlap, PCM reuse and playback fallback.
- [x] Execute native qualification and two final reviews; record actual latency and accuracy gaps.

- [ ] Meet the strict warm latency gate and qualify real microphone/deployed session.

### Cross-scenario local conversation qualification, started 2026-10-06

- [x] Prepare nine starter scenarios with ten spoken questions each.
- [x] Execute the 90-question baseline ASR/model/journal/speaker matrix with private fictional evidence.
- [x] Fix confirmed mixed-intake, clinical-followup scope and general-answer findings.
- [ ] Repeat affected scenarios, run shared/API/desktop checks and review twice.


### VM and local database synchronization, 2026-10-07

- [x] Inspect the current managed VM release, schema, services and private preservation snapshot.
- [x] Back up and upgrade the idle local application database to 0046; verify ORM/grants and preserved models.
- [x] Build and checksum the current API/shared/UI release; run affected verification.
- [x] Deploy with protected VM backup and forward migration; preserve signing identity, model rows and tenant records.
- [x] Verify five services, HTTPS readiness/authentication and source/UI checksums independently.
- Evidence and explicit historical test limitations: docs/vm-update-20261007.md.


### Portable Human-test Windows package, 2026-10-07

- [x] Add native launcher, isolated private Python runtimes and frozen wheel builder.
- [x] Preserve enrollment/sync boundaries; exclude all credentials, state and media.
- [x] Keep portable model downloads on bundled interpreters without uv sync.
- [x] Build CPU/CUDA archives, verify relocation/integrity and review the final package.
- [ ] Qualify on a separate clean Windows machine, including microphone/GPU and live sync.

### Portable hosted API and GPU defaults, 2026-10-07

- [x] Share the hosted HTTPS default between pairing, launcher and desktop/API settings.
- [x] Set every portable build to 20 GPU layers and 2048 tokens; retain lower overrides and CPU fallback.
- [x] Add endpoint/layer/default-serialization regressions and native package checks.
- [x] Finish full desktop checks, rebuild both ZIPs and verify the final archives.


## Human-test executable IP protection - 2026-10-07

- [x] Default release compilation of 15 conversation/model/speech/durable-sync
  modules to Windows x64 Python 3.12 Cython extensions.
- [x] Remove protected source and bytecode; bytecode remaining first-party code
  and retain only script entry shims. Preserve third-party licenses and resources.
- [x] Isolate and pin build tools; compilation failure aborts distribution.
- [x] Add source/compiler-artifact release gates and protection manifest checks.
- [x] Fix Windows linker path limits; verify portable recording process startup.
- [x] Verify final protected CPU/CUDA archives after relocation and record results.
- [ ] Complete Windows machine acceptance with live GPU/microphone/cloud sync.
- [ ] Confirm the one-model-per-component selection before bundling weights.


## Human-test build review and release fixes - 2026-10-07

- [x] Review source/resource copying, native/bytecode inventory and launcher paths.
- [x] Isolate incomplete builds and ZIP writes under staging/partial names;
  distinguish protected releases from debug-source builds.
- [x] Compare archived bytes with manifest hashes and reject changed files.
- [x] Restrict resources and reject linked/junction parents and private state.
- [x] Remove build caches; strengthen source/type-stub/compiler-artifact gates.
- [x] Verify optional CUDA package imports in the CUDA self-test.
- [x] Add and pass 16 build regression tests, including failed/archive mutation.
- [x] Verify rebuilt CPU/CUDA releases, extracted startup and recording imports.
- [ ] Clean-machine live hardware/model/cloud sync qualification remains pending.

- [x] Fix isolated interpreter paths for bundled setup/Qwen launch scripts;
  enforce installer/Whisper CLI startup in portable self-test.


## Protected desktop downloads - 2026-10-07

- [x] Add account-menu Downloads link between separators above Sign out.
- [x] Add responsive Desktop portable directory, CPU/GPU editions and setup notes.
- [x] Authenticate listing, GET, HEAD and resumed downloads for active admins.
- [x] Stream without full ZIP buffering or a held database connection.
- [x] Add private persistent VM storage and an atomic verified release publisher.
- [x] Verify regression tests, production build and real disposable PostgreSQL access.
- [x] Complete VM installation and live authenticated download verification.


## Downloads follow-up review - 2026-10-07

- [x] Review account menu placement, permissions, keyboard and pointer activation.
- [x] Pin page links to the displayed release digest; reject changed-release resumes.
- [x] Correct status-specific download errors and bodyless HEAD errors.
- [x] Preserve immutable ZIPs under concurrent publication and derive copied size.
- [x] Sync publication metadata/directory entries; reject broken catalog links.
- [x] Run regression, disposable PostgreSQL, full UI/API, typing and build checks.
- [x] Complete hosted download and Linux publisher verification of this review.


## Member workbook compatibility - 2026-10-07

- [x] Remove blanket macros/formulas/external-links rejection, including normal email hyperlinks.
- [x] Read cached formula values; report specific missing results and Excel error cells.
- [x] Preserve bounds, safe XML parsing, column/identity checks and tenant permissions.
- [x] Add regressions and verify actual validate/commit with disposable PostgreSQL.
- [x] Review twice and fix saved empty-password handling and stale migration test.
- [x] Deploy and verify installed parser plus API/UI readiness on the VM.


## Short desktop download names - 2026-10-07

- [x] Save downloads as Desktop-App-GPU.zip or Desktop-App-CPU.zip.
- [x] Show Download Desktop App links and short filenames in file details.
- [x] Use matching short extraction folders in future CPU/GPU builds.
- [x] Preserve private immutable storage, digest pinning, checksums and resume.
- [x] Verify API/download/page/archive checks locally; leave the VM untouched.


## Enrollment token visibility - 2026-10-07

- [x] Explain that credential status becomes active after enrollment, not token issuance.
- [x] Show a dedicated token-ready dialog with Device ID, Copy token and manual-copy fallback.
- [x] Show successful issuance immediately; retain the token across status refresh failures.
- [x] Hide tokens on expiry, dismissal, lifecycle restrictions or scope/permission changes.
- [x] Guard overlapping submissions; retain explicit confirmation and server authorization.
- [x] Review twice; verify web regressions, TypeScript checks and production build locally.
- [x] Preserve the user's local-only scope; no VM update or live enrollment.


## Tenant-admin enrollment for laptops and manikins - 2026-10-07

- [x] Verify the tenant role grant and UI/server action/API paths do not filter by device type.
- [x] Explicitly test tenant-admin issuance and copying for laptop and manikin records.
- [x] Verify real issuance, redemption, activation, single use and revocation on isolated PostgreSQL.
- [x] Preserve tenant scope, role permissions, version checks and lifecycle restrictions.
- [x] Fix stale fleet-summary assertions and desktop inference fixtures exposed by broader verification.
- [x] Review twice and complete affected tests, API lint/format/mypy and UI TypeScript checks.
- [x] Keep these changes local; do not deploy or publish.


## Enrollment/download fixes review and VM deployment - 2026-10-07

- [x] Review the pending fixes before deployment and fix the shared configuration/enrollment error race.
- [x] Regress delayed configuration completion while an issuance error is visible.
- [x] Complete the full web suite, API affected checks, typing/lint and production build.
- [x] Build and verify the deployment archive against reviewed working source and SHA-256 manifest.
- [x] Record the VM baseline and verify a private PostgreSQL backup before upgrading.
- [x] Deploy API/UI and synchronize runtime database grants with schema 0046_patient_background.
- [x] Verify source hashes, data/models/signing/catalog preservation and all managed services.
- [x] Verify hosted tenant/admin access, short desktop attachment names, range/resume and workbook parser.

## Portable GPU setup diagnostics and bundled models - 2026-10-07
- [x] Confirm immediate startup failure: no local Qwen/Whisper models installed; saved enrollment succeeds before local preparation.
- [x] Fix suppressed setup errors, failed state, cancellation handling and cleanup progress overwriting the error.
- [x] Add bounded private launcher/installer logs, stage timings, safe structural traces and categorized Qwen installer failures.
- [x] Add explicit --cuda --bundle-models build and reusable build-desktop-gpu.bat; include only verified public Qwen 3.5 4B, Whisper large-v3, Piper voice and CPU/CUDA runtime assets.
- [x] Regression checks: 226 startup/build cases pass; 563 desktop cases pass with 6 skips; native connection/retry UI smoke passes.
- [x] Finish final protected build, qualify extracted bundled models and review final artifacts.
- [x] Publish the verified GPU artifact to the private platform Downloads catalog and confirm download behavior.

## Fresh CPU and GPU portable releases - 2026-10-07

- [x] Build and qualify both protected editions with the latest setup diagnostics fixes.
- [x] Verify private-state exclusions and publish both exact ZIPs to VM Downloads.
- [x] Review twice and record live access, integrity and readiness verification.

## VM temporary-artifact cleanup - 2026-10-08

- [x] Inspect staging folders and database artifacts, remove confirmed temporary files, and verify live releases, downloads and database health.


## Session assignment device confirmation - 2026-10-08

- [x] Review the destination device name/ID and session order before creating queued assignments.
- [x] Allow changing the device in the planner, preserve selected settings, reload eligible trainees and block unavailable selections.
- [x] Preserve retry identity and duplicate-submit prevention; select the confirmed device's queue after saving.
- [x] Verify 33 affected UI tests, TypeScript, and mocked desktop/mobile/light/dark browser flows; evidence is recorded in pms-api-reviews.md.
- [ ] Deploy this web UI change to the hosted server when requested.


## Compact starter scenarios - 2026-10-08

- [x] Correct the two fictional starter documents and both translations; separate clinical timing, family history, prescriptions and concise background facts.
- [x] Provision corrected schema-5 starters through all tenant creation routes; verify content as well as source revision.
- [x] Add forward migration 0047: version unchanged existing starters, preserve customized sources and historical/live records, honor capacity and tenant audit retention.
- [x] Correct compiler 36 family, education, prescriber and event-meal selection; verify native 2,048-token fitting and protected Windows modules.
- [x] Run isolated PostgreSQL regressions, relevant application tests, Ruff and mypy; record skipped checks and existing fixture limitations.
- [x] Apply the authorized VM database upgrade after backup and verify scenario version 2 plus unchanged conversations and archives.
- [ ] Modernize legacy scenario-library tests that still submit retired schema-2 authoring documents; the existing 422 fixture failure is recorded in review evidence.

- [x] Deploy final server code, publish both verified protected desktop downloads, and publish scenario changes through git publish --dry-run followed by git publish.


## Live scenario evaluation and combined session view — 2026-10-09

- [x] Run actual assigned chest/wheeze conversations on the enrolled laptop against the VM; preserve unchanged baseline questions and review answers manually.
- [x] Refine fictional stock facts and new-tenant provisioning with forward migration 0048; preserve customized and historical records.
- [x] Correct scope selection with compiler 38, one generation and exact total 2,048-token fitting.
- [x] Enable conversation-history reporting defaults and the current laptop/VM saved settings.
- [x] Combine session history and captures into one scoped list/details view; show completion, sync and saved/expected items distinctly.
- [x] Fix omitted device department in history/metrics reports without bypassing ownership or frozen context.
- [x] Verify supported isolated DB/device flows and actual native conversations; record skipped tests and older fixture failures explicitly.
- [x] Apply the authorized VM database upgrade and deploy API/UI; leave desktop downloads unchanged.
- [ ] Improve explicit naming of unknown parts in compound answers and remove repeated wheeze-relief wording; these are recorded response-quality limits, not execution failures.
- [ ] Establish a controlled native latency benchmark and broader unseen-question evaluation; current timings do not show a speed improvement.
- [ ] Modernize local-history/metrics DB fixtures that still use the removed tenant model-connection creation endpoint.


## Reliable explicit sign-out - 2026-10-09

- [x] Clear browser session/context/legacy cookies even when API revocation fails; preserve cookie security flags.
- [x] Use a native same-origin logout POST from both controls, with bounded best-effort revocation and sign-in setup checks.
- [x] Verify cross-site rejection, proxy origins, no-referrer submissions, stale action transport, JavaScript-disabled sign-out and protected-route denial.
- [x] Pass the full web suite, final affected tests, TypeScript and production build; record local browser evidence.
- [ ] Deploy to the VM when requested; the user explicitly deferred this deployment.


## Patient background tab layout - 2026-10-09

- [x] Replace crowded background fieldsets with responsive category cards, consistent spacing and expandable approved-detail controls.
- [x] Show published and restricted-viewer background as readable content; preserve saved choices, translations and editing restrictions.
- [x] Verify relevant UI regressions, TypeScript and themed desktop/mobile browser layouts; record evidence in pms-api-reviews.md.
- [ ] Deploy this UI improvement to the VM when requested; deployment remains deferred.


## Shared local model service design - 2026-10-09

- [x] Record the GPU-laptop service direction, shared model downloads/inference, operator lifecycle controls, diagnostics, client boundaries and future acceptance in [the design note](local-model-service-plan.md).
- [ ] Define authenticated capability APIs, platform host/session binding and resource admission before implementation.
- [ ] Build the independent laptop service manager, verified shared assets and local management interface; extract existing engines and migrate Human-test to the client contracts.
- [ ] Qualify independent service lifecycle, client isolation, native GPU capacity and install/remove behavior on the laptop.
- [ ] Implement and verify the Raspberry Pi client later; no Pi code, model/service installation or deployment is authorized by this documentation task.


## Local model directory rename - 2026-10-09

- [x] Rename local-llm to local-models with installed weights, runtimes, private state and configuration retained.
- [x] Update launch/import/install paths, portable source/assets/interpreter paths, test fixtures and documentation; preserve historical evidence directories and existing API/module names.
- [x] Preserve old desktop archive handling and verify new-layout packaging, launcher imports, installed model/runtime integrity and relevant regressions.
- [ ] Implement the shared background-service design later; this rename does not implement or deploy it.


## Manage Local Models desktop UI - 2026-10-09

- [x] Create the standalone Manage Local Models interface inside local-models with Overview, Models, Services, Logs and Settings.
- [x] Add navy/teal styling, local outline/title-bar icons, responsive cards, scrolling pages/dialogs, model and sample-log filters, provisioning/model/status previews and an independent launcher.
- [x] Keep all hardware/inventory/service/log values explicitly labelled sample data and leave operational controls disabled; preserve current model installers and runtimes.
- [x] Verify native layout/navigation/filter/dialog behavior, model regressions and local static checks; record review evidence.
- [x] Implement verified downloads, authenticated service provisioning/lifecycle, live status/logs and saved settings; see the operational phase below.
- [ ] Implement the shared Human-test/Pi inference gateway later; no live inference, Pi integration or VM deployment is part of this UI task.


## Manage Local Models Windows service and automatic startup queue - 2026-10-09

User explicitly queued this after the current button/manager implementation and two reviews.

- [ ] Install the manager as a genuine Windows service with a dedicated least-privileged identity and private asset/state permissions.
- [ ] Connect the Start at boot option to capability auto-start after OS restart, with verified loading/readiness and crash recovery.
- [ ] Qualify service installation/removal, startup before desktop login, machine restart, UI closure and shared inference continuity.
- [ ] Preserve models/configuration at service removal and require explicit decisions for affected active work.

The current phase must already keep the background manager and owned inference workers alive when the desktop UI closes. Windows service registration and reboot auto-start are the follow-on queue, not a claim about a detached per-user process.


## Manage Local Models operational controls - 2026-10-09

- [x] Add authenticated per-operator manager contracts, private atomic metadata, durable UUID actions, bounded logs and revision checks.
- [x] Connect model downloads/runtime preparation, provisioning, start/stop/status, remove configuration, filtered log export, diagnostics and saved defaults to the live desktop.
- [x] Reuse existing verified LLM/audio/voice assets and adapters; stage new verified assets separately and preserve working installations on failure.
- [x] Run resident model workers independently of the UI; verify actual inference continues after desktop closure.
- [x] Complete two implementation reviews, fix confirmed findings and run business/security/concurrency, native UI and native CPU inference checks.
- [ ] Next queued task: genuine Windows service installation/removal, dedicated identity and reboot auto-start; see the Windows service queue above.
- [ ] Qualify native GPU capacity/concurrency and live publisher installation/conversion paths separately.
- [x] Migrate Human-test to the authenticated central inference client; keep clinical/session authorization and immutable contexts in the existing platform/contracts.
- [ ] Implement Pi client, LAN/TLS pairing and shared-session gateway authorization before advertising remote clinical execution.

Reconciliation and limitations: [local-models/manager-review.md](../local-models/manager-review.md). The earlier UI-only entry describes the previous phase; the default desktop is now live and --preview retains the sample layout. No VM deployment, Pi code, commit or publication is included in this implementation.


## Manage Local Models final review and fixes - 2026-10-09

- [x] Preserve saved model, requested CPU/GPU, custom port and runtime options when configuring services; retain entered values on invalid/offline submissions.
- [x] Require explicit readiness and matching execution for repeated starts; reserve the actual manager/native worker ports.
- [x] Fix atomic source/manifest writes, cached-source completeness, interrupted conversion publication, verified model reuse on low disk, voice-installer exits and installer guard cleanup.
- [x] Protect managed state/model/runtime destinations from log exports; refresh service status in place with current lifecycle restrictions and manager port.
- [x] Complete the final two review/fix inspections and affected verification: 83 tests, 27 live desktop checks, 42 preview checks, native CPU and sequential CUDA inference, and verified runtime reuse.
- [ ] Next queued implementation remains genuine Windows SCM installation/removal, dedicated identity and reboot auto-start; desktop closure continuity already passed native checks.
- [ ] Qualify simultaneous GPU capacity and live publisher downloads/conversions; implement journal archive maintenance before exceeding the documented 2000-operation limit.

Evidence and boundaries: [local-models/manager-review.md](../local-models/manager-review.md). No VM update, commit or publication in this final review.


## Human-test central local model consumer - 2026-10-09

- [x] Extract reusable bounded LLM/ASR/TTS transports into local-models/client and provide verified catalog/live readiness with an inference-only credential.
- [x] Remove Human-test model installers, offline management UI, native engines, model lifecycle/cleanup, GPU settings and restart logic. Setup/start scripts only prepare the desktop or connect.
- [x] Move voice installation/locks/native runtime/verified assets and qualification tools centrally; preserve history, enrollment and recordings.
- [x] Retain microphone/speaker/camera, cloud routing, clinical contexts/fact checks, private bounded journals and durable result-before-playback behavior.
- [x] Build model-free Human-test client packages; exclude engines, weights, runtime installers and manager credentials.
- [x] Complete two review/fix passes and affected checks: 674 Human-test tests (2 opt-in skips), final 112 launcher tests, 144 central/package tests plus 41 subtests, native Tk checks and sequential CPU/CUDA inference.
- [ ] Queued: genuine Windows SCM services and reboot auto-start; Pi app/authenticated LAN pairing and video AI remain later phases.

Reconciliation, run steps and limitations: [local-model-client-migration.md](local-model-client-migration.md). No VM update, commit or publication in this migration.


## Human-test portable package cleanup - 2026-10-09

- [x] Remove GPU/model-bundling options, GPU build wrapper and legacy model-containing archive refresh workflow.
- [x] Limit source selection and native/bytecode protection to Human-test app/launcher needs; install SDK/contracts as ordinary private-runtime dependencies.
- [x] Enforce client-only package layout, runtime metadata, engine/asset/private-state exclusions and exact Human-test native module inventory.
- [x] Publish tooling accepts one protected client ZIP and retains the unchanged desktop-runtime API identifier; verify copied archive scope and file/ZIP hashes before immutable publication.
- [x] Verify 56 packaging/publication tests, actual protected executable/ZIP and extracted execution from a relocated path with spaces; lint, formatting and whitespace checks passed.
- [ ] Separate Local Models portable executable/package/download workflow remains a later task; Windows SCM/reboot startup is still queued.

Build/run details: [human-test-portable.md](human-test-portable.md). No hosted/VM update, commit or publication in this cleanup.


## Human-test requirements cleanup - 2026-10-09

- [x] Audit current runtime/script imports; remove unused WebSocket dependency and explicitly declare existing Pydantic usage. Keep microphone/playback, camera/codec, HTTP, settings and thin central-client requirements.
- [x] Regenerate the frozen lock offline without upgrading retained packages; use `uv sync --frozen --no-dev` in normal desktop setup and document separate development installation.
- [x] Verify 731 Human-test/launcher/package tests (2 opt-in live Qwen skips), exact 22-package runtime-only environment, all 27 app module imports, Tcl initialization, lock consistency and installed dependency compatibility.

Existing portable archives were not rebuilt in this requirements task; subsequent builds use the cleaned lock. No API/schema changes, model downloads, VM updates, commit or publication.


## Local Models loading/defaults and Human-test launch fix - 2026-10-09

- [x] Show animated loading across desktop pages until manager/inventory checks finish, with explicit retry after failure and no initial empty-count/action forms.
- [x] Default GPU-capable downloads/provisioning to GPU, use 20 factory GPU layers and prefer installed Qwen 3.5; preserve saved services, CPU-only support and explicit preferences.
- [x] Upgrade untouched legacy factory defaults without rewriting saved worker options; retain operator-authored settings and configuration revision checks.
- [x] Fix the reported Human-test Windows startup TypeError by serializing the manager port and typed desktop environment values before process creation.
- [x] Verify 94 manager/runtime unit tests, 27 inference-client tests, 65 Human-test startup tests, native preview/live/loading controls and Human-test setup geometry; lint/format/whitespace pass.

No inference downloads, paid cloud calls, hosted/VM changes, commit or publication. Existing portable archives require a future rebuild to include these source changes.


## Local Models provisioning runtime options - 2026-10-10

- [x] Show runtime options consumed by the selected LLM, recognition or synthesis adapter; hide GPU controls in CPU mode and unsupported Vosk/Piper tuning.
- [x] Preserve per-capability runtime drafts and saved legacy configurations; parse active inputs without letting hidden drafts block another capability.
- [x] Preserve GPU/Qwen 3.5/20-layer preferences, context-budget validation, revision checks and existing normalized worker options.
- [x] Verify 131 tests plus 50 subtests, 13 native capability-option checks, 14 loading/default checks and 27 isolated HTTP desktop checks; lint/format/whitespace passed.

No inference/model downloads, production service changes, VM update, commit or publication.


## Local tenant and native patient-practice verification - 2026-10-10

- [x] Back up the local application database, apply existing forward migrations/grants, and start the local API/web UI without API source changes.
- [x] Provision an isolated tenant, enroll this laptop and assign real local Qwen 3.5/Whisper services; preserve the previous hosted connection privately.
- [x] Run both desktop apps against installed Qwen (20 CUDA layers), Whisper CUDA and Piper CPU; verify nine typed questions plus one synthesized-speech question across chest and wheeze scenarios, history, audible output and independent service lifetime.
- [x] Fix confirmed shared emotional-evidence and intake-scope findings, preserve mixed clinical/emotional facts, advance compiler version and add ten regressions. Correct stale manager Settings copy.
- [x] Complete two review/fix passes, native service-control checks, broad API/Human-test/manager tests and affected final reruns.
- [ ] Physical microphone returned digital silence; repeat live spoken input after the laptop input is unmuted/checked. SCM/reboot startup and LAN/Pi support remain queued.

Results, credentials recovery locations and limitations: [local-practice-review-20261010.md](local-practice-review-20261010.md). No VM update or portable rebuild. Commit and publication were authorized subsequently.

## Shared client extraction - 2026-10-10

- [x] Complete the common runtime and Human-test cleanup tracked in [shared-client-todo.md](shared-client-todo.md). Raspberry Pi implementation follows in a separate phase.
- [x] Complete the requested follow-up review: fix lifecycle, playback, rejected-audio, model-dialog, camera shutdown, Tk timer and protected-package findings; rerun regression and package checks. See [review evidence](shared-client-review.md).

- [x] Complete the post-extraction live local run: two scenarios with real Qwen/Whisper/Piper, synchronized history/audio, idle-pause fix and regressions, and successful post-fix repetition. API implementation unchanged. See [live review](shared-client-live-review-20261010.md).


## Raspberry Pi framework - 2026-10-11

- [x] Complete all eight software phases in [Pi phase tracking](../pi-test/docs/todo.md): headless service, shared runtime, remote GPU grants/gateway, audio/camera adapters, cloud output, bounded streams/recovery, installation/rollback and ARM64 bundle.
- [x] Limit platform changes to validated device host bindings and scoped inference grants; preserve tenant/device lifecycle, active conversations and assigned-session limits. No schema migration.
- [x] Complete two review/fix passes and desktop/shared/API/gateway regressions, two Pi scenarios through isolated PostgreSQL, and real loopback TLS/WSS verification.
- [ ] Physical Pi/Linux service and hardware acceptance, real GPU over LAN, paid cloud and hosted deployment remain deferred. Video inference and partial live ASR are not implemented by the current model contract.

See [Pi review evidence](../pi-test/docs/review.md) for actual totals, artifacts and limitations. Nothing was committed, published or deployed for this task.


## Raspberry Pi completion implementation - 2026-10-11

- [x] Complete software phases 1-8 in [Pi completion plan](../pi-test/docs/completion-todo.md): strict/native-rate audio, streaming during capture, remote/cloud video processing, private results, shared heartbeat, readiness/recovery and deployment qualification tooling.
- [x] Keep API changes limited to owned single-execution video grants and device run cancellation, with existing quota/audit/lifecycle checks; no schema changes.
- [x] Complete two review/fix passes and regression/release verification; build Pi-test 0.2.0 and gateway 0.2.0.
- [ ] Native Linux/ARM execution and physical Pi acceptance, real GPU over LAN and paid cloud verification still require their target environments. Partial ASR remains unsupported.

Evidence and exact counts: [Pi completion review](../pi-test/docs/completion-review.md). New 24-wheel CPython 3.13 ARM64 bundle: `.test_artifacts/pi-completion/wheelhouse-arm64/`. Application services remain stopped; the disposable test DB was stopped. No commit or publication.


## Client end-to-end review - 2026-10-11

- [x] Review Human-test, Pi-test and training-client across runtime, API and packaging boundaries.
- [x] Fix HTTP 202 video submission, early assigned-video cancellation, standalone finish acknowledgement barriers, storage cookie/URL isolation, speaker reselection and late voice preferences.
- [x] Refresh stale desktop integration fixtures to current device assignments, manager inference and published schemas; verify real client/API/database journeys.
- [x] Complete two review/fix passes, affected regressions, lint/types and a refreshed ARM64 wheel bundle; stop the disposable test server.
- [ ] Native Linux/ARM hardware, systemd, real GPU/LAN, live cloud and endurance qualification require their target environments.

[Findings, exact verification and limits](client-e2e-review-20261011.md). Current Pi bundle: `.test_artifacts/client-e2e-review/wheelhouse-arm64/`. Earlier Pi bundles are superseded. Rebuild the Human-test portable executable before distributing these source changes. Application services remain stopped; no commit or publication.


## Pi-test final review - 2026-10-11

- [x] Reproduce and fix control shutdown ordering, shutdown admission, Unicode command framing and stdin truncation.
- [x] Require successful service stop before upgrade, reject dangling release links, preserve Linux deployment line endings.
- [x] Add regressions, complete final inspection/static checks and rebuild the ARM64 bundle.
- [ ] Physical Pi and native Linux/systemd/GPU/cloud qualification still require target environments.

[Pi final review](../pi-test/docs/final-review.md): Pi/shared 91 passed; API 620 passed and 411 database-dependent skips. Current bundle is `.test_artifacts/pi-final-review/wheelhouse-arm64/`. Application services remain stopped.
