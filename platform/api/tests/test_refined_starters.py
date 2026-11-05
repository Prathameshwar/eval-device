"""Forward-only everyday fact refinement after live desktop evaluation."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb
from test_default_local_models import run_upgrade, upgrade_database  # noqa: F401
from training_contracts.localized_cases import (
    localization_ready,
    mark_system_starter_localization,
    prevent_review_forgery,
)
from training_contracts.scenarios import validate_publication

from pms_api.core.starter_cases import corrected_starter

SEEDS = json.loads(
    (Path(__file__).parents[1] / "migrations/versions/0048_refined_starters.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
def test_refined_starters_keep_clinical_facts_and_make_everyday_values_explicit(seed):
    document = seed["document"]
    assert validate_publication(document) == []
    assert document["localizations"] == {}
    assert prevent_review_forgery(document) == document
    assert all(localization_ready(seed["publication"], language) for language in ("en", "hi"))
    assert document["patient"] == seed["previous"]["patient"]
    assert document["presentation"] == seed["previous"]["presentation"]
    assert document["vitals"] == seed["previous"]["vitals"]
    assert {entry["id"] for entry in document["history"]["social"]["entries"]} == {
        "smoking",
        "alcohol",
        "household",
    }
    assert corrected_starter(UUID(seed["id"]), 6, document)
    assert not corrected_starter(UUID(seed["id"]), 5, seed["previous"])
    assert corrected_starter(UUID(seed["id"]), 5, seed["previous"], allow_previous=True)
    background = {entry["id"]: entry["text"]["en"] for entry in document["background"]}
    assert "eight hours" in background["sleep_activity"] and "five days" in background["work_home"]
    assert "yesterday" not in background["food_drink"]


def test_refinement_preserves_custom_global_and_is_repeatable(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0047_compact_starters")
    custom = deepcopy(SEEDS[0]["previous"])
    custom["background"][0]["text"]["en"] = "A platform-authored custom everyday detail."
    with psycopg.connect(target) as connection:
        connection.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s,revision=revision+1 WHERE id=%s",
            (Jsonb(custom), SEEDS[0]["id"]),
        )
    run_upgrade(target)
    with psycopg.connect(target) as connection:
        assert (
            connection.execute(
                "SELECT document FROM device_platform.patient_case_templates WHERE id=%s", (SEEDS[0]["id"],)
            ).fetchone()[0]
            == custom
        )
        assert connection.execute(
            "SELECT revision,document FROM device_platform.patient_case_templates WHERE id=%s",
            (SEEDS[1]["id"],),
        ).fetchone() == (6, SEEDS[1]["document"])
        before = connection.execute(
            "SELECT id,document,revision FROM device_platform.patient_case_templates ORDER BY id"
        ).fetchall()
    run_upgrade(target)
    with psycopg.connect(target) as connection:
        assert (
            connection.execute(
                "SELECT id,document,revision FROM device_platform.patient_case_templates ORDER BY id"
            ).fetchall()
            == before
        )


def test_fresh_tenant_provisions_refined_stock_and_preserves_its_publication(platform):
    h = platform
    token, _ = h.user("refined-tenant")
    org = h.organization(token)["id"]
    copies = h.sql(
        "SELECT source_global_revision,document FROM device_platform.organization_case_templates WHERE organization_id=%s ORDER BY document->>'code'",
        (org,),
    )
    assert len(copies) == 2 and all(revision == 6 for revision, _ in copies)
    assert {document["code"] for _, document in copies} == {seed["document"]["code"] for seed in SEEDS}
    pubs = h.sql(
        "SELECT version,document FROM device_platform.training_scenarios WHERE organization_id=%s", (org,)
    )
    assert len(pubs) == 2 and all(version == 1 for version, _ in pubs)


def test_upgrade_matches_stock_tenant_and_preserves_all_original_publications(platform):
    h = platform
    token, _ = h.user("refined-existing-tenant")
    org = h.organization(token)["id"]
    with psycopg.connect(h.dsn) as c:
        for table, trigger in (
            ("patient_case_templates", "patient_case_guard"),
            ("organization_case_templates", "organization_case_templates_guard"),
            ("training_scenarios", "training_scenario_guard"),
        ):
            c.execute(f"ALTER TABLE device_platform.{table} DISABLE TRIGGER {trigger}")
        for seed in SEEDS:
            published = seed["previous"]
            for language in ("en", "hi"):
                published = mark_system_starter_localization(published, language)
            c.execute(
                "UPDATE device_platform.patient_case_templates SET revision=5,document=%s WHERE id=%s",
                (Jsonb(seed["previous"]), seed["id"]),
            )
            c.execute(
                "UPDATE device_platform.organization_case_templates SET source_global_revision=5,document=%s WHERE organization_id=%s AND source_global_id=%s",
                (Jsonb(seed["previous"]), org, seed["id"]),
            )
            c.execute(
                "UPDATE device_platform.training_scenarios SET document=%s WHERE organization_id=%s AND code=%s",
                (Jsonb(published), org, seed["previous"]["code"]),
            )
        for table, trigger in (
            ("training_scenarios", "training_scenario_guard"),
            ("organization_case_templates", "organization_case_templates_guard"),
            ("patient_case_templates", "patient_case_guard"),
        ):
            c.execute(f"ALTER TABLE device_platform.{table} ENABLE TRIGGER {trigger}")
    before = h.sql(
        "SELECT id,document FROM device_platform.training_scenarios WHERE organization_id=%s ORDER BY id",
        (org,),
    )
    h.sql("UPDATE public.alembic_version SET version_num='0047_compact_starters'")
    run_upgrade(h.dsn)
    assert (
        h.sql(
            "SELECT id,document FROM device_platform.training_scenarios WHERE organization_id=%s AND version=1 ORDER BY id",
            (org,),
        )
        == before
    )
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s AND version=2 AND is_active",
        (org,),
    ) == [(2,)]
    assert h.sql(
        "SELECT count(*) FROM pg_trigger WHERE tgrelid IN ('device_platform.organization_case_templates'::regclass,'device_platform.patient_practice_selections'::regclass) AND tgenabled='D'"
    ) == [(0,)]
