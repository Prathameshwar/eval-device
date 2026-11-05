"""Exercise folder publication against disposable local Git repositories."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


class PublishingTests(unittest.TestCase):
    def setUp(self):
        artifacts = PROJECT / ".test_artifacts" / "publish-tests"
        artifacts.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=artifacts)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.seed = self.base / "seed"
        self.local = self.base / "local"
        self.command(self.base, "init", "--bare", "-b", "main", str(self.remote))
        for root in (self.seed, self.local):
            self.command(self.base, "init", "-b", "main", str(root))
            self.command(root, "config", "user.name", "Publishing test")
            self.command(root, "config", "user.email", "test@example.invalid")
            self.command(root, "remote", "add", "origin", str(self.remote))
        self.write(self.seed, "README.md", "Existing repository\n")
        self.write(self.seed, "bill-poc/app.py", "billing = True\n")
        self.commit(self.seed)
        self.command(self.seed, "push", "origin", "main")
        self.write(self.local, "app.py", "device = True\n")
        self.write(self.local, "config.json", '{"enabled": true}\n')
        self.commit(self.local)
        spec = importlib.util.spec_from_file_location("device_publish", PROJECT / "start/publish.py")
        self.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.publisher)
        self.publisher.ROOT = self.local
        self.publisher.REMOTE = str(self.remote)
        self.state = self.local / ".git/device-publish-state.json"

    @staticmethod
    def command(root, *args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
        return result.stdout.decode().strip()

    @staticmethod
    def write(root, name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def commit(self, root):
        self.command(root, "add", "--all")
        self.command(root, "commit", "-m", "Test fixture")

    def head(self):
        return self.command(self.remote, "rev-parse", "main")

    def test_dry_run_mapping_uncommitted_files_and_idempotency(self):
        before = self.head()
        bill = self.command(self.remote, "rev-parse", "main:bill-poc")
        self.write(self.local, "private.txt", "uncommitted\n")
        self.publisher.publish(dry_run=True)
        self.assertEqual(self.head(), before)
        self.assertFalse(self.state.exists())
        self.publisher.publish()
        self.assertEqual(
            self.command(self.remote, "rev-parse", "main:device-poc"),
            self.command(self.local, "rev-parse", "HEAD^{tree}"),
        )
        self.assertEqual(self.command(self.remote, "rev-parse", "main:bill-poc"), bill)
        self.assertEqual(self.command(self.remote, "show", "main:README.md"), "Existing repository")
        self.assertNotIn("private.txt", self.command(self.remote, "ls-tree", "-r", "--name-only", "main"))
        published = self.head()
        self.publisher.publish()
        self.assertEqual(self.head(), published)

    def test_keeps_remote_updates_outside_device_folder(self):
        self.publisher.publish()
        self.command(self.seed, "pull", "--ff-only", "origin", "main")
        self.write(self.seed, "bill-poc/new.py", "new_billing = True\n")
        self.commit(self.seed)
        self.command(self.seed, "push", "origin", "main")
        bill = self.command(self.remote, "rev-parse", "main:bill-poc")
        self.write(self.local, "app.py", "device = 2\n")
        self.commit(self.local)
        self.publisher.publish()
        self.assertEqual(self.command(self.remote, "rev-parse", "main:bill-poc"), bill)
        self.assertEqual(self.command(self.remote, "show", "main:device-poc/app.py"), "device = 2")

    def test_refuses_remote_device_changes(self):
        self.publisher.publish()
        saved = self.state.read_bytes()
        self.command(self.seed, "pull", "--ff-only", "origin", "main")
        self.write(self.seed, "device-poc/remote.py", "remote_change = True\n")
        self.commit(self.seed)
        self.command(self.seed, "push", "origin", "main")
        before = self.head()
        with self.assertRaisesRegex(RuntimeError, "differs from the saved"):
            self.publisher.publish()
        self.assertEqual(self.head(), before)
        self.assertEqual(self.state.read_bytes(), saved)

    def test_refuses_existing_device_folder_without_state(self):
        self.write(self.seed, "device-poc/existing.py", "existing = True\n")
        self.commit(self.seed)
        self.command(self.seed, "push", "origin", "main")
        before = self.head()
        with self.assertRaisesRegex(RuntimeError, "differs from the saved"):
            self.publisher.publish()
        self.assertEqual(self.head(), before)
        self.assertFalse(self.state.exists())

    def test_refuses_different_push_destination(self):
        self.command(self.local, "remote", "set-url", "--push", "origin", str(self.base / "other.git"))
        with self.assertRaisesRegex(RuntimeError, "documented GitHub destination"):
            self.publisher.publish()
        self.assertFalse(self.state.exists())

    def test_concurrent_remote_update_rejects_push_without_state_change(self):
        real_git = self.publisher.git

        def race(*args, **kwargs):
            if args[0] == "push":
                self.write(self.seed, "README.md", "Concurrent change\n")
                self.commit(self.seed)
                self.command(self.seed, "push", "origin", "main")
            return real_git(*args, **kwargs)

        self.publisher.git = race
        with self.assertRaises(RuntimeError):
            self.publisher.publish()
        self.assertFalse(self.state.exists())
        self.assertEqual(self.command(self.remote, "show", "main:README.md"), "Concurrent change")
        self.assertNotIn("device-poc", self.command(self.remote, "ls-tree", "--name-only", "main"))


if __name__ == "__main__":
    unittest.main()
