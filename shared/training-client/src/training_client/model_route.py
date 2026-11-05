"""Desktop speech capabilities for the platform's device execution snapshots."""


def interactive_speech(route):
    audio = (route or {}).get("audio", {})
    mode = audio.get("mode", "local")
    provider = audio.get("provider", "azure_openai" if mode == "cloud" else "local_whisper")
    return bool(audio.get("enabled", True)) and (mode, provider) in {
        ("local", "local_whisper"),
        ("cloud", "azure_openai"),
    }
