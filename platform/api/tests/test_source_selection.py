"""Single-call literal evidence, frozen source boundaries, and useful missing-detail handling."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_patient_background import background_case
from test_patient_conversation import Runner
from training_contracts.conversation.background import restore_starter_background
from training_contracts.conversation.engine import accepted_reply, fit_conversation_prompt, run_conversation
from training_contracts.conversation.prompt import conversation_context
from training_contracts.conversation.question_scope import select_messages
from training_contracts.conversation.sources import constrained_sources, patient_sources
from training_contracts.localized_cases import review_localization
from training_contracts.patient_turn import TurnError


def context():
    return conversation_context(background_case(), "en", "", seed="source-regression")


@pytest.mark.parametrize(
    "code",
    [
        "alex_chest_discomfort",
        "alex_palpitations",
        "alex_blood_pressure",
        "alex_flank_pain",
        "alex_painful_urination",
        "alex_kidney_followup",
        "alex_wheeze",
        "alex_dry_cough",
        "alex_fever_cough",
    ],
)
def test_combined_identity_and_presenting_question_keeps_both_frozen_sources(code):
    rows = json.loads(
        (Path(__file__).parents[1] / "migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(row["document"] for row in rows if row["code"] == code)
    ctx = conversation_context(review_localization(restore_starter_background(case), "en"), "en", "")
    turns = messages(ctx, "What is your name and what brings you in today?")
    selected = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    needed = [key for key, fact in selected.items() if fact["subject"] in {"patient.name", "chief_complaint"}]
    assert len(needed) == 2
    assert accepted_reply(reply(needed), ctx, turns) == (
        "My name is Alex. " + case["presentation"]["chief_complaint"]["en"]
    )


def messages(ctx, question):
    return select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )


def reply(values):
    return {"text": json.dumps(values), "finish_reason": "stop"}


@pytest.mark.parametrize(
    "question,other_text",
    [
        (
            "Does talking make it worse, and what treatment did you try?",
            "The cough is worse when I talk for a long time.",
        ),
        (
            "Have you taken antibiotics, and have you coughed up blood?",
            "I have not coughed up blood.",
        ),
    ],
)
def test_mixed_past_treatment_does_not_remove_the_other_known_clinical_part(question, other_text):
    sources = {
        "f0": {
            "subject": "current_medications",
            "text": "I tried a cough syrup. I have not taken antibiotics.",
            "area": None,
        },
        "f1": {"subject": "associated_symptoms", "text": other_text, "area": None},
        "f2": {
            "subject": "current_medications",
            "text": "I am not currently taking any medicines.",
            "area": None,
        },
    }
    selected, missing = constrained_sources(sources, question)
    assert "f0" in selected and "f1" in selected and "f2" not in selected
    assert missing is False


@pytest.mark.parametrize("code", ["alex_dry_cough", "alex_fever_cough"])
def test_recorded_sleep_with_clinical_words_survives_a_mixed_sleeping_pill_question(code):
    rows = json.loads(
        (Path(__file__).parents[1] / "migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(row["document"] for row in rows if row["code"] == code)
    ctx = conversation_context(review_localization(restore_starter_background(case), "en"), "en", "")
    turns = messages(ctx, "How is your sleep and which sleeping pills did you try?")
    selected = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    keys = [key for key in selected if ctx["fact_sources"][key]["area"] == "sleep_activity"]
    assert keys
    assert not any(fact["subject"] == "current_medications" for fact in selected.values())
    answer = accepted_reply(reply([*keys, "unknown"]), ctx, turns)
    assert "sleep" in answer and answer.endswith(ctx["unknown_reply"])


def test_duplicate_prose_merges_subjects_without_changing_qualifiers_or_units():
    case = background_case()
    case["presentation"]["onset"] = {"en": "It started about two days ago."}
    case["presentation"]["duration"] = deepcopy(case["presentation"]["onset"])
    case["vitals"] = {
        "temperature_c": 37.2,
        "heart_rate_bpm": 84,
        "pulse_bpm": 84,
        "systolic_mmhg": 128,
        "diastolic_mmhg": 82,
        "respirations_per_minute": 18,
        "spo2_percent": 98.0,
        "pain_0_10": 3.0,
    }
    sources = patient_sources(case, [])
    onset = [fact for fact in sources.values() if fact["text"] == "It started about two days ago."]
    assert len(onset) == 1 and "onset" in onset[0]["subject"] and "duration" in onset[0]["subject"]
    vitals = [fact for fact in sources.values() if fact["subject"].startswith("vitals.")]
    assert len(vitals) == 8
    assert any("128 millimetres of mercury" in fact["text"] for fact in vitals)
    assert any("18 breaths per minute" in fact["text"] for fact in vitals)
    assert any("3.0 out of ten" in fact["text"] for fact in vitals)


async def test_one_call_speaks_pinned_approved_detail_without_exposing_selection():
    ctx = context()
    key = next(
        key for key, fact in ctx["fact_sources"].items() if fact["subject"].endswith("selected_detail")
    )
    runner = Runner(reply([key]))
    turns, budget = await fit_conversation_prompt(runner, messages(ctx, "What do you eat?"), 128, context=ctx)
    result = await run_conversation(runner, ctx, turns, 128)
    assert result["text"] == ctx["fact_sources"][key]["text"]
    assert result["provider_calls"] == len(runner.calls) == 1
    assert key not in result["text"] and budget["prompt_mode"] == "standalone_lifestyle"


@pytest.mark.parametrize(
    "values",
    [
        ["invented"],
        ["unknown", "clarify"],
        ["clarify", "f0"],
        ["f0", "f0"],
        {"answer": "No pets"},
        [False],
        [["f0"]],
    ],
)
async def test_invalid_or_conflicting_model_selection_is_not_repaired(values):
    ctx = context()
    runner = Runner(reply(values))
    with pytest.raises(TurnError) as error:
        await run_conversation(runner, ctx, messages(ctx, "What is your name?"), 128)
    assert error.value.code == "llm_invalid_response" and len(runner.calls) == 1


def test_scope_cannot_select_other_pinned_sources_or_mutate_snapshot():
    ctx = context()
    turns = messages(ctx, "Do you have pets?")
    before = deepcopy((ctx, turns))
    name = next(key for key, fact in ctx["fact_sources"].items() if fact["subject"] == "patient.name")
    assert accepted_reply(reply([name]), ctx, turns) == ctx["unknown_reply"]
    with pytest.raises(TurnError):
        accepted_reply(reply([name]), ctx, messages(ctx, "What do you eat?"))
    assert (ctx, turns) == before
    assert accepted_reply(reply(["unknown"]), ctx, turns) == ctx["unknown_reply"]


def test_old_snapshots_and_general_answers_keep_plain_completion_contract():
    event = {"text": "Paris.", "finish_reason": "stop"}
    assert accepted_reply(event, {"language": "en"}, []) == "Paris."
    ctx = context()
    assert accepted_reply(event, ctx, messages(ctx, "What is the capital of France?")) == "Paris."


def test_actor_and_event_uncertainty_is_enforced_even_if_model_omits_it():
    case = background_case()
    case["background"] = [
        {
            "id": "food_drink",
            "text": {"en": "I eat home-cooked meals."},
            "allow_variation": False,
            "choices": [],
        },
        {
            "id": "sleep_activity",
            "text": {"en": "I usually sleep about seven hours."},
            "allow_variation": False,
            "choices": [],
        },
    ]
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    for question, area in (
        ("Do you cook at home?", "food_drink"),
        ("How did you sleep last night?", "sleep_activity"),
    ):
        key = next(key for key, fact in ctx["fact_sources"].items() if fact["area"] == area)
        assert (
            accepted_reply(reply([key]), ctx, messages(ctx, question))
            == ctx["fact_sources"][key]["text"] + " " + ctx["unknown_reply"]
        )


def test_explicit_cooking_and_exact_night_are_known_not_forced_unknown():
    sources = {
        "f1": {"subject": "background.food_drink", "area": "food_drink", "text": "I cook our meals."},
        "f2": {
            "subject": "background.sleep_activity",
            "area": "sleep_activity",
            "text": "Last night I slept seven hours.",
        },
    }
    assert constrained_sources(sources, "Do you cook?")[1] is False
    assert constrained_sources(sources, "How did you sleep last night?")[1] is False


def test_current_none_cannot_supply_past_treatment_and_missing_symptom_is_unknown():
    sources = {
        "f1": {
            "subject": "current_medications",
            "text": "I am not currently taking any medicines.",
            "area": None,
        },
        "f2": {"subject": "symptoms", "text": "I have not fainted or had a fever.", "area": None},
    }
    assert constrained_sources(sources, "What medicine did you try?") == ({}, True)
    assert constrained_sources(sources, "Have you had ringing in your ears?")[0] == {}
    sources["f3"] = {"subject": "medications.past", "text": "I took Brand-X yesterday.", "area": None}
    assert list(constrained_sources(sources, "What medicine did you try?")[0]) == ["f3"]


def test_sentence_compilation_preserves_authored_cross_sentence_references():
    case = background_case()
    background = [
        {"id": "food_drink", "text": "I eat rice and dal. Yesterday I ate the same as usual."},
        {
            "id": "additional",
            "text": "I walk to the market. I do not do any other regular exercise. I have a dog named Milo.",
        },
    ]
    facts = patient_sources(case, background)
    assert any(fact["text"] == background[0]["text"] for fact in facts.values())
    assert any(
        fact["text"] == "I walk to the market. I do not do any other regular exercise."
        for fact in facts.values()
    )
    assert any(fact["text"] == "I have a dog named Milo." for fact in facts.values())


def test_background_cannot_supply_or_override_clinical_claims():
    case = background_case()
    case["background"] = [
        {
            "id": "additional",
            "text": {"en": "I have diabetes and take insulin."},
            "allow_variation": False,
            "choices": [],
        }
    ]
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    key = next(key for key, fact in ctx["fact_sources"].items() if fact["area"] == "additional")
    with pytest.raises(TurnError):
        accepted_reply(reply([key]), ctx, messages(ctx, "Do you have diabetes?"))


@pytest.mark.parametrize(
    "question", ["How old is Bob?", "How old is bob?", "What is bob's name?", "What is your mother's name?"]
)
def test_patient_identity_cannot_answer_another_person(question):
    ctx = context()
    turns = messages(ctx, question)
    key = next(key for key, fact in ctx["fact_sources"].items() if fact["subject"] == "patient.name")
    assert accepted_reply(reply([key]), ctx, turns) == ctx["unknown_reply"]


def test_rendered_reply_cannot_exceed_shared_speech_limit():
    ctx = context()
    long_text = "A" * 600
    ctx["fact_sources"]["extra"] = {
        "subject": "background.sleep_activity",
        "area": "sleep_activity",
        "text": long_text,
    }
    with pytest.raises(TurnError) as error:
        accepted_reply(reply(["extra", "unknown"]), ctx, messages(ctx, "How do you sleep?"))
    assert error.value.code == "llm_response_limit"


def test_one_missing_part_cannot_be_overwritten_by_a_known_part():
    sources = {
        "f1": {"subject": "background.food_drink", "area": "food_drink", "text": "I eat home-cooked meals."},
        "f2": {
            "subject": "background.sleep_activity",
            "area": "sleep_activity",
            "text": "Last night I slept seven hours.",
        },
    }
    assert constrained_sources(sources, "Do you cook, and how did you sleep last night?")[1] is True


def test_recently_does_not_turn_a_mood_question_into_travel():
    sources = {
        "f1": {"subject": "background.personality", "area": "personality", "text": "I feel a little worried."}
    }
    assert constrained_sources(sources, "Have you been worried recently?")[0] == sources


def test_relaxation_does_not_select_an_unrelated_worry():
    sources = {
        "f1": {
            "subject": "background.personality",
            "area": "personality",
            "text": "I feel a little worried.",
        },
        "f2": {
            "subject": "background.work_home",
            "area": "work_home",
            "text": "I spend evenings at home with my family.",
        },
    }
    selected, missing = constrained_sources(sources, "What do you do to relax?")
    assert list(selected) == ["f2"] and missing is True


def test_unknown_response_preserves_one_pinned_known_partial_answer():
    case = background_case()
    known = "I spend evenings at home with my family."
    case["background"] = [{"id": "work_home", "text": {"en": known}, "allow_variation": False, "choices": []}]
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    turns = messages(ctx, "What do you do to relax?")
    assert accepted_reply(reply(["unknown"]), ctx, turns) == known + " " + ctx["unknown_reply"]
    forged = deepcopy(turns)
    forged[0]["content"] = forged[0]["content"].replace(known, "I went skydiving.")
    with pytest.raises(TurnError):
        accepted_reply(reply(["unknown"]), ctx, forged)


@pytest.mark.parametrize(
    "question,subjects",
    [
        ("What is your blood pressure?", {"vitals.systolic_mmhg", "vitals.diastolic_mmhg"}),
        ("What is your temperature?", {"vitals.temperature_c"}),
        ("How tall are you?", {"patient.height_cm"}),
        ("How old are you?", {"patient.age_years"}),
        ("How fast are you breathing?", {"vitals.respirations_per_minute"}),
    ],
)
def test_complete_measurement_question_uses_only_its_pinned_subjects(question, subjects):
    case = background_case()
    case["vitals"] = {
        "systolic_mmhg": 128,
        "diastolic_mmhg": 82,
        "temperature_c": 36.8,
        "respirations_per_minute": 18,
    }
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    turns = [
        {"role": "developer", "content": ctx["system"]},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": question},
    ]
    before = deepcopy((ctx, turns))
    selected = select_messages(ctx, turns)
    view = json.loads(selected[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert all(fact["subject"] in subjects for fact in view.values())
    assert selected[0]["role"] == "developer" and selected[-1] == turns[-1] and len(selected) == 2
    assert "patient_measurement" in selected[0]["content"]
    assert (ctx, turns) == before
    if view:
        assert accepted_reply(reply(list(view)), ctx, selected) == " ".join(
            fact["text"] for fact in view.values()
        )


@pytest.mark.parametrize(
    "question",
    [
        "What is your blood pressure and what medicine did you try?",
        "Is your blood pressure causing the pain?",
        "What is Bob's temperature?",
        "How tall were you last year?",
        "What does that temperature mean?",
        "How often?",
    ],
)
def test_mixed_named_historical_or_reference_question_keeps_normal_scope(question):
    ctx = context()
    assert "Prompt scope: patient_measurement." not in messages(ctx, question)[0]["content"]


def test_absent_measurement_is_unknown_and_old_snapshot_keeps_its_prompt():
    ctx = context()
    ctx["fact_sources"] = {
        key: fact for key, fact in ctx["fact_sources"].items() if fact["subject"] != "vitals.temperature_c"
    }
    assert (
        accepted_reply(reply(["f0"]), ctx, messages(ctx, "What is your temperature?")) == ctx["unknown_reply"]
    )
    old = {"language": "en", "system": "Old pinned facts"}
    turns = [
        {"role": "system", "content": old["system"]},
        {"role": "user", "content": "What is your temperature?"},
    ]
    assert select_messages(old, turns) == turns


def test_partial_blood_pressure_preserves_known_value_and_acknowledges_missing_one():
    case = background_case()
    case["vitals"] = {"systolic_mmhg": 128}
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    key = next(key for key, fact in ctx["fact_sources"].items() if fact["subject"] == "vitals.systolic_mmhg")
    turns = messages(ctx, "What is your blood pressure?")
    assert (
        accepted_reply(reply([key]), ctx, turns)
        == ctx["fact_sources"][key]["text"] + " " + ctx["unknown_reply"]
    )


def test_frequency_reference_retains_its_pair_and_only_previously_spoken_pinned_facts():
    case = background_case()
    known = "I walk to the market most days."
    case["background"] = [
        {"id": "additional", "text": {"en": known}, "allow_variation": False, "choices": []}
    ]
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    turns = [
        {"role": "developer", "content": ctx["system"]},
        {"role": "user", "content": "What medicine did you try?"},
        {"role": "assistant", "content": ctx["unknown_reply"]},
        {"role": "user", "content": "What do you do for exercise?"},
        {"role": "assistant", "content": known},
        {"role": "user", "content": "How often?"},
    ]
    before = deepcopy((ctx, turns))
    selected = select_messages(ctx, turns)
    view = json.loads(selected[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert len(view) == 1 and next(iter(view.values()))["text"] == known
    assert selected[0]["role"] == "developer" and selected[1:] == turns[-3:]
    assert accepted_reply(reply(list(view)), ctx, selected) == known
    assert (ctx, turns) == before
    forged = deepcopy(turns)
    forged[-2]["content"] = "I run twice a day."
    assert "Prompt scope: standalone_lifestyle." not in select_messages(ctx, forged)[0]["content"]


def test_clinical_frequency_reference_keeps_the_clinical_antecedent_and_full_scope():
    ctx = context()
    turns = [
        {"role": "system", "content": ctx["system"]},
        {"role": "user", "content": "How do you get chest pain?"},
        {"role": "assistant", "content": "I get chest pain every day."},
        {"role": "user", "content": "How often?"},
    ]
    selected = select_messages(ctx, turns)
    assert selected[1:] == turns[1:]
    assert "Prompt scope: standalone_lifestyle." not in selected[0]["content"]


@pytest.mark.parametrize("question", ["Do you smoke?", "How much alcohol do you drink?"])
def test_direct_social_question_uses_clinical_social_evidence_and_absence_is_unknown(question):
    ctx = context()
    known = "I do not smoke. I rarely drink alcohol."
    ctx["fact_sources"]["social-test"] = {"subject": "social.statement", "text": known, "area": "social"}
    turns = messages(ctx, question)
    view = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert view and all(ctx["fact_sources"][key]["area"] == "social" for key in view)
    assert accepted_reply(reply(["social-test"]), ctx, turns) == known
    ctx["fact_sources"] = {
        key: fact for key, fact in ctx["fact_sources"].items() if fact.get("area") != "social"
    }
    assert accepted_reply(reply(["f0"]), ctx, messages(ctx, question)) == ctx["unknown_reply"]


def test_direct_other_symptoms_selects_current_presentation_but_mixed_queries_keep_history():
    ctx = context()
    turns = messages(ctx, "Do you have any other symptoms?")
    view = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert view and set(view).issubset(ctx["intake_sources"])
    mixed = messages(ctx, "Do you have other symptoms, and what medicines do you take?")
    other = json.loads(mixed[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert set(other) - set(ctx["intake_sources"])


def test_compact_source_view_and_old_complete_view_speak_identical_pinned_text():
    ctx = context()
    selected = messages(ctx, "What is your name?")
    compact = json.loads(selected[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert all(set(fact) == {"subject", "text"} for fact in compact.values())
    key = next(key for key in compact if ctx["fact_sources"][key]["subject"] == "patient.name")
    old = deepcopy(selected)
    full = {key: ctx["fact_sources"][key] for key in compact}
    old[0]["content"] = old[0]["content"].replace(
        json.dumps(compact, separators=(",", ":")), json.dumps(full, separators=(",", ":"))
    )
    assert accepted_reply(reply([key]), ctx, selected) == accepted_reply(reply([key]), ctx, old)
    forged = deepcopy(old)
    forged[0]["content"] = forged[0]["content"].replace('"area":"identity"', '"area":"additional"')
    with pytest.raises(TurnError):
        accepted_reply(reply([key]), ctx, forged)


def test_symptom_referent_must_belong_to_current_presentation_to_narrow_view():
    case = background_case()
    case["presentation"]["chief_complaint"] = {"en": "I have chest tightness."}
    ctx = conversation_context(review_localization(case, "en"), "en", "")
    for question, narrow in [
        ("Are there any other symptoms with the tightness?", True),
        ("Are there any other symptoms with your medication?", False),
        ("Are there any other symptoms, and what medicines do you take?", False),
    ]:
        turns = messages(ctx, question)
        view = json.loads(turns[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
        assert set(view).issubset(ctx["intake_sources"]) is narrow


@pytest.mark.parametrize(
    "question", ["Did you smoke last year?", "Does smoking affect the pain?", "Does Bob smoke?"]
)
def test_historical_related_and_other_person_smoking_queries_do_not_use_direct_social_scope(question):
    ctx = context()
    turns = messages(ctx, question)
    # The narrow direct query would remove every completed pair.
    history = [
        {"role": "system", "content": ctx["system"]},
        {"role": "user", "content": "What brought you here?"},
        {"role": "assistant", "content": "I have chest discomfort."},
        {"role": "user", "content": question},
    ]
    assert len(select_messages(ctx, history)) == len(history)
    assert turns[-1]["content"] == question
