"""Declared recognizer capabilities; runtime readiness must still verify installation."""

# Speech adapters own model restrictions. Conversation orchestration does not branch
# on language IDs or infer language from a transcript.
MODEL_LANGUAGES = {
    "whisper-medical-v1": ("en",),
    "vosk-model-small-en-us-0.15": ("en",),
    "vosk-model-small-hi-0.22": ("hi",),
    "large-v3": ("en", "hi"),
    "large-v3-turbo": ("en", "hi"),
    "medium": ("en", "hi"),
    "small": ("en", "hi"),
    "base": ("en", "hi"),
    "tiny": ("en", "hi"),
    "nemotron-3.5-asr-streaming-0.6b": ("en",),
}


def recognition_languages(model):
    return MODEL_LANGUAGES.get(model, ())
