# Fictional patient identities

Migration `0012_patient_identities` adds `device_platform.patient_identities` and one reusable identity named **Alex**. This shared, deployment-managed catalog contains fictional simulation templates. Clinical cases, diagnoses, history, vital signs and disclosure rules belong to the selected scenario.

## Alex default

| Attribute | Value |
|---|---|
| Stable ID | `00000000-0000-4000-8000-000000000401` |
| Code | `alex` |
| Name | Alex / एलेक्स |
| Age | 35 years |
| Sex | Male |
| Occupation | Schoolteacher / स्कूल शिक्षक |
| Height | 175 cm |
| Weight | 75 kg |
| Preferred language | English (`en`) |
| Supported languages | English and Hindi (`en`, `hi`) |
| Background | Alex works as a schoolteacher and lives with family. |
| Hindi background | एलेक्स स्कूल शिक्षक हैं और अपने परिवार के साथ रहते हैं। |
| Fictional / active | Yes / yes |

Age is an authored simulation value and does not advance automatically with calendar time. Height and weight describe the fictional patient. Alex is reusable across Cardiology, Nephrology and Respiratory Medicine; no category or disease is assigned by this identity seed.

## Storage contract

| Fields | PostgreSQL type | Validation |
|---|---|---|
| `id` | uuid | Primary key; immutable |
| `code` | text | Unique stable code, 1–40 lowercase letters/digits/underscores, starting with a letter; immutable |
| `name`, `name_hi` | text | Trimmed labels, 1–120 characters |
| `age_years` | integer | 0–150 |
| `sex` | text | `female`, `male`, `intersex`, `unspecified` |
| `occupation_en`, `occupation_hi` | text | Trimmed bilingual text, 1–600 characters |
| `height_cm` | numeric(5,2) | Greater than 0, at most 400; finite |
| `weight_kg` | numeric(6,2) | Greater than 0, at most 2000; finite |
| `preferred_language` | text | `en` or `hi`; must be in `languages` |
| `languages` | text[] | One-dimensional, standard 1-based array; 1–2 distinct non-null `en`/`hi` entries |
| `background_en`, `background_hi` | text | Trimmed bilingual text, 1–600 characters |
| `is_fictional` | boolean | Must be true |
| `is_active` | boolean | Default true |
| `created_at` | timestamptz | Immutable creation time |
| `updated_at` | timestamptz | Database-maintained modification time |

The table adds 18 columns: current domain schema **20 tables, 356 columns**. Bounds reject structurally invalid data; scenario review establishes whether particular clinical content is appropriate.

The current version-2 scenario contract already accepts `patient.name`, `age_years`, `sex`, bilingual `occupation`, `height_cm` and `weight_kg`. Future identity selection must copy the selected values into the editable scenario and preserve the resulting approved snapshot. Identity edits must never change an existing published scenario or active session. This increment adds no selection endpoint, automatic scenario linkage, clinical answers or device assignment. Language metadata does not override the platform/device language policy.

## Initialization and permissions

Run [init.bat](init.bat) from the configured checkout, or `uv run pms-admin init-database` from `platform/api`; an existing managed database can also use `pms-admin migrate`. The existing initializer automatically applies migration 0012. See [database setup](README.md) for owner configuration and verified adoption of a frozen SQL baseline. Apply `platform/api/deploy/grant-runtime-access.sql` after migration.

The API database role may SELECT these templates. Processing/retention roles and PUBLIC have no table access; no runtime role can edit identities. A reviewed owner migration should make future catalog changes with an atomic audit event. Tenant-authored private patient details continue to live in organization-scoped scenario drafts and snapshots.

Alex and one global `platform.patient_identity.seeded` audit event are inserted in the same transaction. Audit metadata contains the stable code/revision, without identity attributes or clinical text. Repeating initialization does not duplicate Alex or reset edited/deactivated values. A failed migration rolls back; retry resumes through Alembic. Existing categories, scenario records and frozen migrations are preserved.
