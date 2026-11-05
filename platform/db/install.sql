\set ON_ERROR_STOP on
-- Run with psql against the intended EMPTY application database as its schema owner.
-- Deliberately fails if the schema already exists; upgrades require migrations.
BEGIN;
SET LOCAL TIME ZONE 'UTC';
CREATE SCHEMA device_platform;
REVOKE ALL ON SCHEMA device_platform FROM PUBLIC;
SET LOCAL search_path = device_platform, pg_catalog;
\ir sql/001_validation.sql
\ir sql/002_tables.sql
\ir sql/003_indexes.sql
\ir sql/004_triggers.sql
\ir sql/005_seed.sql
\ir sql/006_role_catalog.sql
REVOKE ALL ON ALL TABLES IN SCHEMA device_platform FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA device_platform FROM PUBLIC;
-- Future migrations must also explicitly revoke PUBLIC execution on new functions.
COMMENT ON SCHEMA device_platform IS 'Device Platform schema version 1; installed from platform/db/install.sql';
COMMIT;
\echo 'Device Platform schema v1 installed. Providers remain disabled; bootstrap a verified administrator next.'
