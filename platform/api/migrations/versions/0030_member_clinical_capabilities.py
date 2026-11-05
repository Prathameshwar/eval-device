"""Add audited tenant clinical capability assignments."""

from alembic import op

revision = "0030_clinical_capabilities"
down_revision = "0029_tenant_clinical_content"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE device_platform.organization_memberships
      ADD CONSTRAINT organization_memberships_org_id_unique UNIQUE(organization_id,id);
    CREATE TABLE device_platform.organization_member_capabilities (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      organization_id uuid NOT NULL,
      membership_id uuid NOT NULL,
      capability text NOT NULL CHECK(capability IN
        ('org.clinical.author','org.clinical.review','org.training.instruct','org.clinical.read')),
      granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      granted_by uuid NOT NULL REFERENCES device_platform.users(id),
      revoked_at timestamptz,
      revoked_by uuid REFERENCES device_platform.users(id),
      FOREIGN KEY(organization_id,membership_id)
        REFERENCES device_platform.organization_memberships(organization_id,id),
      UNIQUE(membership_id,capability),
      CHECK((revoked_at IS NULL)=(revoked_by IS NULL))
    );
    CREATE INDEX organization_member_capabilities_active
      ON device_platform.organization_member_capabilities(organization_id,membership_id)
      WHERE revoked_at IS NULL;
    REVOKE ALL ON device_platform.organization_member_capabilities FROM PUBLIC;
    CREATE OR REPLACE FUNCTION device_platform.organization_clinical_content_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,device_platform AS $$
    DECLARE current_count bigint; maximum integer;
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.revision<>1 THEN
          RAISE EXCEPTION 'Initial clinical revision must be one' USING ERRCODE='23514';
        END IF;
        PERFORM 1 FROM device_platform.organizations WHERE id=NEW.organization_id FOR UPDATE;
        IF TG_TABLE_NAME='organization_clinical_specialties' THEN maximum:=200;
        ELSIF TG_TABLE_NAME='organization_patient_profiles' THEN maximum:=500;
        ELSE maximum:=1000; END IF;
        EXECUTE format('SELECT count(*) FROM device_platform.%I WHERE organization_id=$1',TG_TABLE_NAME)
          INTO current_count USING NEW.organization_id;
        IF current_count>=maximum THEN
          RAISE EXCEPTION 'Tenant clinical catalog capacity reached' USING ERRCODE='23514';
        END IF;
      ELSE
        IF (NEW.id,NEW.organization_id,NEW.code,NEW.source_global_id,
            NEW.source_global_revision,NEW.created_at,NEW.created_by)
           IS DISTINCT FROM
           (OLD.id,OLD.organization_id,OLD.code,OLD.source_global_id,
            OLD.source_global_revision,OLD.created_at,OLD.created_by) THEN
          RAISE EXCEPTION 'Clinical content identity is immutable' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='organization_case_templates' THEN
          IF (NEW.specialty_id,NEW.patient_profile_id) IS DISTINCT FROM
             (OLD.specialty_id,OLD.patient_profile_id) THEN
            RAISE EXCEPTION 'Clinical case association is immutable' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.revision<>OLD.revision+1 THEN
          RAISE EXCEPTION 'Clinical revision must advance' USING ERRCODE='23514';
        END IF;
        NEW.updated_at:=clock_timestamp();
      END IF;
      RETURN NEW;
    END $$;
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration; capability audit history must be preserved.")
