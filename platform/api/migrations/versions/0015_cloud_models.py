"""Explicit cloud models, profile bindings and bounded interactive speech."""

from alembic import op

revision = "0015_cloud_models"
down_revision = "0014_patient_dialogue"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        ALTER TABLE device_platform.llm_connections
          ADD COLUMN model_options jsonb NOT NULL DEFAULT '{}'::jsonb
            CHECK(jsonb_typeof(model_options)='object' AND octet_length(model_options::text)<=2048),
          DROP CONSTRAINT llm_provider_check,
          ADD CONSTRAINT llm_provider_check CHECK(provider IN
            ('local_llama_cpp','openai','openai_compatible','azure_openai')),
          DROP CONSTRAINT llm_endpoint_check,
          ADD CONSTRAINT llm_endpoint_check CHECK(length(base_url) BETWEEN 1 AND 512 AND
            ((provider='local_llama_cpp' AND base_url ~ '^http://127[.]0[.]0[.]1:[0-9]{1,5}$') OR
             (provider='openai' AND base_url='https://api.openai.com/v1') OR
             (provider='openai_compatible' AND base_url ~ '^(https://|http://127[.]0[.]0[.]1:)') OR
             (provider='azure_openai' AND base_url ~ '^https://[a-z0-9-]+[.](openai[.]azure[.]com|services[.]ai[.]azure[.]com)/openai/v1$')));
        ALTER TABLE device_platform.llm_requests
          DROP CONSTRAINT llm_request_token_limit_check,
          ADD CONSTRAINT llm_request_token_limit_check CHECK(reserved_tokens BETWEEN 16 AND 8192),
          ADD COLUMN profile_revision_id uuid,
          ADD COLUMN configuration_hash text CHECK(configuration_hash ~ '^[a-f0-9]{64}$'),
          ADD CONSTRAINT llm_profile_fk FOREIGN KEY(organization_id,profile_revision_id)
            REFERENCES device_platform.processing_profile_revisions(organization_id,id);
        ALTER TABLE device_platform.processing_profiles
          ADD COLUMN draft_llm_connection_id uuid,
          ADD CONSTRAINT profile_llm_fk FOREIGN KEY(organization_id,draft_llm_connection_id)
            REFERENCES device_platform.llm_connections(organization_id,id);
        ALTER TABLE device_platform.processing_profile_revisions
          ADD COLUMN llm_connection_id uuid,
          ADD CONSTRAINT revision_llm_fk FOREIGN KEY(organization_id,llm_connection_id)
            REFERENCES device_platform.llm_connections(organization_id,id);
        ALTER TABLE device_platform.provider_connections
          DROP CONSTRAINT provider_connections_check,
          ADD CONSTRAINT provider_connections_check CHECK(
            (provider='aws' AND connection_type='aws_processing' AND auth_mode IN ('workload_identity','assume_role','access_key')) OR
            (provider='azure' AND connection_type='azure_speech' AND auth_mode IN ('workload_identity','api_key','service_principal')) OR
            (provider='azure' AND connection_type='azure_video_indexer' AND auth_mode IN ('workload_identity','service_principal')) OR
            (provider='azure' AND connection_type='azure_openai_whisper' AND auth_mode='api_key'));
        CREATE TABLE device_platform.speech_requests (
          id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
          department_id uuid, user_id uuid REFERENCES device_platform.users(id), device_id uuid,
          profile_revision_id uuid NOT NULL, configuration_hash text NOT NULL CHECK(configuration_hash ~ '^[a-f0-9]{64}$'),
          connection_id uuid NOT NULL, connection_revision integer NOT NULL CHECK(connection_revision>0),
          request_key uuid NOT NULL, fingerprint text NOT NULL CHECK(fingerprint ~ '^[a-f0-9]{64}$'),
          status text NOT NULL CHECK(status IN ('running','succeeded','failed','unknown','cancelled')),
          byte_size integer NOT NULL CHECK(byte_size BETWEEN 44 AND 4000000),
          duration_ms integer NOT NULL CHECK(duration_ms BETWEEN 1 AND 120000),
          object_key text NOT NULL CHECK(object_key ~ '^[a-f0-9-]+/speech/[a-f0-9-]+[.]wav$'),
          recording_status text NOT NULL DEFAULT 'pending' CHECK(recording_status IN ('pending','saved','failed')),
          lease_token uuid NOT NULL, lease_expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL, completed_at timestamptz, expires_at timestamptz NOT NULL,
          result jsonb, error_code text CHECK(error_code ~ '^[a-z_]{1,80}$'),
          UNIQUE(organization_id,request_key),
          FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
          FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id),
          FOREIGN KEY(organization_id,profile_revision_id) REFERENCES device_platform.processing_profile_revisions(organization_id,id),
          FOREIGN KEY(organization_id,connection_id) REFERENCES device_platform.provider_connections(organization_id,id),
          CHECK((user_id IS NULL)<>(device_id IS NULL)),
          CHECK(lease_expires_at>created_at AND lease_expires_at<=created_at+interval '11 minutes'),
          CHECK(expires_at>lease_expires_at AND expires_at<=created_at+interval '30 days'),
          CHECK((status='running')=(completed_at IS NULL)),
          CHECK((status='succeeded')=(result IS NOT NULL)),
          CHECK(result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=65536))
        );
        CREATE INDEX speech_daily ON device_platform.speech_requests(organization_id,created_at);
        CREATE INDEX speech_expiry ON device_platform.speech_requests(expires_at);
        CREATE FUNCTION device_platform.speech_guard() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,device_platform AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.expires_at>clock_timestamp() OR OLD.status='running' THEN
              RAISE EXCEPTION 'Speech request not expired' USING ERRCODE='23514'; END IF;
            RETURN OLD;
          ELSIF TG_OP='UPDATE' THEN
            IF NEW.status=OLD.status AND OLD.recording_status='pending' AND NEW.recording_status IN ('saved','failed') AND
              (to_jsonb(NEW)-'recording_status')=(to_jsonb(OLD)-'recording_status') THEN RETURN NEW; END IF;
            IF OLD.status<>'running' OR NEW.status='running' OR
              (to_jsonb(NEW)-ARRAY['status','completed_at','result','error_code','recording_status']) IS DISTINCT FROM
              (to_jsonb(OLD)-ARRAY['status','completed_at','result','error_code','recording_status']) THEN
              RAISE EXCEPTION 'Invalid speech transition' USING ERRCODE='23514'; END IF;
          ELSIF NEW.status<>'running' THEN
            RAISE EXCEPTION 'Invalid initial speech state' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER speech_request_guard BEFORE INSERT OR UPDATE OR DELETE
          ON device_platform.speech_requests FOR EACH ROW EXECUTE FUNCTION device_platform.speech_guard();
        REVOKE ALL ON device_platform.speech_requests FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.speech_guard() FROM PUBLIC;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve cloud records")
