"""Fence connection lifecycle changes and preserve function privilege boundaries."""

from alembic import op

revision = "0004_runtime_guards"
down_revision = "0003_languages"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE OR REPLACE FUNCTION device_platform.connection_version() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$ BEGIN
      IF ROW(NEW.provider, NEW.connection_type, NEW.auth_mode, NEW.settings, NEW.secret_ref,
             NEW.encrypted_credentials, NEW.credential_key_id, NEW.is_active)
       IS DISTINCT FROM ROW(OLD.provider, OLD.connection_type, OLD.auth_mode, OLD.settings, OLD.secret_ref,
                            OLD.encrypted_credentials, OLD.credential_key_id, OLD.is_active) THEN
        NEW.configuration_version := OLD.configuration_version+1;
        NEW.validation_results := '{}'::jsonb;
        NEW.last_validated_at := NULL;
      ELSIF NEW.configuration_version IS DISTINCT FROM OLD.configuration_version THEN
        RAISE EXCEPTION 'Connection version is maintained by the database' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE EXECUTE ON FUNCTION device_platform.check_languages() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Removing lifecycle fencing requires an explicit reviewed rollback")
