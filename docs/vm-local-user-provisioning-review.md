# VM local user provisioning review (2026-10-01)

## Finding and change

The hosted `POST /api/v1/platform/users` returned 503 before writing a user.
`management.email_available` blocked every create, setup resend and tenant
invitation when `PMS_VM_LOCAL_MODE` disabled SMTP. The UI then showed the generic
service-unavailable message. VM local mode now permits these authorized
operations and returns the one-time password setup token only in the successful
create or resend response. New local tenant invitations return their setup token
alongside the invitation token. The web shows private fragment links and tells
the administrator to share the setup link first. The existing password setup,
invitation acceptance, authorization, version, lifecycle, audit and transaction
checks remain in place. A pending tenant administrator's setup link requires the
tenant administrator management grant to regenerate. Token-bearing responses
set `Cache-Control: no-store`; list and detail responses never return tokens.
Self-service password recovery and email change still require SMTP.

## Local verification

- An isolated, newly initialized PostgreSQL 17 cluster was used only for this
  task, on port 55441. The affected people-management and administrator suites
  passed: 22 tests. The VM-mode test covered platform and tenant administrator
  creation, setup-token rotation, rejected old token, password setup, local
  sign-in and tenant invitation acceptance. The cluster was stopped afterward.
- Full API suite without a database test DSN: 374 passed, 300 database tests
  skipped. Ruff check and format, and mypy, passed.
- Full web suite: 484 passed across 70 files. TypeScript check and the
  production Next.js build passed.
- Final archive: `start/dist/pms-platform-20261001-125541-8146ef.zip`, SHA-256
  `df2043a43c5e9fb068708e54528f2aadf269af6dbd1903fe93baaf19b4312955`.
  All 737 manifest entries and API wheel/source parity were verified.

## Hosted verification

- Before deployment, a custom-format database backup was saved at
  `/var/backups/pms-platform/pre-manual-users-20261001.dump`, mode 600, 913,968
  bytes. `pg_restore --list` passed.
- The final deployment completed at
  `/opt/pms-platform/releases/20261001-125633-16046`. API, web, worker and
  retention services are active. No error-priority service messages appeared
  after the release start.
- Local API readiness and HTTPS web readiness returned 200. An external HTTPS
  probe also returned 200. Anonymous `POST /api/v1/platform/users` returned
  401. The database remained at one user and one tenant after deployment.
- The administrator submitted the hosted Create user form and reported that
  both links appeared. Read-only database checks then showed
  two users and one tenant; the audit table contained one
  `platform.user.created`, one `membership.invited`, and one
  `identity.setup_completed` event. API logs recorded successful password setup
  and browser sign-in. No administrator password, session token, or one-time
  link was handled during this check.
