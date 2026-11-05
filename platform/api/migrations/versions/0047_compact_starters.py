"""Publish corrected compact starters; retain customized and historical documents."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from alembic import op
from psycopg.types.json import Jsonb
from training_contracts import fingerprint
from training_contracts.localized_cases import mark_practice_override

revision = "0047_compact_starters"
down_revision = "0046_patient_background"
branch_labels = None
depends_on = None


def body(document, *, practice=False):
    return {
        key: value
        for key, value in document.items()
        if key not in ({"localizations", "vitals"} if practice else {"localizations"})
    }


def audit(c, organization_id, entity_type, entity_id, details):
    c.execute(
        """INSERT INTO device_platform.activity_events
        (id,organization_id,actor_type,category,event_type,severity,entity_type,entity_id,
         occurred_at,received_at,details,expires_at)
        SELECT gen_random_uuid(),%s,'system','audit','platform.starters.corrected','info',%s,%s,
          now(),now(),%s,now()+least(coalesce((o.policy_settings->>'audit_retention_days')::integer,
            (p.default_organization_policy->>'audit_retention_days')::integer),
            (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
        FROM device_platform.platform_settings p
        LEFT JOIN device_platform.organizations o ON o.id=%s WHERE p.id=1""",
        (organization_id, entity_type, entity_id, Jsonb({"source": revision, **details}), organization_id),
    )


def upgrade():
    c = op.get_bind().connection.driver_connection
    # Serialize source matching, quota checks, defaults and assignment preservation.
    c.execute("""LOCK TABLE device_platform.organizations,
        device_platform.patient_case_templates, device_platform.organization_case_templates,
        device_platform.training_scenarios, device_platform.tenant_scenario_defaults,
        device_platform.patient_practice_selections, device_platform.patient_conversations,
        device_platform.practice_sessions, device_platform.training_sessions
        IN SHARE ROW EXCLUSIVE MODE""")
    c.execute("DROP INDEX device_platform.training_scenario_system_starter_unique")
    c.execute("""CREATE UNIQUE INDEX training_scenario_system_starter_unique
        ON device_platform.training_scenarios(organization_id,starter_case_id,version)
        WHERE publication_source='system_starter'""")
    # Only deployment-owner repair can advance immutable source provenance.
    c.execute(
        "ALTER TABLE device_platform.organization_case_templates DISABLE TRIGGER organization_case_templates_guard"
    )
    c.execute(
        "ALTER TABLE device_platform.patient_practice_selections DISABLE TRIGGER patient_selection_guard"
    )
    seeds = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
    for seed in seeds:
        source = c.execute(
            "SELECT revision,document FROM device_platform.patient_case_templates WHERE id=%s", (seed["id"],)
        ).fetchone()
        if source is None or source[0] != 4 or body(source[1]) != body(seed["previous"]):
            continue  # Never replace platform-authored changes with a bundled example.
        document = seed["document"]
        c.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s,revision=revision+1 WHERE id=%s",
            (Jsonb(document), seed["id"]),
        )
        audit(c, None, "patient_case", seed["id"], {"template_revision": 5})
        cases = c.execute(
            """SELECT t.id,t.organization_id,t.document FROM device_platform.organization_case_templates t
            JOIN device_platform.organization_patient_profiles p ON p.organization_id=t.organization_id AND p.id=t.patient_profile_id
            JOIN device_platform.organization_clinical_specialties s ON s.organization_id=t.organization_id AND s.id=t.specialty_id
            WHERE t.source_global_id=%s AND t.source_global_revision=4 AND t.archived_at IS NULL
              AND p.archived_at IS NULL AND s.archived_at IS NULL
              AND jsonb_build_object('name',p.name,'age_years',p.age_years,'sex',p.sex,'occupation',p.occupations,
                'height_cm',p.height_cm,'weight_kg',p.weight_kg)=t.document->'patient'
              AND s.name=t.document->>'specialty' ORDER BY t.organization_id,t.id""",
            (seed["id"],),
        ).fetchall()
        for case_id, org, old_case in cases:
            if body(old_case) != body(seed["previous"]):
                continue
            c.execute(
                """UPDATE device_platform.organization_case_templates
                SET document=%s,source_global_revision=5,revision=revision+1,updated_at=clock_timestamp()
                WHERE id=%s AND organization_id=%s""",
                (Jsonb(document), case_id, org),
            )
            audit(c, org, "cases", case_id, {"source_global_revision": 5})
            published = c.execute(
                """SELECT id,version,document,created_by,specialty_id FROM device_platform.training_scenarios
                WHERE organization_id=%s AND starter_case_id=%s AND publication_source='system_starter'
                  AND is_active ORDER BY version DESC LIMIT 1""",
                (org, case_id),
            ).fetchone()
            if not published or body(published[2]) != body(seed["previous"]):
                continue
            old_id, old_version, old_doc, creator, specialty = published
            latest, count = c.execute(
                """SELECT coalesce(max(version) FILTER (WHERE code=%s),0),count(*)
                FROM device_platform.training_scenarios WHERE organization_id=%s""",
                (document["code"], org),
            ).fetchone()
            if latest != old_version or count >= 100:
                audit(
                    c, org, "training_scenario", old_id, {"publication_skipped": "newer_version_or_capacity"}
                )
                continue
            new_id, new_version = uuid4(), old_version + 1
            publication = seed["publication"]
            c.execute(
                """INSERT INTO device_platform.training_scenarios
                (id,organization_id,request_key,code,version,document,fingerprint,created_by,approved_at,
                 publication_source,starter_case_id,specialty_id,is_active)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,now(),'system_starter',%s,%s,true)""",
                (
                    new_id,
                    org,
                    uuid4(),
                    document["code"],
                    new_version,
                    Jsonb(publication),
                    fingerprint(publication),
                    creator,
                    case_id,
                    specialty,
                ),
            )
            c.execute(
                """UPDATE device_platform.tenant_scenario_defaults
                SET scenario_id=%s,revision=revision+1 WHERE organization_id=%s AND scenario_id=%s""",
                (new_id, org, old_id),
            )
            # Preserve vitals overrides, but never change a selected or assigned live conversation.
            selections = c.execute(
                """SELECT p.id,p.document,p.language FROM device_platform.patient_practice_selections p
                WHERE p.organization_id=%s AND p.scenario_id=%s AND NOT EXISTS (
                  SELECT 1 FROM device_platform.patient_conversations x WHERE x.practice_id=p.id AND x.status='active')
                AND NOT EXISTS (SELECT 1 FROM device_platform.practice_sessions x
                  WHERE x.device_id=p.device_id AND x.status IN ('queued','active','stopping'))""",
                (org, old_id),
            ).fetchall()
            for practice_id, old_selection, language in selections:
                if body(old_selection, practice=True) != body(old_doc, practice=True):
                    continue
                selected = mark_practice_override(deepcopy(publication), language, old_selection["vitals"])
                c.execute(
                    """UPDATE device_platform.patient_practice_selections SET scenario_id=%s,
                    template_revision=%s,document=%s,revision=revision+1,updated_at=clock_timestamp()
                    WHERE id=%s AND organization_id=%s""",
                    (new_id, new_version, Jsonb(selected), practice_id, org),
                )
                audit(
                    c,
                    org,
                    "patient_practice",
                    practice_id,
                    {"scenario_id": str(new_id), "vitals_preserved": True},
                )
            # Older content remains immutable and accessible to historical records.
            # Keep it available if queued/live assignments or private choices still need it.
            c.execute(
                """UPDATE device_platform.training_scenarios SET is_active=false
                WHERE id=%s AND organization_id=%s AND NOT EXISTS (
                  SELECT 1 FROM device_platform.practice_sessions WHERE scenario_id=%s AND status IN ('queued','active','stopping'))
                AND NOT EXISTS (SELECT 1 FROM device_platform.training_sessions WHERE scenario_id=%s AND status IN ('authorized','active'))
                AND NOT EXISTS (SELECT 1 FROM device_platform.patient_conversations WHERE scenario_id=%s AND status='active')
                AND NOT EXISTS (SELECT 1 FROM device_platform.patient_practice_selections WHERE scenario_id=%s)""",
                (old_id, org, old_id, old_id, old_id, old_id),
            )
            audit(
                c,
                org,
                "training_scenario",
                new_id,
                {
                    "previous_scenario_id": str(old_id),
                    "version": new_version,
                    "publication_source": "system_starter",
                },
            )
    c.execute(
        "ALTER TABLE device_platform.patient_practice_selections ENABLE TRIGGER patient_selection_guard"
    )
    c.execute(
        "ALTER TABLE device_platform.organization_case_templates ENABLE TRIGGER organization_case_templates_guard"
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore; published history must be preserved")
