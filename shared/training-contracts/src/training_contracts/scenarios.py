"""Authoring contracts. The existing version-1 runtime contract remains unchanged."""

from string import Formatter
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from training_contracts import Code, Contract, RubricItem, Scenario, canonical

Text = Annotated[str, Field(min_length=1, max_length=600)]
Label = Annotated[str, Field(min_length=1, max_length=120)]
Disclosure = Literal["volunteered", "on_question", "never"]
FactPath = Literal[
    "patient.name",
    "patient.age_years",
    "patient.height_cm",
    "patient.weight_kg",
    "vitals.temperature_c",
    "vitals.heart_rate_bpm",
    "vitals.pulse_bpm",
    "vitals.systolic_mmhg",
    "vitals.diastolic_mmhg",
    "vitals.respirations_per_minute",
    "vitals.spo2_percent",
    "vitals.pain_0_10",
]
FACT_PATHS = frozenset(FactPath.__args__)
# Patient speech that carries no case fact of its own; each may reference volunteered facts only.
SPOKEN_REPLIES = ("greeting", "clarification", "backchannel", "command_ack", "boundary")


class DraftBilingual(Contract):
    en: Text | None = None
    hi: Text | None = None


class Patient(Contract):
    name: Label | None = None
    age_years: Annotated[int, Field(strict=True, ge=0, le=150)] | None = None
    sex: Literal["female", "male", "intersex", "unspecified"] | None = None
    occupation: DraftBilingual | None = None
    height_cm: Annotated[float, Field(strict=True, gt=0, le=400, allow_inf_nan=False)] | None = None
    weight_kg: Annotated[float, Field(strict=True, gt=0, le=2000, allow_inf_nan=False)] | None = None


class Symptom(Contract):
    id: Code
    description: DraftBilingual | None = None
    disclosure: Disclosure = "on_question"


class Presentation(Contract):
    chief_complaint: DraftBilingual | None = None
    symptoms: list[Symptom] = Field(default_factory=list, max_length=24)
    onset: DraftBilingual | None = None
    duration: DraftBilingual | None = None
    severity: DraftBilingual | None = None


class HistoryItem(Contract):
    knowledge: Literal["unknown", "none", "present"]
    entries: list[DraftBilingual] = Field(default_factory=list, max_length=16)
    disclosure: Disclosure = "on_question"

    @model_validator(mode="after")
    def consistent(self):
        if self.knowledge != "present" and self.entries:
            raise ValueError("only present history can contain entries")
        return self


class History(Contract):
    past_conditions: HistoryItem | None = None
    surgeries: HistoryItem | None = None
    medications: HistoryItem | None = None
    allergies: HistoryItem | None = None
    family: HistoryItem | None = None
    social: HistoryItem | None = None


Rate = Annotated[float, Field(strict=True, ge=0, le=1000, allow_inf_nan=False)]


class Vitals(Contract):
    temperature_c: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None = None
    heart_rate_bpm: Rate | None = None
    pulse_bpm: Rate | None = None
    systolic_mmhg: Rate | None = None
    diastolic_mmhg: Rate | None = None
    respirations_per_minute: Rate | None = None
    spo2_percent: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None = None
    pain_0_10: Annotated[float, Field(strict=True, ge=0, le=10, allow_inf_nan=False)] | None = None


class DraftTopic(Contract):
    id: Code
    intent: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    examples: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=8
    )
    answer: DraftBilingual | None = None


class PatientTopic(DraftTopic):
    disclosure: Disclosure = "on_question"


class Dialogue(Contract):
    greeting: DraftBilingual | None = None
    clarification: DraftBilingual | None = None
    # Spoken replies for utterances that ask for no case fact; runtime falls back to clarification.
    backchannel: DraftBilingual | None = None
    command_ack: DraftBilingual | None = None
    boundary: DraftBilingual | None = None
    topics: list[PatientTopic] = Field(default_factory=list, max_length=32)


class Instructor(Contract):
    objectives: list[Text] = Field(default_factory=list, max_length=16)
    notes: Annotated[str, Field(max_length=4000)] | None = None
    diagnosis: Label | None = None
    rubric: list[RubricItem] = Field(default_factory=list, max_length=24)


def unique(rows):
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("duplicate identifiers")


def check_text(value):
    """Reject text PostgreSQL JSONB cannot store, before submitting any SQL."""
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("null characters are not supported")
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_text(key)
            check_text(item)
    elif isinstance(value, list):
        for item in value:
            check_text(item)


def check_size(document: dict):
    check_text(document)
    if len(canonical(document).encode("utf-8")) > (384000 if document.get("version") in (3, 4, 5) else 48000):
        raise ValueError("scenario exceeds document budget")


def references(text: str) -> list[str]:
    """Only explicit scalar names: never getattr, eval, format traversal or expressions."""
    result = []
    for _, field, spec, conversion in Formatter().parse(text):
        if field is not None:
            if field not in FACT_PATHS or spec or conversion:
                raise ValueError("unsupported patient fact reference")
            result.append(field)
    return result


class ScenarioDraftV1(Contract):
    version: Literal[1] = 1
    code: Code
    title: Label | None = None
    persona: DraftBilingual | None = None
    greeting: DraftBilingual | None = None
    clarification: DraftBilingual | None = None
    topics: list[DraftTopic] = Field(default_factory=list, max_length=32)
    rubric: list[RubricItem] = Field(default_factory=list, max_length=24)

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value):
        if isinstance(value, dict) and "version" in value and type(value["version"]) is not int:
            raise ValueError("integer schema version required")
        return value

    @model_validator(mode="after")
    def bounded(self):
        unique(self.topics)
        unique(self.rubric)
        check_size(self.model_dump(mode="json", exclude_none=True))
        return self


class ScenarioDraftV2(Contract):
    version: Literal[2] = 2
    code: Code
    title: Label | None = None
    learner_label: Label | None = None
    specialty: Label | None = None
    patient: Patient | None = None
    presentation: Presentation | None = None
    history: History | None = None
    vitals: Vitals | None = None
    dialogue: Dialogue | None = None
    instructor: Instructor | None = None
    fact_disclosure: dict[FactPath, Disclosure] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value):
        if isinstance(value, dict) and "version" in value and type(value["version"]) is not int:
            raise ValueError("integer schema version required")
        return value

    @model_validator(mode="after")
    def bounded(self):
        if self.presentation:
            unique(self.presentation.symptoms)
        if self.instructor:
            unique(self.instructor.rubric)
        if self.dialogue:
            unique(self.dialogue.topics)
            texts = [(getattr(self.dialogue, name), "volunteered") for name in SPOKEN_REPLIES]
            texts.extend((topic.answer, topic.disclosure) for topic in self.dialogue.topics)
            for value, disclosure in texts:
                for text in value.model_dump(exclude_none=True).values() if value else []:
                    for path in references(text):
                        policy = self.fact_disclosure.get(path, "never")
                        if policy == "never" or (disclosure == "volunteered" and policy != "volunteered"):
                            raise ValueError("answer references a fact outside its disclosure policy")
        check_size(self.model_dump(mode="json", exclude_none=True))
        return self


def parse_draft(document: dict):
    version = document.get("version")
    if type(version) is not int or version not in (1, 2, 3, 4, 5):
        raise ValueError("unsupported scenario schema version")
    if version in (4, 5):
        from training_contracts.clinical_cases import ScenarioDraftV4, ScenarioDraftV5

        return (ScenarioDraftV5 if version == 5 else ScenarioDraftV4).model_validate(document)
    if version == 3:
        from training_contracts.localized_cases import ScenarioDraftV3

        return ScenarioDraftV3.model_validate(document)
    model = ScenarioDraftV1 if version == 1 else ScenarioDraftV2
    return model.model_validate(document)


def normalize_draft(document: dict) -> dict:
    return parse_draft(document).model_dump(mode="json", exclude_none=True)


class Issue(Contract):
    path: list[str | int]
    code: str
    message: str


def publication_issues(case: ScenarioDraftV2) -> list[Issue]:
    if case.version in (4, 5):
        from training_contracts.clinical_cases import clinical_issues

        return clinical_issues(case)
    issues = []

    def missing(path):
        issues.append(
            Issue(
                path=path,
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
        "dialogue.greeting",
        "dialogue.clarification",
        "dialogue.topics",
        "instructor.objectives",
        "instructor.rubric",
    ):
        value = data
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is None or value == []:
            missing(path.split("."))

    def visit(value, path):
        from training_contracts.languages.contracts import LocalizedText

        if isinstance(value, LocalizedText):
            if case.source_language not in value.root:
                missing(path + [case.source_language])
        elif isinstance(value, DraftBilingual):
            for language in ("en", "hi"):
                if getattr(value, language) is None:
                    missing(path + [language])
        elif isinstance(value, Contract):
            for key in type(value).model_fields:
                visit(getattr(value, key), path + [key])
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, path + [index])

    visit(case, [])
    if case.history:
        for key in History.model_fields:
            value = getattr(case.history, key)
            if value and value.knowledge == "present" and not value.entries:
                missing(["history", key, "entries"])
    if case.presentation:
        for i, symptom in enumerate(case.presentation.symptoms):
            if symptom.description is None:
                missing(["presentation", "symptoms", i, "description"])
    if case.dialogue:
        for i, topic in enumerate(case.dialogue.topics):
            for key in ("intent", "examples", "answer"):
                if not getattr(topic, key):
                    missing(["dialogue", "topics", i, key])
        for value in [
            *(getattr(case.dialogue, name) for name in SPOKEN_REPLIES),
            *(t.answer for t in case.dialogue.topics),
        ]:
            for text in value.model_dump(exclude_none=True).values() if value else []:
                for path in references(text):
                    group, key = path.split(".")
                    if data.get(group, {}).get(key) is None:
                        missing(path.split("."))
    return issues


class PublishedScenarioV2(ScenarioDraftV2):
    @model_validator(mode="after")
    def complete(self):
        if publication_issues(self):
            raise ValueError("scenario is incomplete for publication")
        return self


def validate_publication(document: dict) -> list[Issue]:
    case = parse_draft(document)
    if isinstance(case, ScenarioDraftV2) or case.version in (4, 5):
        return publication_issues(case)
    try:
        Scenario.model_validate(document)
    except ValidationError as exc:
        return [
            Issue(
                path=list(e["loc"]),
                code=e["type"],
                message="Complete or correct this field before publication",
            )
            for e in exc.errors()
        ]
    return []


def render_text(value: DraftBilingual | None, document: dict) -> dict:
    rendered = {}
    from training_contracts.languages.contracts import LocalizedText

    if value is not None and hasattr(value, "id") and hasattr(value, "text"):
        value = value.text
    texts = (
        value.root
        if isinstance(value, LocalizedText)
        else (value.model_dump() if value else {"en": None, "hi": None})
    )
    for language, text in texts.items():
        if text is None:
            rendered[language] = None
            continue
        parts = []
        for literal, field, _, _ in Formatter().parse(text):
            parts.append(literal)
            if field is not None:
                group, key = field.split(".")
                fact = document.get(group, {}).get(key)
                if fact is None:
                    break
                parts.append(str(fact))
        else:
            rendered[language] = "".join(parts)
            continue
        rendered[language] = None
    return rendered


def patient_preview(document: dict) -> dict:
    case = parse_draft(document)
    if case.version in (4, 5):
        return case.model_dump(
            mode="json",
            include={"version", "patient", "presentation", "history", "vitals", "background"},
            exclude_none=True,
        )
    if isinstance(case, ScenarioDraftV1):
        return case.model_dump(mode="json", exclude={"rubric", "code", "title"}, exclude_none=True)
    # Explicit projection; instructor content and concealed material are never returned.
    dialogue = case.dialogue or Dialogue()
    presentation = case.presentation or Presentation()
    return {
        "version": case.version,
        **{name: render_text(getattr(dialogue, name), document) for name in SPOKEN_REPLIES},
        "presentation": {
            "chief_complaint": render_text(presentation.chief_complaint, document),
            **{
                key: render_text(getattr(presentation, key), document)
                for key in ("onset", "duration", "severity")
            },
            "symptoms": [
                {"id": s.id, "description": render_text(s.description, document)}
                for s in presentation.symptoms
                if s.disclosure != "never"
            ],
        },
        "history": {
            key: {
                "knowledge": item.knowledge,
                "entries": [render_text(entry, document) for entry in item.entries],
            }
            for key, item in ((k, getattr(case.history or History(), k)) for k in History.model_fields)
            if item and item.disclosure != "never"
        },
        "topics": [
            {
                "id": topic.id,
                "disclosure": topic.disclosure,
                "answer": render_text(topic.answer, document),
            }
            for topic in dialogue.topics
            if topic.disclosure != "never"
        ],
        "facts": [
            {
                "reference": path,
                "disclosure": policy,
                "value": document.get(path.split(".")[0], {}).get(path.split(".")[1]),
            }
            for path, policy in case.fact_disclosure.items()
            if policy != "never"
        ],
    }
