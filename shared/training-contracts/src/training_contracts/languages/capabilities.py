"""Deterministic readiness; listing a language is not evidence of model quality."""

from dataclasses import dataclass

from .contracts import LanguagePack


@dataclass(frozen=True)
class CapabilityResult:
    language: str
    pack_version: str
    pack_hash: str
    text: bool
    voice_input: bool
    voice_output: bool
    reasons: tuple[str, ...]


def resolve_capabilities(
    pack: LanguagePack, *, enabled: bool, localized: bool, llm_languages, asr_locales=(), tts_locales=()
) -> CapabilityResult:
    reasons = []
    if not enabled:
        reasons.append("language_disabled")
    if not localized:
        reasons.append("case_translation_unavailable")
    if pack.language not in llm_languages:
        reasons.append("model_language_unavailable")
    text = not reasons
    voice_input = bool(set(pack.speech_locales).intersection(asr_locales))
    voice_output = bool(set(pack.speech_locales).intersection(tts_locales))
    if not voice_input:
        reasons.append("recognition_unavailable")
    if not voice_output:
        reasons.append("voice_unavailable")
    return CapabilityResult(
        pack.language,
        pack.version,
        pack.content_hash,
        text,
        text and voice_input,
        text and voice_output,
        tuple(reasons),
    )
