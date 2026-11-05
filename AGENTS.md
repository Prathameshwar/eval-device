# Repository instructions

Applies throughout this repository. Follow the user's scope, preserve unrelated work, and keep solutions lightweight.

## Security first

- Enforce authentication, role permissions, organization/department scope, and lifecycle restrictions on every operation. Platform administrator access does not implicitly grant tenant media access.
- Validate untrusted input; use parameterized SQL and least-privilege runtime database roles. Enforce quotas and integrity server-side, including concurrent requests.
- Store provider credentials encrypted in PostgreSQL; keep encryption keys outside the database. Never commit or log secrets, tokens, signed URLs, or sensitive media. Preserve credential redaction and audit trails.
- Keep media private and bounded. Preserve idempotency and worker lease checks; never blindly retry an external submission whose outcome is unknown.

## Database and API changes

- Follow the existing Python/FastAPI, SQLAlchemy, and PostgreSQL architecture. Read the relevant [API guide](platform/api/README.md), [database guide](platform/db/README.md), and [service plan](docs/platform-service-plan.md) before substantial changes.
- Add forward Alembic migrations; do not rewrite the frozen SQL baseline or existing migrations. Preserve existing data and test upgrades. Keep models, request/response schemas, runtime grants, readiness checks, and documentation consistent.
- Keep business changes and their audit records atomic. Preserve tenant boundaries, subscription limits, and device configuration behavior.

## Testing and review

- Add meaningful unit tests for changed business rules and edge cases, and regression tests for fixes. Use isolated PostgreSQL integration tests for migrations, constraints, permissions, and concurrency; mock cloud calls.
- Run relevant tests and checks from `platform/api`: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/pms_api`. Broaden testing for shared, security, or schema changes. Documentation-only edits need inspection, not new runtime tests.
- Set `PMS_TEST_ADMIN_DSN` only to a dedicated disposable test server. Report skipped database tests explicitly; never run destructive tests against an application or production database.
- Review changes for authorization gaps, data integrity, error handling, and compatibility. Fix confirmed findings, rerun affected checks, then review the final result again.
- For substantial work, maintain [TODO](docs/pms-api-todo.md) and [review evidence](docs/pms-api-reviews.md). Report actual verification and remaining limitations.

## External services

Live cloud integration, hosted deployment, and Raspberry Pi hardware verification remain deferred until requested. Local tests and mocks must not be presented as live verification.


## GitHub folder mapping for this workspace

- Keep project files at their existing local paths in `C:\Pratham\poc-device`. GitHub destination: `O230008-CTO-10006ZE690/Pratham-POCs`, branch `main`, folder `device-poc/`.
- Use `git publish --dry-run` followed by `git publish` when publishing is authorized. The local alias runs `python start/publish.py` and preserves all other GitHub contents, including `bill-poc/`.
- Never use direct `git push` or force pushes from this standalone workspace. Keep `push.default=nothing`, do not set an upstream to `origin/main`, and do not pull/merge/rebase that branch into the local branch. Fetching for inspection is allowed.
- Stage only the authorized task's files. The helper publishes committed files; preserve concurrent and unrelated work.
- If the alias or `.git/device-publish-state.json` is missing after initial setup, or publishing reports unexpected changes to GitHub's `device-poc/`, stop publishing and report it. Do not invent replacement state, bypass the helper, or overwrite remote changes.
- The mapping applies to this standalone workspace, not automatically to another clone. See [GitHub publishing](docs/github-publishing.md) for the workflow and exclusions.
