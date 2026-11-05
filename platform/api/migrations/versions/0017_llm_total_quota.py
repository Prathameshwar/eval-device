"""Reserve and settle organization cloud input + output tokens without changing history."""

from alembic import op

revision = "0017_llm_total_quota"
down_revision = "0016_local_turns"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    ALTER TABLE device_platform.llm_requests
      ADD COLUMN reserved_total_tokens integer,
      ADD COLUMN charged_total_tokens integer;
    ALTER TABLE device_platform.llm_requests DISABLE TRIGGER llm_request_guard;
    -- Old prompts were deliberately not stored. Bound unknown usage conservatively;
    -- known local execution is exempt. Do not relabel output reservations as total usage.
    UPDATE device_platform.llm_requests r SET reserved_total_tokens = CASE
      WHEN c.provider='local_llama_cpp' AND c.revision=r.connection_revision THEN 0
      WHEN r.practice_id IS NULL THEN 100000
      ELSE 2 * CASE
        WHEN c.revision=r.connection_revision
          AND (c.model_options->>'context_tokens') ~ '^[0-9]{1,7}$'
          THEN least(1048576, greatest(512, (c.model_options->>'context_tokens')::integer))
        ELSE 1048576 END END
      FROM device_platform.llm_connections c WHERE c.id=r.connection_id;
    WITH usage AS (
      SELECT id, result->'usage' AS u FROM device_platform.llm_requests
      WHERE status='succeeded' AND reserved_total_tokens>0
    ), counts AS (
      SELECT id,u, CASE WHEN jsonb_typeof(u->'prompt_tokens')='number'
        AND (u->>'prompt_tokens') ~ '^[0-9]{1,10}$'
        THEN (u->>'prompt_tokens')::bigint END AS p,
        CASE WHEN jsonb_typeof(u->'completion_tokens')='number'
        AND (u->>'completion_tokens') ~ '^[0-9]{1,10}$'
        THEN (u->>'completion_tokens')::bigint END AS c
      FROM usage
    )
    UPDATE device_platform.llm_requests r SET charged_total_tokens=(p+c)::integer
      FROM counts WHERE counts.id=r.id AND p+c BETWEEN 0 AND 2147483647
      AND (NOT (u ? 'total_tokens') OR u->'total_tokens'=to_jsonb(p+c));
    ALTER TABLE device_platform.llm_requests ENABLE TRIGGER llm_request_guard;
    ALTER TABLE device_platform.llm_requests
      ALTER COLUMN reserved_total_tokens SET NOT NULL,
      ADD CONSTRAINT llm_total_reservation CHECK(reserved_total_tokens BETWEEN 0 AND 2097152),
      ADD CONSTRAINT llm_total_charge CHECK(charged_total_tokens IS NULL OR
        (status='succeeded' AND charged_total_tokens>=0));

    CREATE OR REPLACE FUNCTION device_platform.llm_guard() RETURNS trigger LANGUAGE plpgsql
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
          (to_jsonb(NEW)-ARRAY['status','completed_at','result','error_code','charged_total_tokens']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','completed_at','result','error_code','charged_total_tokens']) THEN
          RAISE EXCEPTION 'Invalid LLM request transition' USING ERRCODE='23514';
        END IF;
      ELSIF NEW.status<>'running' THEN RAISE EXCEPTION 'Invalid initial LLM state' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    REVOKE ALL ON FUNCTION device_platform.llm_guard() FROM PUBLIC;
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore for LLM quota data")
