"""Pure request checks shared by admission, workers and cloud adapters."""

from typing import TypedDict

from pms_api.core.common import require


class SynthesisContract(TypedDict):
    formats: set[str]
    max_characters: int
    default_language: str
    voices: dict[str, str]


SYNTHESIS: dict[str, SynthesisContract] = {
    "aws_polly": {
        "formats": {"mp3", "ogg", "pcm", "wav"},
        "max_characters": 3000,
        "default_language": "en-IN",
        "voices": {"en-IN": "Aditi", "hi-IN": "Aditi", "en-US": "Joanna"},
    },
    "azure_speech": {
        "formats": {"mp3", "wav", "pcm"},
        # Application request limit; this is not a claim about the provider quota.
        "max_characters": 10000,
        "default_language": "en-US",
        "voices": {"en-IN": "en-IN-NeerjaNeural", "hi-IN": "hi-IN-SwaraNeural", "en-US": "en-US-JennyNeural"},
    },
}


def synthesis_parameters(engine, section, request) -> dict[str, str]:
    contract = SYNTHESIS[engine]
    output_format = section.get("format") or "mp3"
    require(
        isinstance(output_format, str) and output_format in contract["formats"],
        "unsupported_format",
        "Synthesis format is unsupported for this engine",
    )
    text = request.get("text")
    require(isinstance(text, str) and bool(text), "text_required", "Supply text for synthesis")
    require(
        len(text) <= contract["max_characters"],
        "text_too_long",
        "Synthesis text exceeds this engine's request limit",
    )
    language = section.get("language") or contract["default_language"]
    require(isinstance(language, str), "invalid_language", "Configure a valid speech language")
    voice = section.get("voice") or contract["voices"].get(language)
    require(isinstance(voice, str) and bool(voice), "voice_required", "Configure a voice for this language")
    assert isinstance(voice, str)
    return {"format": output_format, "language": language, "voice": voice}


def validate_submission(engine, operation, section, request):
    if operation == "audio.synthesize" and engine in SYNTHESIS:
        synthesis_parameters(engine, section, request)
