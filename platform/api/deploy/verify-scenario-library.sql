-- Read-only installation check. Does not create data, approve cases, or modify grants.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
DO $verify$
BEGIN
  -- Verify the authoring storage contract, independently of unrelated later migrations.
  -- API/worker readiness separately requires their exact current Alembic head.
  IF to_regclass('public.alembic_version') IS NULL
      OR to_regclass('device_platform.training_scenario_drafts') IS NULL
      OR to_regclass('device_platform.training_scenarios') IS NULL THEN
    RAISE EXCEPTION 'Apply the reviewed scenario authoring migrations before verifying storage';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num IS NOT NULL) THEN
    RAISE EXCEPTION 'Missing Alembic migration revision';
  END IF;
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='device_platform'
      AND table_name='training_scenario_drafts') NOT IN (14,17,21) THEN
    RAISE EXCEPTION 'Missing or unexpected draft columns';
  END IF;
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='device_platform'
      AND table_name='training_scenario_drafts') >= 17 AND
      ((SELECT count(*) FROM pg_constraint
        WHERE conrelid='device_platform.training_scenario_drafts'::regclass
        AND conname IN ('training_draft_case_pair','training_draft_case_fk','training_draft_one_source')
        AND convalidated) <> 3 OR
       NOT EXISTS (SELECT 1 FROM information_schema.columns
         WHERE table_schema='device_platform' AND table_name='training_scenario_drafts'
         AND column_name='content_updated_by' AND is_nullable='NO')) THEN
    RAISE EXCEPTION 'Missing tenant case provenance contract';
  END IF;
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='device_platform'
      AND table_name='training_scenario_drafts') = 21 AND
      (to_regclass('device_platform.tenant_scenario_defaults') IS NULL OR
       (SELECT count(*) FROM pg_constraint
        WHERE conrelid='device_platform.training_scenario_drafts'::regclass
        AND conname IN ('training_draft_specialty_fk','training_draft_submission_pair')
        AND convalidated) <> 2) THEN
    RAISE EXCEPTION 'Missing unified scenario workflow contract';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conrelid='device_platform.training_scenario_drafts'::regclass
      AND conname='training_draft_document' AND contype='c' AND convalidated) THEN
    RAISE EXCEPTION 'Missing or unvalidated draft envelope constraint';
  END IF;
  IF (SELECT count(*) FROM pg_constraint WHERE conrelid='device_platform.training_scenarios'::regclass
      AND conname IN ('training_scenario_draft_pair','training_scenario_draft_fk','training_scenario_draft_once')
      AND convalidated) <> 3 THEN
    RAISE EXCEPTION 'Missing publication provenance constraints';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='O' AND
      ((tgrelid='device_platform.training_scenario_drafts'::regclass AND tgname='training_draft_guard') OR
       (tgrelid='device_platform.training_scenarios'::regclass AND tgname IN ('training_scenario_guard','training_scenario_source_guard')))) <> 3 THEN
    RAISE EXCEPTION 'Missing or disabled authoring guards';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE n.nspname='device_platform' AND p.proname IN ('training_draft_guard','training_scenario_source_guard')
      AND a.grantee=0 AND a.privilege_type='EXECUTE') THEN
    RAISE EXCEPTION 'PUBLIC execution must be revoked from authoring guard functions';
  END IF;
END $verify$;
SELECT 'scenario authoring storage verified; API workflow and clinical validation remain separate' AS result;
COMMIT;
