"""Versioned management of existing shared patient catalog records."""

from alembic import op

revision = "0027_catalog_management"
down_revision = "0026_member_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute("""
    ALTER TABLE device_platform.scenario_categories ADD COLUMN management_version integer NOT NULL DEFAULT 1
      CHECK(management_version BETWEEN 1 AND 2147483646);
    ALTER TABLE device_platform.patient_identities ADD COLUMN management_version integer NOT NULL DEFAULT 1
      CHECK(management_version BETWEEN 1 AND 2147483646);
    CREATE FUNCTION device_platform.catalog_version_guard() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.management_version <> 1 THEN
          RAISE EXCEPTION 'Initial catalog version must be one' USING ERRCODE='23514';
        END IF;
      ELSE
        IF NEW.management_version IS DISTINCT FROM OLD.management_version THEN
          RAISE EXCEPTION 'Catalog version is database maintained' USING ERRCODE='23514';
        END IF;
        NEW.management_version := OLD.management_version+1;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER catalog_version BEFORE INSERT OR UPDATE ON device_platform.scenario_categories
      FOR EACH ROW EXECUTE FUNCTION device_platform.catalog_version_guard();
    CREATE TRIGGER catalog_version BEFORE INSERT OR UPDATE ON device_platform.patient_identities
      FOR EACH ROW EXECUTE FUNCTION device_platform.catalog_version_guard();
    REVOKE ALL ON FUNCTION device_platform.catalog_version_guard() FROM PUBLIC;
    COMMENT ON TABLE device_platform.scenario_categories IS 'Platform-managed shared fictional scenario categories.';
    COMMENT ON TABLE device_platform.patient_identities IS 'Platform-managed fictional patient/manikin identity templates; saved practice uses snapshots.';
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration; catalog history must be preserved.")
