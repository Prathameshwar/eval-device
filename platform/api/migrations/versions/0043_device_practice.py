"""Device-owned desktop Practice with isolated selections, contexts and turn records."""

from alembic import op
from psycopg import sql

revision = "0043_device_practice"
down_revision = "0042_clinical_source_references"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind().connection.driver_connection
    for table in (
        "patient_practice_selections",
        "patient_conversations",
        "llm_requests",
        "local_turns",
        "local_conversation_turns",
    ):
        c.execute(
            sql.SQL("""
          ALTER TABLE device_platform.{table}
            ALTER COLUMN user_id DROP NOT NULL,
            ADD COLUMN device_id uuid,
            ADD CONSTRAINT {owner} CHECK ((user_id IS NULL) <> (device_id IS NULL)),
            ADD CONSTRAINT {fk} FOREIGN KEY (organization_id,device_id)
              REFERENCES device_platform.devices(organization_id,id);
        """).format(
                table=sql.Identifier(table),
                owner=sql.Identifier(table + "_owner"),
                fk=sql.Identifier(table + "_device_fk"),
            )
        )
    c.execute(
        """
      ALTER TABLE device_platform.patient_practice_selections
        ADD UNIQUE(organization_id,device_id), ADD UNIQUE(organization_id,device_id,id),
        ADD CHECK(device_id IS NULL OR scenario_id IS NOT NULL);
      ALTER TABLE device_platform.patient_conversations
        ADD UNIQUE(organization_id,device_id,id), ADD UNIQUE(organization_id,device_id,request_key),
        ADD FOREIGN KEY(organization_id,device_id,practice_id)
          REFERENCES device_platform.patient_practice_selections(organization_id,device_id,id);
      ALTER TABLE device_platform.llm_requests
        ADD COLUMN device_credential_version integer,
        ADD CHECK((device_id IS NULL)=(device_credential_version IS NULL)),
        ADD CHECK(device_credential_version IS NULL OR device_credential_version>=1),
        ADD CHECK(device_id IS NULL OR (conversation_id IS NOT NULL AND profile_revision_id IS NOT NULL)),
        ADD FOREIGN KEY(organization_id,device_id,practice_id)
          REFERENCES device_platform.patient_practice_selections(organization_id,device_id,id),
        ADD FOREIGN KEY(organization_id,device_id,conversation_id)
          REFERENCES device_platform.patient_conversations(organization_id,device_id,id);
      ALTER TABLE device_platform.local_turns
        ADD CHECK(device_id IS NULL OR (practice_id IS NOT NULL AND context_ref IS NOT NULL)),
        ADD FOREIGN KEY(organization_id,device_id,practice_id)
          REFERENCES device_platform.patient_practice_selections(organization_id,device_id,id);
      ALTER TABLE device_platform.local_conversation_turns
        ADD UNIQUE(organization_id,device_id,conversation_id,sequence),
        ADD FOREIGN KEY(organization_id,device_id,conversation_id)
          REFERENCES device_platform.patient_conversations(organization_id,device_id,id);
    """,
        prepare=False,
    )
    constraints = c.execute("""
      SELECT conname FROM pg_constraint WHERE conrelid='device_platform.patient_conversations'::regclass
        AND contype='c' AND pg_get_constraintdef(oid) LIKE '%owner_id%'
    """).fetchall()
    if len(constraints) != 1:
        raise RuntimeError("Expected conversation owner identity constraint")
    c.execute(
        sql.SQL("ALTER TABLE device_platform.patient_conversations DROP CONSTRAINT {}").format(
            sql.Identifier(constraints[0][0])
        )
    )
    c.execute(
        """
      ALTER TABLE device_platform.patient_conversations ADD CONSTRAINT patient_conversation_identity CHECK (
        (context->>'conversation_id'=id::text AND context->>'organization_id'=organization_id::text
        AND context->>'owner_id'=coalesce(user_id,device_id)::text
        AND context->>'practice_id'=practice_id::text) IS TRUE);
      CREATE OR REPLACE FUNCTION device_platform.patient_practice_guard() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,device_platform AS $$
      BEGIN
        IF TG_OP='UPDATE' THEN
          IF TG_TABLE_NAME='patient_case_templates' THEN
            IF (NEW.id,NEW.code,NEW.category_id,NEW.patient_identity_id,NEW.created_at)
              IS DISTINCT FROM (OLD.id,OLD.code,OLD.category_id,OLD.patient_identity_id,OLD.created_at) THEN
              RAISE EXCEPTION 'Case identity is immutable' USING ERRCODE='23514';
            END IF;
          ELSE
            IF (NEW.id,NEW.organization_id,NEW.user_id,NEW.device_id,NEW.created_at)
              IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.user_id,OLD.device_id,OLD.created_at) THEN
              RAISE EXCEPTION 'Practice ownership is immutable' USING ERRCODE='23514';
            END IF;
          END IF;
          IF NEW.revision<>OLD.revision+1 THEN
            RAISE EXCEPTION 'Practice revision must advance' USING ERRCODE='23514';
          END IF;
          NEW.updated_at=clock_timestamp();
        ELSIF NEW.revision<>1 THEN
          RAISE EXCEPTION 'Initial practice revision must be one' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='patient_practice_selections' THEN
          IF NEW.device_id IS NOT NULL THEN
            IF NOT EXISTS (
              SELECT 1 FROM device_platform.devices d JOIN device_platform.organizations o ON o.id=d.organization_id
              LEFT JOIN device_platform.departments dep ON dep.id=d.department_id
              WHERE d.id=NEW.device_id AND d.organization_id=NEW.organization_id AND d.is_active
                AND d.enrollment_state='enrolled' AND d.credential_hash IS NOT NULL AND d.credential_revoked_at IS NULL
                AND o.is_active AND o.archived_at IS NULL
                AND (d.department_id IS NULL OR (dep.is_active AND dep.archived_at IS NULL))
            ) THEN RAISE EXCEPTION 'Active enrolled device required' USING ERRCODE='23514'; END IF;
          ELSE
            IF NOT EXISTS (
              SELECT 1 FROM device_platform.organization_memberships m JOIN device_platform.users u ON u.id=m.user_id
              WHERE m.organization_id=NEW.organization_id AND m.user_id=NEW.user_id AND m.is_active AND u.is_active
                AND m.invitation_status='accepted' AND m.department_id IS NULL AND m.role IN ('org_admin','org_user')
            ) THEN RAISE EXCEPTION 'Active organization-wide staff membership required' USING ERRCODE='23514'; END IF;
          END IF;
        END IF;
        RETURN NEW;
      END $$;
    """,
        prepare=False,
    )
    guard = c.execute(
        "SELECT pg_get_functiondef('device_platform.patient_conversation_guard()'::regprocedure)"
    ).fetchone()[0]
    for old, new in (
        ("user_id=NEW.user_id", "(user_id=NEW.user_id OR device_id=NEW.device_id)"),
        ("NEW.user_id,NEW.department_id", "NEW.user_id,NEW.device_id,NEW.scenario_id,NEW.department_id"),
        ("OLD.user_id,OLD.department_id", "OLD.user_id,OLD.device_id,OLD.scenario_id,OLD.department_id"),
    ):
        if old not in guard:
            raise RuntimeError("Unexpected conversation guard definition")
        guard = guard.replace(old, new)
    c.execute(guard)


def downgrade():
    raise RuntimeError(
        "Use a reviewed forward migration or restore; device Practice records must be preserved"
    )
