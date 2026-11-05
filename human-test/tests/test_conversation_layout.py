"""Run each display scale in its own Tcl interpreter."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("scaling", [4 / 3, 2, 8 / 3], ids=["100-percent", "150-percent", "200-percent"])
def test_conversation_menu_stays_reachable_with_drawer_and_preview(scaling):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("conversation_layout_smoke.py")),
            "--scaling",
            str(scaling),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
