"""Bounded tenant member imports and encrypted invitation delivery."""

from alembic import op

revision = "0026_member_imports"
down_revision = "0025_manual_subscriptions"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute("""
    CREATE TABLE device_platform.member_imports (
      id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      role text NOT NULL CHECK (role IN ('org_admin','org_user','org_read_only','org_trainee')),
      auth_method text NOT NULL CHECK (auth_method IN ('local','oidc')),
      department_id uuid,
      FOREIGN KEY (department_id,organization_id)
        REFERENCES device_platform.departments(id,organization_id),
      status text NOT NULL DEFAULT 'validated' CHECK (status IN ('validated','completed')),
      rows jsonb NOT NULL CHECK (jsonb_typeof(rows)='array' AND jsonb_array_length(rows) BETWEEN 1 AND 200
        AND octet_length(rows::text) <= 1048576),
      created_at timestamptz NOT NULL DEFAULT now(),
      validated_until timestamptz NOT NULL,
      completed_at timestamptz,
      expires_at timestamptz NOT NULL,
      CHECK (role <> 'org_admin' OR department_id IS NULL),
      CHECK (isfinite(created_at) AND isfinite(validated_until) AND isfinite(expires_at)
        AND validated_until > created_at AND expires_at > validated_until
        AND expires_at <= created_at + interval '31 days'),
      CHECK ((status='validated' AND completed_at IS NULL) OR
        (status='completed' AND completed_at IS NOT NULL AND isfinite(completed_at)))
    );
    CREATE INDEX member_imports_tenant_created ON device_platform.member_imports(organization_id,created_at DESC,id);
    CREATE INDEX member_imports_expiry ON device_platform.member_imports(expires_at);
    CREATE TABLE device_platform.invitation_email_outbox (
      id uuid PRIMARY KEY,
      membership_id uuid NOT NULL REFERENCES device_platform.organization_memberships(id),
      encrypted_payload bytea NOT NULL,
      key_id text NOT NULL,
      token_hash text NOT NULL,
      status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sending','sent','failed','unknown','cancelled')),
      lease_token uuid,
      lease_expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      CHECK (isfinite(expires_at) AND expires_at > created_at)
    );
    CREATE INDEX invitation_email_pending ON device_platform.invitation_email_outbox(created_at)
      WHERE status='pending';
    CREATE INDEX invitation_email_membership ON device_platform.invitation_email_outbox(membership_id);
    CREATE INDEX invitation_email_expiry ON device_platform.invitation_email_outbox(expires_at);
    REVOKE ALL ON device_platform.member_imports,device_platform.invitation_email_outbox FROM PUBLIC;
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration; import records must be preserved.")
