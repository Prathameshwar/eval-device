"""Retire editable connection/profile setup; retain immutable historical records."""

from alembic import op

revision = "0038_retire_model_setup"
down_revision = "0037_direct_device_models"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DROP TRIGGER sync_runtime_model ON device_platform.llm_connections;
    DROP TRIGGER sync_runtime_model ON device_platform.provider_connections;
    DROP FUNCTION device_platform.sync_legacy_runtime_model();
    ALTER TABLE device_platform.processing_profiles
      ADD COLUMN retired_assignments jsonb NOT NULL DEFAULT '{}'::jsonb;
    UPDATE device_platform.processing_profiles p SET retired_assignments=jsonb_build_object(
      'organization_default', EXISTS(SELECT 1 FROM device_platform.organizations o WHERE o.default_profile_id=p.id),
      'device_ids', COALESCE((SELECT jsonb_agg(d.id ORDER BY d.id) FROM device_platform.devices d WHERE d.profile_id=p.id), '[]'::jsonb)
    );
    ALTER TABLE device_platform.devices DROP COLUMN profile_id;
    ALTER TABLE device_platform.organizations DROP COLUMN default_profile_id;
    CREATE FUNCTION device_platform.retired_model_configuration() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    BEGIN
      RAISE EXCEPTION 'Configuration history is immutable; manage models and device selections'
        USING ERRCODE='23514';
    END $$;
    CREATE TRIGGER retired_configuration BEFORE INSERT OR UPDATE OR DELETE
      ON device_platform.llm_connections FOR EACH ROW EXECUTE FUNCTION device_platform.retired_model_configuration();
    CREATE TRIGGER retired_configuration BEFORE INSERT OR UPDATE OR DELETE
      ON device_platform.provider_connections FOR EACH ROW EXECUTE FUNCTION device_platform.retired_model_configuration();
    CREATE TRIGGER retired_configuration BEFORE INSERT OR UPDATE OR DELETE
      ON device_platform.processing_profiles FOR EACH ROW EXECUTE FUNCTION device_platform.retired_model_configuration();
    REVOKE ALL ON FUNCTION device_platform.retired_model_configuration() FROM PUBLIC;
    COMMENT ON TABLE device_platform.llm_connections IS 'Immutable pre-0038 history; canonical executable models are in runtime_models';
    COMMENT ON TABLE device_platform.provider_connections IS 'Immutable pre-0038 history; canonical executable models are in runtime_models';
    COMMENT ON TABLE device_platform.processing_profiles IS 'Immutable pre-0038 history; device_model_selections is the only assignment store';
    """)


def downgrade():
    raise RuntimeError("Historical model setup cannot be re-enabled by downgrade")
