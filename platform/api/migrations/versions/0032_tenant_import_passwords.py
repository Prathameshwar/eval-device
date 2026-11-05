"""Add the manikin device type and encrypted, expiring import password escrow."""

from alembic import op

revision = "0032_tenant_import_passwords"
down_revision = "0031_case_draft_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DO $$
    DECLARE old_check text;
    BEGIN
      SELECT c.conname INTO old_check
      FROM pg_constraint c
      WHERE c.conrelid = 'device_platform.devices'::regclass
        AND c.contype = 'c'
        AND pg_get_constraintdef(c.oid) LIKE '%raspberry_pi%'
      LIMIT 1;
      IF old_check IS NULL THEN
        RAISE EXCEPTION 'Expected device type constraint is missing';
      END IF;
      EXECUTE format('ALTER TABLE device_platform.devices DROP CONSTRAINT %I', old_check);
    END $$;
    ALTER TABLE device_platform.devices
      ADD CONSTRAINT devices_allowed_type CHECK (device_type IN ('manikin','laptop','raspberry_pi','other'));
    ALTER TABLE device_platform.member_imports
      ADD COLUMN passwords_encrypted bytea,
      ADD COLUMN passwords_key_id text,
      ADD CONSTRAINT member_import_password_escrow_pair CHECK
        ((passwords_encrypted IS NULL) = (passwords_key_id IS NULL)),
      ADD CONSTRAINT member_import_password_escrow_size CHECK
        (passwords_encrypted IS NULL OR octet_length(passwords_encrypted) <= 1048576);
    COMMENT ON COLUMN device_platform.member_imports.passwords_encrypted IS
      'AES-GCM import password escrow; expires with the import after 30 days.';
    """)


def downgrade():
    raise RuntimeError(
        "Use a reviewed forward migration or restore; import password history must be preserved."
    )
