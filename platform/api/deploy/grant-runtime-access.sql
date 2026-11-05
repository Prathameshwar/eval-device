-- Self-contained API grant bundle; keep synchronized with platform/db/grant-access.sql.
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
REVOKE ALL ON device_platform.device_identities FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT ON device_platform.device_identities TO :"api_role";
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
GRANT SELECT ON public.alembic_version TO :"api_role", :"worker_role", :"maintenance_role";
GRANT UPDATE ON device_platform.subscription_plans TO :"api_role";
GRANT EXECUTE ON FUNCTION device_platform.subscription_usage(uuid) TO :"api_role";
GRANT INSERT, UPDATE ON device_platform.training_scenarios, device_platform.training_sessions TO :"api_role";
GRANT SELECT, DELETE ON device_platform.training_sessions TO :"maintenance_role";
-- Drafts contain private instructor content; workers/retention do not need it.
REVOKE ALL ON device_platform.training_scenario_drafts FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.training_scenario_drafts TO :"api_role";
REVOKE ALL ON device_platform.tenant_scenario_defaults FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.tenant_scenario_defaults TO :"api_role";
REVOKE ALL ON device_platform.llm_connections,device_platform.llm_requests FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.llm_connections,device_platform.llm_requests TO :"api_role";
REVOKE ALL ON device_platform.speech_requests FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.speech_requests TO :"api_role";
GRANT SELECT, DELETE ON device_platform.llm_requests TO :"maintenance_role";
-- Shared category defaults are deployment-managed; runtime roles cannot edit them.
REVOKE ALL ON device_platform.scenario_categories FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT ON device_platform.scenario_categories TO :"api_role";
-- Fictional identity templates are deployment-managed and contain no tenant records.
REVOKE ALL ON device_platform.patient_identities FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT ON device_platform.patient_identities TO :"api_role";
-- Practice snapshots belong to staff; background workers have no access.
REVOKE ALL ON device_platform.patient_case_templates,device_platform.patient_practice_selections FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT ON device_platform.patient_case_templates TO :"api_role";
-- Migration 0043 user/device owner columns inherit these table-level grants.
GRANT SELECT, INSERT, UPDATE ON device_platform.device_session_queues, device_platform.practice_sessions TO :"api_role";
REVOKE ALL ON device_platform.device_session_queues, device_platform.practice_sessions FROM :"worker_role", :"maintenance_role";
-- Devices authenticate through the API; they never receive a PostgreSQL login.
GRANT SELECT, INSERT, UPDATE ON device_platform.patient_practice_selections TO :"api_role";
-- A turn executed on a caller's own machine is reported once and never amended here, so the
-- API inserts and reads only; retention deletes rows the trigger has already let expire.
REVOKE ALL ON device_platform.local_turns FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT ON device_platform.local_turns TO :"api_role";
GRANT SELECT, DELETE ON device_platform.local_turns TO :"maintenance_role";
REVOKE ALL ON device_platform.local_conversation_turns FROM :"api_role", :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT ON device_platform.local_conversation_turns TO :"api_role";
GRANT SELECT, DELETE ON device_platform.local_conversation_turns TO :"maintenance_role";
-- Local identity secrets and delivery payloads are API-owned. Processing and retention workers
-- receive no access; retention is handled by bounded API maintenance until a dedicated role exists.
REVOKE ALL ON device_platform.local_credentials,device_platform.local_sessions,
  device_platform.account_action_tokens,device_platform.auth_rate_limits,
  device_platform.account_email_outbox FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.local_credentials TO :"api_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.local_sessions,
  device_platform.account_action_tokens,
  device_platform.auth_rate_limits,device_platform.account_email_outbox TO :"api_role";
-- Model definitions are platform-managed through the API; tenant workers only consume immutable
-- profile/run snapshots and do not edit or discover this catalog.
REVOKE ALL ON device_platform.model_definitions FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.model_definitions TO :"api_role";
REVOKE ALL ON device_platform.platform_model_connections FROM :"worker_role", :"maintenance_role";
GRANT SELECT ON device_platform.platform_model_connections TO :"api_role";
REVOKE ALL ON device_platform.media_model_configs FROM :"worker_role", :"maintenance_role";
GRANT SELECT ON device_platform.media_model_configs TO :"api_role";
REVOKE ALL ON device_platform.patient_conversations FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.patient_conversations TO :"api_role";
GRANT SELECT, DELETE ON device_platform.patient_conversations TO :"maintenance_role";
-- Tenant import records and encrypted invitation tokens are API-owned.
REVOKE ALL ON device_platform.member_imports,device_platform.invitation_email_outbox
  FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.member_imports,device_platform.invitation_email_outbox
  TO :"api_role";
-- Existing shared patient catalog is frozen for API callers at cutover.
REVOKE INSERT, UPDATE, DELETE ON device_platform.scenario_categories,
  device_platform.patient_identities,device_platform.patient_case_templates FROM :"api_role";
-- Tenant clinical drafts are API-owned; workers and retention do not read private case facts.
REVOKE ALL ON device_platform.organization_clinical_specialties,
  device_platform.organization_patient_profiles,device_platform.organization_case_templates
  FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.organization_clinical_specialties,
  device_platform.organization_patient_profiles,device_platform.organization_case_templates
  TO :"api_role";
REVOKE ALL ON device_platform.tenant_patient_setup_defaults
  FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.tenant_patient_setup_defaults TO :"api_role";
REVOKE ALL ON device_platform.organization_member_capabilities
  FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.organization_member_capabilities TO :"api_role";
-- Localization row validators run as the API caller; workers do not edit this catalog.
REVOKE ALL ON FUNCTION device_platform.valid_language_map(jsonb,integer),
  device_platform.valid_language_list(text[],text) FROM PUBLIC, :"worker_role", :"maintenance_role";
GRANT EXECUTE ON FUNCTION device_platform.valid_language_map(jsonb,integer),
  device_platform.valid_language_list(text[],text) TO :"api_role";
GRANT SELECT, INSERT, UPDATE ON device_platform.runtime_models, device_platform.device_model_selections TO :"api_role";
GRANT SELECT ON device_platform.runtime_models, device_platform.device_model_selections TO :"worker_role";
GRANT UPDATE(last_used_at) ON device_platform.runtime_models TO :"worker_role";
REVOKE ALL ON device_platform.runtime_models, device_platform.device_model_selections FROM :"maintenance_role";

-- Workers can read media credentials only; conversation credentials stay with the API.
ALTER TABLE device_platform.runtime_models ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_models_api ON device_platform.runtime_models;
CREATE POLICY runtime_models_api ON device_platform.runtime_models TO :"api_role" USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS runtime_models_worker ON device_platform.runtime_models;
CREATE POLICY runtime_models_worker ON device_platform.runtime_models TO :"worker_role" USING (kind<>'llm') WITH CHECK (kind<>'llm');

-- Historical configurations are not an alternate management path.
REVOKE INSERT, UPDATE, DELETE ON device_platform.provider_connections,
  device_platform.llm_connections, device_platform.processing_profiles FROM :"api_role";
REVOKE UPDATE(last_used_at) ON device_platform.provider_connections FROM :"worker_role";
-- Only the API can receive, serve and expire private session archive objects.
REVOKE ALL ON device_platform.session_archives,device_platform.session_archive_items FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.session_archives,device_platform.session_archive_items TO :"api_role";
COMMIT;
