"""One generation patient conversations; retain historical routing metadata."""

from alembic import op

revision = "0023_patient_conversation"
down_revision = "0022_browser_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        ALTER TABLE device_platform.local_turns ADD COLUMN policy_version text;
        -- These two original cross-column checks were unnamed. Discover their generated
        -- names using their columns, without assuming a PostgreSQL name suffix.
        DO $$ DECLARE item record; removed integer := 0; BEGIN
          FOR item IN SELECT conname FROM pg_constraint
            WHERE conrelid='device_platform.local_turns'::regclass AND contype='c'
              AND pg_get_constraintdef(oid) LIKE '%practice_id%'
              AND (pg_get_constraintdef(oid) LIKE '%routing_status%'
                   OR pg_get_constraintdef(oid) LIKE '%kind%')
          LOOP
            EXECUTE format('ALTER TABLE device_platform.local_turns DROP CONSTRAINT %I', item.conname);
            removed := removed + 1;
          END LOOP;
          IF removed <> 2 THEN RAISE EXCEPTION 'Unexpected local turn routing constraints'; END IF;
        END $$;
        ALTER TABLE device_platform.local_turns
          DROP CONSTRAINT local_turns_answer_source_check,
          ADD CONSTRAINT local_turns_answer_source_check CHECK(answer_source IN
            ('patient_conversation','patient_voice','patient_deflection','scripted_case',
             'case_backchannel','case_command_ack','case_boundary','case_clarification',
             'routing_invalid','plain_completion')),
          ADD CONSTRAINT local_turns_conversation_check CHECK(
            (answer_source='patient_conversation' AND practice_id IS NOT NULL
             AND policy_version IS NOT NULL AND policy_version='patient-conversation-v1'
             AND routing_status IS NULL AND kind IS NULL AND topics='[]'::jsonb
             AND provider_calls=1 AND finish_reason='stop')
            OR (answer_source<>'patient_conversation' AND policy_version IS NULL
                AND (practice_id IS NULL)=(routing_status IS NULL)
                AND (practice_id IS NULL)=(kind IS NULL)));
        WITH changed AS (
          UPDATE device_platform.llm_connections
            SET model_options=model_options-ARRAY['patient_answer_mode','patient_deflection_mode'],
                max_tokens=CASE WHEN provider='local_llama_cpp' THEN greatest(max_tokens,256)
                                ELSE max_tokens END,
                revision=revision+1
            WHERE model_options ?| ARRAY['patient_answer_mode','patient_deflection_mode']
               OR (provider='local_llama_cpp' AND max_tokens<256)
            RETURNING id,organization_id,revision
        )
        INSERT INTO device_platform.activity_events
          (id,organization_id,actor_type,category,event_type,severity,entity_type,entity_id,
           occurred_at,received_at,details,expires_at)
        SELECT gen_random_uuid(),c.organization_id,'system','audit','llm.conversation.configured',
          'info','llm_connection',c.id,now(),now(),
          jsonb_build_object('source','migration','revision','0023_patient_conversation',
                             'connection_revision',c.revision),
          now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
                      (p.policy_limits->>'audit_retention_days')::integer,
                      coalesce((o.policy_settings->>'audit_retention_days')::integer,90))*interval '1 day'
        FROM changed c JOIN device_platform.organizations o ON o.id=c.organization_id
        CROSS JOIN device_platform.platform_settings p WHERE p.id=1;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a forward migration to preserve recorded patient conversations")
