# Login and account lifecycle review — 2026-09-23

The web application does not provide an end-to-end login to the PMS API. It runs an explicitly labelled demo sign-in alongside a separate local/OIDC API. Review found eight actionable bugs or integration gaps, including a fresh-install failure and two reproduced API concurrency defects. P1 means fix before enabling real accounts in this frontend; P2 means a material functional failure. Preview limitations below are not evidence of access to real tenant data.

This was a review, not a remediation change. Application source, migrations and application databases were left unchanged. Reproduction probes are retained locally under `.test_artifacts/login-review-20260923/`.

## Findings

### L01 — P1: Fresh database initialization fails before login is available

Source: `platform/api/src/pms_api/database/baseline/005_seed.sql:42`, `platform/api/migrations/versions/0001_baseline.py:20`, and `platform/api/migrations/versions/0020_management_api.py:17`.

The frozen baseline now inserts a local administrator using `auth_method`, `management_version` and `local_credentials`. These objects are introduced only in migration 0020. Migration 0001 executes the seed first, so a fresh upgrade fails with `column "auth_method" of relation "users" does not exist`.

Reproduced on a new dedicated PostgreSQL 17 cluster: all three existing management integration tests and four initial review probes failed during fixture migration. This also prevents a fresh local-account bootstrap. Existing databases already past 0001 will not receive this seed through an ordinary upgrade.

Remediation: reconcile the accidentally changed frozen baseline with its reviewed version, following repository migration policy. Keep subsequent schema/data changes in forward migrations. Do not move the shared credential into a later migration; use the verified-operator bootstrap and one-time setup flow.

### L02 — P1: The database seed contains a shared administrator password

Source: `platform/api/src/pms_api/database/baseline/005_seed.sql:42`.

The seed contains a plaintext default administrator password, its hash, and an active, verified administrator with setup marked complete. There is no environment gate or mandatory first-password setup. Unlike the UI's fictional accounts, this SQL targets the real API credential tables. If installed against a compatible schema, it creates a reusable shared administrative credential.

The migration failure prevents claiming that a fresh install successfully creates this account. No application database was inspected for its presence. Remove shared credential provisioning and assess any environment where this SQL was applied. Replace/revoke affected credentials through the operator workflow. The password and hash are intentionally omitted from this report.

### L03 — P1: A concurrent login rehash restores a replaced password

Source: `platform/api/src/pms_api/modules/auth.py:84` and `:101`.

Login reads and verifies a credential without a lock or version-checked update. When its hash needs upgrading, login later saves a hash of the submitted password. That write can occur after another request has successfully changed the password.

Reproduction on the isolated fixture:

1. Start login with the old password and pause its rehash operation.
2. Complete `/auth/password/change` with a new password.
3. Resume the original login.
4. A subsequent login with the old password returns 200 and can call `/me`; the newly selected password returns 401.

The probe forced `password_needs_rehash` true to deterministically exercise the real rehash path. Production exposure requires a hash that actually needs upgrading. Credential-version checks reject a stale access token but do not prevent the stale password hash being saved.

Remediation: serialize credential changes or compare-and-update against the verified hash/version, reloading and revalidating before session issuance. Add a regression overlapping password replacement with login rehash.

### L04 — P1: An email-change request can outlive credential revocation

Source: `platform/api/src/pms_api/modules/auth.py:265`, `:280`, and `:287`; `platform/api/src/pms_api/security/local_auth.py:194`.

Email change verifies the current password, then creates a confirmation action without locking/rechecking the credential version. A concurrent password change can revoke all existing sessions and action tokens in between. The original email request then creates a new action that survives that revocation.

Reproduced by pausing the email request immediately before action creation, successfully changing the password, and resuming the request. Confirmation returned 200; login with the new password moved to the requested address, and the original address stopped working. The probe read its disposable encrypted outbox to emulate email receipt; no SMTP service was contacted and no token was printed.

Someone holding the old password/session could leave a usable email-change link after the owner replaces that password. Serialize action creation with credential replacement and bind confirmation actions to the credential version that authorized them. Reject stale versions on consumption.

### L05 — P1 integration gap: The login page never authenticates with the API

Source: `platform/ui/apps/web/src/lib/actions.ts:28`, `platform/ui/apps/web/src/lib/demo-auth.ts:27`, and `platform/ui/apps/web/src/lib/session.ts:24`.

The path is `LoginForm → signIn → authenticateDemoUser → demo cookie → /home`. There is no `/auth/login`, `/auth/refresh`, `/me`, or API logout call in this path. Roles, permissions and tenant identity come from hardcoded demo users. Real provisioned accounts cannot use this page; API suspension, password changes and session revocation cannot govern its displayed console.

This is documented preview behavior, but blocks a real end-to-end journey. Connecting one login call is insufficient: implement verified session lookup, secure server token handling, current access from `/me`, refresh coordination, logout/revocation, and expired-session recovery.

### L06 — P1 integration gap: A forged demo cookie selects the administrator

Source: `platform/ui/apps/web/src/lib/session.ts:24` and `platform/ui/apps/web/src/app/(console)/layout.tsx:22`.

`currentUser` trusts the raw `ae-demo-session` value as a known demo user ID. Local HTTP checks showed `/tenants` redirects an anonymous visitor to `/login`, but returns 200 when supplied `ae-demo-session=platform-admin`, without a password exchange. A tenant-user demo ID is redirected to `/home`.

Cookie flags do not authenticate the value. There is no server-side expiry or revocation record: remember duration is browser cookie retention, and logout only deletes that browser's cookie. A copied value can be supplied again. Current impact is fictional preview content; no API bypass was demonstrated. Replace this identity source before connecting real data, and explicitly bound preview mode if retained.

### L07 — P2: Account email links have no completion pages

Source: `platform/api/src/pms_api/integrations/email.py:48`, `platform/api/src/pms_api/core/config.py:47`, and `platform/ui/apps/web/src/components/ForgotPasswordForm.tsx:42`.

The default API email contract points to `/account/setup`, `/account/password-reset`, and `/account/email-change`. All three returned 404 from the running web app. Even correctly delivered setup/reset mail cannot complete the journey with this frontend.

Forgot-password only waits and displays “Nothing was sent”; the change-password dialog changes nothing. Google/Microsoft buttons display a not-configured notice. These are disclosed preview limitations. Implement purpose-specific completion pages and connect recovery/password actions. Connect configured provider flows or make their unavailable state apparent before the user tries them.

### L08 — P2: A rejected sign-in request leaves the form stuck

Source: `platform/ui/apps/web/src/components/LoginForm.tsx:75`.

The form sets `submitting=true` before awaiting the server action and restores it only when the action resolves with `{error}`. A network/server-action exception escapes without clearing the pending state or displaying a failure.

A component probe injected a rejecting sign-in call: the promise rejected, “Signing in…” remained disabled, and no sign-in error appeared. Handle transport failures with a safe error message and retryable form state, preserving successful redirects.

## Coverage and design gaps

- Existing login component tests inject a fake sign-in callback. Demo-session tests verify hardcoded credentials and imports, not authenticated sessions. They cannot catch the frontend/API disconnect or account-action 404s.
- Committed API tests have a combined setup/login/password-change/logout journey, but no HTTP tests for refresh replay/concurrency, reset-token purpose/reuse, email confirmation, or the reproduced races. Review probes cover some of these locally; they are evidence, not a committed regression suite.
- Simultaneous refresh returned one success and one reuse rejection, after which the winner's access token was also rejected. This follows the current family-revocation design. The future frontend must coordinate concurrent refreshes and must not blindly retry uncertain refresh outcomes.
- Review shared abuse controls before deployment: login/recovery counters use source plus email; hashing concurrency is process-local. Verify effective account/source limits across replicas and the configured ingress. No distributed load or proxy deployment test was performed.

## Verification and limits

- Existing UI authentication tests: **22 passed** across four files. App TypeScript checking passed. The additional rejection probe passed, asserting the observed defect. Six local HTTP checks confirmed cookie behavior and missing action pages.
- Existing API management/unit tests without a test DSN: **14 passed, 3 skipped**.
- Unmodified dedicated-database run: **7 passed, 7 setup errors**, all errors due to the broken baseline. This is not a passing migration/integration result.
- Six supplemental probes passed across focused runs using the original `platform/db/sql` baseline only for fixture provisioning, then current forward migrations and runtime grants. The baseline files match the packaged files after newline normalization except the changed seed. No repository baseline was edited. Probes covered refresh/replay/access restrictions, both races, reset purpose/reuse/revocation, deactivation/reactivation/expiry/disabled authentication, and simultaneous refresh. An initial expiry-fixture check violated the session timestamp constraint; correcting the synthetic timestamps made that probe pass.
- Full API `uv run pytest -q`, without a database DSN: **244 passed, 22 failed, 179 skipped**. Failures are outside login in `test_local_parity.py` and `test_patient_practice.py`. Database tests were skipped in this broad run and are not presented as passing.
- `uv run ruff check .` and `uv run mypy src/pms_api` passed. Formatting check failed on existing comment line endings in `modules/llm.py` and `modules/local_turns.py`; 125 files passed formatting.
- No application database, hosted deployment, live OIDC provider, SMTP delivery, cloud integration or Raspberry Pi was used. Checks used local Next HTTP requests, component tests, and in-process API HTTP calls against disposable PostgreSQL databases with real least-privilege runtime grants.
- Temporary Next and PostgreSQL services were stopped after review. Review artifacts remain local, and the pre-existing patient-routing directory was preserved.

Fix L01/L02 and both API races first, then replace demo authentication, implement account completion pages, and add a browser-to-API regression journey before considering login complete.

## Implementation follow-up

The user authorized implementation after this review. The findings above describe the original state; the current source now addresses L01-L08:

| Finding | Implemented change |
| --- | --- |
| L01/L02 | Restore the original seed without an administrator or shared password. Fresh migration succeeds; administrator provisioning uses the audited CLI. |
| L03 | Verify the original hash/version under refreshed user/credential locks before issuing a session or applying a rehash. Concurrent password replacement rejects the stale login. |
| L04 | Reauthorize local account mutations under consistent locks and bind action tokens to credential versions. Password/email changes revoke sessions and outstanding actions. |
| L05/L06 | Replace demo authentication with real API sessions, current identity and separate active access contexts. Ignore forged legacy cookies. |
| L07 | Implement setup, reset, email confirmation, password recovery, password change and email change. Unconfigured Google/Microsoft login is explicitly unavailable. |
| L08 | Catch rejected submissions, release pending state and allow a retry. |

Migration `0022_browser_sessions` preserves existing credentials and bearer sessions, adds the opaque browser credential hash and action version, and consumes old pending email-change tokens whose authorization version is unknown. It follows the separate existing `0021_events_platform_audit_idx` migration.

The Next server keeps the opaque browser credential in an HttpOnly SameSite=Lax cookie. Production uses Secure `__Host-` cookies, including when expiring them. The server fetches identity and exact grants from the API; account cookies cannot supply a role or tenant permission. Non-remembered sessions have an eight-hour server limit; remembered sessions use the configured duration. Stable credentials avoid cross-tab refresh races, while existing bearer clients retain rotating refresh and replay revocation.

New account emails put tokens in a URL fragment. Browser verification found and fixed two additional integration defects: a cookie-triggered Next rerender could restore a removed token fragment, and prefix-cookie deletion needed the original Secure/Path attributes. It also added support for opening another account fragment on an already completed page. Server actions are checked against a foreign Origin in the real browser regression.

Validation evidence and broader-suite limitations are recorded in [the implementation review record](pms-api-reviews.md). Reproducible tests are `platform/api/tests/test_auth_sessions.py`, `test_browser_migration.py`, `browser_fixture.py`, and `platform/ui/apps/web/tests/browser-login.mjs`. Local logs are under `.test_artifacts/login-implementation-20260923/`.

The subsequent database synchronization applied migration 0022 and runtime grants to the configured local database, with a verified private backup and all 1,765 existing rows preserved. Other deployments still require migration/grants; API URL, local-auth secrets, SMTP and web account URL configuration remain deployment requirements. If an older seed was manually applied, an operator must rotate that account's password and revoke its sessions. SMTP delivery, external SSO, cloud and hosted deployment were not exercised. Business dashboards/directories retain clearly labelled fictional preview data.
