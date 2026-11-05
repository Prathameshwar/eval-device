"""Synthetic case templates, private staff practice selections and request provenance."""

import json
from pathlib import Path

from alembic import op
from psycopg.types.json import Jsonb

revision = "0013_patient_practice"
down_revision = "0012_patient_identities"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind().connection.driver_connection
    c.execute(
        """
        CREATE TABLE device_platform.patient_case_templates (
          id uuid PRIMARY KEY, code text NOT NULL UNIQUE CHECK(code ~ '^[a-z][a-z0-9_]{0,39}$'),
          category_id uuid NOT NULL REFERENCES device_platform.scenario_categories(id),
          patient_identity_id uuid NOT NULL REFERENCES device_platform.patient_identities(id),
          title text NOT NULL CHECK(length(btrim(title)) BETWEEN 1 AND 120),
          title_hi text NOT NULL CHECK(length(btrim(title_hi)) BETWEEN 1 AND 120),
          document jsonb NOT NULL CHECK((jsonb_typeof(document)='object' AND octet_length(document::text)<=48000
            AND document->'version'='2'::jsonb AND document->>'code'=code AND document->>'title'=title) IS TRUE),
          revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
          is_synthetic boolean NOT NULL DEFAULT true CHECK(is_synthetic),
          is_active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          UNIQUE(id,category_id,patient_identity_id)
        );
        CREATE TABLE device_platform.patient_practice_selections (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
          user_id uuid NOT NULL REFERENCES device_platform.users(id),
          template_id uuid NOT NULL,
          category_id uuid NOT NULL,
          patient_identity_id uuid NOT NULL,
          template_revision integer NOT NULL CHECK(template_revision BETWEEN 1 AND 2147483646),
          document jsonb NOT NULL CHECK((jsonb_typeof(document)='object' AND octet_length(document::text)<=48000
            AND document->'version'='2'::jsonb) IS TRUE),
          language text NOT NULL CHECK(language IN ('en','hi','auto')),
          revision integer NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 2147483646),
          created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          UNIQUE(organization_id,user_id), UNIQUE(organization_id,user_id,id),
          FOREIGN KEY(template_id,category_id,patient_identity_id)
            REFERENCES device_platform.patient_case_templates(id,category_id,patient_identity_id)
        );
        CREATE FUNCTION device_platform.patient_practice_guard() RETURNS trigger LANGUAGE plpgsql
          SET search_path=pg_catalog,device_platform AS $$
        BEGIN
          IF TG_OP='UPDATE' THEN
            IF TG_TABLE_NAME='patient_case_templates' THEN
              IF (NEW.id,NEW.code,NEW.category_id,NEW.patient_identity_id,NEW.created_at)
                 IS DISTINCT FROM (OLD.id,OLD.code,OLD.category_id,OLD.patient_identity_id,OLD.created_at) THEN
                RAISE EXCEPTION 'Case identity is immutable' USING ERRCODE='23514';
              END IF;
            ELSIF (NEW.id,NEW.organization_id,NEW.user_id,NEW.created_at)
                   IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.user_id,OLD.created_at) THEN
              RAISE EXCEPTION 'Practice ownership is immutable' USING ERRCODE='23514';
            END IF;
            IF NEW.revision<>OLD.revision+1 THEN
              RAISE EXCEPTION 'Practice revision must advance' USING ERRCODE='23514';
            END IF;
            NEW.updated_at=clock_timestamp();
          ELSIF NEW.revision<>1 THEN
            RAISE EXCEPTION 'Initial practice revision must be one' USING ERRCODE='23514';
          END IF;
          IF TG_TABLE_NAME='patient_practice_selections' THEN
           IF NOT EXISTS (
            SELECT 1 FROM device_platform.organization_memberships m JOIN device_platform.users u ON u.id=m.user_id
            WHERE m.organization_id=NEW.organization_id AND m.user_id=NEW.user_id AND m.is_active AND u.is_active
              AND m.invitation_status='accepted' AND m.department_id IS NULL AND m.role IN ('org_admin','org_user')
          ) THEN
            RAISE EXCEPTION 'Active organization-wide staff membership required' USING ERRCODE='23514';
           END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER patient_case_guard BEFORE INSERT OR UPDATE ON device_platform.patient_case_templates
          FOR EACH ROW EXECUTE FUNCTION device_platform.patient_practice_guard();
        CREATE TRIGGER patient_selection_guard BEFORE INSERT OR UPDATE ON device_platform.patient_practice_selections
          FOR EACH ROW EXECUTE FUNCTION device_platform.patient_practice_guard();
        REVOKE ALL ON device_platform.patient_case_templates,device_platform.patient_practice_selections FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.patient_practice_guard() FROM PUBLIC;
        ALTER TABLE device_platform.llm_requests ADD COLUMN practice_id uuid,
          ADD COLUMN practice_revision integer CHECK(practice_revision BETWEEN 1 AND 2147483646),
          ADD COLUMN practice_snapshot_hash text CHECK(practice_snapshot_hash ~ '^[a-f0-9]{64}$'),
          ADD FOREIGN KEY(organization_id,user_id,practice_id) REFERENCES device_platform.patient_practice_selections(organization_id,user_id,id),
          ADD CHECK((practice_id IS NULL)=(practice_revision IS NULL) AND (practice_id IS NULL)=(practice_snapshot_hash IS NULL));
        COMMENT ON TABLE device_platform.patient_case_templates IS
          'Fictional staff practice examples; not clinically approved training scenario versions.';
        COMMENT ON TABLE device_platform.patient_practice_selections IS
          'One private setup per organization/staff user. Saved scenario snapshots remain fixed until explicitly resaved.';
        """,
        prepare=False,
    )
    rows = json.loads(
        Path(__file__).with_name("0013_patient_case_templates.json").read_text(encoding="utf-8")
    )
    for row in rows:
        c.execute(
            """WITH inserted AS (
              INSERT INTO device_platform.patient_case_templates
                (id,code,category_id,patient_identity_id,title,title_hi,document)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING RETURNING id,code
            )
            INSERT INTO device_platform.activity_events
              (id,actor_type,category,event_type,severity,entity_type,entity_id,occurred_at,received_at,details,expires_at)
            SELECT gen_random_uuid(),'system','audit','platform.patient_case.seeded','info','patient_case',i.id,now(),now(),
              jsonb_build_object('actor_role','system','scope','platform','source','migration',
                'revision','0013_patient_practice','case_code',i.code),
              now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
                           (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
            FROM inserted i CROSS JOIN device_platform.platform_settings p WHERE p.id=1""",
            (
                row["id"],
                row["code"],
                row["category_id"],
                row["patient_identity_id"],
                row["document"]["title"],
                row["title_hi"],
                Jsonb(row["document"]),
            ),
        )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve practice data")
