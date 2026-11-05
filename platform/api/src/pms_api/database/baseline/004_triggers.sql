-- IDs, tenant ownership and original creation metadata never move between records.
CREATE FUNCTION protect_context() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
DECLARE key text;
BEGIN
  FOREACH key IN ARRAY TG_ARGV LOOP
    IF to_jsonb(NEW)->key IS DISTINCT FROM to_jsonb(OLD)->key THEN
      RAISE EXCEPTION '%: immutable context field %', TG_TABLE_NAME, key USING ERRCODE = '23514';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

CREATE FUNCTION touch_record() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  NEW.updated_at := clock_timestamp();
  IF to_jsonb(NEW) ? 'is_active' THEN
    IF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
      NEW.status_changed_at := NEW.updated_at;
    ELSE
      NEW.status_changed_at := OLD.status_changed_at;
    END IF;
  END IF;
  RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['organizations','departments','users','organization_memberships',
    'devices','provider_connections','processing_profiles'] LOOP
    EXECUTE format('CREATE TRIGGER context_immutable BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION protect_context(''id'',''created_at'',''created_by'',''organization_id'')',t);
    EXECUTE format('CREATE TRIGGER timestamps BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_record()',t);
  END LOOP;
END $$;
CREATE TRIGGER user_identity_immutable BEFORE UPDATE ON users FOR EACH ROW
  EXECUTE FUNCTION protect_context('identity_issuer','identity_subject');
CREATE FUNCTION protect_membership_identity() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF OLD.user_id IS NOT NULL AND NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'An existing membership cannot be assigned to another user' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER membership_identity_immutable BEFORE UPDATE ON organization_memberships FOR EACH ROW
  EXECUTE FUNCTION protect_membership_identity();

CREATE TRIGGER run_context_immutable BEFORE UPDATE ON processing_runs FOR EACH ROW
  EXECUTE FUNCTION protect_context('id','organization_id','device_id','department_id',
    'profile_revision_id','requested_by','capture_id','request_key','operation','execution_mode',
    'engine','connection_id','effective_settings','created_at','captured_at');
CREATE TRIGGER run_timestamps BEFORE UPDATE ON processing_runs FOR EACH ROW EXECUTE FUNCTION touch_record();

CREATE FUNCTION protect_revision() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  RAISE EXCEPTION 'Published revisions are immutable; publish a new revision' USING ERRCODE = '23514';
END $$;
CREATE TRIGGER revision_immutable BEFORE UPDATE OR DELETE ON processing_profile_revisions
  FOR EACH ROW EXECUTE FUNCTION protect_revision();

CREATE FUNCTION protect_history() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '23514';
  END IF;
  IF OLD.expires_at > clock_timestamp() THEN
    RAISE EXCEPTION '% retention has not expired', TG_TABLE_NAME USING ERRCODE = '23514';
  END IF;
  RETURN OLD;
END $$;
CREATE TRIGGER telemetry_history BEFORE UPDATE OR DELETE ON device_telemetry_samples
  FOR EACH ROW EXECUTE FUNCTION protect_history();
CREATE TRIGGER event_history BEFORE UPDATE OR DELETE ON activity_events
  FOR EACH ROW EXECUTE FUNCTION protect_history();

CREATE FUNCTION protect_run_deletion() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF OLD.expires_at > clock_timestamp()
    OR OLD.status NOT IN ('succeeded','failed','cancelled','expired')
    OR OLD.cleanup_status NOT IN ('not_required','succeeded')
    OR OLD.playback_status IN ('pending','playing','unknown')
    OR OLD.provider_submission_status IN ('submitting','unknown')
    OR (OLD.lease_expires_at IS NOT NULL AND OLD.lease_expires_at > clock_timestamp()) THEN
    RAISE EXCEPTION 'Run retention, processing, playback or cleanup is incomplete' USING ERRCODE = '23514';
  END IF;
  RETURN OLD;
END $$;
CREATE TRIGGER run_retention BEFORE DELETE ON processing_runs
  FOR EACH ROW EXECUTE FUNCTION protect_run_deletion();

CREATE FUNCTION connection_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF ROW(NEW.provider, NEW.connection_type, NEW.auth_mode, NEW.settings, NEW.secret_ref)
    IS DISTINCT FROM ROW(OLD.provider, OLD.connection_type, OLD.auth_mode, OLD.settings, OLD.secret_ref) THEN
    NEW.configuration_version := OLD.configuration_version + 1;
    NEW.validation_results := '{}'::jsonb;
    NEW.last_validated_at := NULL;
  ELSIF NEW.configuration_version IS DISTINCT FROM OLD.configuration_version THEN
    RAISE EXCEPTION 'Connection version is maintained by the database' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER connection_versioning BEFORE UPDATE ON provider_connections
  FOR EACH ROW EXECUTE FUNCTION connection_version();

CREATE FUNCTION credential_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF NEW.credential_hash IS DISTINCT FROM OLD.credential_hash
    OR NEW.credential_revoked_at IS DISTINCT FROM OLD.credential_revoked_at THEN
    NEW.credential_version := OLD.credential_version + 1;
    IF NEW.credential_hash IS NOT NULL THEN
      NEW.credential_issued_at := clock_timestamp();
    ELSIF OLD.credential_hash IS NOT NULL THEN
      NEW.credential_revoked_at := clock_timestamp();
    END IF;
  ELSIF NEW.credential_version IS DISTINCT FROM OLD.credential_version THEN
    RAISE EXCEPTION 'Credential version changes only on issuance/rotation/revocation' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER device_credential_version BEFORE UPDATE ON devices
  FOR EACH ROW EXECUTE FUNCTION credential_version();

-- A global singleton lock serializes administrator-affecting statements. Use
-- PostgreSQL's default READ COMMITTED so checks see a predecessor's committed work.
-- Callers acquiring organization locks must take this singleton lock first.
CREATE FUNCTION lock_admin_changes() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Administrator mutations require READ COMMITTED transactions' USING ERRCODE = '25000';
  END IF;
  PERFORM id FROM device_platform.platform_settings WHERE id = 1 FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Platform singleton must be initialized first'; END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER admin_lock BEFORE INSERT OR DELETE OR UPDATE OF platform_role, is_active ON users
  FOR EACH STATEMENT EXECUTE FUNCTION lock_admin_changes();
CREATE TRIGGER admin_lock BEFORE INSERT OR DELETE OR UPDATE OF role, user_id, is_active, invitation_status ON organization_memberships
  FOR EACH STATEMENT EXECUTE FUNCTION lock_admin_changes();
CREATE TRIGGER admin_lock BEFORE INSERT OR DELETE OR UPDATE OF is_active ON organizations
  FOR EACH STATEMENT EXECUTE FUNCTION lock_admin_changes();

CREATE FUNCTION check_org_admin(org_id uuid) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM device_platform.organizations WHERE id = org_id AND is_active)
    AND NOT EXISTS (
      SELECT 1 FROM device_platform.organization_memberships m
      JOIN device_platform.users u ON u.id = m.user_id
      WHERE m.organization_id = org_id AND m.role = 'org_admin' AND m.is_active
        AND m.invitation_status = 'accepted' AND u.is_active
    ) THEN
    RAISE EXCEPTION 'Active organization % requires an active accepted administrator', org_id USING ERRCODE = '23514';
  END IF;
END $$;

CREATE FUNCTION check_admin_coverage() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
DECLARE org_id uuid; affected_user uuid;
BEGIN
  IF TG_TABLE_NAME = 'users' THEN
    IF TG_OP <> 'INSERT' THEN
      IF OLD.platform_role = 'platform_admin' AND OLD.is_active
        AND NOT EXISTS (SELECT 1 FROM device_platform.users WHERE platform_role = 'platform_admin' AND is_active) THEN
        RAISE EXCEPTION 'Cannot remove the last active platform administrator' USING ERRCODE = '23514';
      END IF;
    END IF;
    affected_user := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
    FOR org_id IN SELECT DISTINCT organization_id FROM device_platform.organization_memberships
      WHERE user_id = affected_user AND role = 'org_admin' ORDER BY organization_id LOOP
      PERFORM device_platform.check_org_admin(org_id);
    END LOOP;
  ELSIF TG_TABLE_NAME = 'organizations' THEN
    PERFORM device_platform.check_org_admin(CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END);
  ELSE
    PERFORM device_platform.check_org_admin(CASE WHEN TG_OP = 'DELETE' THEN OLD.organization_id ELSE NEW.organization_id END);
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER admin_coverage AFTER INSERT OR UPDATE OR DELETE ON organizations
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_admin_coverage();
CREATE CONSTRAINT TRIGGER admin_coverage AFTER INSERT OR UPDATE OR DELETE ON organization_memberships
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_admin_coverage();
CREATE CONSTRAINT TRIGGER admin_coverage AFTER UPDATE OR DELETE ON users
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_admin_coverage();

CREATE FUNCTION maintain_platform_settings() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Cannot delete the platform settings singleton' USING ERRCODE = '23514';
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'Platform settings identity is immutable' USING ERRCODE = '23514';
  END IF;
  IF NEW.updated_by IS NULL OR NOT EXISTS (SELECT 1 FROM device_platform.users
    WHERE id = NEW.updated_by AND is_active AND platform_role = 'platform_admin') THEN
    RAISE EXCEPTION 'Settings changes require an active platform administrator' USING ERRCODE = '23514';
  END IF;
  NEW.configuration_version := OLD.configuration_version + 1;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER platform_settings_guard BEFORE UPDATE OR DELETE ON platform_settings
  FOR EACH ROW EXECUTE FUNCTION maintain_platform_settings();
