"""User-requested authenticated encrypted provider credentials in PostgreSQL."""

from alembic import op

revision = "0002_credentials"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE device_platform.provider_connections ADD COLUMN encrypted_credentials bytea, ADD COLUMN credential_key_id text"
    )
    op.execute("""DO $$ DECLARE c record; BEGIN
      FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='device_platform.provider_connections'::regclass
        AND contype='c' AND pg_get_constraintdef(oid) LIKE '%auth_mode%' AND pg_get_constraintdef(oid) LIKE '%secret_ref%' LOOP
        EXECUTE format('ALTER TABLE device_platform.provider_connections DROP CONSTRAINT %I',c.conname);
      END LOOP;
    END $$""")
    op.execute("""ALTER TABLE device_platform.provider_connections
      ADD CONSTRAINT encrypted_credentials_pair CHECK ((encrypted_credentials IS NULL) = (credential_key_id IS NULL)),
      ADD CONSTRAINT encrypted_credentials_size CHECK (octet_length(encrypted_credentials) BETWEEN 29 AND 65536),
      ADD CONSTRAINT credential_key_nonblank CHECK (char_length(btrim(credential_key_id)) BETWEEN 1 AND 128),
      ADD CONSTRAINT secret_auth_material CHECK (auth_mode NOT IN ('access_key','api_key','service_principal') OR encrypted_credentials IS NOT NULL OR secret_ref IS NOT NULL)""")
    op.execute("""CREATE OR REPLACE FUNCTION device_platform.connection_version() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$ BEGIN
      IF ROW(NEW.provider, NEW.connection_type, NEW.auth_mode, NEW.settings, NEW.secret_ref, NEW.encrypted_credentials, NEW.credential_key_id)
       IS DISTINCT FROM ROW(OLD.provider, OLD.connection_type, OLD.auth_mode, OLD.settings, OLD.secret_ref, OLD.encrypted_credentials, OLD.credential_key_id) THEN
        NEW.configuration_version := OLD.configuration_version+1;
        NEW.validation_results := '{}'::jsonb;
        NEW.last_validated_at := NULL;
      ELSIF NEW.configuration_version IS DISTINCT FROM OLD.configuration_version THEN
        RAISE EXCEPTION 'Connection version is maintained by the database' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")


def downgrade():
    raise RuntimeError("Credential migration requires an explicit data-preserving rollback procedure")
