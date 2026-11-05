"""Only trusted bundled resources are executable language packs."""

import json
from importlib.resources import files

from .contracts import LanguagePack


class LanguageRegistry:
    def __init__(self, packs):
        self._packs = {}
        for pack in packs:
            if not isinstance(pack, LanguagePack) or pack.language in self._packs:
                raise ValueError("Invalid or duplicate language pack")
            self._packs[pack.language] = pack

    def get(
        self, language: str, *, version: str | None = None, content_hash: str | None = None
    ) -> LanguagePack:
        pack = self._packs.get(language)
        if pack is None:
            raise ValueError("Conversation language is unavailable; select an installed language")
        if version is not None and pack.version != version:
            raise ValueError("Conversation language pack version is unavailable")
        if content_hash is not None and pack.content_hash != content_hash:
            raise ValueError("Conversation language pack content changed")
        return pack

    def all(self) -> tuple[LanguagePack, ...]:
        return tuple(self._packs.values())


def bundled_pack(name):
    # Only this code-owned list calls the loader. No request supplies name or resource paths.
    root = files("training_contracts.languages").joinpath("packs", name)
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    return LanguagePack.model_validate(
        {
            **manifest,
            **json.loads(root.joinpath("phrases.json").read_text(encoding="utf-8")),
            "instructions": root.joinpath("instructions.txt").read_text(encoding="utf-8").strip(),
            "pronunciation": json.loads(root.joinpath("pronunciation.json").read_text(encoding="utf-8")),
        }
    )


DEFAULT_REGISTRY = LanguageRegistry([bundled_pack("en")])


def get_pack(language: str, **references) -> LanguagePack:
    return DEFAULT_REGISTRY.get(language, **references)
