"""Keep three local starter models without changing configured deployments."""

from alembic import op

revision = "0039_default_local_models"
down_revision = "0038_retire_model_setup"
branch_labels = None
depends_on = None


def upgrade():
    # Earlier migrations seed the supported catalog. Keep that historical chain
    # intact, then archive only its untouched, unused executable starter rows.
    # Deleted/disabled defaults stay deleted/disabled on subsequent deployments.
    op.execute("""
    SELECT id FROM device_platform.platform_settings WHERE id=1 FOR UPDATE;
    LOCK TABLE device_platform.runtime_models,
      device_platform.device_model_selections IN SHARE ROW EXCLUSIVE MODE;
    WITH archived AS (
      UPDATE device_platform.runtime_models m
      SET archived_at=now(), is_active=false, updated_at=now(), revision=m.revision+1
      WHERE m.organization_id IS NULL AND m.location='local'
        AND m.archived_at IS NULL AND m.is_active AND m.revision=1
        AND m.created_by IS NULL AND m.updated_by IS NULL AND m.last_used_at IS NULL
        AND m.settings='{}'::jsonb AND m.defaults='{}'::jsonb AND m.legacy='{}'::jsonb
        AND m.encrypted_credentials IS NULL AND m.credential_key_id IS NULL
        AND m.credential_owner_id IS NULL AND m.credential_owner_org IS NULL
        AND (
          EXISTS (
            SELECT 1 FROM device_platform.model_definitions d
            WHERE d.id=m.id AND d.provider=m.provider AND d.model_key=m.model_key
              AND ((m.kind='llm' AND m.provider='local_llama_cpp' AND m.engine='llm'
                    AND m.name=m.model_key
                    AND m.model_key IN ('qwen3-4b-local','qwen3-1.7b-local','qwenmedic-v1-local'))
                OR (m.kind='asr' AND m.provider='local_whisper' AND m.engine='local_whisper'
                    AND m.name='Whisper ' || m.model_key
                    AND m.model_key IN ('tiny','base','small','medium','large-v3-turbo','whisper-medical-v1')))
          )
          OR (m.kind='video' AND m.provider='local' AND m.engine='opencv_motion'
              AND m.model_key='opencv_motion' AND m.name='OpenCV motion')
        )
        AND NOT EXISTS (
          SELECT 1 FROM device_platform.device_model_selections s
          WHERE m.id IN (s.llm_model_id,s.asr_model_id,s.tts_model_id,s.video_model_id)
        )
      RETURNING m.id
    )
    INSERT INTO device_platform.activity_events
      (id,actor_type,category,event_type,entity_type,entity_id,severity,occurred_at,received_at,details,expires_at)
    SELECT gen_random_uuid(),'system','audit','model.deleted','runtime_model',a.id,'info',now(),now(),
      '{"actor_role":"system","scope":"platform","source":"0039_default_local_models","reason":"Retire unused starter model"}'::jsonb,
      now() + make_interval(days => LEAST(
        (p.default_organization_policy->>'audit_retention_days')::integer,
        (p.policy_limits->>'audit_retention_days')::integer))
    FROM archived a CROSS JOIN device_platform.platform_settings p WHERE p.id=1;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; retired starter models must not be silently reactivated")
