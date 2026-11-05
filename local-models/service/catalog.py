"""Approved engine/model IDs; publisher metadata is resolved only on explicit download."""

import copy
import json

from .errors import require
from .security import LOCAL_ROOT, REPO_ROOT, checked

WHISPER = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "whisper-medical-v1")


class Catalog:
    def __init__(self, local_root=LOCAL_ROOT, repo_root=REPO_ROOT):
        self.local_root, self.repo_root = checked(local_root), checked(repo_root)
        lock = json.loads((self.local_root / "assets.lock.json").read_text(encoding="utf-8"))
        self.runtime_specs = {key: lock[key] for key in ("cpu", "cuda", "cuda_runtime")}
        self.models = {}
        for name, spec in {"qwen3-4b": lock["model"], **lock["models"]}.items():
            self.add(
                name,
                name.replace("qwen", "Qwen ").replace("-", " "),
                "llm",
                "GGUF",
                True,
                spec["bytes"],
                "Multilingual",
                "Apache-2.0 (model); verify publisher terms",
                "llm",
                spec=spec,
            )
        self.add(
            "qwenmedic-v1",
            "QwenMedic v1",
            "llm",
            "GGUF · Q4_K_M",
            True,
            None,
            "English",
            "Publisher model terms",
            "qwenmedic",
        )
        for name in WHISPER:
            method = "medical" if name == "whisper-medical-v1" else "hf"
            repo = (
                "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
                if name == "large-v3-turbo"
                else "Systran/faster-whisper-" + name
            )
            self.add(
                name,
                "Whisper " + name,
                "asr",
                "CTranslate2",
                True,
                None,
                "English" if method == "medical" else "English, Hindi and more",
                "MIT / publisher model terms",
                method,
                repo=repo,
            )
        self.add(
            "nemotron-3.5-asr-streaming-0.6b",
            "Nemotron streaming ASR",
            "asr",
            "ONNX · INT8",
            False,
            475271763,
            "Multilingual",
            "OpenMDW-1.1",
            "nemotron",
        )
        for name, lang in (("vosk-model-small-en-us-0.15", "English"), ("vosk-model-small-hi-0.22", "Hindi")):
            self.add(name, "Vosk · " + lang, "asr", "Vosk", False, None, lang, "Apache-2.0", "vosk")
        voices = json.loads((self.local_root / "voices.lock.json").read_text(encoding="utf-8"))["voices"]
        for key, spec in voices.items():
            self.add(
                "piper-" + key,
                "Piper · " + spec["label"],
                "tts",
                "ONNX",
                False,
                spec["bytes"],
                spec["language"],
                "Voice-specific publisher terms; Piper runtime GPL-3.0",
                "voice",
                spec=spec,
                voice=key,
            )

    def add(
        self, identifier, name, capability, format_name, gpu, size, languages, license_name, method, **extra
    ):
        kind = {"llm": "llm", "asr": "audio", "tts": "voice"}[capability]
        detail = {"llm": "Local language generation", "asr": "Speech to text", "tts": "Text to speech"}[
            capability
        ]
        self.models[identifier] = {
            "id": identifier,
            "name": name,
            "capability": capability,
            "category": "LLM" if capability == "llm" else "Audio",
            "kind": kind,
            "detail": detail,
            "format": format_name,
            "gpu_supported": gpu,
            "bytes": size,
            "languages": languages,
            "license": license_name,
            "device": "CPU / NVIDIA GPU" if gpu else "CPU",
            "method": method,
            **extra,
        }

    def get(self, identifier):
        require(isinstance(identifier, str) and identifier in self.models, "model", "Unsupported model ID")
        return copy.deepcopy(self.models[identifier])

    def public(self, inventory):
        result = []
        for model in self.models.values():
            item = {k: v for k, v in model.items() if k not in {"spec", "repo", "method", "voice"}}
            item.update(copy.deepcopy(inventory.get(model["id"], {"status": "Checking", "installed": False})))
            size = model["bytes"]
            item["size"] = f"{size / 1e9:.2f} GB" if size else "Resolved during download"
            result.append(item)
        return result

    def locations(self, model):
        new = self.local_root / ".library" / model["id"]
        if model["capability"] == "llm":
            legacy = self.local_root / ".models"
            if model["method"] == "qwenmedic":
                legacy /= "qwenmedic-v1"
        elif model["capability"] == "asr":
            legacy = self.repo_root / "device/audio-process/.models" / model["id"]
        else:
            legacy = self.local_root / ".voices" / model["voice"]
        return checked(new, self.local_root), checked(legacy, self.repo_root)
