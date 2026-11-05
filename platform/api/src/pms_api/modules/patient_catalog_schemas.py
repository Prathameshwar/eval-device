"""Bounded fictional tenant catalog forms and simplified clinical cases."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator
from training_contracts.clinical_cases import ClinicalCase
from training_contracts.languages import LanguageTag
from training_contracts.scenarios import check_text

from pms_api.modules.schemas import Input

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Names = dict[LanguageTag, Label]


class CatalogInput(Input):
    @model_validator(mode="after")
    def storage_text(self):
        check_text(self.model_dump(mode="json"))
        return self


class CategoryInput(CatalogInput):
    code: Code
    name: Label
    names: Names = Field(min_length=1, max_length=8)
    description: Text
    sort_order: int = Field(0, ge=0, le=10000)
    is_active: bool = True

    @model_validator(mode="after")
    def english_name(self):
        if self.names.get("en") != self.name:
            raise ValueError("The English name must match the display name")
        return self


class PatientInput(CatalogInput):
    code: Code
    name: Label
    names: Names = Field(min_length=1, max_length=8)
    age_years: int = Field(ge=0, le=150, strict=True)
    sex: Literal["female", "male", "intersex", "unspecified"]
    occupations: dict[LanguageTag, Text] = Field(min_length=1, max_length=8)
    height_cm: float = Field(gt=0, le=400)
    weight_kg: float = Field(gt=0, le=2000)
    preferred_language: LanguageTag = "en"
    languages: list[LanguageTag] = Field(min_length=1, max_length=8)
    backgrounds: dict[LanguageTag, Text] = Field(min_length=1, max_length=8)
    is_active: bool = True

    @model_validator(mode="after")
    def translations(self):
        if self.names.get("en") != self.name:
            raise ValueError("The English name must match the display name")
        if len(set(self.languages)) != len(self.languages) or self.preferred_language not in self.languages:
            raise ValueError("Choose unique languages including the preferred language")
        if any(
            not set(self.languages) <= set(mapping)
            for mapping in (self.names, self.occupations, self.backgrounds)
        ):
            raise ValueError("Complete name, occupation and background for every profile language")
        return self


class CaseInput(CatalogInput):
    code: Code
    specialty_id: UUID
    patient_profile_id: UUID
    title: Label
    titles: dict[LanguageTag, Label] = Field(min_length=1, max_length=8)
    document: ClinicalCase
    is_active: bool = False

    @model_validator(mode="after")
    def identity(self):
        if (
            self.document.code != self.code
            or self.document.title != self.title
            or self.titles.get("en") != self.title
        ):
            raise ValueError("The case code and English title must match its document")
        return self


CatalogBody = CategoryInput | PatientInput | CaseInput


class CatalogUpdate(Input):
    expected_version: int = Field(gt=0)
    data: CatalogBody


class CatalogState(Input):
    expected_version: int = Field(gt=0)
