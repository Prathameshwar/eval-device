"""Keep only presentation, symptoms, history and vitals in authored cases."""

from alembic import op
from psycopg import sql
from psycopg.types.json import Jsonb
from training_contracts import fingerprint
from training_contracts.clinical_cases import ScenarioDraftV4, simplify_case
from training_contracts.localized_cases import language_document, localization_ready

revision = "0041_simple_clinical_cases"
down_revision = "0040_device_unique_ids"
branch_labels = None
depends_on = None

TABLES = {
    "patient_case_templates": ("patient_case_guard", "patient_case_templates_document_check"),
    "organization_case_templates": (
        "organization_case_templates_guard",
        "organization_case_templates_document_check",
    ),
    "training_scenario_drafts": ("training_draft_guard", "training_draft_document"),
    "training_scenarios": ("training_scenario_guard", "training_scenarios_document_check"),
    "patient_practice_selections": ("patient_selection_guard", "patient_practice_selections_document_check"),
}


def converted(document):
    result = simplify_case(document)
    case = ScenarioDraftV4.model_validate(result)
    # Only carry existing, current approvals through a structural removal.
    # No new clinical content or translations are approved by this migration.
    if document.get("version") == 3:
        for language, stamp in document.get("localizations", {}).items():
            if localization_ready(document, language):
                result["localizations"][language] = {
                    **stamp,
                    "revision": stamp["revision"] + 1,
                    "source_hash": fingerprint(language_document(case, case.source_language)),
                    "content_hash": fingerprint(language_document(case, language)),
                }
    return result


def upgrade():
    c = op.get_bind().connection.driver_connection
    for table, (trigger, constraint) in TABLES.items():
        if table == "organization_case_templates":
            constraints = c.execute("""SELECT conname FROM pg_constraint
                WHERE conrelid='device_platform.organization_case_templates'::regclass AND contype='c'
                AND pg_get_constraintdef(oid) LIKE '%%octet_length%%'
                AND pg_get_constraintdef(oid) LIKE '%%document%%'""").fetchall()
            if len(constraints) != 1:
                raise RuntimeError("Unexpected tenant case document constraints")
            constraint = constraints[0][0]
        c.execute(
            sql.SQL("ALTER TABLE device_platform.{} DISABLE TRIGGER {}, DROP CONSTRAINT {}").format(
                sql.Identifier(table), sql.Identifier(trigger), sql.Identifier(constraint)
            )
        )
    c.execute(
        "ALTER TABLE device_platform.training_scenario_drafts DROP CONSTRAINT training_scenario_drafts_schema_version_check"
    )
    for table in TABLES:
        rows = c.execute(
            sql.SQL("SELECT id,document FROM device_platform.{} FOR UPDATE").format(sql.Identifier(table))
        ).fetchall()
        for record_id, document in rows:
            value = converted(document)
            extra = ""
            parameters = [Jsonb(value)]
            if table == "training_scenarios":
                extra = ", fingerprint=%s"
                parameters.append(fingerprint(value))
            else:
                extra = ", revision=revision+1, updated_at=now()"
            if table == "training_scenario_drafts":
                extra += ", schema_version=4, workflow_version=2, submitted_revision=NULL, submitted_at=NULL"
            parameters.append(record_id)
            c.execute(
                sql.SQL("UPDATE device_platform.{} SET document=%s" + extra + " WHERE id=%s").format(
                    sql.Identifier(table)
                ),
                parameters,
            )

        # Constrain writes at the database boundary as well as the API.
        check = """(jsonb_typeof(document)='object' AND octet_length(document::text)<=524288
          AND document->'version'='4'::jsonb
          AND document - ARRAY['version','code','title','learner_label','specialty','source_language',
            'patient','presentation','history','vitals','localizations'] = '{}'::jsonb
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
        trigger, constraint = TABLES[table]
        c.execute(
            sql.SQL("ALTER TABLE device_platform.{} ADD CONSTRAINT {} CHECK ({}), ENABLE TRIGGER {}").format(
                sql.Identifier(table), sql.Identifier(constraint), sql.SQL(check), sql.Identifier(trigger)
            )
        )
    c.execute(
        "ALTER TABLE device_platform.training_scenario_drafts ADD CONSTRAINT training_scenario_drafts_schema_version_check CHECK(schema_version=4)"
    )
    # Historical prompts contain compiled Q&A facts, without recoverable source
    # boundaries. Remove the prompt, retaining the transcript and provenance.
    # Close active contexts so no client can continue with a removed snapshot.
    c.execute(
        """
      ALTER TABLE device_platform.patient_conversations DISABLE TRIGGER patient_conversation_guard;
      UPDATE device_platform.patient_conversations
        SET snapshot=(snapshot-'system') || '{"scenario_context_removed":true}'::jsonb,
            status='closed',closed_at=coalesce(closed_at,now());
      ALTER TABLE device_platform.patient_conversations ENABLE TRIGGER patient_conversation_guard;
    """,
        prepare=False,
    )
    c.execute("""
      INSERT INTO device_platform.activity_events
        (id,actor_type,category,event_type,severity,entity_type,occurred_at,received_at,details,expires_at)
      SELECT gen_random_uuid(),'system','audit','platform.scenarios.simplified','info','platform',now(),now(),
        '{"source":"0041_simple_clinical_cases","schema_version":4,"historical_scenario_contexts_removed":true}'::jsonb,
        now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
          (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
      FROM device_platform.platform_settings p WHERE id=1
    """)


def downgrade():
    raise RuntimeError("Restore a backup; removed scenario authoring sections cannot be reconstructed")
