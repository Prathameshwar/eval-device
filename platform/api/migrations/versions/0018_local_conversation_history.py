"""Private client-reported history, independent of inference and metrics."""

from alembic import op

revision = "0018_local_conversation_history"
down_revision = "0017_llm_total_quota"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        CREATE TABLE device_platform.local_conversation_turns (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
          department_id uuid,
          user_id uuid NOT NULL REFERENCES device_platform.users(id),
          turn_key uuid NOT NULL,
          conversation_id uuid NOT NULL,
          sequence integer NOT NULL CHECK(sequence BETWEEN 1 AND 2147483647),
          profile_revision_id uuid NOT NULL,
          connection_id uuid NOT NULL,
          fingerprint text NOT NULL CHECK(fingerprint ~ '^[a-f0-9]{64}$'),
          input_text text NOT NULL CHECK(char_length(input_text) BETWEEN 1 AND 8000),
          response_text text CHECK(octet_length(response_text) BETWEEN 1 AND 32000),
          outcome text NOT NULL CHECK(outcome IN ('completed','failed','cancelled')),
          document jsonb NOT NULL CHECK(jsonb_typeof(document)='object' AND octet_length(document::text)<=131072),
          byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 131072),
          occurred_at timestamptz NOT NULL, completed_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
          UNIQUE(organization_id,turn_key),
          UNIQUE(organization_id,user_id,conversation_id,sequence),
          FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
          FOREIGN KEY(organization_id,profile_revision_id)
            REFERENCES device_platform.processing_profile_revisions(organization_id,id),
          FOREIGN KEY(organization_id,connection_id) REFERENCES device_platform.llm_connections(organization_id,id),
          CHECK((outcome='completed')=(response_text IS NOT NULL)),
          CHECK(completed_at>=occurred_at AND completed_at<=created_at+interval '5 minutes'),
          CHECK(occurred_at>=created_at-interval '24 hours'),
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '7 days')
        );
        CREATE INDEX local_conversation_recent ON device_platform.local_conversation_turns
          (organization_id,occurred_at DESC,id DESC);
        CREATE INDEX local_conversation_owner ON device_platform.local_conversation_turns
          (organization_id,user_id,occurred_at DESC,id DESC);
        CREATE INDEX local_conversation_expiry ON device_platform.local_conversation_turns(expires_at);
        CREATE TRIGGER local_conversation_guard BEFORE UPDATE OR DELETE
          ON device_platform.local_conversation_turns FOR EACH ROW
          EXECUTE FUNCTION device_platform.local_turn_guard();
        REVOKE ALL ON device_platform.local_conversation_turns FROM PUBLIC;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a forward migration or restore to preserve history")
