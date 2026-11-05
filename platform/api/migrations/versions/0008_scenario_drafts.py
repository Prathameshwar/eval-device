"""Editable authoring drafts and immutable publication provenance; no API workflow."""

from alembic import op

revision = "0008_scenario_drafts"
down_revision = "0007_training_pilot"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().connection.driver_connection.execute(
        """
    CREATE TABLE device_platform.training_scenario_drafts (
      id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
      request_key uuid NOT NULL,
      request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
      code text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]{0,39}$'),
      schema_version smallint NOT NULL CHECK (schema_version IN (1,2)),
      document jsonb NOT NULL,
      revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
      source_scenario_id uuid,
      created_by uuid NOT NULL REFERENCES device_platform.users(id),
      updated_by uuid NOT NULL REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      is_archived boolean NOT NULL DEFAULT false,
      UNIQUE (organization_id,id),
      UNIQUE (organization_id,code),
      UNIQUE (organization_id,request_key),
      FOREIGN KEY (organization_id,source_scenario_id)
        REFERENCES device_platform.training_scenarios(organization_id,id),
      CONSTRAINT training_draft_document CHECK (
        COALESCE(jsonb_typeof(document)='object'
          AND octet_length(document::text)<=65536
          AND document->'version'=to_jsonb(schema_version)
          AND document->'code'=to_jsonb(code), false)),
      CHECK (updated_at >= created_at)
    );
    CREATE INDEX training_draft_org_updated
      ON device_platform.training_scenario_drafts(organization_id,updated_at DESC,id);

    ALTER TABLE device_platform.training_scenarios
      ADD COLUMN source_draft_id uuid,
      ADD COLUMN source_draft_revision integer,
      ADD CONSTRAINT training_scenario_draft_pair CHECK (
        (source_draft_id IS NULL AND source_draft_revision IS NULL) OR
        (source_draft_id IS NOT NULL AND source_draft_revision IS NOT NULL AND source_draft_revision > 0)),
      ADD CONSTRAINT training_scenario_draft_fk FOREIGN KEY (organization_id,source_draft_id)
        REFERENCES device_platform.training_scenario_drafts(organization_id,id),
      ADD CONSTRAINT training_scenario_draft_once
        UNIQUE (organization_id,source_draft_id,source_draft_revision);

    CREATE FUNCTION device_platform.training_draft_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        -- The quota relies on a fresh snapshot after this serialization lock.
        IF current_setting('transaction_isolation') <> 'read committed' THEN
          RAISE EXCEPTION 'Draft creation requires READ COMMITTED' USING ERRCODE='25000';
        END IF;
        PERFORM 1 FROM device_platform.organizations WHERE id=NEW.organization_id FOR UPDATE;
        IF (SELECT count(*) FROM device_platform.training_scenario_drafts
            WHERE organization_id=NEW.organization_id)>=100 THEN
          RAISE EXCEPTION 'Draft capacity reached'
            USING ERRCODE='23514', CONSTRAINT='training_draft_capacity';
        END IF;
        IF NEW.revision <> 1 OR NEW.created_by IS DISTINCT FROM NEW.updated_by THEN
          RAISE EXCEPTION 'Invalid initial draft revision or editor'
            USING ERRCODE='23514', CONSTRAINT='training_draft_initial';
        END IF;
        NEW.created_at := clock_timestamp();
        NEW.updated_at := NEW.created_at;
      ELSE
        IF ROW(NEW.id,NEW.organization_id,NEW.code,NEW.request_key,NEW.request_fingerprint,
               NEW.source_scenario_id,NEW.created_by,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.code,OLD.request_key,OLD.request_fingerprint,
               OLD.source_scenario_id,OLD.created_by,OLD.created_at) THEN
          RAISE EXCEPTION 'Immutable draft identity'
            USING ERRCODE='23514', CONSTRAINT='training_draft_identity';
        END IF;
        -- The caller must submit its expected revision; the database advances it.
        IF NEW.revision IS DISTINCT FROM OLD.revision THEN
          RAISE EXCEPTION 'Stale draft revision'
            USING ERRCODE='40001', CONSTRAINT='training_draft_revision';
        END IF;
        IF OLD.is_archived AND NEW.document IS DISTINCT FROM OLD.document THEN
          RAISE EXCEPTION 'Restore the archived draft before editing'
            USING ERRCODE='23514', CONSTRAINT='training_draft_archived';
        END IF;
        NEW.revision := OLD.revision + 1;
        NEW.updated_at := greatest(clock_timestamp(),OLD.updated_at);
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER training_draft_guard BEFORE INSERT OR UPDATE
      ON device_platform.training_scenario_drafts
      FOR EACH ROW EXECUTE FUNCTION device_platform.training_draft_guard();

    CREATE FUNCTION device_platform.training_scenario_source_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    DECLARE draft device_platform.training_scenario_drafts%ROWTYPE;
    BEGIN
      IF NEW.source_draft_id IS NULL THEN RETURN NEW; END IF;
      -- training_scenario_guard acquires the organization lock before this trigger.
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Draft publication requires READ COMMITTED' USING ERRCODE='25000';
      END IF;
      SELECT * INTO draft FROM device_platform.training_scenario_drafts
        WHERE organization_id=NEW.organization_id AND id=NEW.source_draft_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'Draft unavailable' USING ERRCODE='23503', CONSTRAINT='training_scenario_draft_fk';
      END IF;
      IF draft.is_archived OR draft.code IS DISTINCT FROM NEW.code
        OR draft.revision IS DISTINCT FROM NEW.source_draft_revision
        OR draft.document IS DISTINCT FROM NEW.document
        OR NEW.approved_at IS NULL OR NEW.approved_by IS NULL OR NEW.approval IS NULL THEN
        RAISE EXCEPTION 'Publication requires the current draft and explicit approval'
          USING ERRCODE='23514', CONSTRAINT='training_scenario_draft_snapshot';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER training_scenario_source_guard BEFORE INSERT
      ON device_platform.training_scenarios
      FOR EACH ROW EXECUTE FUNCTION device_platform.training_scenario_source_guard();
    REVOKE ALL ON device_platform.training_scenario_drafts FROM PUBLIC;
    REVOKE ALL ON FUNCTION device_platform.training_draft_guard(),
      device_platform.training_scenario_source_guard() FROM PUBLIC;
    COMMENT ON TABLE device_platform.training_scenario_drafts IS
      'Private incomplete authoring documents; not executable or clinically approved. API authorization and full schema validation required.';
    COMMENT ON COLUMN device_platform.training_scenario_drafts.request_fingerprint IS
      'Immutable fingerprint of the ORIGINAL create request, not of the mutable current document.';
    COMMENT ON COLUMN device_platform.training_scenario_drafts.revision IS
      'Optimistic editing revision; UPDATE with expected revision in WHERE and SET revision, database increments once.';
    COMMENT ON COLUMN device_platform.training_scenarios.source_draft_revision IS
      'Draft revision captured at publication; immutable provenance, not a reference to the current draft revision.';
    """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Scenario authoring data requires a reviewed forward migration or restore")
