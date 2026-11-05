"""Platform-owned cloud model credentials and Anthropic protocol support."""

from alembic import op
from sqlalchemy import text

revision = "0034_platform_model_connections"
down_revision = "0033_tenant_training_starters"
branch_labels = None
depends_on = None


def upgrade():
    existing_grants = (
        op.get_bind()
        .execute(text("SELECT pg_get_viewdef('device_platform.default_role_permissions'::regclass, true)"))
        .scalar_one()
        .rstrip()
        .rstrip(";")
    )
    op.execute(
        "CREATE OR REPLACE VIEW device_platform.default_role_permissions AS "
        "SELECT * FROM (" + existing_grants + ") AS prior_grants "
        "WHERE NOT (role_code='org_admin' AND permission IN "
        "('org.connections.manage','org.profiles.manage'))"
    )
    op.execute("""
    CREATE TABLE device_platform.platform_model_connections (
      model_definition_id uuid PRIMARY KEY REFERENCES device_platform.model_definitions(id),
      provider text NOT NULL CHECK(provider IN ('openai','azure_openai','openai_compatible','anthropic')),
      base_url text NOT NULL CHECK(length(base_url) BETWEEN 1 AND 512),
      model text NOT NULL CHECK(model ~ '^[A-Za-z0-9_.:/-]{1,100}$'),
      encrypted_credentials bytea NOT NULL,
      credential_key_id text NOT NULL,
      max_tokens integer NOT NULL DEFAULT 1024 CHECK(max_tokens BETWEEN 16 AND 4096),
      revision integer NOT NULL DEFAULT 1 CHECK(revision > 0),
      is_active boolean NOT NULL DEFAULT false,
      tested_at timestamptz,
      tested_revision integer,
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      updated_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK(tested_revision IS NULL OR tested_revision BETWEEN 1 AND revision)
    );
    REVOKE ALL ON device_platform.platform_model_connections FROM PUBLIC;
    ALTER TABLE device_platform.llm_connections
      ADD COLUMN managed_by_platform boolean NOT NULL DEFAULT false,
      DROP CONSTRAINT llm_provider_check,
      ADD CONSTRAINT llm_provider_check CHECK(provider IN
        ('local_llama_cpp','openai','openai_compatible','azure_openai','anthropic')),
      DROP CONSTRAINT llm_endpoint_check,
      ADD CONSTRAINT llm_endpoint_check CHECK(length(base_url) BETWEEN 1 AND 512 AND
        ((provider='local_llama_cpp' AND base_url ~ '^http://127[.]0[.]0[.]1:[0-9]{1,5}$') OR
         (provider='openai' AND base_url='https://api.openai.com/v1') OR
         (provider='openai_compatible' AND base_url ~ '^(https://|http://127[.]0[.]0[.]1:)') OR
         (provider='azure_openai' AND base_url ~ '^https://[a-z0-9-]+[.](openai[.]azure[.]com|services[.]ai[.]azure[.]com)/openai/v1$') OR
         (provider='anthropic' AND base_url='https://api.anthropic.com/v1')));
    INSERT INTO device_platform.model_definitions
      (id,provider,model_key,display_name,categories,operations,adapter_status)
    SELECT pg_catalog.gen_random_uuid(),'local_llama_cpp',name,name,
           '["conversation"]'::jsonb,'["text.generate"]'::jsonb,'available'
      FROM (VALUES ('qwen3-4b-local'),('qwen3-1.7b-local'),
                   ('qwen3.5-4b-local'),('qwenmedic-v1-local')) AS supported(name)
    ON CONFLICT (provider,model_key) DO NOTHING;
    INSERT INTO device_platform.model_definitions
      (id,provider,model_key,display_name,categories,operations,adapter_status)
    SELECT pg_catalog.gen_random_uuid(),'local_whisper',name,'Whisper ' || name,
           '["asr"]'::jsonb,'["audio.transcribe"]'::jsonb,'available'
      FROM (VALUES ('tiny'),('base'),('small'),('medium'),('large-v3'),
                   ('large-v3-turbo'),('whisper-medical-v1')) AS supported(name)
    ON CONFLICT (provider,model_key) DO NOTHING;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; this migration preserves configured credentials")
