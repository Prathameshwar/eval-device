"""OpenAI and explicitly allowed compatible endpoints; preserve local settings."""

from alembic import op

revision = "0010_llm_providers"
down_revision = "0009_local_llm"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        ALTER TABLE device_platform.llm_connections
          ADD COLUMN provider text NOT NULL DEFAULT 'local_llama_cpp',
          ADD COLUMN token_parameter text NOT NULL DEFAULT 'max_tokens',
          ADD COLUMN stream_usage boolean NOT NULL DEFAULT true,
          ADD COLUMN instruction_role text NOT NULL DEFAULT 'system',
          DROP CONSTRAINT llm_connections_base_url_check,
          DROP CONSTRAINT llm_connections_max_tokens_check,
          ADD CONSTRAINT llm_provider_check CHECK(provider IN ('local_llama_cpp','openai','openai_compatible')),
          ADD CONSTRAINT llm_token_parameter_check CHECK(token_parameter IN ('max_tokens','max_completion_tokens')),
          ADD CONSTRAINT llm_instruction_role_check CHECK(instruction_role IN ('system','developer')),
          ADD CONSTRAINT llm_endpoint_check CHECK(length(base_url) BETWEEN 1 AND 512 AND
            ((provider='local_llama_cpp' AND base_url ~ '^http://127[.]0[.]0[.]1:[0-9]{1,5}$') OR
             (provider='openai' AND base_url='https://api.openai.com/v1') OR
             (provider='openai_compatible' AND base_url ~ '^(https://|http://127[.]0[.]0[.]1:)'))),
          ADD CONSTRAINT llm_output_limit_check CHECK(max_tokens BETWEEN 16 AND 4096 AND
            (provider<>'local_llama_cpp' OR max_tokens<=512)),
          ADD CONSTRAINT llm_protocol_check CHECK(
            (provider<>'openai' OR (token_parameter='max_completion_tokens' AND stream_usage)) AND
            (provider<>'local_llama_cpp' OR (token_parameter='max_tokens' AND stream_usage AND instruction_role='system')));
        ALTER TABLE device_platform.llm_requests
          DROP CONSTRAINT llm_requests_reserved_tokens_check,
          ADD CONSTRAINT llm_request_token_limit_check CHECK(reserved_tokens BETWEEN 16 AND 4096);
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore for LLM data")
