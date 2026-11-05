"""Simplified clinical scenarios: presentation, symptoms, history and eight vitals."""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import Field, model_validator

from training_contracts import Bilingual, Code, Contract, Scenario
from training_contracts.languages.contracts import LanguageTag, LocalizedText
from training_contracts.localized_cases import HistoryEntry, Localization, PatientV3
from training_contracts.scenarios import Issue, Label, Vitals, check_size, unique


class ClinicalSymptom(Contract):
    id: Code
    description: LocalizedText | None = None


class ClinicalPresentation(Contract):
    chief_complaint: LocalizedText | None = None
    onset: LocalizedText | None = None
    duration: LocalizedText | None = None
    severity: LocalizedText | None = None
    symptoms: list[ClinicalSymptom] = Field(default_factory=list, max_length=24)


class ClinicalHistoryItem(Contract):
    knowledge: Literal["unknown", "none", "present"]
    entries: list[HistoryEntry] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def consistent(self):
        unique(self.entries)
        if self.knowledge != "present" and self.entries:
            raise ValueError("Only present history can contain entries")
        return self


class ClinicalHistory(Contract):
    past_conditions: ClinicalHistoryItem | None = None
    surgeries: ClinicalHistoryItem | None = None
    medications: ClinicalHistoryItem | None = None
    allergies: ClinicalHistoryItem | None = None
    family: ClinicalHistoryItem | None = None
    social: ClinicalHistoryItem | None = None


class ScenarioDraftV4(Contract):
    version: Literal[4] = 4
    code: Code
    title: Label | None = None
    learner_label: Label | None = None
    specialty: Label | None = None
    source_language: LanguageTag = "en"
    patient: PatientV3 | None = None
    presentation: ClinicalPresentation | None = None
    history: ClinicalHistory | None = None
    vitals: Vitals | None = None
    localizations: dict[LanguageTag, Localization] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value):
        if isinstance(value, dict) and "version" in value and type(value["version"]) is not int:
            raise ValueError("Integer schema version required")
        return value

    @model_validator(mode="after")
    def bounded(self):
        if self.presentation:
            unique(self.presentation.symptoms)
        check_size(self.model_dump(mode="json", exclude_none=True))
        return self


class BackgroundEntry(Contract):
    id: Literal["food_drink", "sleep_activity", "work_home", "personality", "additional"]
    text: LocalizedText
    allow_variation: bool = Field(default=False, strict=True)
    choices: list[HistoryEntry] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def bounded(self):
        unique(self.choices)
        if any(len(text) > 240 for text in self.text.root.values()):
            raise ValueError("Keep background entries within 240 characters per language")
        if any(len(text) > 160 for choice in self.choices for text in choice.text.root.values()):
            raise ValueError("Keep everyday choices within 160 characters per language")
        if self.allow_variation and not self.choices:
            raise ValueError("Flexible background requires author-supplied everyday choices")
        return self


class ScenarioDraftV5(ScenarioDraftV4):
    version: Literal[5] = 5  # type: ignore[assignment]
    background: list[BackgroundEntry] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def background_ids(self):
        unique(self.background)
        return self


ClinicalCase = Annotated[ScenarioDraftV4 | ScenarioDraftV5, Field(discriminator="version")]


def clinical_issues(case):
    from training_contracts.localized_cases import localized_values

    issues = []

    def missing(path):
        issues.append(
            Issue(
                path=path.split("."),
                code="required_for_publication",
                message="Complete this field before publication",
            )
        )

    data = case.model_dump(mode="json", exclude_none=True)
    for path in (
        "title",
        "learner_label",
        "patient.name",
        "patient.age_years",
        "presentation.chief_complaint",
        "history.medications",
        "history.allergies",
    ):
        value = data
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is None:
            missing(path)
    if any(case.source_language not in value.root for value in localized_values(case)):
        missing("source_language")
    if case.presentation:
        for index, symptom in enumerate(case.presentation.symptoms):
            if symptom.description is None:
                missing(f"presentation.symptoms.{index}.description")
    if case.history:
        for key in ClinicalHistory.model_fields:
            item = getattr(case.history, key)
            if item and item.knowledge == "present" and not item.entries:
                missing(f"history.{key}.entries")
    return issues


def simplify_case(document):
    """Explicit migration/import conversion; public writes never silently drop fields."""
    if document.get("version") == 5:
        return ScenarioDraftV5.model_validate(document).model_dump(mode="json", exclude_none=True)
    old = deepcopy(document)
    result = {key: old[key] for key in ScenarioDraftV4.model_fields if key in old}
    result.update(version=4, localizations={})
    result.setdefault("source_language", "en")
    if old.get("version") == 1:
        result["presentation"] = {"chief_complaint": old.get("persona"), "symptoms": []}
        result.setdefault("learner_label", "Patient interview")
    for symptom in (result.get("presentation") or {}).get("symptoms", []):
        symptom.pop("disclosure", None)
    for item in (result.get("history") or {}).values():
        if item is None:
            continue
        item.pop("disclosure", None)
        item["entries"] = [
            entry if "id" in entry else {"id": f"entry_{i + 1}", "text": entry}
            for i, entry in enumerate(item.get("entries", []))
        ]
    return ScenarioDraftV4.model_validate(result).model_dump(mode="json", exclude_none=True)


class ClinicalRuntime(Contract):
    version: Literal[2] = 2
    case: ClinicalCase

    @property
    def greeting(self):
        return Bilingual(en="Hello.", hi="नमस्ते।")

    @property
    def clarification(self):
        return Bilingual(en="Could you explain what you mean?", hi="क्या आप बता सकते हैं कि आपका क्या मतलब है?")

    @property
    def rubric(self):
        # Legacy completed-session feedback can still use its old contract.
        return []

    def patient(self):
        return self.model_dump(mode="json")


def parse_runtime(document):
    return (
        ClinicalRuntime.model_validate(document)
        if document.get("version") == 2
        else Scenario.model_validate(document)
    )
