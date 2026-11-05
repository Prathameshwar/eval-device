"""System-labeled scenario starters and a tenant-wide patient setup template."""

from alembic import op

revision = "0033_tenant_training_starters"
down_revision = "0032_tenant_import_passwords"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE device_platform.training_scenarios
      ADD COLUMN publication_source text NOT NULL DEFAULT 'tenant_review'
        CHECK (publication_source IN ('tenant_review','system_starter')),
      ADD COLUMN starter_case_id uuid,
      ADD CONSTRAINT training_scenario_starter_case_fk
        FOREIGN KEY (organization_id,starter_case_id)
        REFERENCES device_platform.organization_case_templates(organization_id,id);

    DO $$
    DECLARE old_check text;
    BEGIN
      SELECT c.conname INTO old_check FROM pg_constraint c
      WHERE c.conrelid='device_platform.training_scenarios'::regclass
        AND c.contype='c'
        AND pg_get_constraintdef(c.oid) LIKE '%approved_by IS NULL%'
        AND pg_get_constraintdef(c.oid) LIKE '%approved_at IS NULL%'
        AND pg_get_constraintdef(c.oid) LIKE '%approval IS NULL%'
      LIMIT 1;
      IF old_check IS NULL THEN
        RAISE EXCEPTION 'Expected training scenario approval constraint is missing';
      END IF;
      EXECUTE format('ALTER TABLE device_platform.training_scenarios DROP CONSTRAINT %I',old_check);
    END $$;
    ALTER TABLE device_platform.training_scenarios
      ADD CONSTRAINT training_scenario_publication_source_check CHECK (
        (publication_source='tenant_review' AND starter_case_id IS NULL AND
          ((approved_by IS NULL AND approved_at IS NULL AND approval IS NULL) OR
           (approved_by IS NOT NULL AND approved_at IS NOT NULL AND approval IS NOT NULL)))
        OR
        (publication_source='system_starter' AND starter_case_id IS NOT NULL AND
          approved_by IS NULL AND approved_at IS NOT NULL AND approval IS NULL)
      );
    CREATE UNIQUE INDEX training_scenario_system_starter_unique
      ON device_platform.training_scenarios(organization_id,starter_case_id)
      WHERE publication_source='system_starter';

    CREATE TABLE device_platform.tenant_patient_setup_defaults (
      organization_id uuid PRIMARY KEY REFERENCES device_platform.organizations(id),
      case_id uuid NOT NULL,
      specialty_id uuid NOT NULL,
      patient_profile_id uuid NOT NULL,
      language text NOT NULL CHECK(language IN ('en','hi')),
      revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      updated_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      FOREIGN KEY (organization_id,case_id,specialty_id,patient_profile_id)
        REFERENCES device_platform.organization_case_templates
          (organization_id,id,specialty_id,patient_profile_id)
    );
    CREATE FUNCTION device_platform.tenant_patient_setup_default_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF (NEW.organization_id,NEW.created_by,NEW.created_at) IS DISTINCT FROM
           (OLD.organization_id,OLD.created_by,OLD.created_at) OR
           NEW.revision<>OLD.revision+1 THEN
          RAISE EXCEPTION 'Patient setup default identity or revision changed'
            USING ERRCODE='23514';
        END IF;
        NEW.updated_at:=clock_timestamp();
      ELSIF NEW.revision<>1 THEN
        RAISE EXCEPTION 'Initial patient setup default revision must be one'
          USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER tenant_patient_setup_default_guard
      BEFORE INSERT OR UPDATE ON device_platform.tenant_patient_setup_defaults
      FOR EACH ROW EXECUTE FUNCTION device_platform.tenant_patient_setup_default_guard();
    REVOKE ALL ON FUNCTION device_platform.tenant_patient_setup_default_guard() FROM PUBLIC;
    REVOKE ALL ON device_platform.tenant_patient_setup_defaults FROM PUBLIC;
    COMMENT ON TABLE device_platform.tenant_patient_setup_defaults IS
      'Tenant-wide suggested staff rehearsal case; each staff member explicitly adopts it into a private setup.';
    COMMENT ON COLUMN device_platform.training_scenarios.publication_source IS
      'System starter publication is labeled separately from tenant clinician approval.';
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore; tenant starters must be preserved")
