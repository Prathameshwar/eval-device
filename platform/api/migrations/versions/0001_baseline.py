"""Frozen reviewed PostgreSQL schema v1; future changes require a new revision."""

from importlib.resources import files

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    cursor = connection.connection.driver_connection.cursor()
    cursor.execute(
        "CREATE SCHEMA device_platform; REVOKE ALL ON SCHEMA device_platform FROM PUBLIC; SET LOCAL search_path=device_platform,pg_catalog; SET LOCAL TIME ZONE 'UTC';",
        prepare=False,
    )
    source = files("pms_api.database.baseline")
    for name in (
        "001_validation.sql",
        "002_tables.sql",
        "003_indexes.sql",
        "004_triggers.sql",
        "005_seed.sql",
        "006_role_catalog.sql",
    ):
        cursor.execute(source.joinpath(name).read_text(encoding="utf-8"), prepare=False)
    cursor.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA device_platform FROM PUBLIC; REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA device_platform FROM PUBLIC; COMMENT ON SCHEMA device_platform IS 'Device Platform schema version 1; Alembic 0001_baseline';",
        prepare=False,
    )
    cursor.close()


def downgrade():
    raise RuntimeError("Baseline downgrade would destroy application data; restore a verified backup instead")
