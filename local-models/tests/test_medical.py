"""Model selection, provenance and failure behavior; no public downloads."""

import hashlib
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import client
import common
import install
import medical
import run


def source():
    return medical.source_spec(
        {
            "id": medical.REPO,
            "sha": "a" * 40,
            "siblings": [{"rfilename": medical.SOURCE, "lfs": {"size": 3_450_000_000, "sha256": "b" * 64}}],
        }
    )


class MedicalModels(unittest.TestCase):
    def test_old_configs_default_and_invalid_model_rejected(self):
        base = common.config()
        base.pop("model", None)
        with tempfile.TemporaryDirectory() as temp, patch.object(common, "ROOT", Path(temp)):
            root = Path(temp)
            (root / "config.json").write_text(json.dumps(base))
            self.assertEqual(common.config()["model"], "qwen3.5-4b")
            for bad in (None, 1, "../model", "large-v3"):
                (root / "config.local.json").write_text(json.dumps({"model": bad}))
                with self.assertRaises(ValueError):
                    common.config()
            (root / "config.local.json").write_text(json.dumps({"model": "qwenmedic-v1"}))
            self.assertEqual(common.config()["model"], "qwenmedic-v1")

    def test_server_and_client_use_same_selected_model(self):
        for name in common.MODEL_NAMES:
            settings = dict(common.config(), model=name)
            profile = common.model_profile(settings)
            args = run.Server(settings).arguments(Path("server.exe"), Path("key.txt"))
            self.assertEqual(args[args.index("--model") + 1], str(profile["path"]))
            self.assertEqual(args[args.index("--alias") + 1], profile["alias"])
            with patch.object(client, "request", side_effect=RuntimeError("fixture")) as request:
                with self.assertRaises(RuntimeError):
                    client.infer(settings, "fixture", [{"role": "user", "content": "hello"}])
                self.assertEqual(request.call_args.args[3]["model"], profile["alias"])
                self.assertFalse(request.call_args.args[3]["chat_template_kwargs"]["enable_thinking"])

    def test_source_lock_is_exact_and_cannot_redirect(self):
        valid = source()
        self.assertIn("a" * 40, valid["url"])
        medical.validate_source(valid)
        for key, value in (
            ("url", "https://example.invalid/file"),
            ("sha256", "bad"),
            ("repo", "other/repo"),
            ("revision", "main"),
            ("bytes", 9_000_000_000),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                medical.validate_source({**valid, key: value})

    def test_corrupted_quantization_is_rejected_before_inference(self):
        data = b"GGUFfixture"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / medical.OUTPUT).write_bytes(data)
            manifest = {
                "source": source(),
                "name": medical.OUTPUT,
                "quantization": "Q4_K_M",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            (root / "manifest.json").write_text(json.dumps(manifest))
            medical.verify_medical(root)
            (root / medical.OUTPUT).write_bytes(b"GGUFchanged")
            with self.assertRaisesRegex(ValueError, "integrity"):
                medical.verify_medical(root)

    def test_denial_not_retried_and_partial_install_does_not_replace_default(self):
        failure = urllib.error.HTTPError("https://huggingface.co", 403, "denied", None, None)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".models").mkdir()
            original = root / ".models/baseline.gguf"
            original.write_bytes(b"preserved")
            with patch.object(medical.urllib.request, "urlopen", side_effect=failure) as request:
                with self.assertRaisesRegex(RuntimeError, "403"):
                    medical.install_medical(root, {}, root / "archive.zip")
                self.assertEqual(request.call_count, 1)
            self.assertEqual(original.read_bytes(), b"preserved")
            self.assertFalse((root / ".models/qwenmedic-v1").exists())

    def test_medical_cpu_setup_does_not_download_default_model_or_cuda(self):
        specs = json.loads((install.ROOT / "assets.lock.json").read_text())
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(install, "ROOT", Path(temp)),
            patch.object(sys, "argv", ["install.py", "--cpu", "--model", "qwenmedic-v1"]),
        ):
            root = Path(temp)
            (root / "assets.lock.json").write_text(json.dumps(specs))
            with (
                patch.object(install, "download", return_value=root / "cpu.zip") as download,
                patch.object(install, "extract_runtime"),
                patch.object(medical, "install_medical") as setup,
            ):
                install.main()
            self.assertEqual([c.args[0]["name"] for c in download.call_args_list], [specs["cpu"]["name"]])
            setup.assert_called_once()

    def check_optional_install(self, name):
        specs = json.loads((install.ROOT / "assets.lock.json").read_text())
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(install, "ROOT", Path(temp)),
            patch.object(sys, "argv", ["install.py", "--cpu", "--model", name]),
        ):
            root = Path(temp)
            (root / "assets.lock.json").write_text(json.dumps(specs))
            (root / ".models").mkdir()
            default = root / ".models" / specs["model"]["name"]
            default.write_bytes(b"existing default")
            manifest = root / ".models/model-manifest.json"
            manifest.write_text("preserved")
            with (
                patch.object(install, "download", return_value=root / "cpu.zip") as download,
                patch.object(install, "extract_runtime"),
            ):
                install.main()
            self.assertEqual(
                [c.args[0]["name"] for c in download.call_args_list],
                [specs["cpu"]["name"], specs["models"][name]["name"]],
            )
            self.assertEqual(default.read_bytes(), b"existing default")
            self.assertEqual(manifest.read_text(), "preserved")
            self.assertEqual(
                json.loads((root / f".models/{name}-manifest.json").read_text()),
                specs["models"][name],
            )

    def check_optional_integrity(self, name):
        with tempfile.TemporaryDirectory() as temp, patch.object(common, "ROOT", Path(temp)):
            root = Path(temp)
            runtime = root / ".runtime/cpu"
            runtime.mkdir(parents=True)
            (runtime / "llama-server.exe").write_bytes(b"runtime")
            (runtime / "manifest.json").write_text(
                json.dumps({"llama-server.exe": hashlib.sha256(b"runtime").hexdigest()})
            )
            profile = common.model_profile({"model": name})
            profile["path"].parent.mkdir()
            profile["path"].write_bytes(b"model")
            (root / "assets.lock.json").write_text(
                json.dumps({"models": {name: {"bytes": 5, "sha256": hashlib.sha256(b"model").hexdigest()}}})
            )
            self.assertEqual(common.verify_install(False, {"model": name}), runtime / "llama-server.exe")
            profile["path"].write_bytes(b"wrong")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch.*setup-" + name + ".bat"):
                common.verify_install(False, {"model": name})

    def test_small_qwen_cpu_install_preserves_default_manifest_and_model(self):
        self.check_optional_install("qwen3-1.7b")

    def test_qwen35_cpu_install_preserves_default_manifest_and_model(self):
        self.check_optional_install("qwen3.5-4b")

    def test_small_qwen_launch_verifies_selected_asset_and_names_its_repair(self):
        self.check_optional_integrity("qwen3-1.7b")

    def test_qwen35_launch_verifies_selected_asset_and_names_its_repair(self):
        self.check_optional_integrity("qwen3.5-4b")


if __name__ == "__main__":
    unittest.main()
