import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common
import run


class PromptCacheTests(unittest.TestCase):
    def test_legacy_config_default_disable_and_bounds(self):
        original = common.config()
        original.pop("prompt_cache_mib", None)
        with tempfile.TemporaryDirectory() as temp, patch.object(common, "ROOT", Path(temp)):
            root = Path(temp)
            (root / "config.json").write_text(json.dumps(original))
            self.assertEqual(common.config()["prompt_cache_mib"], 256)
            for size in (0, 128, 1024):
                (root / "config.local.json").write_text(json.dumps({"prompt_cache_mib": size}))
                args = run.Server(common.config()).arguments(Path("server.exe"), Path("private-key.txt"))
                self.assertEqual(args[args.index("--cache-ram") + 1], str(size))
                self.assertIn("--no-slots", args)
                self.assertNotIn("--slot-save-path", args)
            for value in (-1, 1025, True, "256"):
                (root / "config.local.json").write_text(json.dumps({"prompt_cache_mib": value}))
                with self.assertRaises(ValueError):
                    common.config()
