"""Only permitted case facts enter the prompt."""

import json

from training_contracts.scenarios import parse_draft, patient_preview


def canonical_text(value, language="en"):
    """Require selected-language wording; missing translations are never silently substituted."""
    if not value or not any(value.values()):
        return None
    if language not in value or not value[language]:
        raise ValueError("Case translation is missing for the selected language")
    return value[language]


def case_facts(document, language="en"):
    case = parse_draft(document)
    if case.version in (4, 5):
        return clinical_facts(document, language)
    preview = patient_preview(document)
    # All values come from the projection. The parsed case supplies disclosure metadata
    # that the UI projection does not carry for symptoms and history sections.
    facts: list[list[str]] = []
    seen: dict[str | tuple[str, str], int] = {}

    def add(label, value, policy="on_question"):
        if value is None or policy == "never":
            return
        rendered = str(value).strip()
        if not rendered:
            return
        # Exact duplicates only: do not erase qualifications by fuzzy matching.
        identity = (label, rendered) if isinstance(value, (int, float)) else rendered
        if identity in seen:
            index = seen[identity]
            if policy == "on_question":
                facts[index][0] = "Q"
            return
        seen[identity] = len(facts)
        facts.append(["V" if policy == "volunteered" else "Q", label, rendered])

    for fact in sorted(preview["facts"], key=lambda item: item["reference"]):
        add(fact["reference"], fact["value"], fact["disclosure"])
    for topic in preview["topics"]:
        add(topic["id"], canonical_text(topic["answer"], language), topic["disclosure"])
    for key in ("chief_complaint", "onset", "duration", "severity"):
        add(key, canonical_text(preview["presentation"].get(key), language), "volunteered")
    symptoms = {s.id: s.disclosure for s in case.presentation.symptoms} if case.presentation else {}
    for symptom in preview["presentation"]["symptoms"]:
        add(symptom["id"], canonical_text(symptom["description"], language), symptoms[symptom["id"]])
    for key, section in sorted(preview["history"].items()):
        policy = getattr(case.history, key).disclosure
        if section["knowledge"] != "present":
            add(key, f"{key}: {section['knowledge']}", policy)
        for entry in section["entries"]:
            add(key, canonical_text(entry, language), policy)
    # JSON escaping stops authored newlines from masquerading as section boundaries.
    return "\n".join(
        f"{flag} {label}: {json.dumps(value, ensure_ascii=False)}" for flag, label, value in facts
    )


def clinical_facts(document, language):
    facts = []

    def add(path, value, flag="Q"):
        if value is not None:
            facts.append(f"{flag} {path}: {json.dumps(str(value), ensure_ascii=False)}")

    for group in ("patient", "vitals"):
        for key, value in (document.get(group) or {}).items():
            add(f"{group}.{key}", canonical_text(value, language) if isinstance(value, dict) else value)
    presentation = document.get("presentation") or {}
    for key in ("chief_complaint", "onset", "duration", "severity"):
        add(key, canonical_text(presentation.get(key), language), "V")
    for symptom in presentation.get("symptoms", []):
        add(symptom["id"], canonical_text(symptom.get("description"), language))
    for key, item in (document.get("history") or {}).items():
        if item is None:
            continue
        label = "current_medications" if key == "medications" else key
        if item["knowledge"] != "present":
            add(label, item["knowledge"])
        for entry in item.get("entries", []):
            add(f"{key}.{entry['id']}", canonical_text(entry["text"], language))
    return "\n".join(facts)
