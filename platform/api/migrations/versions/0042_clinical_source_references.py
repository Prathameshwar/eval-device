"""Preserve current source references across the clinical format-only upgrade."""

from alembic import op

revision = "0042_clinical_source_references"
down_revision = "0041_simple_clinical_cases"
branch_labels = None
depends_on = None


def upgrade():
    # 0041 advanced clinical document revisions without advancing references to
    # those same snapshots. Repair only rows untouched since that conversion,
    # and only references that were current immediately before it. A genuinely
    # stale reference must continue to require the author's explicit refresh.
    op.execute("""
      CREATE TEMP TABLE clinical_conversion_stamp ON COMMIT DROP AS
        SELECT occurred_at AS stamp FROM device_platform.activity_events
        WHERE event_type='platform.scenarios.simplified'
          AND details->>'source'='0041_simple_clinical_cases';

      ALTER TABLE device_platform.organization_case_templates DISABLE TRIGGER organization_case_templates_guard;
      ALTER TABLE device_platform.training_scenario_drafts DISABLE TRIGGER training_draft_guard;
      ALTER TABLE device_platform.patient_practice_selections DISABLE TRIGGER patient_selection_guard;

      UPDATE device_platform.organization_case_templates c
        SET source_global_revision=g.revision
        FROM device_platform.patient_case_templates g, clinical_conversion_stamp m
        WHERE c.source_global_id=g.id AND c.source_global_revision=g.revision-1
          AND c.updated_at=m.stamp AND g.updated_at=m.stamp;

      UPDATE device_platform.training_scenario_drafts d
        SET source_case_revision=c.revision,revision=d.revision+1,updated_at=now()
        FROM device_platform.organization_case_templates c, clinical_conversion_stamp m
        WHERE d.organization_id=c.organization_id AND d.source_case_id=c.id
          AND d.source_case_revision=c.revision-1 AND d.submitted_revision IS NULL
          AND d.updated_at=m.stamp AND c.updated_at=m.stamp;

      UPDATE device_platform.patient_practice_selections p
        SET template_revision=c.revision,revision=p.revision+1,updated_at=now()
        FROM device_platform.organization_case_templates c, clinical_conversion_stamp m
        WHERE p.scenario_id IS NULL AND p.tenant_template_id=c.id AND p.organization_id=c.organization_id
          AND p.template_revision=c.revision-1 AND p.updated_at=m.stamp AND c.updated_at=m.stamp;
      UPDATE device_platform.patient_practice_selections p
        SET template_revision=g.revision,revision=p.revision+1,updated_at=now()
        FROM device_platform.patient_case_templates g, clinical_conversion_stamp m
        WHERE p.scenario_id IS NULL AND p.tenant_template_id IS NULL AND p.template_id=g.id
          AND p.template_revision=g.revision-1 AND p.updated_at=m.stamp AND g.updated_at=m.stamp;

      ALTER TABLE device_platform.organization_case_templates ENABLE TRIGGER organization_case_templates_guard;
      ALTER TABLE device_platform.training_scenario_drafts ENABLE TRIGGER training_draft_guard;
      ALTER TABLE device_platform.patient_practice_selections ENABLE TRIGGER patient_selection_guard;

      INSERT INTO device_platform.activity_events
        (id,actor_type,category,event_type,severity,entity_type,occurred_at,received_at,details,expires_at)
      SELECT gen_random_uuid(),'system','audit','platform.scenarios.references_repaired','info','platform',now(),now(),
        jsonb_build_object('source','0042_clinical_source_references','clinical_content_changed',false),
        now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
          (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
      FROM device_platform.platform_settings p WHERE id=1;
    """)


def downgrade():
    raise RuntimeError("Use a forward migration to preserve clinical provenance")
