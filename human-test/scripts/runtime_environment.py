"""Keep backend credentials out of desktop process environments."""

import os


def provider_free_environment(values=None):
    inherited = os.environ if values is None else values
    return {
        key: value
        for key, value in inherited.items()
        if not key.upper().startswith(
            ("PMS_", "PG", "DATABASE_URL", "OPENAI_", "AZURE_", "AWS_", "ANTHROPIC_")
        )
    }


def client_environment():
    return {
        key: value
        for key, value in provider_free_environment().items()
        if not key.upper().startswith(("HUMAN_", "AUDIO_", "VIDEO_", "CUDA_"))
    }


def desktop_environment(values):
    inherited = {
        key: value
        for key, value in provider_free_environment().items()
        if not key.upper().startswith(("HUMAN_", "AUDIO_", "VIDEO_"))
    }
    # Windows CreateProcess requires strings; internal settings include numeric ports.
    desktop = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in values.items()
        if value is not None
    }
    return {**inherited, **desktop}
