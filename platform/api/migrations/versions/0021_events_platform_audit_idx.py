"""Add partial global index for platform audit queries.

This migration creates a partial index on activity_events (id) where category = 'audit'
to optimize the platform-wide audit log endpoint GET /platform/audit, avoiding sequential
scans as activity events grow.
"""

from alembic import op

revision = "0021_events_platform_audit_idx"
down_revision = "0020_management_api"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        CREATE INDEX IF NOT EXISTS events_platform_audit_idx
          ON device_platform.activity_events (id)
          WHERE category = 'audit';
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve training records")
