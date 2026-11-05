"""Ordered desktop sessions with explicit trainee attribution."""

from alembic import op

revision = "0044_session_queue"
down_revision = "0043_device_practice"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
      CREATE TABLE device_platform.device_session_queues (
        device_id uuid PRIMARY KEY REFERENCES device_platform.devices(id),
        organization_id uuid NOT NULL,
        paused boolean NOT NULL DEFAULT false,
        revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
        last_seen_at timestamptz,
        runtime_state text NOT NULL DEFAULT 'offline' CHECK(runtime_state IN ('offline','idle','standalone','assigned')),
        FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id)
      );
      CREATE TABLE device_platform.practice_sessions (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL,
        department_id uuid,
        device_id uuid NOT NULL,
        learner_id uuid NOT NULL REFERENCES device_platform.users(id),
        instructor_id uuid NOT NULL REFERENCES device_platform.users(id),
        scenario_id uuid NOT NULL,
        request_key uuid NOT NULL,
        batch_index integer NOT NULL CHECK(batch_index>=0),
        fingerprint text NOT NULL,
        position integer NOT NULL CHECK(position>=0),
        language text NOT NULL,
        duration_seconds integer NOT NULL CHECK(duration_seconds BETWEEN 30 AND 600),
        status text NOT NULL CHECK(status IN ('queued','active','stopping','completed','cancelled','expired','failed')),
        credential_version integer,
        runtime_id uuid,
        created_at timestamptz NOT NULL,
        expires_at timestamptz NOT NULL,
        started_at timestamptz,
        ended_at timestamptz,
        lease_until timestamptz,
        FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id),
        FOREIGN KEY(organization_id,scenario_id) REFERENCES device_platform.training_scenarios(organization_id,id),
        FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
        UNIQUE(organization_id,device_id,id),
        UNIQUE(organization_id,device_id,request_key,batch_index),
        CHECK ((status='queued' AND started_at IS NULL) OR status<>'queued'),
        CHECK(expires_at=created_at+interval '24 hours'),
        CHECK(lease_until IS NULL OR lease_until<=expires_at),
        CHECK(status NOT IN ('active','stopping') OR (started_at IS NOT NULL AND lease_until IS NOT NULL AND runtime_id IS NOT NULL AND credential_version IS NOT NULL))
      );
      CREATE UNIQUE INDEX practice_session_one_active ON device_platform.practice_sessions(device_id)
        WHERE status IN ('active','stopping');
      CREATE INDEX practice_session_queue_order ON device_platform.practice_sessions(device_id,status,position);
      ALTER TABLE device_platform.patient_conversations ADD COLUMN assigned_session_id uuid,
        ADD CONSTRAINT conversation_assigned_session_fk FOREIGN KEY(organization_id,device_id,assigned_session_id)
          REFERENCES device_platform.practice_sessions(organization_id,device_id,id),
        ADD CHECK(assigned_session_id IS NULL OR device_id IS NOT NULL);
      CREATE UNIQUE INDEX conversation_one_assignment ON device_platform.patient_conversations(assigned_session_id)
        WHERE assigned_session_id IS NOT NULL;
      CREATE FUNCTION device_platform.practice_session_guard() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,device_platform AS $$
      BEGIN
        IF TG_TABLE_NAME='patient_conversations' THEN
          IF NEW.assigned_session_id IS DISTINCT FROM OLD.assigned_session_id THEN
            RAISE EXCEPTION 'Session attribution is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF (NEW.id,NEW.organization_id,NEW.device_id,NEW.department_id,NEW.instructor_id,
            NEW.created_at,NEW.expires_at,NEW.request_key,NEW.batch_index,NEW.fingerprint)
          IS DISTINCT FROM
           (OLD.id,OLD.organization_id,OLD.device_id,OLD.department_id,OLD.instructor_id,
            OLD.created_at,OLD.expires_at,OLD.request_key,OLD.batch_index,OLD.fingerprint) THEN
          RAISE EXCEPTION 'Session identity and deadline are immutable' USING ERRCODE='23514';
        END IF;
        IF OLD.status<>'queued' AND (NEW.learner_id,NEW.scenario_id,NEW.language,NEW.duration_seconds,NEW.position,
             NEW.started_at,NEW.credential_version,NEW.runtime_id)
          IS DISTINCT FROM (OLD.learner_id,OLD.scenario_id,OLD.language,OLD.duration_seconds,OLD.position,
             OLD.started_at,OLD.credential_version,OLD.runtime_id) THEN
          RAISE EXCEPTION 'A started assignment is immutable' USING ERRCODE='23514';
        END IF;
        IF (OLD.status NOT IN ('queued','active','stopping') AND NEW IS DISTINCT FROM OLD)
          OR (OLD.status='queued' AND NEW.status NOT IN ('queued','active','cancelled','expired'))
          OR (OLD.status IN ('active','stopping') AND NEW.status='queued')
          OR (OLD.status='stopping' AND NEW.status='active') THEN
          RAISE EXCEPTION 'Invalid session transition' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER practice_session_guard BEFORE UPDATE ON device_platform.practice_sessions
        FOR EACH ROW EXECUTE FUNCTION device_platform.practice_session_guard();
      CREATE TRIGGER conversation_assignment_guard BEFORE UPDATE ON device_platform.patient_conversations
        FOR EACH ROW EXECUTE FUNCTION device_platform.practice_session_guard();
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Restore a backup or use a reviewed forward migration")
