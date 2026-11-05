"""Regressions for source selection observed with real local patient interviews."""

import json

import pytest
from test_local_execution import document
from training_contracts.conversation.background import restore_starter_background
from training_contracts.conversation.engine import accepted_reply
from training_contracts.conversation.prompt import conversation_context
from training_contracts.conversation.question_scope import select_messages
from training_contracts.localized_cases import review_localization


def context():
    case = restore_starter_background(document())
    case["background"] = [row for row in case["background"] if row["id"] != "personality"]
    case = review_localization(case, "en")
    return conversation_context(case, "en", "", seed="local-desktop-review")


def selected(ctx, question):
    messages = select_messages(
        ctx, [{"role": "system", "content": ctx["system"]}, {"role": "user", "content": question}]
    )
    view = json.loads(messages[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    return messages, view


@pytest.mark.parametrize(
    "question",
    ["How are you feeling about being here today?", "Are you nervous?", "What is your mood?"],
)
def test_emotional_question_cannot_borrow_a_pain_measurement(question):
    ctx = context()
    pain = next(key for key, fact in ctx["fact_sources"].items() if fact["subject"] == "vitals.pain_0_10")
    messages, view = selected(ctx, question)
    assert not view
    assert (
        accepted_reply({"text": json.dumps([pain]), "finish_reason": "stop"}, ctx, messages)
        == ctx["unknown_reply"]
    )


def test_recorded_emotional_fact_is_available_without_unrelated_clinical_facts():
    ctx = context()
    text = "I am nervous about this visit."
    ctx["fact_sources"]["emotional"] = {
        "subject": "background.personality",
        "text": text,
        "area": "personality",
    }
    messages, view = selected(ctx, "How are you feeling about being here today?")
    assert list(view) == ["emotional"]
    assert accepted_reply({"text": '["emotional"]', "finish_reason": "stop"}, ctx, messages) == text


def test_mixed_emotional_and_clinical_question_retains_known_part_and_uncertainty():
    ctx = context()
    messages, view = selected(ctx, "Are you nervous, and do you have a cough?")
    assert view and all("cough" in fact["text"].lower() for fact in view.values())
    answer = accepted_reply(
        {"text": json.dumps([next(iter(view)), "unknown"]), "finish_reason": "stop"}, ctx, messages
    )
    assert "cough" in answer.lower() and ctx["unknown_reply"] in answer


def test_current_symptoms_are_still_available_for_generic_how_are_you_feeling():
    ctx = context()
    _, view = selected(ctx, "How are you feeling today?")
    assert view and all(fact["subject"] in {"chief_complaint", "severity"} for fact in view.values())


@pytest.mark.parametrize(
    "question", ["What has brought you in today?", "What brought you in today?", "What brings you here?"]
)
def test_intake_wording_uses_presenting_facts(question):
    ctx = context()
    _, view = selected(ctx, question)
    assert view and set(view).issubset(ctx["intake_sources"])


def test_mixed_clinical_question_preserves_recorded_emotional_background():
    ctx = context()
    text = "I am nervous about this visit."
    ctx["fact_sources"]["emotional"] = {
        "subject": "background.personality",
        "text": text,
        "area": "personality",
    }
    messages, view = selected(ctx, "Are you nervous, and do you have a cough?")
    assert "emotional" in view
    cough = next(key for key, fact in view.items() if "cough" in fact["text"].lower())
    answer = accepted_reply(
        {"text": json.dumps(["emotional", cough]), "finish_reason": "stop"}, ctx, messages
    )
    assert text in answer and "cough" in answer.lower()
