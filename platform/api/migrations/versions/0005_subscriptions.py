"""Organization subscription plans and serialized user/device capacity guards."""

from alembic import op

revision = "0005_subscriptions"
down_revision = "0004_runtime_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    CREATE TABLE device_platform.subscription_plans (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      code text NOT NULL UNIQUE CHECK (code IN ('standard','advanced')),
      name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 256),
      price_amount numeric(14,2) NOT NULL CHECK (price_amount >= 0 AND price_amount < 1000000000000),
      currency text NOT NULL CHECK (currency IN ('INR','USD')),
      billing_period text NOT NULL DEFAULT 'unspecified'
        CHECK (billing_period IN ('unspecified','monthly','annual','one_time')),
      max_users integer NOT NULL CHECK (max_users BETWEEN 1 AND 1000000),
      max_devices integer NOT NULL CHECK (max_devices BETWEEN 1 AND 1000000),
      is_active boolean NOT NULL DEFAULT true,
      configuration_version integer NOT NULL DEFAULT 1 CHECK (configuration_version > 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    INSERT INTO device_platform.subscription_plans
      (id,code,name,price_amount,currency,max_users,max_devices) VALUES
      ('00000000-0000-4000-8000-000000000101','standard','Standard',350000,'INR',25,10),
      ('00000000-0000-4000-8000-000000000102','advanced','Advanced',500000,'INR',100,50);

    ALTER TABLE device_platform.organizations ADD COLUMN subscription_plan_id uuid
      REFERENCES device_platform.subscription_plans(id) ON DELETE RESTRICT;
    ALTER TABLE device_platform.organizations ADD COLUMN subscription_assigned_at timestamptz;
    -- Preserve existing organizations, including any already above the initial caps.
    -- Subsequent capacity increases require a free slot; no existing record is disabled.
    UPDATE device_platform.organizations
      SET subscription_plan_id='00000000-0000-4000-8000-000000000101',
          subscription_assigned_at=created_at;
    -- Backfill queues the baseline's deferred administrator-coverage triggers.
    -- Drain them before ALTER TABLE, then restore deferred validation semantics.
    SET CONSTRAINTS ALL IMMEDIATE;
    ALTER TABLE device_platform.organizations ALTER COLUMN subscription_plan_id SET NOT NULL;
    ALTER TABLE device_platform.organizations ALTER COLUMN subscription_assigned_at SET NOT NULL;
    ALTER TABLE device_platform.organizations ALTER COLUMN subscription_assigned_at SET DEFAULT now();
    SET CONSTRAINTS ALL DEFERRED;
    CREATE INDEX organizations_subscription_plan ON device_platform.organizations(subscription_plan_id);

    CREATE FUNCTION device_platform.subscription_usage(org_id uuid)
      RETURNS TABLE(active_users bigint, pending_invitations bigint, active_devices bigint)
      LANGUAGE sql VOLATILE SET search_path = pg_catalog, device_platform AS $$
        SELECT
          (SELECT count(*) FROM device_platform.organization_memberships
            WHERE organization_id=org_id AND is_active AND invitation_status='accepted'),
          (SELECT count(*) FROM device_platform.organization_memberships
            WHERE organization_id=org_id AND invitation_status='pending'
              AND invitation_expires_at > clock_timestamp()),
          (SELECT count(*) FROM device_platform.devices WHERE organization_id=org_id AND is_active)
      $$;

    CREATE FUNCTION device_platform.guard_subscription_plan() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    BEGIN
      IF NEW.configuration_version IS DISTINCT FROM OLD.configuration_version THEN
        RAISE EXCEPTION 'Plan version is maintained by the database' USING ERRCODE='23514';
      END IF;
      IF NEW.max_users < OLD.max_users AND EXISTS (
        SELECT 1 FROM device_platform.organizations o,
          LATERAL device_platform.subscription_usage(o.id) u
          WHERE o.subscription_plan_id=NEW.id AND u.active_users+u.pending_invitations > NEW.max_users
      ) THEN
        RAISE EXCEPTION 'Plan user limit is below existing usage'
          USING ERRCODE='23514', CONSTRAINT='subscription_user_limit';
      END IF;
      IF NEW.max_devices < OLD.max_devices AND EXISTS (
        SELECT 1 FROM device_platform.organizations o,
          LATERAL device_platform.subscription_usage(o.id) u
          WHERE o.subscription_plan_id=NEW.id AND u.active_devices > NEW.max_devices
      ) THEN
        RAISE EXCEPTION 'Plan device limit is below existing usage'
          USING ERRCODE='23514', CONSTRAINT='subscription_device_limit';
      END IF;
      NEW.configuration_version := OLD.configuration_version+1;
      NEW.updated_at := clock_timestamp();
      RETURN NEW;
    END $$;

    CREATE FUNCTION device_platform.guard_organization_subscription() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    DECLARE plan device_platform.subscription_plans%ROWTYPE; usage record;
    BEGIN
      IF TG_OP='INSERT' OR NEW.subscription_plan_id IS DISTINCT FROM OLD.subscription_plan_id THEN
        SELECT * INTO plan FROM device_platform.subscription_plans WHERE id=NEW.subscription_plan_id;
        IF NOT FOUND OR NOT plan.is_active THEN
          RAISE EXCEPTION 'Select an active subscription plan'
            USING ERRCODE='23514', CONSTRAINT='subscription_plan_unavailable';
        END IF;
        SELECT * INTO usage FROM device_platform.subscription_usage(NEW.id);
        IF usage.active_users+usage.pending_invitations > plan.max_users THEN
          RAISE EXCEPTION 'Selected plan user limit is below organization usage'
            USING ERRCODE='23514', CONSTRAINT='subscription_user_limit';
        END IF;
        IF usage.active_devices > plan.max_devices THEN
          RAISE EXCEPTION 'Selected plan device limit is below organization usage'
            USING ERRCODE='23514', CONSTRAINT='subscription_device_limit';
        END IF;
        NEW.subscription_assigned_at := clock_timestamp();
      ELSIF NEW.subscription_assigned_at IS DISTINCT FROM OLD.subscription_assigned_at THEN
        RAISE EXCEPTION 'Subscription assignment time is maintained by the database' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION device_platform.guard_subscription_capacity() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    DECLARE plan device_platform.subscription_plans%ROWTYPE; usage record;
      new_counted boolean; old_counted boolean := false; checked_at timestamptz := clock_timestamp();
    BEGIN
      IF TG_TABLE_NAME='devices' THEN
        new_counted := NEW.is_active;
        IF TG_OP='UPDATE' THEN old_counted := OLD.is_active; END IF;
      ELSE
        new_counted := (NEW.is_active AND NEW.invitation_status='accepted') OR
          (NEW.invitation_status='pending' AND NEW.invitation_expires_at > checked_at);
        IF TG_OP='UPDATE' THEN
          old_counted := (OLD.is_active AND OLD.invitation_status='accepted') OR
            (OLD.invitation_status='pending' AND OLD.invitation_expires_at > checked_at);
        END IF;
      END IF;
      IF coalesce(new_counted,false) AND NOT coalesce(old_counted,false) THEN
        SELECT p.* INTO plan FROM device_platform.subscription_plans p
          JOIN device_platform.organizations o ON o.subscription_plan_id=p.id
          WHERE o.id=NEW.organization_id;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'Organization subscription is required'
            USING ERRCODE='23514', CONSTRAINT='subscription_plan_unavailable';
        END IF;
        SELECT * INTO usage FROM device_platform.subscription_usage(NEW.organization_id);
        IF TG_TABLE_NAME='devices' AND usage.active_devices >= plan.max_devices THEN
          RAISE EXCEPTION 'Organization device limit reached'
            USING ERRCODE='23514', CONSTRAINT='subscription_device_limit';
        ELSIF TG_TABLE_NAME='organization_memberships' AND
          usage.active_users+usage.pending_invitations >= plan.max_users THEN
          RAISE EXCEPTION 'Organization user limit reached'
            USING ERRCODE='23514', CONSTRAINT='subscription_user_limit';
        END IF;
      END IF;
      RETURN NEW;
    END $$;

    -- Reuse the existing administration lock/order and READ COMMITTED requirement.
    -- Statement triggers acquire it before row locks, including for direct SQL writes.
    CREATE TRIGGER subscription_lock BEFORE INSERT OR UPDATE OR DELETE
      ON device_platform.subscription_plans FOR EACH STATEMENT
      EXECUTE FUNCTION device_platform.lock_admin_changes();
    CREATE TRIGGER subscription_lock BEFORE UPDATE OF subscription_plan_id
      ON device_platform.organizations FOR EACH STATEMENT
      EXECUTE FUNCTION device_platform.lock_admin_changes();
    CREATE TRIGGER subscription_lock BEFORE INSERT OR DELETE OR UPDATE OF is_active
      ON device_platform.devices FOR EACH STATEMENT
      EXECUTE FUNCTION device_platform.lock_admin_changes();
    -- Resending an expired invitation reserves capacity again.
    CREATE TRIGGER subscription_lock BEFORE UPDATE OF invitation_expires_at
      ON device_platform.organization_memberships FOR EACH STATEMENT
      EXECUTE FUNCTION device_platform.lock_admin_changes();

    CREATE TRIGGER context_immutable BEFORE UPDATE ON device_platform.subscription_plans
      FOR EACH ROW EXECUTE FUNCTION device_platform.protect_context('id','code','created_at');
    CREATE TRIGGER subscription_plan_guard BEFORE UPDATE ON device_platform.subscription_plans
      FOR EACH ROW EXECUTE FUNCTION device_platform.guard_subscription_plan();
    CREATE TRIGGER organization_subscription_guard BEFORE INSERT OR UPDATE
      ON device_platform.organizations FOR EACH ROW
      EXECUTE FUNCTION device_platform.guard_organization_subscription();
    CREATE TRIGGER subscription_capacity BEFORE INSERT OR UPDATE OF is_active
      ON device_platform.devices FOR EACH ROW
      EXECUTE FUNCTION device_platform.guard_subscription_capacity();
    CREATE TRIGGER subscription_capacity BEFORE INSERT OR UPDATE OF is_active, invitation_status, invitation_expires_at
      ON device_platform.organization_memberships FOR EACH ROW
      EXECUTE FUNCTION device_platform.guard_subscription_capacity();

    REVOKE EXECUTE ON FUNCTION device_platform.subscription_usage(uuid),
      device_platform.guard_subscription_plan(), device_platform.guard_organization_subscription(),
      device_platform.guard_subscription_capacity() FROM PUBLIC;
    COMMENT ON TABLE device_platform.subscription_plans IS
      'Editable Standard/Advanced commercial metadata and organization capacity; no payment processing.';
    COMMENT ON COLUMN device_platform.subscription_plans.billing_period IS
      'Unspecified until commercial terms are confirmed; does not schedule charges or expiry.';
    COMMENT ON COLUMN device_platform.organizations.subscription_plan_id IS
      'Required plan. Existing organizations adopt Standard without removing existing records.';
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Subscription assignments require an explicit reviewed forward migration or restore")
