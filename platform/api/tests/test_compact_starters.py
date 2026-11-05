"""Correct starter provisioning and forward upgrades without historical rewrites."""

import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from test_default_local_models import run_upgrade, upgrade_database  # noqa: F401
from test_patient_conversation import Runner
from test_session_queue import queue_device as queue_device
from training_contracts.conversation.engine import accepted_reply, fit_conversation_prompt, run_conversation
from training_contracts.conversation.prompt import conversation_context
from training_contracts.conversation.question_scope import select_messages
from training_contracts.localized_cases import localization_ready, mark_system_starter_localization
from training_contracts.scenarios import validate_publication

from pms_api.database.tenant_catalog_backfill import backfill

SEEDS = json.loads(
    (Path(__file__).parents[1] / "migrations/versions/0047_compact_starters.json").read_text(encoding="utf-8")
)


def selected(document, question):
    ctx = conversation_context(document, "en", question, seed="starter-regression")
    turns = select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )
    return json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
def test_starter_facts_bilingual_and_question_scope(seed):
    document = seed["publication"]
    assert validate_publication(document) == []
    assert all(localization_ready(document, language) for language in ("en", "hi"))
    assert document["presentation"]["onset"] != document["presentation"]["duration"]
    for question in (
        "In family also have anybody the similar problem?",
        "Anybody in your family have the similar problem?",
    ):
        facts = selected(document, question)
        assert facts and all(fact["subject"].startswith("family") for fact in facts.values())
    facts = selected(document, "Tell me about your educational qualification.")
    assert len(facts) == 1 and "degree" in next(iter(facts.values()))["text"]
    assert not selected(
        mark_system_starter_localization(seed["previous"], "en"),
        "Tell me about your educational qualification.",
    )
    assert "social.entry_1" in {
        fact["subject"] for fact in selected(document, "Who do you live with?").values()
    }
    assert "social.entry_1" in {
        fact["subject"]
        for fact in selected(document, "Do you live in the same house with your family?").values()
    }


@pytest.mark.parametrize(
    "question,subjects",
    [
        (
            "Who prescribed your inhaler and what makes your wheeze worse?",
            {"medications.prescriber", "main_symptoms"},
        ),
        (
            "Does your family have similar wheezing? Who prescribed your inhaler?",
            {"family.similar_condition", "medications.prescriber"},
        ),
        (
            "What is your educational qualification and does your family have any similar problems?",
            {"background.work_home", "family.similar_condition"},
        ),
    ],
)
def test_combined_starter_questions_retain_each_known_answer(question, subjects):
    ctx = conversation_context(SEEDS[1]["publication"], "en", "", seed="combined-review")
    turns = select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )
    facts = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert subjects.issubset({fact["subject"] for fact in facts.values()})
    keys = [key for key, fact in facts.items() if fact["subject"] in subjects][:3]
    answer = accepted_reply({"text": json.dumps(keys), "finish_reason": "stop"}, ctx, turns)
    assert all(ctx["fact_sources"][key]["text"] in answer for key in keys)


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
def test_combined_unrecorded_meal_and_qualification_keeps_known_part_and_unknown(seed):
    question = "What did you eat yesterday and what is your educational qualification?"
    ctx = conversation_context(seed["publication"], "en", "", seed="combined-unknown-review")
    turns = select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )
    facts = selected(seed["publication"], question)
    assert len(facts) == 1 and "degree" in next(iter(facts.values()))["text"]
    assert 'include "unknown"' in turns[0]["content"]
    key = next(iter(facts))
    answer = accepted_reply({"text": json.dumps([key]), "finish_reason": "stop"}, ctx, turns)
    assert answer == facts[key]["text"] + " " + ctx["unknown_reply"]


def test_degree_of_pain_does_not_select_educational_qualification():
    facts = selected(SEEDS[0]["publication"], "What degree of pain are you experiencing?")
    assert {fact["subject"] for fact in facts.values()} == {"vitals.pain_0_10"}


def test_usual_meal_cannot_establish_last_night_but_authored_event_can():
    from training_contracts.conversation.sources import constrained_sources

    facts = {
        "usual": {"subject": "background.food_drink", "area": "food_drink", "text": "I usually eat rice."},
        "event": {"subject": "background.food_drink", "area": "food_drink", "text": "I ate soup last night."},
    }
    eligible, missing = constrained_sources(facts, "What did you eat last night?")
    assert eligible == {"event": facts["event"]} and not missing
    eligible, _ = constrained_sources({"usual": facts["usual"]}, "What did you eat last night?")
    assert eligible == {}


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
def test_live_wellbeing_does_not_force_onset_and_duration_into_current_answer(seed):
    facts = selected(seed["publication"], "How are you feeling today?")
    assert {fact["subject"] for fact in facts.values()} == {"chief_complaint", "severity"}


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
@pytest.mark.parametrize(
    "question", ["What is your occupation?", "What do you do for a living?", "What do you do for work?"]
)
def test_live_occupation_excludes_education_and_unrequested_schedule(seed, question):
    facts = selected(seed["publication"], question)
    assert {fact["subject"] for fact in facts.values()} == {"patient.occupation"}


@pytest.mark.parametrize(
    "question", ["What makes it better?", "What helps it?", "What relieves your chest discomfort?"]
)
def test_live_relief_question_keeps_explicit_help_and_not_current_pain_score(question):
    facts = selected(SEEDS[0]["publication"], question)
    assert [fact["text"] for fact in facts.values()] == ["Rest usually helps."]


def test_live_joined_similar_family_and_prescriber_excludes_unrelated_father_condition():
    facts = selected(
        SEEDS[1]["publication"], "Does your family have similar wheezing? Who prescribed your inhaler?"
    )
    assert {fact["subject"] for fact in facts.values()} == {
        "family.similar_condition",
        "medications.prescriber",
    }


def test_live_fever_and_unrecorded_cough_retains_denial_and_marks_missing_part():
    ctx = conversation_context(SEEDS[0]["publication"], "en", "", seed="known-fever-unknown-cough")
    turns = select_messages(
        ctx,
        [
            {"role": "system", "content": ctx["system"]},
            {"role": "user", "content": "Do you have a fever or a cough?"},
        ],
    )
    facts = selected(SEEDS[0]["publication"], turns[-1]["content"])
    assert len(facts) == 1 and "fever" in next(iter(facts.values()))["text"]
    key = next(iter(facts))
    answer = accepted_reply({"text": json.dumps([key]), "finish_reason": "stop"}, ctx, turns)
    assert answer.endswith(ctx["unknown_reply"])


def test_sentence_sources_retain_condition_qualifiers_and_pronoun_references():
    from training_contracts.conversation.sources import source_sentences

    assert source_sentences("I get chest pain. But only when exercising.") == [
        "I get chest pain. But only when exercising."
    ]
    assert source_sentences("I use an inhaler. It helps briefly.") == ["I use an inhaler. It helps briefly."]
    assert source_sentences("I use an inhaler. I take it when needed.") == [
        "I use an inhaler. I take it when needed."
    ]
    assert source_sentences("My temperature is 36.8 degrees Celsius.") == [
        "My temperature is 36.8 degrees Celsius."
    ]


@pytest.mark.parametrize("seed", SEEDS, ids=lambda seed: seed["document"]["code"])
def test_explicit_current_presentation_sheds_unneeded_history_and_other_domains(seed):
    ctx = conversation_context(seed["publication"], "en", "", seed="lean-presentation-review")
    original = [
        {"role": "system", "content": ctx["system"]},
        {"role": "user", "content": "Who do you live with?"},
        {"role": "assistant", "content": "I live with my wife."},
        {"role": "user", "content": "How are you feeling today?"},
    ]
    turns = select_messages(ctx, original)
    assert len(turns) == 2 and turns[-1] == original[-1]
    facts = selected(seed["publication"], original[-1]["content"])
    assert facts and set(facts).issubset(ctx["intake_sources"])
    assert {"chief_complaint", "severity"}.issubset({fact["subject"] for fact in facts.values()})


def test_combined_prescriber_and_trigger_uses_only_presentation_and_prescriber_evidence():
    document = SEEDS[1]["publication"]
    ctx = conversation_context(document, "en", "", seed="lean-mixed-review")
    facts = selected(document, "Who prescribed your inhaler and what makes your wheeze worse?")
    prescriber = {
        key for key, fact in ctx["fact_sources"].items() if fact["subject"] == "medications.prescriber"
    }
    assert set(facts).issubset(set(ctx["intake_sources"]) | prescriber)
    assert "main_symptoms" in {fact["subject"] for fact in facts.values()}


def test_ambiguous_trigger_followup_retains_its_recent_reference():
    ctx = conversation_context(SEEDS[1]["publication"], "en", "", seed="followup-review")
    original = [
        {"role": "system", "content": ctx["system"]},
        {"role": "user", "content": "Why are you wheezing?"},
        {"role": "assistant", "content": "I have asthma."},
        {"role": "user", "content": "What makes it worse?"},
    ]
    turns = select_messages(ctx, original)
    assert turns[1:] == original[1:]


def test_explicit_qualification_sheds_history_without_replacing_missing_education_with_a_job():
    for document in (SEEDS[1]["publication"], mark_system_starter_localization(SEEDS[1]["previous"], "en")):
        ctx = conversation_context(document, "en", "", seed="lean-qualification-review")
        original = [
            {"role": "system", "content": ctx["system"]},
            {"role": "user", "content": "What is your occupation?"},
            {"role": "assistant", "content": "I am a schoolteacher."},
            {"role": "user", "content": "Tell me about your educational qualification."},
        ]
        turns = select_messages(ctx, original)
        assert len(turns) == 2 and turns[-1] == original[-1]
        facts = selected(document, original[-1]["content"])
        assert all("degree" in fact["text"] for fact in facts.values())
        assert bool(facts) == (document["version"] == 5)


async def test_combined_question_uses_one_generation_with_the_total_local_context_limit():
    question = "What did you eat yesterday and what is your educational qualification?"
    ctx = conversation_context(SEEDS[1]["publication"], "en", "", seed="one-call-review")
    turns = select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )
    key = next(iter(selected(SEEDS[1]["publication"], question)))
    runner = Runner({"text": json.dumps([key]), "finish_reason": "stop"})
    fitted, budget = await fit_conversation_prompt(runner, turns, 128, context=ctx)
    assert budget["context_limit"] == 2048
    assert budget["prompt_tokens"] + budget["reserved_output_tokens"] + budget["safety_margin_tokens"] <= 2048
    result = await run_conversation(runner, ctx, fitted, 128)
    assert result["provider_calls"] == len(runner.calls) == 1
    assert result["text"].endswith(ctx["unknown_reply"])


def test_upgrade_preserves_customized_globals_and_is_repeatable(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0046_patient_background")
    custom = deepcopy(SEEDS[0]["previous"])
    custom["presentation"]["chief_complaint"]["en"] = "A customized chest case."
    with psycopg.connect(target) as c:
        c.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s,revision=revision+1 WHERE id=%s",
            (Jsonb(custom), SEEDS[0]["id"]),
        )
    run_upgrade(target, "0047_compact_starters")
    with psycopg.connect(target) as c:
        assert (
            c.execute(
                "SELECT document FROM device_platform.patient_case_templates WHERE id=%s", (SEEDS[0]["id"],)
            ).fetchone()[0]
            == custom
        )
        assert c.execute(
            "SELECT revision,document FROM device_platform.patient_case_templates WHERE id=%s",
            (SEEDS[1]["id"],),
        ).fetchone() == (5, SEEDS[1]["document"])
        before = c.execute(
            "SELECT id,revision,document FROM device_platform.patient_case_templates ORDER BY id"
        ).fetchall()
    run_upgrade(target, "0047_compact_starters")
    with psycopg.connect(target) as c:
        assert (
            c.execute(
                "SELECT id,revision,document FROM device_platform.patient_case_templates ORDER BY id"
            ).fetchall()
            == before
        )


def test_upgrade_versions_existing_tenant_preserves_live_assignment_and_overrides(queue_device):
    h, instructor, _, org, device, token, path, item, case = queue_device
    with psycopg.connect(h.dsn) as c:
        # Reconstruct the deployed pre-upgrade stock content in this disposable database.
        c.execute("ALTER TABLE device_platform.patient_case_templates DISABLE TRIGGER patient_case_guard")
        c.execute(
            "ALTER TABLE device_platform.organization_case_templates DISABLE TRIGGER organization_case_templates_guard"
        )
        c.execute("ALTER TABLE device_platform.training_scenarios DISABLE TRIGGER training_scenario_guard")
        for seed in SEEDS:
            old = seed["previous"]
            published = old
            for language in ("en", "hi"):
                published = mark_system_starter_localization(published, language)
            c.execute(
                "UPDATE device_platform.patient_case_templates SET document=%s,revision=4 WHERE id=%s",
                (Jsonb(old), seed["id"]),
            )
            c.execute(
                "UPDATE device_platform.organization_case_templates SET document=%s,source_global_revision=4 WHERE organization_id=%s AND source_global_id=%s",
                (Jsonb(old), org, seed["id"]),
            )
            c.execute(
                "UPDATE device_platform.training_scenarios SET document=%s WHERE organization_id=%s AND code=%s",
                (Jsonb(published), org, old["code"]),
            )
        c.execute("ALTER TABLE device_platform.training_scenarios ENABLE TRIGGER training_scenario_guard")
        c.execute(
            "ALTER TABLE device_platform.organization_case_templates ENABLE TRIGGER organization_case_templates_guard"
        )
        c.execute("ALTER TABLE device_platform.patient_case_templates ENABLE TRIGGER patient_case_guard")
    base = f"/organizations/{org}/patient-practice"
    saved = h.call(
        "PUT",
        base + "/scenario-selection",
        token,
        json={"expected_revision": 0, "scenario_id": case["id"], "language": "en", "vitals": case["vitals"]},
    )["selection"]
    other = next(
        row
        for row in h.call("GET", base + "/scenario-options", instructor)["items"]
        if row["id"] != case["id"]
    )
    vitals = {**other["vitals"], "pulse_bpm": 87.0}
    private = h.call(
        "PUT",
        base + "/scenario-selection",
        instructor,
        json={"expected_revision": 0, "scenario_id": other["id"], "language": "en", "vitals": vitals},
    )["selection"]
    queue = h.call(
        "POST", path, instructor, expected=201, json={"request_key": str(uuid4()), "items": [item, item]}
    )
    first = queue["items"][0]["id"]
    h.call("POST", f"/device/session-queue/{first}/begin", token, json={"runtime_id": str(uuid4())})
    route = h.call("GET", f"/organizations/{org}/model-config", token)
    h.call(
        "POST",
        base + "/conversations",
        token,
        json={
            "request_key": str(uuid4()),
            "practice_id": saved["id"],
            "practice_revision": saved["revision"],
            "connection_id": route["llm"]["connection_id"],
            "language": "en",
            "profile_revision_id": route["profile_revision_id"],
            "configuration_hash": route["configuration_hash"],
            "assigned_session_id": first,
        },
    )
    protected = ("practice_sessions", "patient_conversations", "session_archives")
    before = {
        table: h.sql(f"SELECT to_jsonb(t) FROM device_platform.{table} t ORDER BY id") for table in protected
    }
    publications = h.sql("SELECT id,document FROM device_platform.training_scenarios ORDER BY id")
    h.sql(
        "UPDATE device_platform.organizations SET policy_settings=policy_settings||%s WHERE id=%s",
        (Jsonb({"audit_retention_days": 7}), org),
    )
    h.sql("UPDATE public.alembic_version SET version_num='0046_patient_background'")
    run_upgrade(h.dsn, "0047_compact_starters")
    for table in protected:
        assert h.sql(f"SELECT to_jsonb(t) FROM device_platform.{table} t ORDER BY id") == before[table]
    assert (
        h.sql("SELECT id,document FROM device_platform.training_scenarios WHERE version=1 ORDER BY id")
        == publications
    )
    versions = h.sql(
        "SELECT version,document FROM device_platform.training_scenarios WHERE organization_id=%s AND version=2",
        (org,),
    )
    assert len(versions) == 2 and all(doc["version"] == 5 for _, doc in versions)
    assert h.sql("SELECT is_active FROM device_platform.training_scenarios WHERE id=%s", (case["id"],)) == [
        (True,)
    ]
    assert h.sql(
        "SELECT scenario_id,revision,document FROM device_platform.patient_practice_selections WHERE id=%s",
        (saved["id"],),
    )[0] == (UUID(saved["scenario_id"]), saved["revision"], saved["document"])
    upgraded = h.call("GET", base + "/scenario-selection", instructor)["selection"]
    assert upgraded["revision"] == private["revision"] + 1 and upgraded["scenario_id"] != other["id"]
    assert upgraded["document"]["vitals"] == vitals and upgraded["document"]["version"] == 5
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE details->>'source'='0047_compact_starters'"
        )[0][0]
        >= 5
    )
    assert h.sql(
        "SELECT DISTINCT expires_at-occurred_at FROM device_platform.activity_events "
        "WHERE organization_id=%s AND details->>'source'='0047_compact_starters'",
        (org,),
    ) == [(timedelta(days=7),)]
    assert h.sql(
        "SELECT count(*) FROM pg_trigger WHERE tgrelid IN ('device_platform.organization_case_templates'::regclass,'device_platform.patient_practice_selections'::regclass) AND tgenabled='D'"
    ) == [(0,)]
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "UPDATE device_platform.training_scenarios SET document=document||%s WHERE id=%s",
            (Jsonb({"title": "Forbidden edit"}), case["id"]),
        )
    # The next forward refinement must preserve the same live assignment and
    # immutable records; an idle override can advance a second time.
    old_publications = h.sql("SELECT id,document FROM device_platform.training_scenarios ORDER BY id")
    run_upgrade(h.dsn)
    for table in protected:
        assert h.sql(f"SELECT to_jsonb(t) FROM device_platform.{table} t ORDER BY id") == before[table]
    assert (
        h.sql("SELECT id,document FROM device_platform.training_scenarios WHERE version<=2 ORDER BY id")
        == old_publications
    )
    assert h.sql(
        "SELECT revision FROM device_platform.patient_case_templates WHERE id IN (%s,%s) ORDER BY id",
        tuple(seed["id"] for seed in SEEDS),
    ) == [(6,), (6,)]
    assert h.sql(
        "SELECT source_global_revision FROM device_platform.organization_case_templates WHERE organization_id=%s ORDER BY source_global_id",
        (org,),
    ) == [(6,), (6,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s AND version=3",
        (org,),
    ) == [(2,)]
    refined = h.call("GET", base + "/scenario-selection", instructor)["selection"]
    assert refined["revision"] == private["revision"] + 2
    assert refined["document"]["vitals"] == vitals
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s AND version=3",
        (org,),
    ) == [(2,)]


def test_global_revision_collision_does_not_provision_edited_starter(platform):
    h = platform
    token, _ = h.user("edited-global-starter")
    edited = deepcopy(SEEDS[0]["document"])
    edited["presentation"]["chief_complaint"]["en"] = "A manually edited global case."
    with psycopg.connect(h.dsn) as c:
        c.execute("ALTER TABLE device_platform.patient_case_templates DISABLE TRIGGER patient_case_guard")
        c.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s WHERE id=%s",
            (Jsonb(edited), SEEDS[0]["id"]),
        )
        c.execute("ALTER TABLE device_platform.patient_case_templates ENABLE TRIGGER patient_case_guard")
    plan = str(h.sql("SELECT id FROM device_platform.subscription_plans WHERE code='standard'")[0][0])
    response = h.call(
        "POST",
        "/organizations",
        token,
        expected=503,
        json={"name": "Refused edited starter", "subscription_plan_id": plan},
    )
    assert response["error"]["code"] == "case_starters_unavailable"
    assert h.sql("SELECT count(*) FROM device_platform.organizations") == [(0,)]
    assert h.sql("SELECT count(*) FROM device_platform.organization_case_templates") == [(0,)]


def test_known_upgrade_preserves_customized_mapped_legacy_case(platform):
    h = platform
    token, user = h.user("legacy-custom-starter")
    org = h.organization(token)["id"]
    old = SEEDS[0]["previous"]
    custom = deepcopy(old)
    custom["presentation"]["chief_complaint"]["en"] = "A tenant-authored chest presentation."
    with psycopg.connect(h.dsn) as c:
        c.execute("ALTER TABLE device_platform.patient_case_templates DISABLE TRIGGER patient_case_guard")
        c.execute(
            "ALTER TABLE device_platform.organization_case_templates DISABLE TRIGGER organization_case_templates_guard"
        )
        c.execute(
            "UPDATE device_platform.patient_case_templates SET document=%s,revision=4 WHERE id=%s",
            (Jsonb(old), SEEDS[0]["id"]),
        )
        c.execute(
            "UPDATE device_platform.organization_case_templates SET document=%s,source_global_revision=4 WHERE organization_id=%s AND source_global_id=%s",
            (Jsonb(custom), org, SEEDS[0]["id"]),
        )
        c.execute(
            "ALTER TABLE device_platform.organization_case_templates ENABLE TRIGGER organization_case_templates_guard"
        )
        c.execute("ALTER TABLE device_platform.patient_case_templates ENABLE TRIGGER patient_case_guard")
        c.execute(
            "INSERT INTO device_platform.patient_practice_selections(id,organization_id,user_id,template_id,category_id,patient_identity_id,template_revision,document,language) SELECT gen_random_uuid(),%s,%s,id,category_id,patient_identity_id,4,document,'en' FROM device_platform.patient_case_templates WHERE id=%s",
            (org, user["id"], SEEDS[0]["id"]),
        )
    mapped = backfill(h.settings, apply=True, after=None, limit=25)
    before = h.sql("SELECT to_jsonb(p) FROM device_platform.patient_practice_selections p ORDER BY id")
    h.sql("UPDATE public.alembic_version SET version_num='0046_patient_background'")
    run_upgrade(h.dsn)
    assert backfill(h.settings, apply=True, after=None, limit=25) == mapped
    assert (
        h.sql("SELECT to_jsonb(p) FROM device_platform.patient_practice_selections p ORDER BY id") == before
    )
    assert h.sql(
        "SELECT document,source_global_revision FROM device_platform.organization_case_templates WHERE organization_id=%s AND source_global_id=%s",
        (org, SEEDS[0]["id"]),
    ) == [(custom, 4)]
