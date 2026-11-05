"""Reusable fictional patient identities; seed Alex for simulation authoring."""

from alembic import op

revision = "0012_patient_identities"
down_revision = "0011_scenario_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        CREATE TABLE device_platform.patient_identities (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{0,39}$'),
          name text NOT NULL CHECK (name=btrim(name) AND length(name) BETWEEN 1 AND 120),
          name_hi text NOT NULL CHECK (name_hi=btrim(name_hi) AND length(name_hi) BETWEEN 1 AND 120),
          age_years integer NOT NULL CHECK (age_years BETWEEN 0 AND 150),
          sex text NOT NULL CHECK (sex IN ('female','male','intersex','unspecified')),
          occupation_en text NOT NULL CHECK (occupation_en=btrim(occupation_en) AND length(occupation_en) BETWEEN 1 AND 600),
          occupation_hi text NOT NULL CHECK (occupation_hi=btrim(occupation_hi) AND length(occupation_hi) BETWEEN 1 AND 600),
          height_cm numeric(5,2) NOT NULL CHECK (height_cm > 0 AND height_cm <= 400),
          weight_kg numeric(6,2) NOT NULL CHECK (weight_kg > 0 AND weight_kg <= 2000),
          preferred_language text NOT NULL DEFAULT 'en' CHECK (preferred_language IN ('en','hi')),
          languages text[] NOT NULL DEFAULT ARRAY['en','hi'] CHECK (
            CASE WHEN array_ndims(languages)=1 THEN
              array_lower(languages,1)=1 AND cardinality(languages) BETWEEN 1 AND 2
              AND languages <@ ARRAY['en','hi']::text[] AND array_position(languages,NULL) IS NULL
              AND (cardinality(languages)=1 OR languages[1]<>languages[2])
              AND preferred_language=ANY(languages)
            ELSE false END
          ),
          background_en text NOT NULL CHECK (background_en=btrim(background_en) AND length(background_en) BETWEEN 1 AND 600),
          background_hi text NOT NULL CHECK (background_hi=btrim(background_hi) AND length(background_hi) BETWEEN 1 AND 600),
          is_fictional boolean NOT NULL DEFAULT true CHECK (is_fictional),
          is_active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE FUNCTION device_platform.patient_identity_guard() RETURNS trigger
          LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF (NEW.id,NEW.code,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.code,OLD.created_at) THEN
            RAISE EXCEPTION 'Patient identity key is immutable' USING ERRCODE='23514';
          END IF;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END $$;
        CREATE TRIGGER patient_identity_guard BEFORE UPDATE ON device_platform.patient_identities
          FOR EACH ROW EXECUTE FUNCTION device_platform.patient_identity_guard();
        REVOKE ALL ON device_platform.patient_identities FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.patient_identity_guard() FROM PUBLIC;
        COMMENT ON TABLE device_platform.patient_identities IS
          'Shared fictional simulation identity templates, never real patient records. Scenario versions own fixed snapshots.';
        COMMENT ON COLUMN device_platform.patient_identities.age_years IS
          'Authored simulation age; does not advance with calendar time.';

        WITH inserted AS (
          INSERT INTO device_platform.patient_identities
            (id,code,name,name_hi,age_years,sex,occupation_en,occupation_hi,height_cm,weight_kg,
             preferred_language,languages,background_en,background_hi)
          VALUES ('00000000-0000-4000-8000-000000000401','alex','Alex','एलेक्स',35,'male',
             'Schoolteacher','स्कूल शिक्षक',175.00,75.00,'en',ARRAY['en','hi'],
             'Alex works as a schoolteacher and lives with family.',
             'एलेक्स स्कूल शिक्षक हैं और अपने परिवार के साथ रहते हैं।')
          ON CONFLICT (code) DO NOTHING RETURNING id,code
        )
        INSERT INTO device_platform.activity_events
          (id,actor_type,category,event_type,severity,entity_type,entity_id,occurred_at,received_at,details,expires_at)
        SELECT gen_random_uuid(),'system','audit','platform.patient_identity.seeded','info',
          'patient_identity',i.id,now(),now(),
          jsonb_build_object('actor_role','system','scope','platform','source','migration',
            'revision','0012_patient_identities','identity_code',i.code),
          now() + least((p.default_organization_policy->>'audit_retention_days')::integer,
                        (p.policy_limits->>'audit_retention_days')::integer) * interval '1 day'
        FROM inserted i CROSS JOIN device_platform.platform_settings p WHERE p.id=1;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve patient identities")
