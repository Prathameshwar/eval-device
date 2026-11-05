"""Fictional software fixtures, not clinically reviewed training material."""

import json
from pathlib import Path


def example(code="sample_cough", kind="cough"):
    path = Path(__file__).resolve().parents[1] / "scripts/scenario-examples" / (kind + "_draft.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["code"] = code
    return value
