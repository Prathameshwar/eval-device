"""Explicit existing-runtime verification without downloads or worker startup."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.assets import Assets  # noqa: E402
from service.catalog import Catalog  # noqa: E402


def main():
    assets = Assets(Catalog())
    expected = assets.verify("qwen3-1.7b")
    with patch.object(assets, "fetch", side_effect=AssertionError("Existing runtime must not download")):
        result = assets.download("qwen3-1.7b", False, lambda **_: None)
    assert result == expected
    print("Existing verified Qwen model/CPU runtime reused under shared installer lock; no downloads")


if __name__ == "__main__":
    main()
