# AI Evaluator web application

`@pms/web` — a Next.js 15 App Router application on React 19, built entirely from `@pms/ui`.

| Route | What it is |
| --- | --- |
| `/` | The session check: the console when signed in, the sign-in screen otherwise. |
| `/login` | Real local-account sign-in, keep-me-signed-in and recovery link; redirects a fresh installation to setup. |
| `/setup` | First-run installation verification, administrator details, review and completion. Closed once any account exists. |
| `/forgot-password` | Request a password reset link with an account-neutral response. |
| `/account/setup` `/account/password-reset` `/account/email-change` | Complete a purpose-bound, one-time account action from email. |
| `/home` | The dashboard for the signed-in role. |
| `/tenants` | Persisted tenant directory with search, filters, paging and an Administrator popup for users and devices. |
| `/tenants/[tenantId]` | Tenant overview, primary contact and record information; Edit, Copy ID and confirmed Delete. |
| `/settings` | Permission-aware Settings cards for administrators; personal settings preview for tenant users. |
| `/users` `/users/[userId]` | Persisted platform account directory, details, local creation/setup, role/profile editing and lifecycle management. |
| `/members` `/members/[memberId]` | Persisted tenant membership directory, invitations, role/department editing and lifecycle management. |
| `/invitations/accept` | Explicit, identity-bound acceptance with an existing session or inline local sign-in. |
| `/models` `/departments` `/sessions` `/reports` `/recordings` | Additional console destinations; remaining preview screens state their limitations. |
| `/logs` `/logs/[logId]` | Persisted, scoped audit/activity logs with filters, cursor paging and direct details. |
| `/icon.svg` | The favicon, via Next's file convention. |

## Tenant associations

The `/tenants` directory has an **Administrator** button immediately after **View** on each row. Its popup has lazy-loaded **Users** and **Devices** tabs, using the shared modal, tabs, search fields, tables, pagination, notices and confirmation dialogs. Users supports existing-account search and association, tenant role changes, enable/disable, removal and disabled restoration. Devices supports registration, searching other tenants for transfer, rename, activate/deactivate and permanent registration removal. Searches, failures and optimistic concurrency remain server-backed; global accounts, other memberships and historical device data are retained.

For a real browser regression, start a separate Next CLI development server with `PMS_WEB_INSTANCE=3125`, `PMS_API_BASE_URL=http://127.0.0.1:8139/api/v1` and port 3125. Set `PMS_TEST_ADMIN_DSN` only to a dedicated disposable PostgreSQL server and `PMS_ASSOCIATIONS_WEB_ORIGIN=http://127.0.0.1:3125`, then run `uv run pytest -q -s tests/test_tenant_associations_web.py` from `platform/api`. This fixture starts/stops API 8139 and creates/removes its own database/roles. Screenshots and sanitized results go to `.test_artifacts/tenant-associations-20260928`. Run database/browser fixtures separately on resource-constrained Windows machines.

## Signing in

Settings > Users & administrators offers two creation roles: Platform administrator and Tenant administrator. The latter requires a tenant selection and creates a pending invitation together with account setup. The result distinguishes queued setup mail from invitation delivery and offers a secure invitation link when mail is unavailable. Self-disable and self-archive controls are unavailable and the API also rejects these actions.

Local development uses Turbopack. Development output is isolated in `.next-dev-<instance>`; production builds continue to use `.next`. Set `PMS_WEB_INSTANCE` to a different short alphanumeric name for each simultaneous development server (the Windows launcher uses its UI port). Use the Next CLI so every compiler process reads the same configuration. Sharing a generated directory between servers or running a build over a development directory can cause missing JavaScript and permanently loading pages. First visits still compile in development; production deployment uses `npm run build` then `npm run start` with HTTPS. Console navigation has a shared loading state, and directory requests stop displaying skeletons after 20 seconds and offer Retry; late results cannot replace a newer retry.

Configure the server-only `PMS_API_BASE_URL` (default `http://127.0.0.1:8000/api/v1`). Copy [.env.example](.env.example) to `.env.local` for local development. HTTPS is required for a remote API; loopback HTTP is allowed. Never use a `NEXT_PUBLIC_` variable for authentication secrets or credentials.

Apply the current API migration head and runtime grants before starting this version. Enable local authentication and configure signing/encryption keys in the API environment. A fresh installation opens `/setup`: paste the private `PMS_INITIAL_SETUP_KEY`, choose the administrator's name/email/password, and review before creating the account. The API generates an Argon2id hash and commits the account and audit record together. No administrator is seeded from a script or environment password. `init-local` generates the installation key; it is never returned by the API or stored in browser persistence. Setup is disabled once any identity exists. See [API provisioning](../../../api/README.md#first-run-web-setup-recommended-for-password-accounts). Configure SMTP and `PMS_ACCOUNT_ACTION_BASE_URL=https://your-web-host/account` for subsequent invitations and recovery; existing administrators create additional accounts in the console. There are no shared/default login credentials.

The browser calls same-origin Next server actions. Next exchanges credentials with `/auth/browser/login` and stores only an opaque session credential in an HttpOnly, SameSite=Lax cookie. Production uses a Secure `__Host-` cookie and requires HTTPS. Browser sessions have a configurable 24-hour server limit (PMS_LOCAL_BROWSER_SESSION_HOURS); Keep me signed in preserves the HttpOnly cookie across browser restarts until that deadline, while an ordinary cookie ends when the browser closes. The API stores a peppered token hash, verifies account status and credential version on every request, and revokes the session on logout. The console rechecks open sessions every minute and on tab focus, clearing invalid cookies and returning to sign-in; temporary API outages leave cookies in place. Stable browser credentials avoid refresh-token rotation races between tabs.

The server obtains identity and each active access context from `/auth/context`, without caching across requests. Context selection is checked against this response; platform and organization grants are kept separate. The obsolete demo cookie has no authority. Accounts without an active access context receive an administrator-contact notice.

Setup, recovery, password change and email confirmation use real API endpoints. New email links carry action tokens in URL fragments; the page removes them from the address bar and requires an explicit submission. Legacy query links remain accepted. Password/email changes revoke all prior sessions. Explicit sign-out clears the browser's session, context and legacy cookies before one best-effort API revocation with a two-second timeout, then returns to sign-in even if the API is unavailable. During an outage, API revocation cannot be confirmed; a separately copied credential can remain valid until its server expiry or another revocation. The rail and account menu use a native, same-origin POST to `/logout`, independent of server-action bundle versions. The sign-in setup-status check also has a two-second timeout. Server actions use the framework's same-origin checks; deploy behind a trusted proxy that preserves the actual host and scheme. The logout route validates Origin against Host and the proxy's scheme; missing or null Origin under the no-referrer policy requires browser Fetch Metadata declaring `same-origin`. Cross-site requests are rejected and no redirect destination is accepted from input. API ingress limits must account for the Next server's source address, since this adapter does not trust or forward arbitrary browser IP headers.

Google/Microsoft browser login remains unavailable; existing API OIDC support is unchanged. Remaining fictional directories are labelled **Preview data**. User and member management use the authenticated API and PostgreSQL.

## Browser regression

The repeatable browser journey uses a real production Next build, an installed Chromium browser, and a disposable PostgreSQL database with unprivileged API runtime grants. No live SMTP/OIDC/cloud services are used. Set `PMS_TEST_ADMIN_DSN` only to a dedicated disposable server, then run from `platform/api`:

```powershell
uv run python tests/browser_fixture.py
```

In separate terminals, from `platform/ui`, build and start with the fixture API:

```powershell
npm run build --workspace=@pms/web
$env:PMS_API_BASE_URL='http://127.0.0.1:8133/api/v1'
npm run start --workspace=@pms/web -- --hostname 127.0.0.1 --port 3123
```

From `platform/ui/apps/web`, run `node tests/browser-login.mjs`. The runner uses installed Edge on Windows; set `PMS_TEST_BROWSER` to another Chromium executable. Test-only loopback control routes expose synthetic action tokens to this runner using a random secret in ignored artifacts; they are never registered by the production app. Stop the fixture with Ctrl+C so its database and runtime roles are removed. Evidence contains check names only, never credentials or action tokens.

### First-run browser regression

For the separate first-run journey, run `tests/setup_browser_fixture.py` from
`platform/api` against a dedicated disposable PostgreSQL server. Start Next in
development mode on port 3124 with
`PMS_API_BASE_URL=http://127.0.0.1:8134/api/v1`, then run
`node tests/browser-initial-setup.mjs` from `platform/ui/apps/web`. It verifies
empty-install redirects, wrong keys, password confirmation, desktop/mobile
review, hashed account/audit creation, stale-tab closure and actual login. The
runner shuts down its API fixture; stop the temporary Next process afterward.
Ignored screenshots and sanitized results are saved under
`.test_artifacts/initial-setup-20260926`. No cloud or email delivery is exercised.

## Roles and permissions

The API supplies authoritative permissions for the selected context. Read-only and trainee accounts reuse the tenant-user navigation shape with their actual API grants and role label. `src/lib/roles.ts` is the only place that translates between the schema's **organization** and the product's **tenant**; the schema is not renamed to match a label.

`src/lib/navigation.ts` declares each role's rail, and every item carries the permission the server will enforce. The shell filters that table through the package's `useGranted()`, which reads the `PermissionProvider` the server layout seeded. So the table decides shape, the permission set decides visibility, and `tests/navigation.test.ts` fails if an item is ever gated on a grant its own role does not hold.

Drawing a menu item is not authorization. The server authorizes; this decides what is worth showing someone.

## Run and verify

Stop the development server before a production build: both commands write to the same `.next` directory. Restart development afterward.

From `platform/ui` (the workspace root, so `@pms/ui` resolves):

```sh
npm ci
npm run dev         # http://localhost:3000
npm test            # both workspaces
npm run typecheck   # both workspaces
npm run build       # production build
```

`next-env.d.ts` and `.next/` are generated and ignored; `npm run typecheck` passes without them.

## Layout

```
src/
  app/
    layout.tsx              root: styles, pre-paint theme script, ThemeProvider
    page.tsx                session check → /home or /login
    icon.svg                favicon
    (auth)/                 the split-screen: brand panel + form column
      login/ forgot-password/
    (console)/
      layout.tsx            the guard: no session, no console
      home/                 the dashboard for the signed-in role
      tenants/ devices/ models/ users/ licenses/ logs/
      members/ departments/ sessions/ reports/ recordings/ settings/
  components/
    BrandMark.tsx           mark, wordmark, lockup (masthead and compact)
    icons-product.tsx       tenant, device, model, pulse, licence, session
    ProviderIcons.tsx       the Microsoft mark @pms/ui does not ship
    ConsoleShell.tsx        AppShell + rail + top bar
    ChangePasswordDialog.tsx
    StatCards.tsx           the four-up band
    dashboards.tsx          one dashboard per role
    ComingSoon.tsx          the placeholder catalogue
    LoginForm.tsx  ForgotPasswordForm.tsx
  data/demo.ts              every number on every dashboard, in one file
  lib/
    roles.ts                role codes, labels, catalogue permissions
    navigation.ts           each role's rail, keyed by permission
    api.ts                 server-only API transport and safe errors
    session-user.ts        API identity and separate access contexts
    session.ts  actions.ts  opaque cookie and real account actions
  styles/
    brand.css  auth.css  console.css
```

Route groups rather than path segments: `(auth)` and `(console)` are presentation and guarding decisions, so the URLs stay `/login` and `/home`.

## What the app owns, and what it borrows

Borrowed whole from `@pms/ui`: `AppShell`, `Rail`, `TopBar`, `UserMenu`, `NotificationBell`, `OrgSwitcher`, `CollapseToggle`, `ContextChip`, `RoleChip`, `ThemeSwitcher`, `ToastProvider`, `PermissionProvider`/`useGranted`, `StatTile`/`StatRow`, `Card`, `PageHeader`, `ListRow`, `Meter`, `BarChart`, `EmptyState`, `Modal`, `EmailField`, `PasswordField`, `Checkbox`, `Button`, `Notice`, `Badge`, `themeScript`, `isEmailLike`, `currentYear`, the icons, and every design token and layout class (`pms-page`, `pms-grid--kpi`, `pms-grid--split`).

The package gained two small additions for this app, both generic and both tested there: an optional `email` on `UserMenu`, which turns on the identity block at the head of the open menu, and an optional `as` on `RailItem`, so a router's link component can be used and a menu click is a client navigation rather than a full document load.

Owned here: the product identity, the split-screen, and the console's sign-out row. `packages/ui/src/styles/shell.css` says why — the shell is shared because every authenticated screen needs it, and "the auth split-screen stays in its own app because nothing else will ever want it".

Two rules hold in `brand.css`, `auth.css` and `console.css`, and `tests/app-css.test.ts` enforces both:

- **No colour literal.** Every colour is a `--pms-*` token, which is what makes the light, dark and ledger palettes work from one set of rules. One hex would be a panel that stays light-indigo in the dark theme.
- **No `z-index`.** The stacking order is declared once in the package's `tokens.css`. The panel's washes are pseudo-elements behind a positioned content layer instead.

The brand tile is the one element that does not change with the theme: it is painted with `--pms-grad-action`, which the theme files define as the same indigo in all three palettes, on purpose.

## Gradients

Four, and no more — the design system spends gradients on brand surfaces and the primary action only:

1. the brand panel (`--pms-grad-panel`, plus a radial `--pms-brand-glow` wash and a faint diagonal ruling);
2. the primary button (`--pms-grad-action`, from the package);
3. the logo tile (the same action gradient);
4. "AI" in the wordmark, and the short rule under the claim (`--pms-brand` → `--pms-brand-bright`).

The wordmark's gradient is clipped to text, so it has a solid-colour fallback declared first and reverts to plain ink under `forced-colors`.

## Responsive behaviour

- **≥ 960px** — two columns, panel slightly wider than the form.
- **< 960px** — the panel becomes a header band keeping the lockup and the claim; the proof points and trust line drop.
- **< 480px** — the form card loses its border, shadow and padding, and the social buttons stack.

Verified at 1440, 760, 390 and in the dark palette with an emulated `prefers-color-scheme`.

## The console

The rail is brand, tenant switcher, Overview, the role's Manage/Activity/Practice sections, then Settings and a pinned **Sign out** above the fold of the rail's foot. Sign-out sits *beside* `RailFooter` rather than inside it: that component's children are `RailItem`s, which render `<li>`.

The top bar carries the tenant chip, the role chip, a "Preview data" badge, the theme switcher, the notification bell and the account menu — which shows name, address and role, then local-account **Change password**, **Change email address**, and **Sign out**.

The context switcher selects among the account's active API contexts. Notification content remains a preview. Account actions and session duration follow the API contract described above.

Each dashboard is the same three pieces in the same order — page header, four `StatTile`s, one split band — so the three roles read as one product:

| | Platform Admin | Tenant Admin | Tenant User |
| --- | --- | --- | --- |
| | Total devices | Devices | My sessions |
| | Live devices | Live devices | Hours practised |
| | Total tenants | Active members | Average score |
| | Expired licences | Licence expires in | Awaiting review |
| Below | Devices by tenant (chart) + recent activity | Recent sessions + device health | Recent sessions + start a session |

Tone is load-bearing on that band: only the tile that needs acting on is tinted, and `tests/dashboard.test.tsx` checks it lands there and nowhere else. Figures are strings end to end — `StatTile` refuses numbers, and renders an em-dash with a "No value" text equivalent for missing data, which is not the same fact as zero.

Every dashboard number lives in `src/data/demo.ts`. The tenant directory uses its own fixture and query adapter below.

## Tenant directory preview

The existing **Tenants** rail link opens `/tenants`. The server checks `platform.organizations.read` before passing the 68 fictional records to the page. Mutation controls also require `platform.organizations.manage`; identity and permissions come from the API; the directory records remain fictional.

The list reuses `DataTable`, `FilterBar`, `TableSearch`, `Select`, `Pager`, `Badge`, `Menu`, `Drawer`, `ConfirmDialog` and the existing icons. Search, Status, Records and Sort share a desktop row, with total count and paging below the table. The desktop table scrolls while these controls stay visible. Smaller viewports use the main page's scrolling and the shared stacked table layout. App CSS adds grouping and compact footer spacing; all colours remain shared theme tokens.

| UI control | Existing organization API contract |
| --- | --- |
| Search by tenant name | `q`, case-insensitive substring, at most 128 characters |
| All / Active / Inactive | Omit `is_active`, or `true` / `false` |
| Current / Archived / All records | `archived=false` / `true`, or omit it |
| Name / Created / Updated, both directions | `sort_by=name/created_at/updated_at`, `sort_order=asc/desc` |
| 25 / 50 / 100 rows, Previous / Next | `limit` capped at 100; a future adapter must retain cursor history and consume `next_cursor` / `has_more` |
| Filtered tenant count | Local fixture total; a future API request can use `include_total=true` |

`src/lib/tenant-directory.ts` applies filters and stable sorting to the whole fixture before paging. `src/data/tenants.ts` supplies stable UUIDs and dates, missing contacts, a long name and six archived tenants. The default is 62 current tenants sorted by name. Plan labels come from a separate sample catalogue, matching the API's `subscription_plan_id` reference.

**View** opens the dedicated `/tenants/[tenantId]` page, with an Edit action for current tenants the user can manage. **Copy ID** writes the complete ID to the clipboard and offers a manual-copy fallback on failure. **Delete** requires confirmation, then locally archives the record and marks it inactive, matching the API's soft-delete semantics; archived rows disable Edit/Delete. **Create new tenant** and **Edit** open the local forms described below. Reloading resets sample changes. No tenant API calls are made.

The shared theme provider renders a deterministic initial state for server hydration before adopting browser preferences. The pre-paint script still applies the saved palette immediately. Toast portals mount after hydration. Regression tests and browser reload checks cover saved Light, Dark, Ledger and System preferences.

## Tenant View page

View is a real Next link, so it supports browser Back/Forward, direct URLs and opening in another tab. The tenant name heads the page above a status/plan/creation summary. About this tenant, Primary contact and Record information cards show the existing directory fields without inventing device/user counts, plan quotas or activity events. Layout and icons reuse the shared design system; the two-column card layout stacks on smaller screens, and long names/IDs wrap.

The guarded `tenants/layout.tsx` owns `TenantDirectoryProvider`. Its in-memory records, query, sort, page and list bookmark are shared by the directory and detail routes. Creating or editing a tenant remains visible when moving between them. Returning to the directory restores the list context and row/table focus. Hard reload resets the fixture; a newly created tenant opened after reload or in another tab gets a clear unavailable-preview state and a return link. Missing local records use a UI empty state, not a claim of a server 404.

Both pages and the layout check `platform.organizations.read` on the server. Detail actions also honor the manage grant and archive state. Edit opens the existing form and saves in place. Copy ID provides feedback and a selectable fallback if clipboard access fails. Delete requires confirmation and leaves the archived details visible with mutation controls unavailable. Empty contacts/descriptions and unknown plan labels have explicit fallbacks. Email links are constructed only for addresses accepted by the shared typo validator; descriptions render as plain text.

This remains fictional UI data with no API integration or persistent browser storage. Subscriptions, membership management and tenant usage remain outside this directory adapter's scope.

## Tenant Create/Edit preview

Both actions open the existing large drawer and preserve the list query, sort and page. The footer keeps Cancel and Create tenant / Save changes visible while the fields scroll. Tenant details, Primary contact and Subscription and status use shared controls and icons. Desktop contact fields share a row; small screens stack them.

Creation requires a trimmed tenant name (up to 256 characters) and a sample subscription plan. Description (4,000), contact name (256), email and phone (80) are optional. Email uses the shared normalization and typo validation; phone accepts country codes, formatting and extensions. New tenants start **inactive**, matching `POST /platform/organizations`. Contact information does not create an administrator account or send invitations.

Edit prepopulates the current details and permits name, description, contact and preview status changes. The current plan is read-only because subscription assignment is a separate API operation. Saving preserves the ID, creation timestamp and plan, increments the local management version and updates the modified timestamp. Blank optional fields become null. UUIDs and timestamps are generated only when saving, so initial rendering remains deterministic.

Errors appear beside their fields; submission focuses the first invalid control. Unchanged edits cannot save. Cancel, Escape, the close button and backdrop ask before discarding a changed draft; Keep editing preserves the entries. A dirty form also registers the browser's refresh/tab-close warning. Saving immediately updates the in-memory list with no simulated network delay. A success notice offers View tenant even when the saved record falls outside the current filters or page. List edits return focus to the row or table; detail-page edits keep the view open and updated.

Create/Edit require the existing manage grant; archived tenants remain noneditable. Local saves also check the record version/lifecycle. These are presentation guards, not production authorization or concurrency enforcement. No fetch, browser persistence, live account creation, notification delivery, subscription reassignment or API integration is added. Real activation prerequisites and all server validation remain responsibilities of the future API integration.

## Settings hub

The platform rail contains Home, Tenants, Devices and Logs, with Settings and Sign out pinned below. Models, Licenses and Administrators are accessed through Settings cards at `/settings`, linking to the existing `/models`, `/licenses` and `/users` URLs. Tenant administrator Home and Settings show only Clinical specialties, Patient profiles and Cases & Q&A cards. Existing authorized model, LLM, subscription, provider and processing routes remain available by direct URL and through their other navigation flows. Tenant users retain their personal settings preview.

`src/lib/settings.ts` defines visible cards and direct-route access separately. A card is shown only when its role and permission match; hiding a card does not revoke an existing route grant. A category reader can reach platform Settings even without the separate settings-management grant, while that management grant alone does not unlock other categories. Visitors redirect to Login and unauthorized direct destination requests redirect to Home.

| Role | Settings cards |
| --- | --- |
| Platform Admin | Models, Licenses, Administrators, filtered by their respective grants |
| Tenant Admin | Clinical specialties, Patient profiles, Cases & Q&A |
| Tenant User | Personal settings preview; no management cards |

Cards reuse `Card`, `PageHeader`, theme tokens and the existing model, license and role icons. Each whole card is one named keyboard link with a visible focus outline and bottom-aligned action. The grid has three desktop columns, two medium columns and one mobile column; hover movement respects reduced-motion preferences. Breadcrumbs use Next links and preserve client navigation. The page adds no API calls, data mutations or management forms.

The shell passes the current pathname to `AppShell.navigationKey`, so completed client navigation closes the mobile drawer. Focus returns from a hidden rail to its menu control without disturbing focus that has already moved into the destination. Ordinary updates keep the drawer open.
## LLM connection management

Tenant administrators can open `/llm-connections` when authorized, although it is no longer a Home or Settings card.
The page uses the selected authenticated organization and `org.connections.manage`;
platform administrator access alone does not grant tenant connection access.

Create local llama.cpp, OpenAI, Azure OpenAI or OpenAI-compatible connections;
search and filter all lifecycle states; view/edit model, prompt, output budget and
provider parameters; replace keys; enable/disable; archive and restore. Keys are
encrypted by the API and never returned. Leaving the edit key blank preserves it;
changing the provider or endpoint requires a fresh key. Restoring leaves a connection
disabled. Archive is the reversible delete operation and preserves history.

The API must enable `PMS_LLM_ENABLED` and allow the configured endpoint. Local
output budgets are 16–512 (default 256); cloud budgets are 16–4,096. The model catalog
is optional metadata; Azure's deployment ID remains separately editable. Saving a
connection does not change the model selected by a published profile. Disabling a
connection stops new calls through any profile using it. A local connection check
validates configuration only; remote checks verify provider access/model discovery,
not generated-answer quality.

For the opt-in browser regression, start Next.js on loopback port 3124 with
`PMS_API_BASE_URL=http://127.0.0.1:8137/api/v1`. From `platform/api`, set
`PMS_TEST_ADMIN_DSN` to a dedicated disposable PostgreSQL server and
`PMS_LLM_WEB_ORIGIN=http://127.0.0.1:3124`, then run
`uv run pytest -q tests/test_llm_web.py -s`. It creates and cleans its own database
and API server, uses headless Edge (`PMS_TEST_BROWSER` can override its executable),
and makes no cloud calls. The test writes screenshots to `.test_artifacts/llm-web/`.

## User and member management

Platform administrators open **Settings > Users & administrators**. Create local
accounts, queue/resend password setup, search/filter/sort/page all accounts, read
direct details, edit local names/phones and platform roles, disable/enable, archive
and restore. Email changes still require account verification; OIDC profile fields
remain provider-managed. Account setup is shown separately from enabled status.

Tenant administrators open **Members** in the selected tenant. Invite local or
OIDC identities, choose a role and active department, resend/revoke invitations,
edit accepted access, disable/enable, archive and restore. Administrators cover the
whole tenant. Invitations cannot be pre-accepted, and disabled global accounts
must be enabled by a platform administrator before tenant activation. The API
enforces seat limits, accepted administrator coverage and tenant isolation.
Platform permissions alone do not permit tenant membership management.

Delete means archive, preserving audit history. Accepted members and users restore
as disabled; closed unaccepted invitations can be archived and replaced with a new
invitation. Web mutations send version guards. A changed context or stale version
returns an error; no optimistic local-only update claims success.

Set `PMS_INVITATION_BASE_URL=https://your-web-host/invitations/accept` on the API.
New invitation links carry a fragment token, cleared from the address bar before
explicit acceptance. Undelivered invitations have a temporary manual-share drawer.
Setup emails use the existing encrypted durable outbox; queued does not mean sent.
Configure SMTP and run the mail worker for local account setup and delivery.

For browser verification, use the same Next/API ports as the LLM test above, set
`PMS_PEOPLE_WEB_ORIGIN=http://127.0.0.1:3124`, then run
`uv run pytest -q -s tests/test_people_web.py` from `platform/api`. Run these two
browser fixtures separately because both own port 8137. The people fixture uses
disposable accounts/database and disabled SMTP; screenshots are written under
`.test_artifacts/people-web/`. It does not verify a live OIDC or SMTP provider.

## Activity logs

Open **Logs** in the selected platform or tenant context. The screen reads persisted
API events, with search, category/severity/actor filters, occurrence dates, device
ID, platform tenant-ID filtering, sorting, 25/50/100-row cursor pagination and manual
refresh. Date inputs explicitly use UTC; the through-day is inclusive. Search
matches event type, entity type or log ID. Detail links work after a reload and
show actor/scope identifiers, occurrence/receipt/expiry times and approved metadata.

Platform context shows administrative audit only. Tenant administrators can choose
all, audit or operational events; activity readers see operational events within
their permitted department. Changing context resets the directory. Every server
action revalidates the selected context and permission. Expired/out-of-scope
details show a recoverable error. Logs are read-only and contain recorded business
and device events, not an application terminal or a feed of every HTTP request.

The API projects an allowlist of metadata and flags omitted payload fields. The
detail screen explains omissions, and no sensitive payload search is supported.
Refresh is manual; this screen adds no background polling.

For a real local browser/API/PostgreSQL test, start Next on port 3124 with
`PMS_API_BASE_URL=http://127.0.0.1:8137/api/v1`. From `platform/api`, set
`PMS_TEST_ADMIN_DSN` to a dedicated disposable server and
`PMS_ACTIVITY_WEB_ORIGIN=http://127.0.0.1:3124`, then run
`uv run pytest -q -s tests/test_activity_web.py`. Run browser fixtures separately
because they share API port 8137. Edge can be overridden with `PMS_TEST_BROWSER`.
The fixture upgrades and cleans its own database/roles and writes local screenshots
under `.test_artifacts/logs-web/`; it does not contact cloud providers or SMTP.


## Device and tenant association management

Platform **Create tenant** is now a four-step page: tenant details, new/transfer
device, new/existing tenant administrator, and review. Finish also creates one
tenant-owned, inactive fictional Alex patient profile and three active clinical
specialties (Cardiology, Nephrology, Respiratory Medicine), plus two inactive case
drafts (Chest discomfort interview and Wheeze interview), in the same transaction
and activates the tenant. It also publishes two clearly labeled system starter
scenarios and selects a tenant Practice default. These defaults are independent
of other tenants and should receive tenant clinical review before routine use.
Transferred devices receive
a fresh ID; the old tenant keeps its history. New device types are **Manikin
(Physical)** and **Laptop (Software)**. Platform administrators alone create
devices and select published model profiles; tenant administrators edit private
device details, departments, enrollment, and lifecycle. Their Departments page
is reached through Settings and returns to the list after save.

Only platform administrators can open Models and LLM connections. The LLM page
selects a tenant before editing its connection. Tenant Settings includes
Scenarios and Practice cards plus a separate Departments link. **Members > Import members**
accepts optional passwords for new local accounts; it generates missing ones.
Results display initial passwords, and **Import History** offers audited
downloads for 30 days. Existing account passwords stay unchanged.

## Tenant Scenarios and Practice

The tenant rail and Settings lead to **Scenarios** for the patient story, Case QnA,
instructor guidance, and a guided submit/review/publish workflow. Authors can add a
tenant clinical specialty inline. A different reviewer records the language review
for the submitted revision; current device sessions require both English and Hindi
reviews. **Practice** lists published scenarios, lets each user choose a language
and private starting vitals, and lets a tenant administrator set the default.
Existing catalog URLs and records remain available for historical management;
`/patient-setup` redirects to `/practice`. The desktop client reads the user's
published scenario selection when present.

**Devices** uses the authenticated API and PostgreSQL. Platform administrators
can register a device with an active tenant, edit its public name/status, select
an existing published processing profile, revoke credentials,
deactivate/reactivate, retire/remove, and transfer registrations. The create/edit
drawer and device-list **Configure models** action show Local GPU/device, Cloud,
or mixed profiles with their published model choices by operation. Local GPU
execution still depends on the device runtime and installed models. Tenant
administrators publish those profiles and manage enrollment, private fields,
departments, media provider credentials and lifecycle within their selected tenant.
Platform fleet access does not grant tenant drafts, credentials or media.

The detail page shows the tenant association and a platform-only transfer form.
Transfer requires confirmation, retires the source registration and creates a
fresh destination ID, inactive by default. Its tenant administrator completes
configuration, activation and fresh enrollment. Source history remains under the
original tenant and ID. No private fields or credentials are copied.

Deactivation is reversible and frees a device seat. Remove/Retire is terminal;
the device's historical record is retained. The directory defaults to current
registrations; choose Retired or All enrollment states to view removed records.
Search, tenant/status/type/assignment filters, sorting, cursor paging, refresh and
direct links use server data. Context and version guards prevent stale edits;
confirmation dialogs retain actionable server errors. Refresh is manual.

For the real local browser/API/PostgreSQL journey, start Next on port 3124 with
`PMS_API_BASE_URL=http://127.0.0.1:8137/api/v1`. From `platform/api`, set
`PMS_TEST_ADMIN_DSN` to a dedicated disposable server and
`PMS_DEVICE_WEB_ORIGIN=http://127.0.0.1:3124`, then run
`uv run pytest -q -s tests/test_device_management_web.py`. The fixture migrates its
own database, applies runtime grants, disables SMTP and cleans up its records and
API process. Run browser fixtures separately because they share port 8137.
Headless Edge can be overridden with `PMS_TEST_BROWSER`; screenshots go to
`.test_artifacts/device-management-web/`. No cloud provider or hardware is used.


## Manual subscriptions

**Settings > Subscriptions** (`/licenses`) replaces the platform license placeholder
with persisted subscriptions and Standard/Advanced plan catalog management. Search
by tenant name/ID, filter by derived status or plan, page results, refresh, and open
reloadable details at `/licenses/{organizationId}`. On tenant details, the top-right
**Tenant administration** button opens the shared modal with separate **Subscription**
and **Administrators** tabs. Subscription shows current capacity, a confirmed plan
change and a link to dates/status management. Administrators lists current access
and searches existing active accounts to assign tenant administrator access; the
confirmation names the account and explains replacement of any existing member role.
Details load when the popup opens, and existing permission checks still govern each
action. Tenant administrators can open `/licenses` for their selected tenant's
read-only summary/history; it is no longer a Home or Settings card.

Platform administrators can change plans, record optional UTC start/end instants,
extend the end to record renewal, suspend/resume/cancel, and maintain private
references/notes. Cancelling retains the assignment and history. Recorded status
and dates **do not block processing**; seat limits still apply. Resuming preserves
dates, so an expired term must be extended separately. Platform-only notes and
references are excluded from tenant responses and audit payloads. History shows
retained changes, actors and older plan assignments.

Catalog editors manage exact price strings, INR/USD, billing period, user/device
limits and availability. A confirmation explains that these edits affect every
assigned tenant. Lower limits/downgrades cannot strand occupied seats. Closing a
plan to new assignments does not invalidate existing ones. There is no currency
conversion, payment collection, payment gateway or automatic renewal.

Every server action checks the selected context and exact permission. Subscription,
organization and plan versions have separate contracts; dialogs retain conflicts
and errors, protect unsaved drafts and preserve exact unchanged timestamps. Apply
API migration `0025_manual_subscriptions` before using this screen.

Real local browser verification: run Next on port 3124 with
`PMS_API_BASE_URL=http://127.0.0.1:8137/api/v1`; from `platform/api`, set
`PMS_TEST_ADMIN_DSN` to a dedicated disposable PostgreSQL server and
`PMS_SUBSCRIPTIONS_WEB_ORIGIN=http://127.0.0.1:3124`, then run
`uv run pytest -q -s tests/test_subscriptions_web.py`. The fixture uses a fresh
migrated database and actual runtime grants, disables SMTP, and removes its own
records/roles/API process. Run browser fixtures separately because port 8137 is
shared. Screenshots are under `.test_artifacts/subscriptions-web/`; cloud providers,
payment services and hardware are not used.
