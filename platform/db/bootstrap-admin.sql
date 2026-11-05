\set ON_ERROR_STOP on
-- psql 17 ignores an exit-code argument to \quit; SQL exceptions fail preflight reliably.
-- The deployment operator must verify this OIDC identity before invoking this file.
-- This is a one-time bootstrap, not a public signup or routine admin-grant endpoint.
\if :{?admin_id}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply admin_id (UUID), issuer, subject, email, and display_name with -v.';
  END $preflight$;
\endif
\if :{?issuer}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply issuer with -v.';
  END $preflight$;
\endif
\if :{?subject}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply subject with -v.';
  END $preflight$;
\endif
\if :{?email}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply email with -v.';
  END $preflight$;
\endif
\if :{?display_name}
\else
  DO $preflight$ BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Supply display_name with -v.';
  END $preflight$;
\endif
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL search_path = device_platform, pg_catalog;
SELECT id FROM platform_settings WHERE id = 1 FOR UPDATE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM device_platform.users WHERE platform_role = 'platform_admin') THEN
    RAISE EXCEPTION 'Bootstrap already completed; use audited administrator management';
  END IF;
END $$;
WITH administrator AS (
  INSERT INTO users (id, identity_issuer, identity_subject, display_name, email, email_verified, platform_role)
  VALUES (:'admin_id'::uuid, :'issuer', :'subject', :'display_name', :'email', true, 'platform_admin')
  ON CONFLICT (identity_issuer, identity_subject) DO UPDATE
    SET platform_role = 'platform_admin', is_active = true
  RETURNING id
)
INSERT INTO activity_events (id, actor_type, category, event_type, entity_type, entity_id,
  occurred_at, details, expires_at)
SELECT gen_random_uuid(), 'system', 'audit', 'platform.admin_bootstrapped', 'user', a.id,
  now(), '{"source":"trusted_deployment","scope":"platform"}'::jsonb,
  now() + make_interval(days => (s.default_organization_policy->>'audit_retention_days')::integer)
FROM administrator a CROSS JOIN platform_settings s;
COMMIT;
\echo 'First platform administrator provisioned; no password was created.'
