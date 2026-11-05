"""Metadata-only record of turns executed on a laptop's own local model.

A local model runs on the caller's machine, so this service never sees the prompt, the
transcript or the answer and must not pretend to: this table stores counts, timings and the
authored routing outcome only. There is deliberately no text column and no request key to
recover, because there is nothing here to resubmit.
"""

from alembic import op

revision = "0016_local_turns"
down_revision = "0015_cloud_models"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        CREATE TABLE device_platform.local_turns (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
          department_id uuid,
          user_id uuid NOT NULL REFERENCES device_platform.users(id),
          turn_key uuid NOT NULL,
          profile_revision_id uuid NOT NULL,
          configuration_hash text NOT NULL CHECK(configuration_hash ~ '^[a-f0-9]{64}$'),
          connection_id uuid NOT NULL, connection_revision integer NOT NULL CHECK(connection_revision>0),
          practice_id uuid, practice_revision integer CHECK(practice_revision>0),
          practice_snapshot_hash text CHECK(practice_snapshot_hash ~ '^[a-f0-9]{64}$'),
          language text NOT NULL CHECK(language IN ('en','hi')),
          answer_source text NOT NULL CHECK(answer_source IN
            ('patient_voice','scripted_case','case_backchannel','case_command_ack','case_boundary',
             'case_clarification','routing_invalid','plain_completion')),
          routing_status text CHECK(routing_status IN
            ('matched','backchannel','command','boundary','unknown','invalid')),
          kind text CHECK(kind IN ('topic','backchannel','command','boundary','unknown')),
          topics jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(topics)='array' AND
            jsonb_array_length(topics)<=3 AND octet_length(topics::text)<=256),
          provider_calls smallint NOT NULL CHECK(provider_calls BETWEEN 1 AND 2),
          finish_reason text NOT NULL CHECK(finish_reason IN ('stop','length')),
          prompt_tokens integer CHECK(prompt_tokens BETWEEN 0 AND 1000000),
          completion_tokens integer CHECK(completion_tokens BETWEEN 0 AND 1000000),
          first_token_ms integer CHECK(first_token_ms BETWEEN 0 AND 600000),
          total_ms integer NOT NULL CHECK(total_ms BETWEEN 0 AND 600000),
          occurred_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL,
          expires_at timestamptz NOT NULL,
          UNIQUE(organization_id,turn_key),
          FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
          FOREIGN KEY(organization_id,profile_revision_id)
            REFERENCES device_platform.processing_profile_revisions(organization_id,id),
          FOREIGN KEY(organization_id,connection_id)
            REFERENCES device_platform.llm_connections(organization_id,id),
          CHECK((practice_id IS NULL)=(practice_revision IS NULL)),
          CHECK((practice_id IS NULL)=(practice_snapshot_hash IS NULL)),
          CHECK((practice_id IS NULL)=(routing_status IS NULL)),
          CHECK((practice_id IS NULL)=(kind IS NULL)),
          CHECK(practice_id IS NOT NULL OR (answer_source='plain_completion' AND
            jsonb_array_length(topics)=0 AND provider_calls=1)),
          CHECK(practice_id IS NULL OR answer_source<>'plain_completion'),
          CHECK(occurred_at<=created_at AND occurred_at>created_at-interval '1 hour'),
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '90 days')
        );
        CREATE INDEX local_turn_recent ON device_platform.local_turns(organization_id,occurred_at DESC);
        CREATE INDEX local_turn_expiry ON device_platform.local_turns(expires_at);
        CREATE FUNCTION device_platform.local_turn_guard() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,device_platform AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.expires_at>clock_timestamp() THEN
              RAISE EXCEPTION 'Local turn not expired' USING ERRCODE='23514'; END IF;
            RETURN OLD;
          END IF;
          -- A completed local turn is a fact about the past; it is never amended here.
          RAISE EXCEPTION 'Local turn records are append-only' USING ERRCODE='23514';
        END $$;
        CREATE TRIGGER local_turn_guard BEFORE UPDATE OR DELETE
          ON device_platform.local_turns FOR EACH ROW EXECUTE FUNCTION device_platform.local_turn_guard();
        REVOKE ALL ON device_platform.local_turns FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.local_turn_guard() FROM PUBLIC;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve training records")
