# Tenant administrator clinical access and cards review (2026-10-01)

## Decision and implementation

An active, accepted tenant administrator now receives `org.clinical.author` from
the role in their selected tenant. This covers Clinical specialties, Patient
profiles, and Cases & Q&A without a per-member assignment. The API evaluates
the current membership on each request, so an inactive membership or a platform
administrator without tenant membership gains no clinical access. Explicit
staff capability assignments and their audit records remain unchanged. A
redundant administrator assignment may be revoked, but the role grant persists.

Tenant administrator Home and Settings show exactly three destination cards:
Clinical specialties, Patient profiles, and Cases & Q&A. The old statistics and
activity cards do not render on Home. Other Settings cards are hidden. Direct
model and LLM routes retain their existing role and permission checks; hiding
a card does not revoke access. The member responsibility panel shows Clinical
author as included with the administrator role and offers no revoke button.

The database schema and frozen baseline role view are unchanged. The API role
catalog is the current runtime policy; the baseline view records the original
catalog. No migration or data rewrite is required. The hosted VM was not changed.

## Verification

- Dedicated disposable PostgreSQL 17 at `127.0.0.1:55467`: 15 clinical
  catalog integration tests passed. The new administrator case-import check
  passed again after its final edit. Another 36 scenario, review, and session
  tests passed against the same dedicated server.
- Web tests: 497 passed across 72 files with a 10-second test timeout.
  TypeScript typecheck and the production Next.js build passed.
- API Ruff lint, Ruff format check, and mypy passed. `git diff --check` passed.
- Windows transfer archive `start/dist/pms-platform-20261001-163219-6441cb.zip`
  has SHA-256 `90fa4b7570a09d38e4355b4d8f3e226076a21be115cd1efdf0c5a891ca29359b`.
  All 740 manifest entries were rehashed and matched, including the new web
  component and API role catalog.
- The complete API suite was started but stopped while progressing slowly;
  the affected integration suites above completed. No hosted VM checks or
  deployment were performed.
