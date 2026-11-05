"""Reusable media defaults; credentials remain in tenant provider connections."""

from alembic import op

revision = "0036_media_model_configs"
down_revision = "0035_unified_scenarios"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE device_platform.media_model_configs (
      id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      connection_id uuid NOT NULL,
      name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 100),
      engine text NOT NULL CHECK(engine IN ('aws_transcribe','azure_speech',
        'azure_openai_whisper','aws_polly','aws_rekognition','azure_video_indexer')),
      operation text NOT NULL CHECK(operation IN ('audio.transcribe','audio.synthesize','video.labels')),
      defaults jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(defaults)='object' AND octet_length(defaults::text)<=4096),
      is_active boolean NOT NULL DEFAULT true,
      archived_at timestamptz,
      version integer NOT NULL DEFAULT 1 CHECK(version>0),
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      updated_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY (organization_id,connection_id)
        REFERENCES device_platform.provider_connections(organization_id,id),
      UNIQUE(organization_id,id),
      CHECK(archived_at IS NULL OR NOT is_active),
      CHECK((operation='audio.transcribe' AND engine IN ('aws_transcribe','azure_speech','azure_openai_whisper'))
         OR (operation='audio.synthesize' AND engine IN ('aws_polly','azure_speech'))
         OR (operation='video.labels' AND engine IN ('aws_rekognition','azure_video_indexer')))
    );
    CREATE INDEX media_model_configs_tenant ON device_platform.media_model_configs(organization_id,name,id);
    CREATE INDEX media_model_configs_connection ON device_platform.media_model_configs(connection_id);
    REVOKE ALL ON device_platform.media_model_configs FROM PUBLIC;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; media configuration history must be preserved")
