-- Read-only preflight/postcutover inventory: identifiers and counts only.
-- to_jsonb(p) keeps the selection mapping count valid before and after migration 0029.
-- The same projection keeps published-scenario counts compatible before migration 0035.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';

SELECT version_num AS alembic_revision,
       current_setting('transaction_read_only') AS read_only_transaction
FROM public.alembic_version;

SELECT 'specialties' AS kind, count(*) AS total,
       count(*) FILTER (WHERE is_active) AS active,
       count(*) FILTER (WHERE management_version > 1) AS version_above_initial
FROM device_platform.scenario_categories
UNION ALL
SELECT 'patient_profiles', count(*), count(*) FILTER (WHERE is_active),
       count(*) FILTER (WHERE management_version > 1)
FROM device_platform.patient_identities
UNION ALL
SELECT 'case_templates', count(*), count(*) FILTER (WHERE is_active),
       count(*) FILTER (WHERE revision > 1)
FROM device_platform.patient_case_templates;

-- Version above one does not prove manual changes; earlier migrations revised seed cases.
SELECT o.id AS organization_id,
       (SELECT count(*) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id) AS practice_selections,
       (SELECT count(*) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id AND to_jsonb(p)->>'tenant_template_id' IS NOT NULL)
          AS mapped_tenant_selections,
       (SELECT count(*) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id AND to_jsonb(p)->>'scenario_id' IS NOT NULL)
          AS published_scenario_selections,
       (SELECT count(*) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id AND p.template_id IS NOT NULL
          AND to_jsonb(p)->>'tenant_template_id' IS NULL) AS unmapped_legacy_selections,
       (SELECT count(DISTINCT template_id) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id) AS referenced_global_cases,
       (SELECT count(DISTINCT category_id) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id) AS referenced_global_specialties,
       (SELECT count(DISTINCT patient_identity_id) FROM device_platform.patient_practice_selections p
        WHERE p.organization_id = o.id) AS referenced_global_profiles,
       (SELECT count(*) FROM device_platform.patient_practice_selections p
        JOIN device_platform.patient_case_templates c ON c.id = p.template_id
        JOIN device_platform.scenario_categories specialty ON specialty.id = p.category_id
        JOIN device_platform.patient_identities profile ON profile.id = p.patient_identity_id
        WHERE p.organization_id = o.id
          AND (NOT c.is_active OR NOT specialty.is_active OR NOT profile.is_active))
          AS unusable_legacy_practice_selections,
       (SELECT count(*) FROM device_platform.training_scenario_drafts d
        WHERE d.organization_id = o.id) AS scenario_drafts,
       (SELECT count(*) FROM device_platform.training_scenarios s
        WHERE s.organization_id = o.id AND s.approved_at IS NOT NULL) AS approved_scenarios,
       (SELECT count(*) FROM device_platform.training_scenarios s
        WHERE s.organization_id = o.id AND s.approved_at IS NULL) AS awaiting_approval,
       (SELECT count(*) FROM device_platform.training_sessions t
        WHERE t.organization_id = o.id) AS training_sessions,
       (SELECT count(*) FROM device_platform.training_sessions t
        WHERE t.organization_id = o.id AND t.status IN ('authorized', 'active')
          AND t.expires_at > now()) AS unexpired_active_sessions,
       (SELECT count(*) FROM device_platform.training_sessions t
        WHERE t.organization_id = o.id AND t.status IN ('authorized', 'active')
          AND t.expires_at <= now()) AS expired_active_status_sessions,
       (SELECT count(*) FROM device_platform.devices d
        WHERE d.organization_id = o.id AND d.enrollment_state = 'enrolled') AS enrolled_registrations,
       (SELECT count(*) FROM device_platform.devices d
        WHERE d.organization_id = o.id AND d.enrollment_state = 'enrolled'
          AND d.credential_hash IS NOT NULL AND d.credential_revoked_at IS NULL)
          AS enrolled_with_unrevoked_credential
FROM device_platform.organizations o
ORDER BY o.id;

SELECT 'selection_missing_global_case' AS issue, count(*) AS rows
FROM device_platform.patient_practice_selections p
LEFT JOIN device_platform.patient_case_templates c ON c.id = p.template_id
WHERE p.template_id IS NOT NULL AND c.id IS NULL
UNION ALL
SELECT 'selection_parent_mismatch', count(*)
FROM device_platform.patient_practice_selections p
JOIN device_platform.patient_case_templates c ON c.id = p.template_id
WHERE c.category_id <> p.category_id OR c.patient_identity_id <> p.patient_identity_id
UNION ALL
SELECT 'session_device_tenant_mismatch', count(*)
FROM device_platform.training_sessions t
LEFT JOIN device_platform.devices d ON d.id = t.device_id
WHERE d.id IS NULL OR d.organization_id <> t.organization_id
UNION ALL
SELECT 'session_scenario_tenant_mismatch', count(*)
FROM device_platform.training_sessions t
LEFT JOIN device_platform.training_scenarios s ON s.id = t.scenario_id
WHERE s.id IS NULL OR s.organization_id <> t.organization_id;

-- Informational: historical membership rows may have been removed after a session.
SELECT 'historical_learner_membership_missing' AS observation, count(*) AS rows
FROM device_platform.training_sessions t
WHERE NOT EXISTS (
  SELECT 1 FROM device_platform.organization_memberships m
  WHERE m.organization_id = t.organization_id AND m.user_id = t.learner_id
)
UNION ALL
SELECT 'historical_instructor_membership_missing', count(*)
FROM device_platform.training_sessions t
WHERE NOT EXISTS (
  SELECT 1 FROM device_platform.organization_memberships m
  WHERE m.organization_id = t.organization_id AND m.user_id = t.instructor_id
);

SELECT count(*) AS global_cases_used_by_multiple_tenants
FROM (
  SELECT template_id FROM device_platform.patient_practice_selections
  GROUP BY template_id HAVING count(DISTINCT organization_id) > 1
) shared;

ROLLBACK;
