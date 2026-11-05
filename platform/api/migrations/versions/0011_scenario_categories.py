"""Shared patient-scenario categories and three reviewed deployment defaults."""

from alembic import op

revision = "0011_scenario_categories"
down_revision = "0010_llm_providers"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        CREATE TABLE device_platform.scenario_categories (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{0,39}$'),
          name text NOT NULL CHECK (name = btrim(name) AND length(name) BETWEEN 1 AND 120),
          name_hi text NOT NULL CHECK (name_hi = btrim(name_hi) AND length(name_hi) BETWEEN 1 AND 160),
          description text NOT NULL CHECK (description = btrim(description) AND length(description) BETWEEN 1 AND 600),
          sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order BETWEEN 0 AND 10000),
          is_active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX scenario_category_name_unique
          ON device_platform.scenario_categories(lower(name));
        CREATE FUNCTION device_platform.scenario_category_guard() RETURNS trigger
          LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF (NEW.id,NEW.code,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.code,OLD.created_at) THEN
            RAISE EXCEPTION 'Category identity is immutable' USING ERRCODE='23514';
          END IF;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END $$;
        CREATE TRIGGER scenario_category_guard BEFORE UPDATE ON device_platform.scenario_categories
          FOR EACH ROW EXECUTE FUNCTION device_platform.scenario_category_guard();
        REVOKE ALL ON device_platform.scenario_categories FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.scenario_category_guard() FROM PUBLIC;
        COMMENT ON TABLE device_platform.scenario_categories IS
          'Shared non-patient category catalog. Initial deployment seeds; scenario specialty text remains compatible.';
        COMMENT ON COLUMN device_platform.scenario_categories.code IS
          'Stable unique code for future scenario references; never relabel existing clinical snapshots automatically.';

        WITH inserted AS (
          INSERT INTO device_platform.scenario_categories
            (id,code,name,name_hi,description,sort_order) VALUES
            ('00000000-0000-4000-8000-000000000301','cardiology','Cardiology','हृदय रोग',
             'Patient interview scenarios concerning the heart and circulation.',10),
            ('00000000-0000-4000-8000-000000000302','nephrology','Nephrology','गुर्दा रोग',
             'Patient interview scenarios concerning kidney conditions and related history.',20),
            ('00000000-0000-4000-8000-000000000303','respiratory_medicine','Respiratory Medicine','श्वसन रोग',
             'Patient interview scenarios concerning breathing, lungs and respiratory symptoms.',30)
          ON CONFLICT (code) DO NOTHING
          RETURNING id,code
        )
        INSERT INTO device_platform.activity_events
          (id,actor_type,category,event_type,severity,entity_type,entity_id,occurred_at,received_at,details,expires_at)
        SELECT gen_random_uuid(),'system','audit','platform.scenario_category.seeded','info',
          'scenario_category',i.id,now(),now(),
          jsonb_build_object('actor_role','system','scope','platform','source','migration',
            'revision','0011_scenario_categories','category_code',i.code),
          now() + least((p.default_organization_policy->>'audit_retention_days')::integer,
                        (p.policy_limits->>'audit_retention_days')::integer) * interval '1 day'
        FROM inserted i CROSS JOIN device_platform.platform_settings p WHERE p.id=1;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve category data")
