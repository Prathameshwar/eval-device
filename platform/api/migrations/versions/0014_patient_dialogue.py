"""Everyday-question topics and non-clinical spoken replies for the seeded practice cases.

Rewrites the nine synthetic case documents produced by `scripts/build_patient_dialogue.py`:
ten added everyday topics, wider routing intents and authored backchannel/command/boundary
replies. Saved practice selections keep their own snapshot until a user resaves the setup.
"""

import json
from pathlib import Path

from alembic import op
from psycopg.types.json import Jsonb

revision = "0014_patient_dialogue"
down_revision = "0013_patient_practice"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind().connection.driver_connection
    rows = json.loads(
        Path(__file__).with_name("0014_patient_case_templates.json").read_text(encoding="utf-8")
    )
    for row in rows:
        c.execute(
            """WITH updated AS (
              UPDATE device_platform.patient_case_templates
                 SET document=%s, revision=revision+1
               WHERE code=%s AND is_synthetic RETURNING id,code,revision
            )
            INSERT INTO device_platform.activity_events
              (id,actor_type,category,event_type,severity,entity_type,entity_id,occurred_at,received_at,details,expires_at)
            SELECT gen_random_uuid(),'system','audit','platform.patient_case.dialogue_expanded','info','patient_case',
              u.id,now(),now(),
              jsonb_build_object('actor_role','system','scope','platform','source','migration',
                'revision','0014_patient_dialogue','case_code',u.code,'template_revision',u.revision),
              now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
                           (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
            FROM updated u CROSS JOIN device_platform.platform_settings p WHERE p.id=1""",
            (Jsonb(row["document"]), row["code"]),
            prepare=False,
        )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore to preserve case documents")
