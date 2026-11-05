"""Room for a repaired routing attempt and a generated deflection.

An unusable routing object used to cost the learner an answer the case could have given, so a
turn may now spend one repaired routing attempt, and an unroutable question may spend the
spoken call on an in-character deflection instead of the stock clarification line. Both are
additional completions, so the recorded call count and the reserved output allowance grow, and
`patient_deflection` joins the authored outcomes a caller-executed turn can report. No column
is added or removed and no existing record changes meaning.
"""

from alembic import op

revision = "0019_patient_turn_recovery"
down_revision = "0018_local_conversation_history"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        ALTER TABLE device_platform.local_turns
          DROP CONSTRAINT local_turns_provider_calls_check,
          ADD CONSTRAINT local_turns_provider_calls_check CHECK(provider_calls BETWEEN 1 AND 3),
          DROP CONSTRAINT local_turns_answer_source_check,
          ADD CONSTRAINT local_turns_answer_source_check CHECK(answer_source IN
            ('patient_voice','patient_deflection','scripted_case','case_backchannel',
             'case_command_ack','case_boundary','case_clarification','routing_invalid',
             'plain_completion'));
        ALTER TABLE device_platform.llm_requests
          DROP CONSTRAINT llm_request_token_limit_check,
          ADD CONSTRAINT llm_request_token_limit_check CHECK(reserved_tokens BETWEEN 16 AND 16384);
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve training records")
