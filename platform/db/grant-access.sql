\set ON_ERROR_STOP on
-- psql 17 ignores an exit-code argument to \quit; SQL exceptions fail preflight reliably.
-- Existing backend PostgreSQL roles, provisioned by your deployment operator.
-- They are not the six application roles and must not be given to humans/devices.
\if :{?api_role}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply api_role, worker_role, maintenance_role, and db_name with -v.';
  END $preflight$;
\endif
\if :{?worker_role}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply worker_role with -v.';
  END $preflight$;
\endif
\if :{?maintenance_role}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply maintenance_role with -v.';
  END $preflight$;
\endif
\if :{?db_name}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply db_name with -v.';
  END $preflight$;
\endif
BEGIN;
SELECT current_database() = :'db_name' AS target_ok
\gset
\if :target_ok
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'db_name must match the connected database.';
  END $preflight$;
\endif
SELECT count(*) = 3 AND count(DISTINCT oid) = 3
  AND bool_and(NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
    AND NOT pg_has_role(oid, (SELECT nspowner FROM pg_namespace WHERE nspname = 'device_platform'), 'MEMBER'))
  AND NOT EXISTS (
    SELECT 1 FROM pg_roles member JOIN pg_roles granted ON member.oid <> granted.oid
    WHERE member.rolname IN (:'api_role', :'worker_role', :'maintenance_role')
      AND granted.rolname IN (:'api_role', :'worker_role', :'maintenance_role')
      AND pg_has_role(member.oid, granted.oid, 'MEMBER')
  ) AS roles_ok
FROM pg_roles WHERE rolname IN (:'api_role', :'worker_role', :'maintenance_role')
\gset
\if :roles_ok
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Use three distinct, unprivileged runtime roles without inherited access to each other or the schema owner.';
  END $preflight$;
\endif
GRANT CONNECT ON DATABASE :"db_name" TO :"api_role", :"worker_role", :"maintenance_role";
GRANT USAGE ON SCHEMA device_platform TO :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT ON ALL TABLES IN SCHEMA device_platform TO :"api_role", :"worker_role";
GRANT INSERT, UPDATE ON device_platform.organizations, device_platform.departments,
  device_platform.users, device_platform.organization_memberships, device_platform.devices,
  device_platform.provider_connections, device_platform.processing_profiles,
  device_platform.processing_runs TO :"api_role";
GRANT INSERT ON device_platform.processing_profile_revisions, device_platform.device_telemetry_samples,
  device_platform.activity_events TO :"api_role";
GRANT UPDATE ON device_platform.platform_settings TO :"api_role";
GRANT UPDATE ON device_platform.processing_runs TO :"worker_role";
GRANT UPDATE (last_used_at) ON device_platform.provider_connections TO :"worker_role";
GRANT INSERT ON device_platform.activity_events TO :"worker_role";
GRANT SELECT, DELETE ON device_platform.processing_runs, device_platform.device_telemetry_samples,
  device_platform.activity_events TO :"maintenance_role";
GRANT SELECT ON device_platform.platform_settings, device_platform.provider_connections TO :"maintenance_role";
GRANT UPDATE (request, result, error, updated_at) ON device_platform.processing_runs TO :"maintenance_role";
-- Row validators execute as the caller. Trigger functions are attached by owner.
GRANT EXECUTE ON FUNCTION device_platform.positive_integer(jsonb), device_platform.valid_policy(jsonb),
  device_platform.policy_within(jsonb,jsonb), device_platform.valid_device_defaults(jsonb),
  device_platform.valid_processing_settings(jsonb,uuid,uuid,uuid), device_platform.valid_metrics(jsonb)
  TO :"api_role", :"worker_role", :"maintenance_role";
GRANT EXECUTE ON FUNCTION device_platform.check_org_admin(uuid) TO :"api_role";
GRANT EXECUTE ON FUNCTION device_platform.valid_patient_background(jsonb) TO :"api_role";
-- No DELETE for API/worker, no UPDATE of revision/telemetry/audit payloads, no TRUNCATE.
-- Roles must be newly provisioned without broader pre-existing/inherited grants.
COMMIT;
