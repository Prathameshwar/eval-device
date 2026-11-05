"""Manual subscription dates and status; tracking only, no processing gates."""

from alembic import op

revision = "0025_manual_subscriptions"
down_revision = "0024_conversation_languages"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute("""
    ALTER TABLE device_platform.organizations
      ADD COLUMN subscription_status text NOT NULL DEFAULT 'active'
        CHECK (subscription_status IN ('active','suspended','cancelled')),
      ADD COLUMN subscription_starts_at timestamptz,
      ADD COLUMN subscription_ends_at timestamptz,
      ADD COLUMN subscription_reference text CHECK (length(subscription_reference) <= 256),
      ADD COLUMN subscription_notes text CHECK (length(subscription_notes) <= 2000),
      ADD COLUMN subscription_version integer NOT NULL DEFAULT 1 CHECK (subscription_version > 0),
      ADD CONSTRAINT subscription_dates_valid CHECK (
        (subscription_starts_at IS NULL OR isfinite(subscription_starts_at)) AND
        (subscription_ends_at IS NULL OR isfinite(subscription_ends_at)) AND
        (subscription_starts_at IS NULL OR subscription_ends_at IS NULL
          OR subscription_ends_at > subscription_starts_at));
    CREATE FUNCTION device_platform.guard_manual_subscription() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.subscription_version <> 1 THEN
          RAISE EXCEPTION 'Subscription version starts at one' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      IF NEW.subscription_version IS DISTINCT FROM OLD.subscription_version THEN
        RAISE EXCEPTION 'Subscription version is maintained by the database' USING ERRCODE='23514';
      END IF;
      IF ROW(NEW.subscription_plan_id,NEW.subscription_status,NEW.subscription_starts_at,
             NEW.subscription_ends_at,NEW.subscription_reference,NEW.subscription_notes)
         IS DISTINCT FROM
         ROW(OLD.subscription_plan_id,OLD.subscription_status,OLD.subscription_starts_at,
             OLD.subscription_ends_at,OLD.subscription_reference,OLD.subscription_notes) THEN
        NEW.subscription_version := OLD.subscription_version+1;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER manual_subscription_version BEFORE INSERT OR UPDATE
      ON device_platform.organizations FOR EACH ROW EXECUTE FUNCTION device_platform.guard_manual_subscription();
    REVOKE ALL ON FUNCTION device_platform.guard_manual_subscription() FROM PUBLIC;
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration; subscription records must be preserved.")
