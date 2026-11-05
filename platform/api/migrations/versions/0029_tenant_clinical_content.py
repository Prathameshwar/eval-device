"""Expand tenant-owned fictional clinical catalog without rewriting history."""

from alembic import op

revision = "0029_tenant_clinical_content"
down_revision = "0028_language_validator_acl"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE device_platform.organization_clinical_specialties (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      code text NOT NULL CHECK(code ~ '^[a-z][a-z0-9_]{0,39}$'),
      name text NOT NULL CHECK(name=btrim(name) AND length(name) BETWEEN 1 AND 120),
      names jsonb NOT NULL CHECK(device_platform.valid_language_map(names,120)
        AND octet_length(names::text)<=8192),
      description text NOT NULL CHECK(description=btrim(description) AND length(description) BETWEEN 1 AND 600),
      sort_order integer NOT NULL DEFAULT 0 CHECK(sort_order BETWEEN 0 AND 10000),
      revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
      is_active boolean NOT NULL DEFAULT false,
      archived_at timestamptz,
      created_by uuid REFERENCES device_platform.users(id),
      updated_by uuid REFERENCES device_platform.users(id),
      source_global_id uuid REFERENCES device_platform.scenario_categories(id),
      source_global_revision integer CHECK(source_global_revision BETWEEN 1 AND 2147483646),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), UNIQUE(organization_id,code),
      UNIQUE(organization_id,source_global_id),
      CHECK((source_global_id IS NULL)=(source_global_revision IS NULL)),
      CHECK(archived_at IS NULL OR NOT is_active)
    );
    CREATE UNIQUE INDEX organization_clinical_specialties_name_unique
      ON device_platform.organization_clinical_specialties(organization_id,lower(name));
    CREATE INDEX organization_clinical_specialties_listing
      ON device_platform.organization_clinical_specialties(organization_id,is_active,sort_order,id);

    CREATE TABLE device_platform.organization_patient_profiles (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      code text NOT NULL CHECK(code ~ '^[a-z][a-z0-9_]{0,39}$'),
      name text NOT NULL CHECK(name=btrim(name) AND length(name) BETWEEN 1 AND 120),
      names jsonb NOT NULL CHECK(device_platform.valid_language_map(names,120)
        AND octet_length(names::text)<=8192),
      age_years integer NOT NULL CHECK(age_years BETWEEN 0 AND 150),
      sex text NOT NULL CHECK(sex IN ('female','male','intersex','unspecified')),
      occupations jsonb NOT NULL CHECK(device_platform.valid_language_map(occupations,600)
        AND octet_length(occupations::text)<=16384),
      height_cm numeric(5,2) NOT NULL CHECK(height_cm>0 AND height_cm<=400),
      weight_kg numeric(6,2) NOT NULL CHECK(weight_kg>0 AND weight_kg<=2000),
      preferred_language text NOT NULL,
      languages text[] NOT NULL,
      backgrounds jsonb NOT NULL CHECK(device_platform.valid_language_map(backgrounds,600)
        AND octet_length(backgrounds::text)<=65536),
      is_fictional boolean NOT NULL DEFAULT true CHECK(is_fictional),
      revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
      is_active boolean NOT NULL DEFAULT false,
      archived_at timestamptz,
      created_by uuid REFERENCES device_platform.users(id),
      updated_by uuid REFERENCES device_platform.users(id),
      source_global_id uuid REFERENCES device_platform.patient_identities(id),
      source_global_revision integer CHECK(source_global_revision BETWEEN 1 AND 2147483646),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), UNIQUE(organization_id,code),
      UNIQUE(organization_id,source_global_id),
      CHECK((source_global_id IS NULL)=(source_global_revision IS NULL)),
      CHECK(archived_at IS NULL OR NOT is_active),
      CHECK(device_platform.valid_language_list(languages,preferred_language) IS TRUE),
      CHECK(names ?& languages AND occupations ?& languages AND backgrounds ?& languages)
    );
    CREATE INDEX organization_patient_profiles_listing
      ON device_platform.organization_patient_profiles(organization_id,is_active,name,id);

    CREATE TABLE device_platform.organization_case_templates (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      code text NOT NULL CHECK(code ~ '^[a-z][a-z0-9_]{0,39}$'),
      specialty_id uuid NOT NULL,
      patient_profile_id uuid NOT NULL,
      title text NOT NULL CHECK(title=btrim(title) AND length(title) BETWEEN 1 AND 120),
      titles jsonb NOT NULL CHECK(device_platform.valid_language_map(titles,160)
        AND octet_length(titles::text)<=8192),
      document jsonb NOT NULL CHECK((jsonb_typeof(document)='object'
        AND octet_length(document::text)<=524288
        AND document->'version' IN ('2'::jsonb,'3'::jsonb)
        AND document->>'code'=code AND document->>'title'=title) IS TRUE),
      revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
      is_synthetic boolean NOT NULL DEFAULT true CHECK(is_synthetic),
      is_active boolean NOT NULL DEFAULT false,
      archived_at timestamptz,
      created_by uuid REFERENCES device_platform.users(id),
      updated_by uuid REFERENCES device_platform.users(id),
      source_global_id uuid REFERENCES device_platform.patient_case_templates(id),
      source_global_revision integer CHECK(source_global_revision BETWEEN 1 AND 2147483646),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), UNIQUE(organization_id,code),
      UNIQUE(organization_id,id,specialty_id,patient_profile_id),
      UNIQUE(organization_id,source_global_id),
      FOREIGN KEY(organization_id,specialty_id)
        REFERENCES device_platform.organization_clinical_specialties(organization_id,id),
      FOREIGN KEY(organization_id,patient_profile_id)
        REFERENCES device_platform.organization_patient_profiles(organization_id,id),
      CHECK((source_global_id IS NULL)=(source_global_revision IS NULL)),
      CHECK(archived_at IS NULL OR NOT is_active)
    );
    CREATE INDEX organization_case_templates_listing
      ON device_platform.organization_case_templates(organization_id,is_active,title,id);
    CREATE INDEX organization_case_templates_specialty
      ON device_platform.organization_case_templates(organization_id,specialty_id);
    CREATE INDEX organization_case_templates_profile
      ON device_platform.organization_case_templates(organization_id,patient_profile_id);

    CREATE FUNCTION device_platform.organization_clinical_content_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,device_platform AS $$
    DECLARE current_count bigint; maximum integer;
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.revision<>1 THEN
          RAISE EXCEPTION 'Initial clinical revision must be one' USING ERRCODE='23514';
        END IF;
        -- Serialize tenant quotas through the parent row, including concurrent API requests.
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
        IF TG_TABLE_NAME='organization_case_templates' AND
           (NEW.specialty_id,NEW.patient_profile_id) IS DISTINCT FROM
           (OLD.specialty_id,OLD.patient_profile_id) THEN
          RAISE EXCEPTION 'Clinical case association is immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.revision<>OLD.revision+1 THEN
          RAISE EXCEPTION 'Clinical revision must advance' USING ERRCODE='23514';
        END IF;
        NEW.updated_at:=clock_timestamp();
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER organization_clinical_specialties_guard
      BEFORE INSERT OR UPDATE ON device_platform.organization_clinical_specialties
      FOR EACH ROW EXECUTE FUNCTION device_platform.organization_clinical_content_guard();
    CREATE TRIGGER organization_patient_profiles_guard
      BEFORE INSERT OR UPDATE ON device_platform.organization_patient_profiles
      FOR EACH ROW EXECUTE FUNCTION device_platform.organization_clinical_content_guard();
    CREATE TRIGGER organization_case_templates_guard
      BEFORE INSERT OR UPDATE ON device_platform.organization_case_templates
      FOR EACH ROW EXECUTE FUNCTION device_platform.organization_clinical_content_guard();
    REVOKE ALL ON FUNCTION device_platform.organization_clinical_content_guard() FROM PUBLIC;
    REVOKE ALL ON device_platform.organization_clinical_specialties,
      device_platform.organization_patient_profiles,
      device_platform.organization_case_templates FROM PUBLIC;

    ALTER TABLE device_platform.patient_practice_selections
      ALTER COLUMN template_id DROP NOT NULL,
      ALTER COLUMN category_id DROP NOT NULL,
      ALTER COLUMN patient_identity_id DROP NOT NULL,
      ADD COLUMN tenant_template_id uuid,
      ADD COLUMN tenant_category_id uuid,
      ADD COLUMN tenant_patient_identity_id uuid,
      ADD CONSTRAINT patient_practice_legacy_ref_complete CHECK (
        (template_id IS NULL)=(category_id IS NULL)
        AND (template_id IS NULL)=(patient_identity_id IS NULL)),
      ADD CONSTRAINT patient_practice_tenant_ref_complete CHECK (
        (tenant_template_id IS NULL)=(tenant_category_id IS NULL)
        AND (tenant_template_id IS NULL)=(tenant_patient_identity_id IS NULL)),
      ADD CONSTRAINT patient_practice_has_reference CHECK (
        template_id IS NOT NULL OR tenant_template_id IS NOT NULL),
      ADD CONSTRAINT patient_practice_tenant_case_fk
        FOREIGN KEY(organization_id,tenant_template_id,tenant_category_id,
          tenant_patient_identity_id)
        REFERENCES device_platform.organization_case_templates
          (organization_id,id,specialty_id,patient_profile_id);

    COMMENT ON TABLE device_platform.organization_clinical_specialties IS
      'Tenant-owned fictional clinical specialties; imported global examples start inactive.';
    COMMENT ON TABLE device_platform.organization_patient_profiles IS
      'Tenant-owned fictional patient profiles; not real patient records.';
    COMMENT ON TABLE device_platform.organization_case_templates IS
      'Tenant-owned staff rehearsal case drafts; immutable scenario versions are separate.';
    COMMENT ON COLUMN device_platform.patient_practice_selections.tenant_template_id IS
      'Optional same-tenant case reference during the legacy-to-tenant transition.';
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore; tenant content must be preserved.")
