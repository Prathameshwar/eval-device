"""Versioned, bounded patient interview contracts shared by platform and companion."""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["en", "hi"]
Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Bilingual(Contract):
    en: str = Field(min_length=1, max_length=600)
    hi: str = Field(min_length=1, max_length=600)


class Topic(Contract):
    id: Code
    intent: str = Field(min_length=1, max_length=240)
    examples: list[str] = Field(min_length=1, max_length=8)
    answer: Bilingual

    @model_validator(mode="after")
    def bounded_examples(self):
        if any(not example or len(example) > 200 for example in self.examples):
            raise ValueError("examples must contain 1-200 characters")
        return self


class RubricItem(Contract):
    id: Code
    description: str = Field(min_length=1, max_length=300)


class Scenario(Contract):
    version: Literal[1] = 1
    code: Code
    title: str = Field(min_length=1, max_length=120)
    persona: Bilingual
    greeting: Bilingual
    clarification: Bilingual
    topics: list[Topic] = Field(min_length=1, max_length=32)
    rubric: list[RubricItem] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def unique_ids(self):
        for rows in (self.topics, self.rubric):
            if len({row.id for row in rows}) != len(rows):
                raise ValueError("duplicate identifiers")
        if len(canonical(self.model_dump(mode="json")).encode()) > 48000:
            raise ValueError("scenario too large")
        return self

    def patient(self) -> dict:
        return self.model_dump(mode="json", exclude={"rubric"})


class SessionCreate(Contract):
    request_key: UUID
    device_id: UUID
    learner_id: UUID
    scenario_id: UUID
    language: Language = "en"
    duration_seconds: int = Field(default=300, ge=30, le=600)


class ScenarioCreate(Contract):
    request_key: UUID
    scenario: Scenario


class Approval(Contract):
    educator_name: str = Field(min_length=2, max_length=100)
    statement: str = Field(min_length=20, max_length=1000)


class SessionResult(Contract):
    simulated: bool = False
    event_id: UUID
    status: Literal["completed", "failed", "cancelled"]
    turns: int = Field(ge=0, le=100)
    audio_recordings: list[UUID] = Field(default_factory=list, max_length=100)
    video_recordings: list[UUID] = Field(default_factory=list, max_length=10)
    recording_status: Literal["saved", "incomplete", "unavailable"]
    reason: Literal[
        "none",
        "operator_stop",
        "connection_lost",
        "authorization_expired",
        "processing_failed",
        "storage_failed",
    ] = "none"


class Feedback(Contract):
    expected_version: int = Field(ge=0)
    scores: dict[str, Literal["met", "partial", "not_met", "not_observed"]] = Field(max_length=24)
    comments: str = Field(default="", max_length=4000)


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()
