"""Record tenant case snapshot provenance on scenario drafts."""

from alembic import op

revision = "0031_case_draft_provenance"
down_revision = "0030_clinical_capabilities"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE device_platform.training_scenario_drafts
      ADD COLUMN source_case_id uuid,
      ADD COLUMN source_case_revision integer,
      ADD COLUMN content_updated_by uuid REFERENCES device_platform.users(id),
      ADD CONSTRAINT training_draft_case_pair CHECK (
        (source_case_id IS NULL AND source_case_revision IS NULL) OR
        (source_case_id IS NOT NULL AND source_case_revision > 0)),
      ADD CONSTRAINT training_draft_case_fk FOREIGN KEY (organization_id,source_case_id)
        REFERENCES device_platform.organization_case_templates(organization_id,id),
      ADD CONSTRAINT training_draft_one_source CHECK (
        source_scenario_id IS NULL OR source_case_id IS NULL);
    UPDATE device_platform.training_scenario_drafts SET content_updated_by=updated_by;
    ALTER TABLE device_platform.training_scenario_drafts
      ALTER COLUMN content_updated_by SET NOT NULL;
    CREATE OR REPLACE FUNCTION device_platform.training_draft_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, device_platform AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        NEW.content_updated_by := COALESCE(NEW.content_updated_by, NEW.created_by);
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
               NEW.source_scenario_id,NEW.source_case_id,NEW.created_by,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.code,OLD.request_key,
               OLD.request_fingerprint,OLD.source_scenario_id,OLD.source_case_id,
               OLD.created_by,OLD.created_at) THEN
          RAISE EXCEPTION 'Immutable draft identity'
            USING ERRCODE='23514', CONSTRAINT='training_draft_identity';
        END IF;
        IF NEW.document IS NOT DISTINCT FROM OLD.document AND
           NEW.content_updated_by IS DISTINCT FROM OLD.content_updated_by THEN
          RAISE EXCEPTION 'Content author changed without content edit'
            USING ERRCODE='23514', CONSTRAINT='training_draft_content_author';
        END IF;
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
    COMMENT ON COLUMN device_platform.training_scenario_drafts.source_case_revision IS
      'Tenant case revision copied into the draft; explicit refresh is required after case edits.';
    """)


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore; case provenance must be preserved.")
