"""Bounded, tenant-scoped local LLM connections and idempotent generations."""

from alembic import op

revision = "0009_local_llm"
down_revision = "0008_scenario_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    CREATE TABLE device_platform.llm_connections (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
      base_url text NOT NULL CHECK(base_url ~ '^http://127[.]0[.]0[.]1:[0-9]{4,5}$'),
      model text NOT NULL CHECK(model ~ '^[a-zA-Z0-9_.:/-]{1,100}$'),
      system_prompt text NOT NULL CHECK(length(system_prompt) BETWEEN 1 AND 4000),
      max_tokens integer NOT NULL CHECK(max_tokens BETWEEN 16 AND 512),
      encrypted_credentials bytea NOT NULL, credential_key_id text NOT NULL,
      revision integer NOT NULL DEFAULT 1 CHECK(revision>0), is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), UNIQUE(organization_id,name)
    );
    CREATE TABLE device_platform.llm_requests (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      department_id uuid, user_id uuid NOT NULL REFERENCES device_platform.users(id),
      connection_id uuid NOT NULL, connection_revision integer NOT NULL CHECK(connection_revision>0),
      request_key uuid NOT NULL, fingerprint text NOT NULL CHECK(fingerprint ~ '^[a-f0-9]{64}$'),
      target_key text NOT NULL CHECK(target_key ~ '^[a-f0-9]{64}$'),
      status text NOT NULL CHECK(status IN ('running','succeeded','failed','cancelled','unknown')),
      reserved_tokens integer NOT NULL CHECK(reserved_tokens BETWEEN 16 AND 512),
      lease_token uuid NOT NULL, lease_expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(), completed_at timestamptz,
      expires_at timestamptz NOT NULL, result jsonb, error_code text,
      UNIQUE(organization_id,request_key),
      FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
      FOREIGN KEY(organization_id,connection_id) REFERENCES device_platform.llm_connections(organization_id,id),
      CHECK(lease_expires_at>created_at AND lease_expires_at<=created_at+interval '10 minutes'),
      CHECK(expires_at>lease_expires_at AND expires_at<=created_at+interval '24 hours'),
      CHECK((status='running')=(completed_at IS NULL)),
      CHECK((status='succeeded')=(result IS NOT NULL)),
      CHECK(result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=65536)),
      CHECK(error_code IS NULL OR error_code ~ '^[a-z_]{1,80}$')
    );
    CREATE UNIQUE INDEX llm_one_running_target ON device_platform.llm_requests(target_key) WHERE status='running';
    CREATE INDEX llm_request_daily ON device_platform.llm_requests(organization_id,created_at);
    CREATE INDEX llm_request_expiry ON device_platform.llm_requests(expires_at);
    CREATE FUNCTION device_platform.llm_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_TABLE_NAME='llm_connections' THEN
        IF TG_OP='INSERT' THEN
          PERFORM 1 FROM device_platform.organizations WHERE id=NEW.organization_id FOR UPDATE;
          IF (SELECT count(*) FROM device_platform.llm_connections WHERE organization_id=NEW.organization_id)>=10 THEN
            RAISE EXCEPTION 'LLM connection limit' USING ERRCODE='23514';
          END IF;
        ELSE
          IF ROW(NEW.id,NEW.organization_id,NEW.created_by,NEW.created_at) IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.created_by,OLD.created_at)
            OR NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'Invalid LLM connection update' USING ERRCODE='23514'; END IF;
          NEW.updated_at=clock_timestamp();
        END IF;
      ELSIF TG_OP='DELETE' THEN
        IF OLD.expires_at>clock_timestamp() OR OLD.status='running' THEN RAISE EXCEPTION 'LLM request not expired' USING ERRCODE='23514'; END IF;
        RETURN OLD;
      ELSIF TG_OP='UPDATE' THEN
        IF OLD.status<>'running' OR NEW.status='running' OR
          (to_jsonb(NEW)-ARRAY['status','completed_at','result','error_code']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','completed_at','result','error_code']) THEN
          RAISE EXCEPTION 'Invalid LLM request transition' USING ERRCODE='23514';
        END IF;
      ELSIF NEW.status<>'running' THEN RAISE EXCEPTION 'Invalid initial LLM state' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER llm_connection_guard BEFORE INSERT OR UPDATE ON device_platform.llm_connections
      FOR EACH ROW EXECUTE FUNCTION device_platform.llm_guard();
    CREATE TRIGGER llm_request_guard BEFORE INSERT OR UPDATE OR DELETE ON device_platform.llm_requests
      FOR EACH ROW EXECUTE FUNCTION device_platform.llm_guard();
    REVOKE ALL ON device_platform.llm_connections,device_platform.llm_requests FROM PUBLIC;
    REVOKE ALL ON FUNCTION device_platform.llm_guard() FROM PUBLIC;
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore for LLM data")
