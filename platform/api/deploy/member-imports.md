# Tenant member imports

Tenant administrators open **Members > Import members**. The four-step wizard selects access, downloads/uploads an Excel workbook, reviews validation, and imports the ready rows. A batch has exactly one of `org_user`, `org_trainee`, `org_read_only`, or `org_admin`, one sign-in method (`local` or `oidc`), and an optional active department. Administrators cannot be department-scoped. Global platform-administrator creation is not available through this tenant workflow.

## Workbook and results

Download the .xlsx template and fill the **Members** sheet with **Full name**, **Email**, and optional **Password**. Keep the headings. Passwords are accepted only for new local accounts (12-1024 characters); blank passwords are generated. For external sign-in, leave Password blank; the template instructions reflect the selected sign-in method. Legacy two-column workbooks remain accepted. Names are required (1-256 characters); emails are normalized for duplicate checks. Blank rows are ignored. The first well-formed occurrence of an email is considered; subsequent duplicates fail validation. Existing memberships or pending invitations are reported for management, never overwritten.

Limits: **200 data rows**, **512 KiB compressed**, 4 MiB expanded, 80 ZIP entries, and 100 retained batches per tenant. The API rejects uploads above 512 KiB before parsing. The reader validates archive contents and actual worksheet coordinates instead of trusting dimensions. Hyperlinks, external-link metadata, macros and embedded objects do not cause a blanket rejection; only Members cell values are imported, with macros/objects ignored and links never fetched. Formula cells use their saved results without evaluation. A formula without a saved value gets a row/column-specific error asking the user to recalculate and save in Excel. Numeric identity cells and extra data columns remain row errors. Encrypted or malformed archives and unsafe XML remain unreadable. Server-side parsing uses openpyxl with defusedxml. Output strings are explicitly stored as Excel text, never executable formulas.

Validation creates only a bounded import record and audit event. It creates no users, memberships or emails. Validation lasts **24 hours**. The commit rechecks current membership/account state, department, local-auth configuration and remaining subscription seats under the administration lock. Each row uses a savepoint, so a failed row leaves no account, setup token, membership or audit fragment. The final batch and all successful changes commit atomically. Concurrent/repeated commits of the same batch return the saved result; do not create a new batch to retry a lost response.

Results include total, ready, successful and failed counts, original Excel row numbers, correction messages and separate invitation email status. Invalid rows are counted as failed, and never submitted to account creation. **Download errors** contains only unsuccessful people on a reusable Members sheet plus an Errors sheet identifying original rows and reasons. **Download results** includes every row and its final status. Correct the failed Members rows and validate a new batch; successful rows are excluded from that sheet.

Validation/results and downloadable reports remain available to tenant-wide member managers for **30 days**, including read access while the tenant is inactive. **Import History** lets another authorized administrator resume/review a batch and download initial passwords. Passwords are held separately in AES-GCM ciphertext in PostgreSQL using a key outside the database, bound to tenant and batch IDs; they are absent from row JSON and audit details. Viewing/downloading completed passwords is audited. The original uploaded workbook is not stored. Raw names/emails are not copied to audit metadata.

## Identity and email

A successful row means **invitation created**, not accepted membership or delivered email. New local accounts receive the supplied or generated initial password and are marked verified by the authorized tenant administrator; they still need the separate invitation token to join the tenant. Existing accounts retain their profiles and passwords, and a supplied password for one is rejected. External identities use their identity provider profile when signing in and cannot have a workbook password. Password downloads show initial values only; later password changes are not reflected.

Invitation tokens are encrypted with the configured credential key outside PostgreSQL and saved in an API-owned outbox in the same transaction. An independent API delivery loop also runs when local password authentication is disabled. SMTP sends happen after the import transaction, so bulk import does not wait for outbound mail. Missing SMTP configuration leaves delivery queued and is clearly shown in the wizard.

States are pending, sending, sent, failed, unknown and cancelled. Claims are leased; only the owning sender can complete a claim. Interrupted or unconfirmed sends are **not automatically retried**. Revoked, expired, archived, rotated or inactive-tenant/department invitations are not newly sent. Use the existing individual **Resend invitation** action for manual recovery or to obtain a link for secure sharing when email is unavailable. New local accounts use their initial password; this workflow does not create a setup email. Invitation outbox records expire with their two-day invitation. Mail delivery is separately reported and does not change import success counts.

## API

All routes are below `/api/v1/organizations/{organization_id}/member-imports` and require an active human identity with accepted tenant-wide `org.members.manage` permission. Global platform permissions alone grant no access.

| Method / suffix | Behavior |
| --- | --- |
| GET `/template?role=ROLE&auth_method=METHOD&department_id=ID` | Private Excel template; department optional. |
| POST `/validate?role=ROLE&auth_method=METHOD&department_id=ID` | Raw .xlsx body with Excel MIME type; returns 201 with saved validation. |
| GET empty suffix | Up to 100 retained batch summaries, newest first. |
| GET `/{import_id}` | Saved rows, counts and delivery states. |
| POST `/{import_id}/commit` | Import ready rows or return an already completed result. |
| GET `/{import_id}/report?errors_only=true` | Download failed rows/errors; false includes all result rows. |
| GET `/{import_id}/report?passwords_only=true` | Download initial passwords for successful new local accounts; audited. |

Downloads are authenticated and `no-store`. The Next download proxy supports only fixed template/report paths; it binds the request to the current tenant. API credentials stay on the server. Server actions bind upload and commit to that same context.

## Deployment and local verification

Apply forward migrations through `0032_tenant_import_passwords` and reapply `deploy/grant-runtime-access.sql`. This is the feature's minimum schema revision; current API readiness requires the latest head documented in [API setup](../README.md). The two new tables are API-owned; media workers and retention workers receive no privileges. Existing tenant/account/membership data is preserved. Import/outbox expiry cleanup runs in the API process.

Run workbook/business tests using `uv run pytest -q tests/test_member_imports.py tests/test_member_import_migration.py`. Set `PMS_TEST_ADMIN_DSN` only to a dedicated disposable PostgreSQL server for integration cases.

The opt-in browser check is `tests/test_member_import_web.py`. Run Next on port 3124 with `PMS_API_BASE_URL=http://127.0.0.1:8137/api/v1`, set `PMS_IMPORT_WEB_ORIGIN=http://127.0.0.1:3124`, and use the disposable DSN. The test starts/stops its own local API and database, uses a real headless browser, downloads genuine XLSX files, imports mixed valid/invalid rows, refreshes saved results and checks mobile overflow. SMTP is disabled; this is local integration verification, not live email/SSO verification.
