"""Language contracts contain no provider, tenant, or clinical state."""

import hashlib
import json
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

LanguageTag = Annotated[
    str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-[0-9]{3})?$", max_length=24)
]
Text = Annotated[str, Field(min_length=1, max_length=600)]


class LocalizedText(RootModel[dict[LanguageTag, Text]]):
    """A bounded generic language map; no automatic translation fallback."""

    @model_validator(mode="after")
    def bounded(self):
        if not 1 <= len(self.root) <= 8:
            raise ValueError("Localized text requires one to eight languages")
        for value in self.root.values():
            if not value.strip() or "\x00" in value:
                raise ValueError("Invalid localized text")
            value.encode("utf-8")
        return self

    def text(self, language: str) -> str:
        if language not in self.root:
            raise ValueError("Case translation is missing for the selected language")
        return self.root[language]


class LanguagePack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: LanguageTag
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    contract_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=80)
    native_name: str = Field(min_length=1, max_length=80)
    direction: Literal["ltr", "rtl"] = "ltr"
    speech_locales: tuple[LanguageTag, ...] = Field(min_length=1, max_length=16)
    instructions: str = Field(min_length=1, max_length=4000)
    unknown: str = Field(min_length=1, max_length=200)
    clarification: str = Field(min_length=1, max_length=200)
    boundary: str = Field(min_length=1, max_length=200)
    # Immutable tuples rather than a mutable dict inside a frozen model.
    pronunciation: tuple[tuple[str, str], ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def consistent(self):
        if any(locale.split("-")[0] != self.language.split("-")[0] for locale in self.speech_locales):
            raise ValueError("Speech locale does not match the language pack")
        if len(set(self.speech_locales)) != len(self.speech_locales):
            raise ValueError("Duplicate speech locale")
        if len({key for key, _ in self.pronunciation}) != len(self.pronunciation):
            raise ValueError("Duplicate pronunciation term")
        if any(
            not key or not value or len(key) > 64 or len(value) > 120 for key, value in self.pronunciation
        ):
            raise ValueError("Invalid pronunciation term")
        raw = self.model_dump_json()
        if "\\u0000" in raw:
            raise ValueError("Invalid language pack text")
        raw.encode("utf-8")
        return self

    @property
    def content_hash(self) -> str:
        raw = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def normalize(self, text: str) -> str:
        # NFC leaves numerical meaning and compatibility characters intact.
        if not isinstance(text, str) or "\x00" in text:
            raise ValueError("Invalid conversation text")
        text.encode("utf-8")
        return unicodedata.normalize("NFC", text).strip()

    def spoken_text(self, text: str) -> str:
        import re

        text = self.normalize(text)
        for term, spoken in self.pronunciation:
            text = re.sub(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lambda _, value=spoken: value, text)
        return text
