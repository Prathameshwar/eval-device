"""Tenant scenario workflow and published-version practice references.

Legacy catalog and selection rows remain intact for historical sessions and callers.
"""

from alembic import op

revision = "0035_unified_scenarios"
down_revision = "0034_platform_model_connections"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE device_platform.training_scenario_drafts
      ADD COLUMN specialty_id uuid,
      ADD COLUMN workflow_version smallint NOT NULL DEFAULT 2
        CHECK (workflow_version IN (1,2)),
      ADD COLUMN submitted_revision integer,
      ADD COLUMN submitted_at timestamptz,
      ADD CONSTRAINT training_draft_specialty_fk FOREIGN KEY (organization_id,specialty_id)
        REFERENCES device_platform.organization_clinical_specialties(organization_id,id),
      ADD CONSTRAINT training_draft_submission_pair CHECK (
        (submitted_revision IS NULL AND submitted_at IS NULL) OR
        (submitted_revision IS NOT NULL AND submitted_revision BETWEEN 1 AND revision
          AND submitted_at IS NOT NULL));
    ALTER TABLE device_platform.training_scenarios
      ADD COLUMN specialty_id uuid,
      ADD CONSTRAINT training_scenario_specialty_fk FOREIGN KEY (organization_id,specialty_id)
        REFERENCES device_platform.organization_clinical_specialties(organization_id,id);

    ALTER TABLE device_platform.training_scenario_drafts DISABLE TRIGGER training_draft_guard;
    ALTER TABLE device_platform.training_scenarios DISABLE TRIGGER training_scenario_guard;
    UPDATE device_platform.training_scenario_drafts SET workflow_version=1;
    UPDATE device_platform.training_scenario_drafts d SET specialty_id=c.specialty_id
      FROM device_platform.organization_case_templates c
      WHERE d.organization_id=c.organization_id AND d.source_case_id=c.id;
    UPDATE device_platform.training_scenarios s SET specialty_id=c.specialty_id
      FROM device_platform.organization_case_templates c
      WHERE s.organization_id=c.organization_id AND s.starter_case_id=c.id;
    UPDATE device_platform.training_scenario_drafts d SET specialty_id=c.id
      FROM device_platform.organization_clinical_specialties c
      WHERE d.specialty_id IS NULL AND d.organization_id=c.organization_id
        AND lower(d.document->>'specialty')=lower(c.name)
        AND (SELECT count(*) FROM device_platform.organization_clinical_specialties match
             WHERE match.organization_id=d.organization_id
               AND lower(match.name)=lower(d.document->>'specialty'))=1;
    UPDATE device_platform.training_scenarios s SET specialty_id=c.id
      FROM device_platform.organization_clinical_specialties c
      WHERE s.specialty_id IS NULL AND s.organization_id=c.organization_id
        AND lower(s.document->>'specialty')=lower(c.name)
        AND (SELECT count(*) FROM device_platform.organization_clinical_specialties match
             WHERE match.organization_id=s.organization_id
               AND lower(match.name)=lower(s.document->>'specialty'))=1;
    ALTER TABLE device_platform.training_scenario_drafts ENABLE TRIGGER training_draft_guard;
    ALTER TABLE device_platform.training_scenarios ENABLE TRIGGER training_scenario_guard;

    CREATE TABLE device_platform.tenant_scenario_defaults (
      organization_id uuid PRIMARY KEY REFERENCES device_platform.organizations(id),
      scenario_id uuid NOT NULL,
      language text NOT NULL CHECK (language IN ('en','hi')),
      revision integer NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 2147483646),
      updated_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      FOREIGN KEY (organization_id,scenario_id)
        REFERENCES device_platform.training_scenarios(organization_id,id)
    );
    REVOKE ALL ON device_platform.tenant_scenario_defaults FROM PUBLIC;
    CREATE FUNCTION device_platform.tenant_scenario_default_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
          OR NEW.created_at IS DISTINCT FROM OLD.created_at
          OR NEW.revision<>OLD.revision+1 THEN
          RAISE EXCEPTION 'Invalid scenario default revision' USING ERRCODE='23514';
        END IF;
        NEW.updated_at:=clock_timestamp();
      ELSIF NEW.revision<>1 THEN
        RAISE EXCEPTION 'Initial scenario default revision must be one' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM device_platform.training_scenarios s
        WHERE s.organization_id=NEW.organization_id AND s.id=NEW.scenario_id
          AND s.approved_at IS NOT NULL AND s.is_active
      ) THEN
        RAISE EXCEPTION 'Scenario default must be active and published' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER tenant_scenario_default_guard BEFORE INSERT OR UPDATE
      ON device_platform.tenant_scenario_defaults FOR EACH ROW
      EXECUTE FUNCTION device_platform.tenant_scenario_default_guard();
    REVOKE ALL ON FUNCTION device_platform.tenant_scenario_default_guard() FROM PUBLIC;
    INSERT INTO device_platform.tenant_scenario_defaults
      (organization_id,scenario_id,language,updated_by)
    SELECT old.organization_id, s.id, old.language, old.updated_by
      FROM device_platform.tenant_patient_setup_defaults old
      JOIN device_platform.training_scenarios s
        ON s.organization_id=old.organization_id AND s.starter_case_id=old.case_id
      WHERE s.approved_at IS NOT NULL AND s.is_active
      ON CONFLICT (organization_id) DO NOTHING;

    ALTER TABLE device_platform.patient_practice_selections
      ADD COLUMN scenario_id uuid,
      ADD CONSTRAINT patient_practice_scenario_fk FOREIGN KEY (organization_id,scenario_id)
        REFERENCES device_platform.training_scenarios(organization_id,id),
      DROP CONSTRAINT patient_practice_has_reference,
      ADD CONSTRAINT patient_practice_has_reference CHECK (
        template_id IS NOT NULL OR tenant_template_id IS NOT NULL OR scenario_id IS NOT NULL),
      ADD CONSTRAINT patient_practice_scenario_exclusive CHECK (
        scenario_id IS NULL OR (template_id IS NULL AND tenant_template_id IS NULL));
    ALTER TABLE device_platform.patient_conversations
      ADD COLUMN scenario_id uuid,
      ADD CONSTRAINT patient_conversation_scenario_fk FOREIGN KEY (organization_id,scenario_id)
        REFERENCES device_platform.training_scenarios(organization_id,id);
    CREATE INDEX patient_conversations_scenario
      ON device_platform.patient_conversations(organization_id,scenario_id)
      WHERE scenario_id IS NOT NULL;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; scenario workflow references and defaults must be preserved")
