"""Durable session archives and resumable private recording parts."""

from alembic import op

revision = "0045_session_archives"
down_revision = "0044_session_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE device_platform.session_archives (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, department_id uuid,
      device_id uuid NOT NULL, learner_id uuid REFERENCES device_platform.users(id),
      assigned_session_id uuid,
      scenario_id uuid NOT NULL, scenario_title text NOT NULL, language text NOT NULL,
      execution text NOT NULL CHECK(execution IN ('caller','platform')),
      practice_snapshot jsonb NOT NULL, context jsonb NOT NULL,
      created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
      media_expires_at timestamptz NOT NULL, upload_until timestamptz NOT NULL,
      manifest jsonb, finalized_at timestamptz,
      UNIQUE(organization_id,id),
      FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id),
      FOREIGN KEY(organization_id,device_id,assigned_session_id) REFERENCES device_platform.practice_sessions(organization_id,device_id,id),
      FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
      FOREIGN KEY(organization_id,scenario_id) REFERENCES device_platform.training_scenarios(organization_id,id),
      CHECK(created_at < upload_until AND upload_until <= expires_at),
      CHECK(media_expires_at <= expires_at)
    );
    CREATE INDEX session_archive_scope ON device_platform.session_archives(organization_id,department_id,created_at DESC,id);
    CREATE INDEX session_archive_learner ON device_platform.session_archives(organization_id,learner_id,created_at DESC,id);
    CREATE INDEX session_archive_expiry ON device_platform.session_archives(expires_at);
    CREATE TABLE device_platform.session_archive_items (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, archive_id uuid NOT NULL,
      kind text NOT NULL CHECK(kind IN ('turn','microphone','patient_audio','video')),
      byte_size bigint NOT NULL CHECK(byte_size BETWEEN 1 AND 268435456),
      metadata jsonb NOT NULL, received jsonb NOT NULL DEFAULT '[]', purged boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
      FOREIGN KEY(organization_id,archive_id) REFERENCES device_platform.session_archives(organization_id,id) ON DELETE CASCADE
    );
    CREATE INDEX session_archive_item_parent ON device_platform.session_archive_items(archive_id);
    CREATE INDEX session_archive_item_capacity ON device_platform.session_archive_items(organization_id) WHERE NOT purged;
    CREATE INDEX session_archive_item_expiry ON device_platform.session_archive_items(expires_at);
    CREATE FUNCTION device_platform.session_archive_guard() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,device_platform AS $$
    BEGIN
      IF TG_TABLE_NAME='session_archives' THEN
        IF (to_jsonb(NEW)-'manifest'-'finalized_at') IS DISTINCT FROM (to_jsonb(OLD)-'manifest'-'finalized_at')
           OR (OLD.manifest IS NOT NULL AND NEW IS DISTINCT FROM OLD) THEN
          RAISE EXCEPTION 'Archive identity and final manifest are immutable' USING ERRCODE='23514';
        END IF;
      ELSIF (to_jsonb(NEW)-'received'-'purged') IS DISTINCT FROM (to_jsonb(OLD)-'received'-'purged') OR (OLD.purged AND NOT NEW.purged) THEN
        RAISE EXCEPTION 'Recording metadata is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    REVOKE ALL ON FUNCTION device_platform.session_archive_guard(), device_platform.practice_session_guard() FROM PUBLIC;
    CREATE TRIGGER session_archive_guard BEFORE UPDATE ON device_platform.session_archives
      FOR EACH ROW EXECUTE FUNCTION device_platform.session_archive_guard();
    CREATE TRIGGER session_archive_item_guard BEFORE UPDATE ON device_platform.session_archive_items
      FOR EACH ROW EXECUTE FUNCTION device_platform.session_archive_guard();
    """)


def downgrade():
    raise RuntimeError("Restore a backup or use a reviewed forward migration")
