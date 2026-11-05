"""Version-3 case text and localization provenance; clinical values remain singular."""

from copy import deepcopy
from typing import Literal

from pydantic import Field, model_validator

from training_contracts import Code, Contract, fingerprint
from training_contracts.languages.contracts import LanguageTag, LocalizedText
from training_contracts.scenarios import (
    Dialogue,
    History,
    HistoryItem,
    Patient,
    PatientTopic,
    Presentation,
    ScenarioDraftV2,
    Symptom,
    publication_issues,
)


class PatientV3(Patient):
    occupation: LocalizedText | None = None


class SymptomV3(Symptom):
    description: LocalizedText | None = None


class PresentationV3(Presentation):
    chief_complaint: LocalizedText | None = None
    symptoms: list[SymptomV3] = Field(default_factory=list, max_length=24)
    onset: LocalizedText | None = None
    duration: LocalizedText | None = None
    severity: LocalizedText | None = None


class HistoryEntry(Contract):
    id: Code
    text: LocalizedText


class HistoryItemV3(HistoryItem):
    entries: list[HistoryEntry] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def ids(self):
        if len({entry.id for entry in self.entries}) != len(self.entries):
            raise ValueError("Duplicate history entry ID")
        return self


class HistoryV3(History):
    past_conditions: HistoryItemV3 | None = None
    surgeries: HistoryItemV3 | None = None
    medications: HistoryItemV3 | None = None
    allergies: HistoryItemV3 | None = None
    family: HistoryItemV3 | None = None
    social: HistoryItemV3 | None = None


class PatientTopicV3(PatientTopic):
    answer: LocalizedText | None = None


class DialogueV3(Dialogue):
    greeting: LocalizedText | None = None
    clarification: LocalizedText | None = None
    backchannel: LocalizedText | None = None
    command_ack: LocalizedText | None = None
    boundary: LocalizedText | None = None
    topics: list[PatientTopicV3] = Field(default_factory=list, max_length=32)


class Localization(Contract):
    revision: int = Field(ge=1, le=2147483646, strict=True)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["draft", "reviewed", "system_starter", "practice_override"] = "draft"


class ScenarioDraftV3(ScenarioDraftV2):
    version: Literal[3] = 3
    source_language: LanguageTag = "en"
    patient: PatientV3 | None = None
    presentation: PresentationV3 | None = None
    history: HistoryV3 | None = None
    dialogue: DialogueV3 | None = None
    localizations: dict[LanguageTag, Localization] = Field(default_factory=dict, max_length=8)


def parse_localized(document):
    if document.get("version") in (4, 5):
        from training_contracts.clinical_cases import ScenarioDraftV4, ScenarioDraftV5

        return (ScenarioDraftV5 if document["version"] == 5 else ScenarioDraftV4).model_validate(document)
    return ScenarioDraftV3.model_validate(document)


def localized_values(case):
    """Visit only typed localized text, never guess whether a dict is a language map."""
    if isinstance(case, LocalizedText):
        yield case
    elif isinstance(case, Contract):
        for key in type(case).model_fields:
            if key != "localizations":
                yield from localized_values(getattr(case, key))
    elif isinstance(case, list):
        for item in case:
            yield from localized_values(item)


def language_document(case, language):
    """Canonical single-language document; stable IDs survive list reordering."""

    def visit(value):
        if isinstance(value, LocalizedText):
            return value.root.get(language)
        if isinstance(value, Contract):
            return {
                key: visit(getattr(value, key)) for key in type(value).model_fields if key != "localizations"
            }
        if isinstance(value, list):
            result = [visit(item) for item in value]
            if all(isinstance(item, dict) and "id" in item for item in result):
                result.sort(key=lambda item: item["id"])
            return result
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        return value

    return visit(case)


def review_localization(document, language):
    """Called only by an authorized publisher/reviewer, never by a draft PUT."""
    case = parse_localized(document)
    if any(language not in value.root for value in localized_values(case)):
        raise ValueError("Complete the selected case translation before review")
    if publication_issues(case):
        raise ValueError("Complete the case before localization review")
    previous = case.localizations.get(language)
    result = case.model_dump(mode="json", exclude_none=True)
    result["localizations"][language] = {
        "revision": previous.revision + 1 if previous else 1,
        "source_hash": fingerprint(language_document(case, case.source_language)),
        "content_hash": fingerprint(language_document(case, language)),
        "status": "reviewed",
    }
    return result


def mark_system_starter_localization(document, language):
    """Mark validated bundled starter text without attributing it to a clinician."""
    case = parse_localized(document)
    if any(language not in value.root for value in localized_values(case)) or publication_issues(case):
        raise ValueError("Bundled starter is incomplete")
    result = case.model_dump(mode="json", exclude_none=True)
    result["localizations"][language] = {
        "revision": 1,
        "source_hash": fingerprint(language_document(case, case.source_language)),
        "content_hash": fingerprint(language_document(case, language)),
        "status": "system_starter",
    }
    return result


def mark_practice_override(document, language, vitals):
    """Stamp a private vitals override after checking its published source."""
    if not localization_ready(document, language):
        raise ValueError("Published scenario language is unavailable")
    case = parse_localized({**document, "vitals": vitals})
    result = case.model_dump(mode="json", exclude_none=True)
    previous = case.localizations.get(language)
    result["localizations"][language] = {
        "revision": previous.revision + 1 if previous else 1,
        "source_hash": fingerprint(language_document(case, case.source_language)),
        "content_hash": fingerprint(language_document(case, language)),
        "status": "practice_override",
    }
    return result


def localization_ready(document, language):
    case = parse_localized(document)
    approval = case.localizations.get(language)
    return bool(
        approval
        and approval.status in {"reviewed", "system_starter", "practice_override"}
        and approval.source_hash == fingerprint(language_document(case, case.source_language))
        and approval.content_hash == fingerprint(language_document(case, language))
        and all(language in value.root for value in localized_values(case))
    )


def convert_v2(document, *, review_languages=()):
    """Deterministic format conversion, with explicit deployment/publisher review only."""
    old = ScenarioDraftV2.model_validate(document)
    result = old.model_dump(mode="json", exclude_none=True)
    # Every old bilingual value has at most two keys. Walk typed models to avoid
    # treating free text or unrelated dictionaries as translations.
    result["version"] = 3
    result["source_language"] = "en"
    result["localizations"] = {}
    for section in (result.get("history") or {}).values():
        section["entries"] = [
            {"id": f"entry_{index + 1}", "text": entry} for index, entry in enumerate(section["entries"])
        ]
    result = ScenarioDraftV3.model_validate(result).model_dump(mode="json", exclude_none=True)
    for language in review_languages:
        result = review_localization(result, language)
    return result


def prevent_review_forgery(document, previous=None):
    """Draft edits preserve only existing server-issued provenance; hashes detect edits."""
    document = deepcopy(document)
    incoming = document.get("localizations", {})
    existing = (previous or {}).get("localizations", {})
    if incoming and incoming != existing:
        raise ValueError("Localization review metadata is server managed")
    document["localizations"] = deepcopy(existing)
    return document
