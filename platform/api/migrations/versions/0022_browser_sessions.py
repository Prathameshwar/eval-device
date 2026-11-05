"""Opaque browser sessions and credential-bound account actions."""

from alembic import op

revision = "0022_browser_sessions"
down_revision = "0021_events_platform_audit_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE device_platform.auth_rate_limits
          DROP CONSTRAINT auth_rate_limits_category_check,
          ADD CONSTRAINT auth_rate_limits_category_check CHECK(category IN
            ('login','refresh','recovery','account_action','login_account','recovery_account',
             'password_change','email_change'));
        ALTER TABLE device_platform.local_sessions
          ADD COLUMN browser_token_hash text UNIQUE
            CHECK(browser_token_hash IS NULL OR browser_token_hash ~ '^[a-f0-9]{64}$');
        ALTER TABLE device_platform.account_action_tokens
          ADD COLUMN credential_version integer;
        UPDATE device_platform.account_action_tokens a
          SET credential_version=c.credential_version
          FROM device_platform.local_credentials c WHERE c.user_id=a.user_id;
        -- Old email actions have no proof of the credential version that authorized them.
        UPDATE device_platform.account_action_tokens
          SET consumed_at=coalesce(consumed_at,now()) WHERE purpose='email_change';
        ALTER TABLE device_platform.account_action_tokens
          ALTER COLUMN credential_version SET NOT NULL,
          ADD CONSTRAINT account_action_credential_version CHECK(credential_version>0);
    """)


def downgrade():
    raise RuntimeError("Use a forward migration; downgrading would weaken session/action security")
