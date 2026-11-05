"""Pack isolation and translation provenance; no live model is needed for these rules."""

from copy import deepcopy

import pytest
from test_patient_conversation import CASES, document
from training_contracts.languages import LanguageRegistry, LocalizedText, get_pack
from training_contracts.languages.capabilities import resolve_capabilities
from training_contracts.localized_cases import (
    ScenarioDraftV3,
    convert_v2,
    localization_ready,
    prevent_review_forgery,
    review_localization,
)
from training_contracts.patient_conversation import conversation_context, resolved_language
from training_contracts.scenarios import patient_preview


def second_pack():
    return get_pack("en").model_copy(
        update={
            "language": "fr",
            "name": "Test French",
            "native_name": "Test French",
            "speech_locales": ("fr-FR",),
            "instructions": "TEST PACK INSTRUCTIONS",
            "unknown": "TEST UNCERTAINTY",
        }
    )


def test_registered_language_is_explicit_and_pinned():
    pack = get_pack("en")
    assert resolved_language("en", "Bonjour") == "en"
    for value in ("auto", "hi", "../en", "EN", "en-XX"):
        with pytest.raises(ValueError):
            resolved_language(value)
    with pytest.raises(ValueError):
        get_pack("en", version="99.0.0")
    with pytest.raises(ValueError):
        get_pack("en", content_hash="0" * 64)
    assert get_pack("en", version=pack.version, content_hash=pack.content_hash) is pack
    with pytest.raises(ValueError):
        LanguageRegistry([pack, pack])


def test_generic_text_and_pack_normalization_preserve_meaning():
    value = LocalizedText.model_validate({"en": "No fever; 0.5 mg", "fr": "TEST", "zh-Hant-TW": "TEST"})
    assert value.text("en") == "No fever; 0.5 mg"
    with pytest.raises(ValueError):
        value.text("hi")
    for invalid in ({"auto": "x"}, {"en": " "}, {"en": "x\x00"}, {}):
        with pytest.raises(ValueError):
            LocalizedText.model_validate(invalid)
    pack = get_pack("en")
    assert pack.normalize("  No fever; 0.5 mg  ") == "No fever; 0.5 mg"
    assert pack.spoken_text("0.5 mg, 72 bpm; no fever") == "0.5 milligrams, 72 beats per minute; no fever"
    assert pack.spoken_text("mgmt") == "mgmt"


@pytest.mark.parametrize("row", CASES, ids=lambda row: row["code"])
def test_conversion_preserves_all_permitted_case_values(row):
    old = row["document"]
    converted = convert_v2(old, review_languages=["en"])
    before, after = patient_preview(old), patient_preview(converted)
    before["version"] = 3
    # Legacy projections include explicit None for absent optional text.
    assert before == after
    assert localization_ready(converted, "en")
    assert not localization_ready(converted, "hi")
    assert ScenarioDraftV3.model_validate(converted).patient.age_years == old["patient"]["age_years"]


def test_source_and_translation_edits_invalidate_review_and_drafts_cannot_forge_it():
    converted = convert_v2(document(), review_languages=["en", "hi"])
    changed = deepcopy(converted)
    changed["patient"]["age_years"] += 1
    assert not localization_ready(changed, "en") and not localization_ready(changed, "hi")
    with pytest.raises(ValueError, match="stale"):
        conversation_context(changed, "en", "How old are you?")
    changed = deepcopy(converted)
    changed["presentation"]["chief_complaint"]["hi"] += " CHANGED"
    assert localization_ready(changed, "en") and not localization_ready(changed, "hi")
    assert (
        prevent_review_forgery({**converted, "localizations": {}}, converted)["localizations"]
        == converted["localizations"]
    )
    with pytest.raises(ValueError, match="server managed"):
        prevent_review_forgery(converted)
    with pytest.raises(ValueError, match="server managed"):
        prevent_review_forgery(review_localization(converted, "en"), converted)


def test_missing_translation_is_never_dropped_or_silently_substituted():
    value = document()
    value["presentation"]["chief_complaint"] = {"hi": "TEST"}
    with pytest.raises(ValueError, match="translation"):
        conversation_context(value, "en", "What is wrong?")


def test_second_pack_uses_same_compiler_without_language_branches():
    from training_contracts.localized_cases import localized_values

    value = ScenarioDraftV3.model_validate(convert_v2(document()))
    for text in localized_values(value):
        text.root["fr"] = text.root["en"]
    doc = review_localization(value.model_dump(mode="json", exclude_none=True), "fr")
    registry = LanguageRegistry([get_pack("en"), second_pack()])
    prompt = conversation_context(doc, "fr", "TEST QUESTION", registry=registry)
    assert "TEST PACK INSTRUCTIONS" in prompt["system"]
    assert "TEST UNCERTAINTY" in prompt["system"]
    assert "Use everyday spoken English" not in prompt["system"]
    assert prompt["language"] == "fr" and prompt["language_pack_hash"] == second_pack().content_hash


def test_readiness_distinguishes_text_recognition_and_voice():
    options = dict(enabled=True, localized=True, llm_languages=["en"])
    result = resolve_capabilities(get_pack("en"), **options, asr_locales=["en-IN"])
    assert result.text and result.voice_input and not result.voice_output
    assert result.reasons == ("voice_unavailable",)
    result = resolve_capabilities(
        get_pack("en"), **{**options, "localized": False}, asr_locales=["en-IN"], tts_locales=["en-US"]
    )
    assert not result.text and not result.voice_input and not result.voice_output
    assert "case_translation_unavailable" in result.reasons
