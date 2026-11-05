"""Device language selection and a small platform language catalog."""

from alembic import op

revision = "0003_languages"
down_revision = "0002_credentials"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    ALTER TABLE device_platform.platform_settings ADD COLUMN languages jsonb NOT NULL
      DEFAULT '[{"code":"en","name":"English","speech_locale":"en-IN","is_active":true},{"code":"hi","name":"Hindi","speech_locale":"hi-IN","is_active":true}]'::jsonb;
    ALTER TABLE device_platform.devices ADD COLUMN preferred_language text;
    CREATE FUNCTION device_platform.check_languages() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, device_platform AS $$
    DECLARE catalog_entry jsonb; codes text[] := '{}';
    BEGIN
      IF TG_TABLE_NAME = 'platform_settings' THEN
        IF jsonb_typeof(NEW.languages) <> 'array' OR jsonb_array_length(NEW.languages) NOT BETWEEN 1 AND 100 THEN
          RAISE EXCEPTION 'Invalid language catalog' USING ERRCODE='23514';
        END IF;
        FOR catalog_entry IN SELECT value FROM jsonb_array_elements(NEW.languages) LOOP
          IF jsonb_typeof(catalog_entry) <> 'object' OR jsonb_typeof(catalog_entry->'is_active') IS DISTINCT FROM 'boolean'
            OR coalesce(catalog_entry->>'code','') !~ '^[a-z]{2,3}(-[A-Z]{2})?$'
            OR coalesce(catalog_entry->>'speech_locale','') !~ '^[a-z]{2,3}-[A-Z]{2}$'
            OR length(coalesce(catalog_entry->>'name','')) NOT BETWEEN 1 AND 80
            OR catalog_entry->>'code' = ANY(codes) THEN
            RAISE EXCEPTION 'Invalid or duplicate language' USING ERRCODE='23514';
          END IF;
          codes := array_append(codes,catalog_entry->>'code');
        END LOOP;
        IF NOT NEW.languages @> '[{"code":"en","is_active":true}]'::jsonb THEN
          RAISE EXCEPTION 'English must remain active as the fallback language' USING ERRCODE='23514';
        END IF;
        IF EXISTS(SELECT 1 FROM devices WHERE preferred_language IS NOT NULL AND NOT preferred_language = ANY(codes)) THEN
          RAISE EXCEPTION 'A selected device language cannot be removed; deactivate it instead' USING ERRCODE='23514';
        END IF;
      ELSIF NEW.preferred_language IS NOT NULL AND
        (TG_OP = 'INSERT' OR NEW.preferred_language IS DISTINCT FROM OLD.preferred_language) THEN
        IF NOT EXISTS(SELECT 1 FROM platform_settings, jsonb_array_elements(languages) AS item
          WHERE item->>'code' = NEW.preferred_language AND item->>'is_active' = 'true') THEN
          RAISE EXCEPTION 'Select an active platform language' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER platform_languages_check BEFORE INSERT OR UPDATE OF languages
      ON device_platform.platform_settings FOR EACH ROW EXECUTE FUNCTION device_platform.check_languages();
    CREATE TRIGGER device_language_check BEFORE INSERT OR UPDATE OF preferred_language
      ON device_platform.devices FOR EACH ROW EXECUTE FUNCTION device_platform.check_languages();
    COMMENT ON COLUMN device_platform.devices.preferred_language IS 'Optional catalog code; NULL or inactive selection resolves to English.';
    COMMENT ON COLUMN device_platform.platform_settings.languages IS 'Platform-managed language choices, initially English and Hindi; locale for speech providers.';
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Language selections must be explicitly migrated before removal")
