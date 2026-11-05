"""Initial desktop choices without overriding saved services or operator preferences."""


def preferred_model(models, saved=None):
    identifiers = [model["id"] for model in models]
    if saved in identifiers:
        return saved
    if "qwen3.5-4b" in identifiers:
        return "qwen3.5-4b"
    return identifiers[0] if identifiers else ""


def default_device(model):
    return "gpu" if model and model.get("gpu_supported") else "cpu"


def inventory_state(data):
    state = data.get("initialization")
    if state in {"loading", "ready", "failed"}:
        return state
    # An already-running manager may predate the explicit initialization field.
    if any(model["status"] == "Checking" for model in data["models"]):
        return "loading"
    if data["hardware"].get("gpu_probe") == "Checking":
        return "loading"
    return "ready"
