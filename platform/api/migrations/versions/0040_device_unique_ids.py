"""Immutable platform device identities, retained across tenant registrations."""

from alembic import op

revision = "0040_device_unique_ids"
down_revision = "0039_default_local_models"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    SELECT id FROM device_platform.platform_settings WHERE id=1 FOR UPDATE;
    CREATE TABLE device_platform.device_identities (
      device_unique_id text PRIMARY KEY,
      CONSTRAINT device_unique_id_format CHECK (
        char_length(device_unique_id) BETWEEN 1 AND 50
        AND device_unique_id=btrim(device_unique_id)
        AND device_unique_id !~ '[[:cntrl:]]'
      )
    );
    CREATE UNIQUE INDEX device_unique_id_global ON device_platform.device_identities(lower(device_unique_id));
    ALTER TABLE device_platform.devices ADD COLUMN device_unique_id text;
    INSERT INTO device_platform.device_identities(device_unique_id)
      SELECT id::text FROM device_platform.devices;
    UPDATE device_platform.devices SET device_unique_id=id::text;
    ALTER TABLE device_platform.devices ALTER COLUMN device_unique_id SET NOT NULL;
    ALTER TABLE device_platform.devices ADD CONSTRAINT device_identity_reference
      FOREIGN KEY(device_unique_id) REFERENCES device_platform.device_identities(device_unique_id);
    -- A physical identity may have retired history in previous tenants, but
    -- only one current registration anywhere in the platform.
    CREATE UNIQUE INDEX device_identity_current_registration ON device_platform.devices(device_unique_id)
      WHERE enrollment_state<>'retired';
    CREATE FUNCTION device_platform.guard_device_unique_id() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    BEGIN
      IF TG_TABLE_NAME='device_identities' OR NEW.device_unique_id IS DISTINCT FROM OLD.device_unique_id THEN
        RAISE EXCEPTION 'Device unique ID cannot be changed or released'
          USING ERRCODE='23514', CONSTRAINT='device_unique_id_immutable';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER immutable_device_identity BEFORE UPDATE OR DELETE ON device_platform.device_identities
      FOR EACH ROW EXECUTE FUNCTION device_platform.guard_device_unique_id();
    CREATE TRIGGER immutable_device_unique_id BEFORE UPDATE ON device_platform.devices
      FOR EACH ROW EXECUTE FUNCTION device_platform.guard_device_unique_id();
    REVOKE ALL ON device_platform.device_identities FROM PUBLIC;
    REVOKE ALL ON FUNCTION device_platform.guard_device_unique_id() FROM PUBLIC;
    INSERT INTO device_platform.activity_events
      (id,organization_id,actor_type,category,event_type,entity_type,entity_id,severity,
       occurred_at,received_at,details,expires_at)
    SELECT gen_random_uuid(),d.organization_id,'system','audit','device.unique_id.initialized',
      'device',d.id,'info',now(),now(),
      '{"actor_role":"system","source":"0040_device_unique_ids","source_field":"device.id"}'::jsonb,
      now()+make_interval(days=>LEAST((o.policy_settings->>'audit_retention_days')::int,
        (p.policy_limits->>'audit_retention_days')::int))
    FROM device_platform.devices d JOIN device_platform.organizations o ON o.id=d.organization_id
      CROSS JOIN device_platform.platform_settings p WHERE p.id=1;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; permanent device identities cannot be removed by downgrade")
