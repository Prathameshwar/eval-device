"""Background disclosure, localization, stable choices and compact clinical context."""

from copy import deepcopy
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from scenario_samples import example
from test_default_local_models import run_upgrade, upgrade_database  # noqa: F401
from test_scenario_library import library as library
from test_scenario_library import publication
from training_contracts.clinical_cases import ClinicalRuntime, ScenarioDraftV5, simplify_case
from training_contracts.conversation.background import session_background
from training_contracts.conversation.prompt import conversation_context
from training_contracts.localized_cases import localization_ready, review_localization
from training_contracts.scenarios import parse_draft, patient_preview


def background_case():
    case = simplify_case(example())
    case.update(
        version=5,
        background=[
            {
                "id": "food_drink",
                "text": {"en": "Home-cooked meals.", "hi": "घर का खाना।"},
                "allow_variation": True,
                "choices": [
                    {"id": "rice", "text": {"en": "Rice and vegetables.", "hi": "चावल और सब्ज़ी।"}},
                    {"id": "bread", "text": {"en": "Bread and vegetables.", "hi": "रोटी और सब्ज़ी।"}},
                ],
            }
        ],
    )
    for language in ("en", "hi"):
        case = review_localization(case, language)
    return case


def test_background_survives_runtime_and_preview_and_choice_is_stable():
    case = background_case()
    assert ClinicalRuntime(case=parse_draft(case)).case.version == 5
    assert patient_preview(case)["background"] == case["background"]
    first = session_background(case, "en", "conversation-one")
    assert first == session_background(case, "en", "conversation-one")
    reordered = deepcopy(case)
    reordered["background"][0]["choices"].reverse()
    assert first == session_background(reordered, "en", "conversation-one")
    assert first[0]["detail"] in ("Rice and vegetables.", "Bread and vegetables.")
    assert first[0]["provenance"] == "author_approved_choice"


def test_background_edits_invalidate_review_and_cannot_forge_choices():
    case = background_case()
    case["background"][0]["choices"][0]["text"]["en"] = "Changed meal."
    assert not localization_ready(case, "en")
    with pytest.raises(ValueError, match="stale"):
        conversation_context(case, "en", "What did you eat?")


def test_variation_permission_alone_invalidates_both_language_reviews():
    case = background_case()
    case["background"][0]["allow_variation"] = False
    assert not localization_ready(case, "en") and not localization_ready(case, "hi")


@pytest.mark.parametrize(
    "patch",
    [
        {"choices": []},
        {"text": {"en": "x" * 241}},
        {"id": "medications"},
        {"allow_variation": "true"},
    ],
)
def test_invalid_background_rejected(patch):
    case = background_case()
    case["background"][0].update(patch)
    with pytest.raises(ValidationError):
        ScenarioDraftV5.model_validate(case)


def test_compact_prompt_preserves_clinical_facts_with_literal_source_selection():
    case = background_case()
    context = conversation_context(case, "en", "Yesterday?", seed="stable-id")
    assert context["session_background"] == session_background(case, "en", "stable-id")
    assert "Rice and vegetables." in context["system"] or "Bread and vegetables." in context["system"]
    assert case["presentation"]["chief_complaint"]["en"] in context["system"]
    assert "Missing information is unknown, never no" in context["system"]
    assert not any(fact["text"] == "unknown" for fact in context["fact_sources"].values())
    assert "Current medicines do not establish past treatments" in context["system"]
    assert context["reply_format"] == "fact-selection-v1"
    assert "Output only a JSON array" in context["system"]
    assert context["unknown_reply"] and context["clarification_reply"]
    assert "Examples of the rule" not in context["system"]
    assert len(context["system"]) < 5000


def test_version_four_remains_strict_with_no_session_variation():
    case = simplify_case(example())
    case = review_localization(case, "en")
    context = conversation_context(case, "en", "What did you eat?")
    assert context["session_background"] == []
    assert parse_draft(case).version == 4


def test_restoration_preserves_meal_fact_without_approving_or_hidden_content():
    import json
    from pathlib import Path

    from training_contracts.conversation.background import restore_starter_background

    rows = json.loads(
        (Path(__file__).parents[1] / "migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    original = next(row["document"] for row in rows if row["code"] == "alex_chest_discomfort")
    restored = restore_starter_background(original)
    assert restored["version"] == 5 and restored["localizations"] == {}
    assert any(
        "Yesterday I ate the same as usual." in entry["text"]["en"] for entry in restored["background"]
    )
    assert all(not entry["allow_variation"] for entry in restored["background"])
    original["dialogue"]["topics"][0]["answer"]["en"] = "SECRET-TOPIC"
    original["dialogue"]["topics"][0]["disclosure"] = "never"
    assert "SECRET-TOPIC" not in json.dumps(restore_starter_background(original))


def test_background_upgrade_review_publish_copy_and_scope(library):
    h, author, _, org, base = library
    document = simplify_case(example())
    row = h.call(
        "POST",
        base + "/scenario-drafts",
        author,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "code": document["code"],
            "document": document,
            "specialty_id": h.test_specialty_id,
        },
    )["draft"]
    path = base + f"/scenario-drafts/{row['id']}"
    document = background_case()
    document["localizations"] = {}
    saved = h.call("PUT", path, author, json={"expected_revision": row["revision"], "document": document})
    assert saved["schema_version"] == 5
    assert saved["document"]["background"] == document["background"]
    saved = h.call("POST", path + "/submit", author, json={"expected_revision": saved["revision"]})
    approval = publication()["approval"]
    for language in ("en", "hi"):
        saved = h.call(
            "POST",
            path + f"/localizations/{language}/review",
            h.reviewer_token,
            json={"expected_revision": saved["revision"], "approval": approval},
        )
    published = h.call(
        "POST", path + "/publish", h.reviewer_token, expected=201, json=publication(saved["revision"])
    )["scenario"]
    assert published["schema_version"] == 5 and published["execution_supported"]
    assert published["document"]["background"] == document["background"]
    visible = h.call("GET", base + "/scenarios", author)["items"]
    assert published["id"] in {value["id"] for value in visible}
    copy = h.call(
        "POST",
        base + "/scenario-drafts",
        author,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "code": "background_copy",
            "source_scenario_id": published["id"],
        },
    )["draft"]
    assert copy["document"]["background"] == document["background"]
    assert copy["document"]["localizations"] == {}
    other, _ = h.user("background-outsider")
    h.call("GET", path, other, expected=404)
    checks = h.sql(
        "SELECT device_platform.valid_patient_background(%s::jsonb)",
        ('[{"id":"medications","text":{"en":"Invented drug"}}]',),
    )
    assert checks == [(False,)]


def test_upgrade_preserves_version_four_and_enforces_background_constraints(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0045_session_archives")
    with psycopg.connect(target) as connection:
        before = connection.execute(
            "SELECT id,document,revision FROM device_platform.patient_case_templates ORDER BY id"
        ).fetchall()
    run_upgrade(target, "0046_patient_background")
    with psycopg.connect(target) as connection:
        assert (
            connection.execute(
                "SELECT id,document,revision FROM device_platform.patient_case_templates ORDER BY id"
            ).fetchall()
            == before
        )
        assert before
        identity, document, _ = before[0]
        document.update(version=5, background=background_case()["background"])
        connection.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s,revision=revision+1 WHERE id=%s",
            (Jsonb(document), identity),
        )
        for invalid in (
            {},
            [None],
            [{"id": "food_drink"}],
            [{"id": "food_drink", "text": {"en": "x" * 241}}],
        ):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(
                    "UPDATE device_platform.patient_case_templates SET document=jsonb_set(document,'{background}',%s),revision=revision+1 WHERE id=%s",
                    (Jsonb(invalid), identity),
                )
        assert connection.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_proc p, LATERAL aclexplode(p.proacl) a "
            "WHERE p.oid='device_platform.valid_patient_background(jsonb)'::regprocedure AND a.grantee=0)"
        ).fetchone() == (True,)
