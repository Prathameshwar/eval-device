"""Restrict localized catalog validators to explicitly granted backend roles."""

from alembic import op

revision = "0028_language_validator_acl"
down_revision = "0027_catalog_management"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "REVOKE ALL ON FUNCTION device_platform.valid_language_map(jsonb,integer), "
        "device_platform.valid_language_list(text[],text) FROM PUBLIC"
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration; PUBLIC function access must not be restored.")
