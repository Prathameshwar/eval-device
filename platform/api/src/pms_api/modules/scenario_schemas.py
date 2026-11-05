"""Explicit authoring requests and projections; no database-row serialization."""

from datetime import datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from training_contracts import Approval, Code, Contract
from training_contracts.clinical_cases import ClinicalCase
from training_contracts.languages import LanguageTag
from training_contracts.scenarios import Issue, check_text

Revision = Annotated[int, Field(strict=True, gt=0, le=2147483646)]
Document: TypeAlias = ClinicalCase


class DraftCreate(Contract):
    request_key: UUID
    code: Code
    schema_version: Literal[4, 5] | None = None
    document: Document | None = None
    source_scenario_id: UUID | None = None
    source_case_id: UUID | None = None
    specialty_id: UUID | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @model_validator(mode="after")
    def exclusive(self):
        if self.source_scenario_id is not None and self.source_case_id is not None:
            raise ValueError("Choose one source")
        if (
            self.source_scenario_id is not None or self.source_case_id is not None
        ) and self.model_fields_set & {"document", "schema_version"}:
            raise ValueError("copy cannot include schema version or content")
        if self.document and (
            self.document.code != self.code or self.schema_version not in (None, self.document.version)
        ):
            raise ValueError("document identity must match requested code and schema")
        if "schema_version" in self.model_fields_set and type(self.schema_version) is not int:
            raise ValueError("integer schema version required")
        return self


class DraftSave(Contract):
    expected_revision: Revision
    document: Document
    specialty_id: UUID | None = None


class DraftState(Contract):
    expected_revision: Revision
    is_archived: Annotated[bool, Field(strict=True)]


class DraftValidate(Contract):
    expected_revision: Revision


class DraftSubmit(DraftValidate):
    pass


class PublicationApproval(Approval):
    @model_validator(mode="after")
    def supported_text(self):
        check_text(self.model_dump())
        return self


class LocalizationReview(DraftValidate):
    approval: PublicationApproval


class DraftPublish(DraftValidate):
    request_key: UUID
    approval: PublicationApproval


class DraftSummary(Contract):
    id: UUID
    code: str
    schema_version: int
    title: str | None
    specialty: str | None
    revision: int
    is_archived: bool
    source_scenario_id: UUID | None
    source_case_id: UUID | None
    source_case_revision: int | None
    specialty_id: UUID | None
    workflow_version: int
    submitted_revision: int | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DraftView(DraftSummary):
    document: dict
    created_by: UUID
    updated_by: UUID


class DraftCreated(Contract):
    draft: DraftView
    replayed: bool


class DraftPage(Contract):
    items: list[DraftSummary]
    next_cursor: str | None


class SafeScenario(Contract):
    id: UUID
    title: str
    version: int
    schema_version: int
    languages: list[LanguageTag]
    approved: bool
    is_active: bool
    execution_supported: bool
    publication_source: Literal["tenant_review", "system_starter"]


class ScenarioSummary(SafeScenario):
    code: str
    specialty: str | None
    specialty_id: UUID | None


class ScenarioView(ScenarioSummary):
    document: dict
    fingerprint: str
    created_at: datetime
    created_by: UUID
    approved_at: datetime | None
    approved_by: UUID | None
    approval: Approval | None
    source_draft_id: UUID | None
    source_draft_revision: int | None
    starter_case_id: UUID | None


class ScenarioPage(Contract):
    items: list[ScenarioSummary | SafeScenario]
    next_cursor: str | None


class ScenarioPublished(Contract):
    scenario: ScenarioView
    replayed: bool


class ValidationView(Contract):
    draft_id: UUID
    revision: int
    publishable: bool
    errors: list[Issue]
    warnings: list[Issue]
    preview: dict
