"""Apply confirmed capacity defaults without deleting records or overriding custom caps."""

from alembic import op

revision = "0006_confirmed_plan_limits"
down_revision = "0005_subscriptions"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    -- Serialize with all capacity mutations before acquiring the plan table lock.
    SELECT id FROM device_platform.platform_settings WHERE id=1 FOR UPDATE;
    -- Existing organizations may exceed the confirmed device allowance. Preserve
    -- their records, just as baseline adoption does; subsequent additions are guarded.
    -- Only this owner's transactional migration can suspend the plan edit guard.
    ALTER TABLE device_platform.subscription_plans DISABLE TRIGGER subscription_plan_guard;
    UPDATE device_platform.subscription_plans
      SET max_users=CASE code WHEN 'standard' THEN 200 ELSE 500 END,
          max_devices=CASE code WHEN 'standard' THEN 1 ELSE 3 END,
          configuration_version=configuration_version+1,
          updated_at=clock_timestamp()
      WHERE (code='standard' AND max_users=25 AND max_devices=10)
         OR (code='advanced' AND max_users=100 AND max_devices=50);
    ALTER TABLE device_platform.subscription_plans ENABLE TRIGGER subscription_plan_guard;
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Plan limits require an explicit reviewed forward migration or restore")
