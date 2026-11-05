"""Management directories, local identities, sessions and model catalog."""

from alembic import op

revision = "0020_management_api"
down_revision = "0019_patient_turn_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
        ALTER TABLE device_platform.users
          ALTER COLUMN identity_issuer DROP NOT NULL,
          ALTER COLUMN identity_subject DROP NOT NULL,
          ADD COLUMN auth_method text NOT NULL DEFAULT 'oidc'
            CHECK(auth_method IN ('oidc','local')),
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id),
          ADD COLUMN management_version integer NOT NULL DEFAULT 1 CHECK(management_version>0),
          ADD CONSTRAINT users_identity_method_check CHECK(
            (auth_method='oidc' AND identity_issuer IS NOT NULL AND identity_subject IS NOT NULL) OR
            (auth_method='local' AND identity_issuer IS NULL AND identity_subject IS NULL));
        ALTER TABLE device_platform.organizations
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id),
          ADD COLUMN management_version integer NOT NULL DEFAULT 1 CHECK(management_version>0);
        ALTER TABLE device_platform.departments
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id),
          ADD COLUMN management_version integer NOT NULL DEFAULT 1 CHECK(management_version>0);
        ALTER TABLE device_platform.organization_memberships
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id),
          ADD COLUMN invitation_auth_method text CHECK(invitation_auth_method IN ('local','oidc')),
          ADD COLUMN management_version integer NOT NULL DEFAULT 1 CHECK(management_version>0);
        ALTER TABLE device_platform.provider_connections
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id);
        ALTER TABLE device_platform.processing_profiles
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id),
          ADD COLUMN management_version integer NOT NULL DEFAULT 1 CHECK(management_version>0);
        ALTER TABLE device_platform.llm_connections
          ADD COLUMN archived_at timestamptz,
          ADD COLUMN archived_by uuid REFERENCES device_platform.users(id);

        CREATE OR REPLACE FUNCTION device_platform.check_org_admin(org_id uuid) RETURNS void
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM device_platform.organizations
              WHERE id=org_id AND is_active AND archived_at IS NULL)
            AND NOT EXISTS (
              SELECT 1 FROM device_platform.organization_memberships m
              JOIN device_platform.users u ON u.id=m.user_id
              WHERE m.organization_id=org_id AND m.role='org_admin' AND m.is_active
                AND m.invitation_status='accepted' AND m.archived_at IS NULL
                AND u.is_active AND u.archived_at IS NULL
            ) THEN
            RAISE EXCEPTION 'Active organization % requires an active accepted administrator', org_id
              USING ERRCODE='23514';
          END IF;
        END $$;

        CREATE OR REPLACE FUNCTION device_platform.check_admin_coverage() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        DECLARE org_id uuid; affected_user uuid;
        BEGIN
          IF TG_TABLE_NAME='users' THEN
            IF TG_OP<>'INSERT' THEN
              IF OLD.platform_role='platform_admin' AND OLD.is_active AND OLD.archived_at IS NULL
                AND NOT EXISTS (SELECT 1 FROM device_platform.users
                  WHERE platform_role='platform_admin' AND is_active AND archived_at IS NULL) THEN
                RAISE EXCEPTION 'Cannot remove the last active platform administrator'
                  USING ERRCODE='23514';
              END IF;
            END IF;
            affected_user := CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
            FOR org_id IN SELECT DISTINCT organization_id
              FROM device_platform.organization_memberships
              WHERE user_id=affected_user AND role='org_admin' ORDER BY organization_id LOOP
              PERFORM device_platform.check_org_admin(org_id);
            END LOOP;
          ELSIF TG_TABLE_NAME='organizations' THEN
            PERFORM device_platform.check_org_admin(CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END);
          ELSE
            PERFORM device_platform.check_org_admin(
              CASE WHEN TG_OP='DELETE' THEN OLD.organization_id ELSE NEW.organization_id END);
          END IF;
          RETURN NULL;
        END $$;
        CREATE TRIGGER management_archive_admin_lock
          BEFORE UPDATE OF archived_at ON device_platform.users
          FOR EACH STATEMENT EXECUTE FUNCTION device_platform.lock_admin_changes();
        CREATE TRIGGER management_archive_admin_lock
          BEFORE UPDATE OF archived_at ON device_platform.organizations
          FOR EACH STATEMENT EXECUTE FUNCTION device_platform.lock_admin_changes();
        CREATE TRIGGER management_archive_admin_lock
          BEFORE UPDATE OF archived_at ON device_platform.organization_memberships
          FOR EACH STATEMENT EXECUTE FUNCTION device_platform.lock_admin_changes();
        CREATE OR REPLACE FUNCTION device_platform.maintain_platform_settings() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'Cannot delete the platform settings singleton' USING ERRCODE='23514';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'Platform settings identity is immutable' USING ERRCODE='23514';
          END IF;
          IF NEW.updated_by IS NULL OR NOT EXISTS (
            SELECT 1 FROM device_platform.users WHERE id=NEW.updated_by AND is_active
              AND archived_at IS NULL AND platform_role='platform_admin') THEN
            RAISE EXCEPTION 'Settings changes require an active platform administrator'
              USING ERRCODE='23514';
          END IF;
          NEW.configuration_version := OLD.configuration_version+1;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END $$;

        CREATE TABLE device_platform.local_credentials (
          user_id uuid PRIMARY KEY REFERENCES device_platform.users(id) ON DELETE RESTRICT,
          login_email text NOT NULL,
          password_hash text,
          credential_version integer NOT NULL DEFAULT 1 CHECK(credential_version>0),
          password_changed_at timestamptz,
          setup_completed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK(login_email=lower(btrim(login_email)) AND char_length(login_email) BETWEEN 3 AND 1024),
          CHECK(password_hash IS NULL OR char_length(password_hash) BETWEEN 40 AND 1024),
          CHECK((password_hash IS NULL)=(setup_completed_at IS NULL))
        );
        CREATE UNIQUE INDEX local_credentials_login_unique
          ON device_platform.local_credentials(login_email);

        -- A local administrator is usable only after password setup. Keep the database
        -- availability guards aligned with authentication so a pending local identity
        -- cannot be used to justify removing the last administrator who can sign in.
        CREATE OR REPLACE FUNCTION device_platform.check_org_admin(org_id uuid) RETURNS void
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM device_platform.organizations
              WHERE id=org_id AND is_active AND archived_at IS NULL)
            AND NOT EXISTS (
              SELECT 1 FROM device_platform.organization_memberships m
              JOIN device_platform.users u ON u.id=m.user_id
              WHERE m.organization_id=org_id AND m.role='org_admin' AND m.is_active
                AND m.invitation_status='accepted' AND m.archived_at IS NULL
                AND u.is_active AND u.archived_at IS NULL
                AND (u.auth_method='oidc' OR EXISTS (
                  SELECT 1 FROM device_platform.local_credentials lc
                  WHERE lc.user_id=u.id AND lc.setup_completed_at IS NOT NULL
                    AND lc.password_hash IS NOT NULL))
            ) THEN
            RAISE EXCEPTION 'Active organization % requires an active accepted administrator', org_id
              USING ERRCODE='23514';
          END IF;
        END $$;

        CREATE OR REPLACE FUNCTION device_platform.check_admin_coverage() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        DECLARE org_id uuid; affected_user uuid;
        BEGIN
          IF TG_TABLE_NAME='users' THEN
            IF TG_OP<>'INSERT' THEN
              IF OLD.platform_role='platform_admin' AND OLD.is_active AND OLD.archived_at IS NULL
                AND (OLD.auth_method='oidc' OR EXISTS (
                  SELECT 1 FROM device_platform.local_credentials lc
                  WHERE lc.user_id=OLD.id AND lc.setup_completed_at IS NOT NULL
                    AND lc.password_hash IS NOT NULL))
                AND NOT EXISTS (SELECT 1 FROM device_platform.users u
                  WHERE u.platform_role='platform_admin' AND u.is_active AND u.archived_at IS NULL
                    AND (u.auth_method='oidc' OR EXISTS (
                      SELECT 1 FROM device_platform.local_credentials lc
                      WHERE lc.user_id=u.id AND lc.setup_completed_at IS NOT NULL
                        AND lc.password_hash IS NOT NULL))) THEN
                RAISE EXCEPTION 'Cannot remove the last active platform administrator'
                  USING ERRCODE='23514';
              END IF;
            END IF;
            affected_user := CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
            FOR org_id IN SELECT DISTINCT organization_id
              FROM device_platform.organization_memberships
              WHERE user_id=affected_user AND role='org_admin' ORDER BY organization_id LOOP
              PERFORM device_platform.check_org_admin(org_id);
            END LOOP;
          ELSIF TG_TABLE_NAME='organizations' THEN
            PERFORM device_platform.check_org_admin(CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END);
          ELSE
            PERFORM device_platform.check_org_admin(
              CASE WHEN TG_OP='DELETE' THEN OLD.organization_id ELSE NEW.organization_id END);
          END IF;
          RETURN NULL;
        END $$;

        CREATE OR REPLACE FUNCTION device_platform.maintain_platform_settings() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'Cannot delete the platform settings singleton' USING ERRCODE='23514';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'Platform settings identity is immutable' USING ERRCODE='23514';
          END IF;
          IF NEW.updated_by IS NULL OR NOT EXISTS (
            SELECT 1 FROM device_platform.users u WHERE u.id=NEW.updated_by AND u.is_active
              AND u.archived_at IS NULL AND u.platform_role='platform_admin'
              AND (u.auth_method='oidc' OR EXISTS (
                SELECT 1 FROM device_platform.local_credentials lc
                WHERE lc.user_id=u.id AND lc.setup_completed_at IS NOT NULL
                  AND lc.password_hash IS NOT NULL))) THEN
            RAISE EXCEPTION 'Settings changes require an active platform administrator'
              USING ERRCODE='23514';
          END IF;
          NEW.configuration_version := OLD.configuration_version+1;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END $$;

        CREATE TABLE device_platform.local_sessions (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES device_platform.users(id) ON DELETE RESTRICT,
          family_id uuid NOT NULL,
          refresh_token_hash text NOT NULL UNIQUE CHECK(refresh_token_hash ~ '^[a-f0-9]{64}$'),
          credential_version integer NOT NULL CHECK(credential_version>0),
          created_at timestamptz NOT NULL DEFAULT now(),
          last_used_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          revoke_reason text CHECK(revoke_reason IS NULL OR char_length(revoke_reason)<=80),
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '90 days'),
          CHECK(last_used_at>=created_at AND last_used_at<=expires_at)
        );
        CREATE INDEX local_sessions_user_live
          ON device_platform.local_sessions(user_id,expires_at) WHERE revoked_at IS NULL;
        CREATE INDEX local_sessions_expiry ON device_platform.local_sessions(expires_at);

        CREATE TABLE device_platform.account_action_tokens (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES device_platform.users(id) ON DELETE RESTRICT,
          purpose text NOT NULL CHECK(purpose IN ('setup','password_reset','email_verify','email_change')),
          token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[a-f0-9]{64}$'),
          target_email text,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz,
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '7 days'),
          CHECK(target_email IS NULL OR (target_email=lower(btrim(target_email)) AND char_length(target_email)<=1024))
        );
        CREATE INDEX account_actions_user_purpose
          ON device_platform.account_action_tokens(user_id,purpose,expires_at);

        CREATE TABLE device_platform.auth_rate_limits (
          key_hash text NOT NULL CHECK(key_hash ~ '^[a-f0-9]{64}$'),
          category text NOT NULL CHECK(category IN ('login','refresh','recovery','account_action')),
          window_started_at timestamptz NOT NULL,
          request_count integer NOT NULL CHECK(request_count BETWEEN 1 AND 100000),
          expires_at timestamptz NOT NULL,
          PRIMARY KEY(key_hash,category),
          CHECK(expires_at>window_started_at)
        );
        CREATE INDEX auth_rate_limit_expiry ON device_platform.auth_rate_limits(expires_at);

        CREATE TABLE device_platform.account_email_outbox (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES device_platform.users(id) ON DELETE RESTRICT,
          purpose text NOT NULL CHECK(purpose IN ('setup','password_reset','email_verify','email_change')),
          recipient text NOT NULL CHECK(recipient=lower(btrim(recipient)) AND char_length(recipient)<=1024),
          encrypted_payload bytea NOT NULL CHECK(octet_length(encrypted_payload) BETWEEN 29 AND 16384),
          key_id text NOT NULL CHECK(char_length(key_id) BETWEEN 1 AND 128),
          status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','failed')),
          attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 10),
          available_at timestamptz NOT NULL DEFAULT now(),
          lease_token uuid,
          lease_expires_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          sent_at timestamptz,
          expires_at timestamptz NOT NULL,
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '7 days'),
          CHECK((status='sending')=(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL))
        );
        CREATE INDEX account_email_due ON device_platform.account_email_outbox(status,available_at);

        CREATE TABLE device_platform.model_definitions (
          id uuid PRIMARY KEY,
          provider text NOT NULL CHECK(provider ~ '^[a-z][a-z0-9_]{1,79}$'),
          model_key text NOT NULL CHECK(model_key ~ '^[A-Za-z0-9_.:/-]{1,160}$'),
          display_name text NOT NULL CHECK(char_length(btrim(display_name)) BETWEEN 1 AND 256),
          description text CHECK(description IS NULL OR char_length(description)<=4000),
          publisher text CHECK(publisher IS NULL OR char_length(publisher)<=160),
          model_family text CHECK(model_family IS NULL OR char_length(model_family)<=160),
          model_version text CHECK(model_version IS NULL OR char_length(model_version)<=160),
          categories jsonb NOT NULL CHECK(jsonb_typeof(categories)='array' AND jsonb_array_length(categories) BETWEEN 1 AND 16),
          operations jsonb NOT NULL CHECK(jsonb_typeof(operations)='array' AND jsonb_array_length(operations) BETWEEN 1 AND 32),
          capabilities jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(capabilities)='object' AND octet_length(capabilities::text)<=32768),
          adapter_status text NOT NULL DEFAULT 'unavailable' CHECK(adapter_status IN ('available','unavailable')),
          lifecycle text NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','deprecated','retired')),
          version integer NOT NULL DEFAULT 1 CHECK(version>0),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          created_by uuid REFERENCES device_platform.users(id),
          updated_by uuid REFERENCES device_platform.users(id),
          UNIQUE(provider,model_key)
        );
        CREATE INDEX model_definitions_directory
          ON device_platform.model_definitions(lifecycle,provider,display_name,id);
        ALTER TABLE device_platform.llm_connections
          ADD COLUMN model_definition_id uuid REFERENCES device_platform.model_definitions(id);

        REVOKE ALL ON device_platform.local_credentials,device_platform.local_sessions,
          device_platform.account_action_tokens,device_platform.auth_rate_limits,
          device_platform.account_email_outbox,device_platform.model_definitions FROM PUBLIC;
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve identities and sessions")
