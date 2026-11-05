# Patient scenario categories

Migration `0011_scenario_categories` creates `device_platform.scenario_categories`, a shared clinical-specialty catalog. These records classify future patient scenarios; they are not patient cases, diagnoses, vital-sign presets or LLM instructions. The catalog contains no tenant or patient data. Existing scenario `specialty` text and published snapshots remain unchanged; scenario selection/API integration is a later step.

## Initial records

| Code | English name | Hindi name | Order |
|---|---|---|---|
| `cardiology` | Cardiology | हृदय रोग | 10 |
| `nephrology` | Nephrology | गुर्दा रोग | 20 |
| `respiratory_medicine` | Respiratory Medicine | श्वसन रोग | 30 |

All three are active. Their stable UUIDs end in `0301`, `0302` and `0303` respectively (prefix `00000000-0000-4000-8000-00000000`). Descriptions explain the interview subject without supplying clinical answers. Seeding creates one global system audit event per inserted category in the same migration transaction, using the configured audit-retention policy.

## Fields and access

| Field | PostgreSQL type | Contract |
|---|---|---|
| `id` | uuid | Primary key; immutable |
| `code` | text | Unique stable code; lowercase letters, digits and underscores; starts with a letter; at most 40 characters; immutable |
| `name` | text | Trimmed English label, 1–120 characters; unique ignoring case |
| `name_hi` | text | Trimmed Hindi label, 1–160 characters |
| `description` | text | Trimmed description, 1–600 characters |
| `sort_order` | integer | 0–10000; default 0 |
| `is_active` | boolean | Default true; retained for later selection rules |
| `created_at` | timestamptz | Creation time; immutable |
| `updated_at` | timestamptz | Database-maintained modification time |

Apply `platform/api/deploy/grant-runtime-access.sql` after upgrading. The API database role receives SELECT only. Processing/retention roles and PUBLIC have no category-table access. There is no category write HTTP endpoint in this increment. Future catalog changes should use reviewed owner migrations with atomic audit records; granting platform administration does not grant access to tenant media.

## Initialize or upgrade

Install PostgreSQL and the API dependencies, provision the deployment owner and runtime login roles, and configure private `platform/api/.env` as described in the [API guide](../api/README.md). Set `PMS_MIGRATION_DATABASE_URL` to the deployment-owner URL targeting the intended application database. Do not put credentials in command-line arguments or commit `.env`.

From the repository root on Windows:

```bat
platform\db\init.bat
```

Or, from `platform/api` on any supported platform:

```text
uv run pms-admin init-database
```

The initializer connects to the `postgres` maintenance database, creates the target only if absent, and applies migrations through the current head. Use `--maintenance-database NAME` when necessary. Database creation requires CREATEDB; initialization does not install PostgreSQL or create login roles. Apply the normal runtime grants after it succeeds.

New databases use UTF-8, default UTC and no PUBLIC privileges. They accept connections only after the database ACL and timezone are configured. Existing database settings and records are preserved. Concurrent invocations using the same target and maintenance database serialize creation and upgrade with a PostgreSQL advisory lock and bounded lock wait. Use one deployment process; do not run a separate migration command simultaneously.

Repeating initialization or `pms-admin migrate` does not duplicate records/audit events or overwrite renamed/deactivated categories. Migration history owns the defaults: deleting a category manually is not repaired by rerunning initialization. A database created by the frozen SQL installer must first pass `pms-admin adopt-baseline`; unmanaged application schemas are rejected without modification.

If a migration fails, its transaction rolls back and a later initialization can resume. If initial database ACL configuration fails, the new database remains closed to connections for owner inspection/repair; the initializer never deletes a database as error recovery. The frozen `install.sql`/SQL baseline and older migrations are unchanged.
