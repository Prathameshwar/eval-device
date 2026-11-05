"""Strict operator request validation shared by the HTTP service and tests."""

from uuid import UUID

from .errors import require
from .storage import DEFAULTS

CAPABILITIES = {
    "llm": ("Language model", "LLM", 8797),
    "asr": ("Speech recognition", "Audio", 8795),
    "tts": ("Speech synthesis", "Audio", 8798),
}
BOUNDS = {
    "cpu_threads": (1, 32),
    "gpu_device_index": (0, 15),
    "gpu_layers": (1, 99),
    "startup_timeout_seconds": (10, 600),
    "drain_timeout_seconds": (1, 120),
    "context_size": (512, 8192),
    "max_tokens": (16, 512),
}


def runtime_option_names(capability, device, model=None):
    """Options consumed by the selected adapter and service lifecycle."""
    require(capability in CAPABILITIES, "capability", "Unsupported capability")
    require(device in {"cpu", "gpu"}, "device", "Choose CPU or GPU")
    names = []
    if capability == "llm":
        names.append("cpu_threads")
        if device == "gpu":
            names.extend(("gpu_device_index", "gpu_layers"))
        names.extend(("context_size", "max_tokens"))
    elif capability == "asr":
        # Vosk's adapter does not expose thread tuning; Whisper/Nemotron do.
        if not model or model.get("format") != "Vosk":
            names.append("cpu_threads")
        if device == "gpu":
            names.append("gpu_device_index")
    names.extend(("startup_timeout_seconds", "drain_timeout_seconds"))
    return tuple(names)


def exact(payload, required, optional=()):
    require(
        isinstance(payload, dict)
        and set(required) <= payload.keys()
        and payload.keys() <= set(required) | set(optional),
        "invalid_request",
        "Unsupported or missing fields",
    )


def request_id(value):
    require(isinstance(value, str) and len(value) == 36, "request_id", "A UUID request ID is required")
    try:
        require(str(UUID(value)) == value, "request_id", "Invalid request ID")
    except ValueError:
        require(False, "request_id", "Invalid request ID")
    return value


def integer(value, lower, upper, name):
    require(
        type(value) is int and lower <= value <= upper, "invalid_setting", f"{name} must be {lower}–{upper}"
    )
    return value


def settings(values):
    exact(values, DEFAULTS)
    for name, (lower, upper) in BOUNDS.items():
        integer(values[name], lower, upper, name)
    require(
        values["max_tokens"] + 64 < values["context_size"],
        "context_budget",
        "Output exceeds context capacity",
    )
    return dict(values)


def provision(payload, catalog, defaults, manager_port=8790):
    exact(
        payload,
        ("request_id", "capability", "model_id", "device", "start_at_boot", "port"),
        ("options", "revision"),
    )
    request_id(payload["request_id"])
    kind = payload["capability"]
    require(isinstance(kind, str) and kind in CAPABILITIES, "capability", "Unsupported capability")
    model = catalog.get(payload["model_id"])
    require(model["capability"] == kind, "model_mismatch", "Model does not support this capability")
    require(payload["device"] in ("cpu", "gpu"), "device", "Choose CPU or GPU")
    require(payload["device"] != "gpu" or model["gpu_supported"], "device", "This adapter supports CPU only")
    require(type(payload["start_at_boot"]) is bool, "startup", "Startup preference must be a boolean")
    require(
        not payload["start_at_boot"],
        "startup_queued",
        "Windows service and reboot auto-start are queued for the next phase",
        409,
    )
    integer(payload["port"], 1024, 64000, "Port")
    require(
        payload["port"] != manager_port and (kind != "llm" or payload["port"] + 100 != manager_port),
        "port",
        "Worker port conflicts with the manager",
    )
    options = dict(defaults)
    supplied = payload.get("options", {})
    require(
        isinstance(supplied, dict) and supplied.keys() <= DEFAULTS.keys(),
        "options",
        "Unsupported runtime options",
    )
    options.update(supplied)
    settings(options)
    return {
        "capability": kind,
        "model_id": model["id"],
        "device": payload["device"],
        "start_at_boot": payload["start_at_boot"],
        "port": payload["port"],
        "options": options,
    }
