import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common
import run


class LayerOverrideTests(unittest.TestCase):
    def test_factory_layers_reach_standalone_launcher_without_override(self):
        factory = json.loads(
            (Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(factory["gpu_layers"], 20)
        with tempfile.TemporaryDirectory() as name, patch.object(common, "ROOT", Path(name)):
            (Path(name) / "config.json").write_text(json.dumps(factory), encoding="utf-8")
            settings = common.config()
            with (
                patch.object(sys, "argv", ["run.py", "--server"]),
                patch.object(run, "config", return_value=settings),
                patch.object(run, "Server", side_effect=RuntimeError("fixture stop")) as server,
            ):
                with self.assertRaisesRegex(RuntimeError, "fixture stop"):
                    run.main()
            self.assertEqual(server.call_args.args[0]["gpu_layers"], 20)
            (Path(name) / "config.local.json").write_text('{"gpu_layers": 12}', encoding="utf-8")
            self.assertEqual(common.config()["gpu_layers"], 12)

    def test_gpu_layers_override_only_applies_to_launched_server(self):
        settings = common.config()
        settings["gpu_enabled"] = True
        settings["gpu_layers"] = 99
        with (
            patch.object(sys, "argv", ["run.py", "--server", "--gpu-layers", "16"]),
            patch.object(run, "config", return_value=dict(settings)),
            patch.object(run, "Server", side_effect=RuntimeError("fixture stop")) as server,
        ):
            with self.assertRaisesRegex(RuntimeError, "fixture stop"):
                run.main()
        self.assertEqual(server.call_args.args[0]["gpu_layers"], 16)
        self.assertEqual(settings["gpu_layers"], 99)

    def test_invalid_layer_overrides_do_not_launch(self):
        for flags in (
            ["--gpu-layers", "0"],
            ["--gpu-layers", "100"],
            ["--cpu", "--gpu-layers", "16"],
            ["--connect", "--gpu-layers", "16"],
        ):
            with (
                self.subTest(flags=flags),
                patch.object(sys, "argv", ["run.py", *flags]),
                patch.object(sys, "stderr", io.StringIO()),
                patch.object(run, "Server") as server,
            ):
                with self.assertRaises(SystemExit) as result:
                    run.main()
                self.assertEqual(result.exception.code, 2)
                server.assert_not_called()
