"""Minimal scoped patient interview sessions; the frozen baseline is unchanged."""

from alembic import op

revision = "0007_training_pilot"
down_revision = "0006_confirmed_plan_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    CREATE TABLE device_platform.training_scenarios (
      id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      request_key uuid NOT NULL,
      code text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]{0,39}$'),
      version integer NOT NULL CHECK (version > 0),
      document jsonb NOT NULL CHECK (jsonb_typeof(document)='object' AND octet_length(document::text)<=65536),
      fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      approved_by uuid REFERENCES device_platform.users(id),
      approved_at timestamptz,
      approval jsonb CHECK (approval IS NULL OR (jsonb_typeof(approval)='object' AND octet_length(approval::text)<=4096)),
      is_active boolean NOT NULL DEFAULT true,
      UNIQUE (organization_id,id), UNIQUE (organization_id,code,version), UNIQUE (organization_id,request_key),
      CHECK ((approved_by IS NULL AND approved_at IS NULL AND approval IS NULL) OR
             (approved_by IS NOT NULL AND approved_at IS NOT NULL AND approval IS NOT NULL))
    );
    CREATE TABLE device_platform.training_sessions (
      id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      department_id uuid,
      device_id uuid NOT NULL,
      learner_id uuid NOT NULL REFERENCES device_platform.users(id),
      instructor_id uuid NOT NULL REFERENCES device_platform.users(id),
      scenario_id uuid NOT NULL,
      request_key uuid NOT NULL,
      fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
      device_credential_version integer NOT NULL CHECK (device_credential_version > 0),
      language text NOT NULL CHECK (language IN ('hi','en')),
      status text NOT NULL DEFAULT 'authorized' CHECK (status IN ('authorized','active','completed','failed','cancelled','expired')),
      duration_seconds integer NOT NULL CHECK (duration_seconds BETWEEN 30 AND 600),
      tts_budget integer NOT NULL DEFAULT 3000 CHECK (tts_budget BETWEEN 1 AND 6000),
      limits jsonb NOT NULL CHECK (jsonb_typeof(limits)='object' AND octet_length(limits::text)<=4096),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      expires_at timestamptz NOT NULL,
      results_expires_at timestamptz NOT NULL,
      started_at timestamptz,
      ended_at timestamptz,
      result jsonb CHECK (result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=16384)),
      feedback jsonb CHECK (feedback IS NULL OR (jsonb_typeof(feedback)='object' AND octet_length(feedback::text)<=32768)),
      feedback_version integer NOT NULL DEFAULT 0 CHECK (feedback_version >= 0),
      UNIQUE (organization_id,request_key),
      FOREIGN KEY (organization_id,device_id) REFERENCES device_platform.devices(organization_id,id),
      FOREIGN KEY (organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
      FOREIGN KEY (organization_id,scenario_id) REFERENCES device_platform.training_scenarios(organization_id,id),
      CHECK (expires_at>created_at AND results_expires_at>=expires_at),
      CHECK ((status IN ('authorized','active') AND ended_at IS NULL) OR
             (status NOT IN ('authorized','active') AND ended_at IS NOT NULL))
    );
    CREATE UNIQUE INDEX training_one_device_session ON device_platform.training_sessions(device_id)
      WHERE status IN ('authorized','active');
    CREATE INDEX training_org_created ON device_platform.training_sessions(organization_id,created_at);
    CREATE INDEX training_expiration ON device_platform.training_sessions(results_expires_at);
    CREATE FUNCTION device_platform.training_scenario_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        PERFORM 1 FROM device_platform.organizations WHERE id=NEW.organization_id FOR UPDATE;
        IF (SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=NEW.organization_id)>=100 THEN
          RAISE EXCEPTION 'Scenario capacity reached' USING ERRCODE='23514';
        END IF;
      ELSIF (to_jsonb(NEW)-ARRAY['approved_by','approved_at','approval','is_active']) IS DISTINCT FROM
            (to_jsonb(OLD)-ARRAY['approved_by','approved_at','approval','is_active'])
        OR (OLD.approved_at IS NOT NULL AND ROW(NEW.approved_by,NEW.approved_at,NEW.approval) IS DISTINCT FROM ROW(OLD.approved_by,OLD.approved_at,OLD.approval)) THEN
        RAISE EXCEPTION 'Immutable scenario version' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER training_scenario_guard BEFORE INSERT OR UPDATE ON device_platform.training_scenarios
      FOR EACH ROW EXECUTE FUNCTION device_platform.training_scenario_guard();
    CREATE FUNCTION device_platform.training_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN
        IF OLD.results_expires_at>clock_timestamp() THEN RAISE EXCEPTION 'Unexpired training session' USING ERRCODE='23514'; END IF;
        RETURN OLD;
      END IF;
      IF TG_OP='UPDATE' AND (
        (to_jsonb(NEW)-ARRAY['status','started_at','ended_at','result','feedback','feedback_version']) IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['status','started_at','ended_at','result','feedback','feedback_version']) OR
        (OLD.status NOT IN ('authorized','active') AND ROW(NEW.status,NEW.started_at,NEW.ended_at) IS DISTINCT FROM ROW(OLD.status,OLD.started_at,OLD.ended_at)) OR
        (OLD.result IS NOT NULL AND NEW.result IS DISTINCT FROM OLD.result) OR
        (OLD.status='active' AND NEW.status='authorized') OR
        (OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at)) THEN
        RAISE EXCEPTION 'Immutable training context or terminal state' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER training_session_guard BEFORE UPDATE OR DELETE ON device_platform.training_sessions
      FOR EACH ROW EXECUTE FUNCTION device_platform.training_session_guard();
    REVOKE ALL ON FUNCTION device_platform.training_scenario_guard(), device_platform.training_session_guard() FROM PUBLIC;
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Training data requires a reviewed forward migration or restore")
