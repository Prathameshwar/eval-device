"""Editable, language-specific whole-utterance filter; never edits meaningful input."""

import json
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from training_contracts.languages import LanguageTag

DEFAULT_DICTIONARY = Path(__file__).with_name("input-ignore.json")
MAX_DICTIONARY_BYTES = 65536
# Questions, digits, operators and emoji remain tokens and therefore pass through.
SEPARATORS = str.maketrans(
    dict.fromkeys(".,!;:\u2026\u060c\u3002\uff01\uff0c\uff1b\uff1a\u201c\u201d\u2018\u2019\"'()[]", " ")
)


def words(text: str) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", text).casefold().translate(SEPARATORS).split())


class LanguageRules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    repeat_last_letter: bool = True
    fillers: list[str] = Field(max_length=128)
    acknowledgements: list[str] = Field(max_length=128)

    @field_validator("fillers", "acknowledgements")
    @classmethod
    def literal_phrases(cls, entries: list[str], info: ValidationInfo) -> list[str]:
        for entry in entries:
            if not 1 <= len(entry) <= 80 or not entry.strip():
                raise ValueError("Dictionary phrases must contain 1 to 80 characters")
            if any(not (char.isalpha() or char.isspace()) for char in entry):
                raise ValueError("Dictionary phrases contain only letters and spaces")
            if info.field_name == "fillers" and len(entry.split()) != 1:
                raise ValueError("Fillers must be single words")
        return entries

    def ignores(self, text: str) -> bool:
        tokens = words(text)
        if not self.enabled or not tokens:
            return False
        fillers = {words(entry)[0] for entry in self.fillers}
        phrases = {words(entry) for entry in self.acknowledgements}
        by_first: dict[str, list[tuple[str, ...]]] = {}
        for phrase in phrases:
            by_first.setdefault(phrase[0], []).append(phrase)
        reachable = {0}
        for index, token in enumerate(tokens):
            if index not in reachable:
                continue
            filler = token in fillers or (
                self.repeat_last_letter
                and any(
                    token.startswith(entry) and set(token[len(entry) :]) <= {entry[-1]} for entry in fillers
                )
            )
            if filler:
                reachable.add(index + 1)
            for phrase in by_first.get(token, ()):
                end = index + len(phrase)
                if tokens[index:end] == phrase:
                    reachable.add(end)
        return len(tokens) in reachable


class Dictionary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int = Field(ge=1, le=1)
    languages: dict[LanguageTag, LanguageRules] = Field(min_length=1, max_length=8)


class InputFilterError(ValueError):
    pass


class InputFilter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._raw: bytes | None = None
        self._dictionary: Dictionary | None = None

    def ignores(self, text: str, language: str) -> bool:
        """Reload edits on the next input. A broken dictionary never silently disables filtering."""
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_DICTIONARY_BYTES + 1)
            if len(raw) > MAX_DICTIONARY_BYTES:
                raise ValueError("Dictionary exceeds size limit")
            if raw != self._raw:
                # Explicitly decode UTF-8; accept the BOM some Windows editors add.
                document = Dictionary.model_validate(json.loads(raw.decode("utf-8-sig")))
                self._dictionary, self._raw = document, raw
        except (OSError, ValueError):
            raise InputFilterError(
                "Input ignore dictionary is invalid or unreadable: " + str(self.path)
            ) from None
        assert self._dictionary is not None
        rules = self._dictionary.languages.get(language)
        return rules.ignores(text) if rules is not None else False
