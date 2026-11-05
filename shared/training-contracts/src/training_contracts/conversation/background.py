"""Bounded author-approved background, compiled once without inference."""

import hashlib
import json

from training_contracts.scenarios import parse_draft


def session_background(document, language, seed=""):
    case = parse_draft(document)
    entries = getattr(case, "background", [])
    resolved = []
    for entry in sorted(entries, key=lambda value: value.id):
        text = entry.text.root.get(language)
        if not text:
            raise ValueError("Background translation is missing")
        fact = {"id": entry.id, "text": text, "provenance": "authored"}
        if entry.allow_variation:
            choices = sorted(entry.choices, key=lambda value: value.id)
            number = int.from_bytes(hashlib.sha256(f"{seed}:{entry.id}".encode()).digest()[:8], "big")
            choice = choices[number % len(choices)]
            detail = choice.text.root.get(language)
            if not detail:
                raise ValueError("Everyday choice translation is missing")
            fact.update(detail=detail, choice_id=choice.id, provenance="author_approved_choice")
        resolved.append(fact)
    return resolved


def background_text(resolved):
    return "\n".join(
        f"{fact['id']}: "
        + json.dumps(fact["text"], ensure_ascii=False)
        + ("; everyday detail: " + json.dumps(fact["detail"], ensure_ascii=False) if "detail" in fact else "")
        for fact in resolved
    )


def restore_starter_background(document):
    """Produce an unreviewed draft from explicit permitted legacy starter facts."""
    from training_contracts.clinical_cases import ScenarioDraftV5, simplify_case

    case = parse_draft(document)
    topics = {topic.id: topic for topic in case.dialogue.topics if topic.disclosure != "never"}
    categories = {
        "food_drink": "diet_meals",
        "sleep_activity": "sleep",
        "work_home": "daily_routine",
        "personality": "mood_stress",
        "additional": "exercise",
    }
    result = simplify_case(document)
    result.update(version=5, localizations={}, background=[])
    for category, topic_id in categories.items():
        topic = topics.get(topic_id)
        if topic and topic.answer:
            result["background"].append(
                {
                    "id": category,
                    "text": topic.answer.model_dump(mode="json", exclude_none=True),
                    "allow_variation": False,
                    "choices": [],
                }
            )
    return ScenarioDraftV5.model_validate(result).model_dump(mode="json", exclude_none=True)
