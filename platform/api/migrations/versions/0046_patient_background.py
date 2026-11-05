"""Optional reviewed patient background without rewriting existing scenarios."""

from alembic import op
from psycopg import sql

revision = "0046_patient_background"
down_revision = "0045_session_archives"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION device_platform.valid_patient_background(value jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,device_platform AS $$
    DECLARE item jsonb; choice jsonb; ids text[] := '{}'; choice_ids text[];
    BEGIN
      IF value IS NULL THEN RETURN true; END IF;
      IF jsonb_typeof(value) <> 'array' OR jsonb_array_length(value)>5 THEN RETURN false; END IF;
      FOR item IN SELECT * FROM jsonb_array_elements(value) LOOP
        IF jsonb_typeof(item)<>'object'
          OR item - ARRAY['id','text','allow_variation','choices'] <> '{}'::jsonb
          OR NOT (item->>'id'=ANY(ARRAY['food_drink','sleep_activity','work_home','personality','additional']))
          OR item->>'id'=ANY(ids) OR item->>'id' IS NULL
          OR NOT coalesce(valid_language_map(item->'text',240),false)
          OR (item ? 'allow_variation' AND jsonb_typeof(item->'allow_variation')<>'boolean')
        THEN RETURN false; END IF;
        ids := array_append(ids,item->>'id');
        IF item ? 'choices' THEN
          IF jsonb_typeof(item->'choices')<>'array' OR jsonb_array_length(item->'choices')>3
          THEN RETURN false; END IF;
        END IF;
        IF item->'allow_variation'='true'::jsonb
          AND coalesce(jsonb_array_length(item->'choices'),0)=0 THEN RETURN false; END IF;
        choice_ids := '{}';
        FOR choice IN SELECT * FROM jsonb_array_elements(coalesce(item->'choices','[]'::jsonb)) LOOP
          IF jsonb_typeof(choice)<>'object' OR choice - ARRAY['id','text'] <> '{}'::jsonb
            OR choice->>'id' IS NULL OR choice->>'id' !~ '^[a-z][a-z0-9_]{0,39}$'
            OR choice->>'id'=ANY(choice_ids)
            OR NOT coalesce(valid_language_map(choice->'text',160),false)
          THEN RETURN false; END IF;
          choice_ids := array_append(choice_ids,choice->>'id');
        END LOOP;
      END LOOP;
      RETURN true;
    END $$;
    REVOKE ALL ON FUNCTION device_platform.valid_patient_background(jsonb) FROM PUBLIC;
    ALTER TABLE device_platform.training_scenario_drafts
      DROP CONSTRAINT training_scenario_drafts_schema_version_check,
      ADD CONSTRAINT training_scenario_drafts_schema_version_check CHECK(schema_version IN (4,5));
    """)
    connection = op.get_bind().connection.driver_connection
    tables = {
        "patient_case_templates": "patient_case_templates_document_check",
        "organization_case_templates": None,
        "training_scenario_drafts": "training_draft_document",
        "training_scenarios": "training_scenarios_document_check",
        "patient_practice_selections": "patient_practice_selections_document_check",
    }
    for table, constraint in tables.items():
        if constraint is None:
            found = connection.execute("""SELECT conname FROM pg_constraint
                WHERE conrelid='device_platform.organization_case_templates'::regclass
                  AND contype='c' AND pg_get_constraintdef(oid) LIKE '%%octet_length%%'
                  AND pg_get_constraintdef(oid) LIKE '%%document%%'""").fetchall()
            if len(found) != 1:
                raise RuntimeError("Unexpected tenant document constraints")
            constraint = found[0][0]
        check = """(jsonb_typeof(document)='object' AND octet_length(document::text)<=524288
          AND document->'version' IN ('4'::jsonb,'5'::jsonb)
          AND document - ARRAY['version','code','title','learner_label','specialty','source_language',
            'patient','presentation','history','vitals','localizations','background'] = '{}'::jsonb
          AND (document->'version'='5'::jsonb OR NOT document ? 'background')
          AND device_platform.valid_patient_background(document->'background')
          AND NOT jsonb_path_exists(document,'$.presentation.symptoms[*].disclosure')
          AND NOT jsonb_path_exists(document,'$.history.*.disclosure')
          AND (coalesce(nullif(document->'vitals','null'::jsonb),'{}'::jsonb) - ARRAY[
            'temperature_c','heart_rate_bpm','pulse_bpm','systolic_mmhg','diastolic_mmhg',
            'respirations_per_minute','spo2_percent','pain_0_10'])='{}'::jsonb"""
        if table in {"patient_case_templates", "organization_case_templates"}:
            check += " AND document->>'code'=code AND document->>'title'=title"
        elif table == "training_scenario_drafts":
            check += " AND document->'version'=to_jsonb(schema_version) AND document->>'code'=code"
        check += ") IS TRUE"
        connection.execute(
            sql.SQL("ALTER TABLE device_platform.{} DROP CONSTRAINT {}, ADD CONSTRAINT {} CHECK ({})").format(
                sql.Identifier(table), sql.Identifier(constraint), sql.Identifier(constraint), sql.SQL(check)
            )
        )


def downgrade():
    raise RuntimeError("Preserve reviewed background; use a forward migration or restore a backup")
