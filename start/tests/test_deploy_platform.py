"""Check the Ubuntu transfer script without changing a host machine."""

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "deploy-platform.sh"
REQUIRED = {
    "platform/api/pyproject.toml": b"api",
    "platform/api/uv.lock": b"lock",
    "platform/api/deploy/grant-runtime-access.sql": b"grant",
    "platform/ui/package-lock.json": b"npm",
    "platform/ui/apps/web/.next/BUILD_ID": b"build",
    "shared/training-contracts/pyproject.toml": b"shared",
    "wheels/pms_api-0.1.0-py3-none-any.whl": b"api-wheel",
    "wheels/training_contracts-0.1.0-py3-none-any.whl": b"shared-wheel",
}


def python_block(function_name: str) -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(function_name)}\(\).*?<<'PY'\n(.*?)^PY$", source)
    if not match:
        raise AssertionError(f"Missing Python block in {function_name}")
    return match.group(1)


def bash_function(function_name: str) -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(function_name)}\(\) \{{\n.*?^\}}$", source)
    if not match:
        raise AssertionError(f"Missing Bash function {function_name}")
    return match.group(0)


def archive_at(path: Path, files: dict[str, bytes], hashes: dict[str, str] | None = None) -> None:
    hashes = hashes or {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps({"format": 1, "sha256": hashes}))


class DeployArchiveTests(unittest.TestCase):
    def test_web_and_api_routes_reach_their_respective_services(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("write_site() {", source)
        self.assertIn("\nensure_certificate() {", source)
        site = source.partition("write_site() {")[2].partition("\nensure_certificate() {")[0]
        locations = set(re.findall(r"(?m)^\s*location (/\S*) \{", site))

        def matching_location(path: str) -> str:
            return max((prefix for prefix in locations if path.startswith(prefix)), key=len)

        self.assertEqual(matching_location("/api/v1/auth/login"), "/api/v1/")
        self.assertEqual(matching_location("/api/member-imports/download"), "/")
        self.assertIn("location /api/v1/ {\n        $api_response", site)
        self.assertIn("location / {\n        $response", site)
        self.assertIn(
            "PMS_API_BASE_URL=http://127.0.0.1:8000/api/v1",
            bash_function("install_services"),
        )

    def test_readiness_requires_managed_api_and_web_listeners(self):
        for api_listener, web_listener, inactive_unit, expected in (
            (111, 222, "", 0),
            (999, 222, "", 1),
            (111, 999, "", 1),
            (111, 222, "pms-worker.service", 1),
            (111, 222, "pms-retention.service", 1),
        ):
            with self.subTest(
                api_listener=api_listener, web_listener=web_listener, inactive_unit=inactive_unit
            ):
                harness = "\n".join(
                    (
                        f"systemctl(){{ if [[ $1 == is-active ]]; then [[ $3 != '{inactive_unit}' ]]; return $?; fi; "
                        "if [[ $4 == pms-api.service ]]; then printf '111\\n'; "
                        "else printf '222\\n'; fi; }",
                        "ss(){ if [[ $3 == 'sport = :8000' ]]; then "
                        f"printf 'LISTEN users:((\\\"api\\\",pid={api_listener},fd=3))\\n'; "
                        "else "
                        f"printf 'LISTEN users:((\\\"web\\\",pid={web_listener},fd=3))\\n'; "
                        "fi; }",
                        "curl(){ return 0; }",
                        "sleep(){ exit 1; }",
                        bash_function("unit_listener"),
                        bash_function("wait_ready"),
                        "wait_ready",
                    )
                )
                result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_https_readiness_retries_nginx_reload(self):
        for failures, expected_status, expected_calls in ((2, 0, 3), (15, 1, 15)):
            with self.subTest(failures=failures):
                harness = "\n".join(
                    (
                        "HOST=example.test calls=0",
                        "curl(){ [[ $* == *https://example.test/health/ready?api_port=8000* ]] || return 99; "
                        "((calls+=1)); ((calls>" + str(failures) + ")); }",
                        "sleep(){ :; }",
                        bash_function("wait_https_ready"),
                        'wait_https_ready; status=$?; printf \'%s %s\\n\' "$status" "$calls"',
                    )
                )
                result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"{expected_status} {expected_calls}")

    def test_failed_cross_revision_rollback_restores_current_database(self):
        harness = "\n".join(
            (
                "RECOVERING=0 SERVICES_STOPPED=1 SWITCHED=1 SCHEMA_CHANGED=1",
                "DATABASE_MUTATION=1 ALLOW_DATA_LOSS=1 BACKUP_READY=1",
                "BACKUP_FILE=/safety.dump OLD_RELEASE=/old SITE_CHANGED=0 COMMAND=rollback",
                "log(){ :; }",
                "restore_role_configs(){ return 0; }",
                "stop_services(){ return 0; }",
                'restore_database(){ printf \'restore:%s:%s\\n\' "$1" "$2"; }',
                "switch_release(){ printf 'switch:%s\\n' \"$1\"; }",
                "start_services(){ printf 'start\\n'; }",
                "wait_ready(){ printf 'ready\\n'; }",
                bash_function("on_error"),
                "on_error 1",
            )
        )
        result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(), ["restore:/safety.dump:/old", "switch:/old", "start", "ready"]
        )

    def test_embedded_python_syntax(self):
        for name in (
            "init_config",
            "show_setup_key",
            "bootstrap_database",
            "sync_role_configs",
            "provision_training_key",
            "prepare_pgpass",
            "check_archive_and_extract",
            "migrate_database",
            "backfill_tenant_catalog",
        ):
            compile(python_block(name), f"{name}.py", "exec")

    def test_training_provisioning_upgrades_existing_config_and_preserves_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api").mkdir()
            master, runtime = root / "api.env", root / "api/.env"
            for path in (master, runtime):
                path.write_text("PMS_OTHER=unchanged\n", encoding="utf-8")
            command = [sys.executable, "-c", python_block("provision_training_key"), str(root), ""]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            key = root / "api/training-private.pem"
            original_key = key.read_bytes()
            for path in (master, runtime):
                self.assertIn("PMS_OTHER=unchanged", path.read_text())
                self.assertIn(key.as_posix(), path.read_text())
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(key.read_bytes(), original_key)
            self.assertNotIn(original_key.decode(), result.stdout + repeated.stdout)
            key.unlink()
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(key.exists(), "A configured signing identity must never be silently replaced")

    def test_training_configuration_recovery_restores_master_before_role_configs(self):
        harness = "\n".join(
            (
                "WORK=/work CONFIG=/config ROLE_CONFIG_CHANGED=1",
                'cp(){ printf "%s\\n" "$*"; }',
                "rm(){ :; }",
                # Only the master backup exists in this failure fixture.
                bash_function("restore_role_configs").replace(
                    "[[ -f $WORK/training-master.env.previous ]]", "true"
                ),
                "restore_role_configs",
            )
        )
        result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/work/training-master.env.previous /config/api.env", result.stdout)

    def test_extracts_valid_archive(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_at(root / "platform.zip", REQUIRED)
            target = root / "release"
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    python_block("check_archive_and_extract"),
                    str(root / "platform.zip"),
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((target / "platform/api/pyproject.toml").read_bytes(), b"api")

    def test_latest_windows_archive_if_available(self):
        archives = list((SCRIPT.parent / "dist").glob("pms-platform-*.zip"))
        if not archives:
            self.skipTest("Build a Windows transfer archive first")
        latest = max(archives, key=lambda path: path.stat().st_mtime)
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    python_block("check_archive_and_extract"),
                    str(latest),
                    directory,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(directory) / "platform/api/uv.lock").is_file())

    def test_config_keeps_owner_secret_separate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "api.env"
            migration = root / "migration.url"
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    python_block("init_config"),
                    str(runtime),
                    str(migration),
                    "eval.centralindia.cloudapp.azure.com",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(
                line.split("=", 1)
                for line in runtime.read_text(encoding="utf-8").splitlines()
                if line.startswith("PMS_")
            )
            self.assertNotIn("PMS_MIGRATION_DATABASE_URL", values)
            self.assertEqual(values["PMS_VM_LOCAL_MODE"], "true")
            self.assertEqual(values["PMS_STORAGE_BACKEND"], "local")
            self.assertEqual(values["PMS_STORAGE_ROOT"], "/var/lib/pms-media")
            self.assertEqual(values["PMS_LLM_ENABLED"], "true")
            self.assertEqual(values["PMS_EXTERNAL_CALLS_ENABLED"], "false")
            self.assertFalse(any("REPLACE_" in value for value in values.values()))
            urls = [
                urlsplit(values[name])
                for name in (
                    "PMS_DATABASE_URL",
                    "PMS_WORKER_DATABASE_URL",
                    "PMS_RETENTION_DATABASE_URL",
                )
            ]
            urls.append(urlsplit(migration.read_text(encoding="utf-8").strip()))
            self.assertEqual(len({url.password for url in urls}), 4)
            self.assertTrue(all(url.password for url in urls))
            self.assertEqual(values["PMS_ENVIRONMENT"], "production")
            with runtime.open("a", encoding="utf-8") as stream:
                stream.write("PMS_TRAINING_KEY_FILE=/private/training.pem\n")
            for role in ("api", "worker", "retention"):
                (root / role).mkdir()
            separated = subprocess.run(
                [sys.executable, "-c", python_block("sync_role_configs"), str(runtime), str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(separated.returncode, 0, separated.stderr)
            expected = {
                "api": "PMS_DATABASE_URL",
                "worker": "PMS_WORKER_DATABASE_URL",
                "retention": "PMS_RETENTION_DATABASE_URL",
            }
            for role, kept in expected.items():
                role_env = (root / role / ".env").read_text(encoding="utf-8")
                self.assertIn(kept + "=", role_env)
                self.assertNotIn("PMS_MIGRATION_DATABASE_URL=", role_env)
                self.assertEqual("PMS_TRAINING_KEY_FILE=" in role_env, role == "api")
                for other in set(expected.values()) - {kept}:
                    self.assertNotIn(other + "=", role_env)
            api_root = SCRIPT.parent.parent / "platform" / "api"
            api_python = api_root / ".venv" / "Scripts" / "python.exe"
            if api_python.is_file():
                clean_env = {key: value for key, value in os.environ.items() if not key.startswith("PMS_")}
                parsed = subprocess.run(
                    [
                        str(api_python),
                        "-c",
                        "import sys; from pms_api.core.config import Settings; Settings(_env_file=sys.argv[1])",
                        str(runtime),
                    ],
                    cwd=api_root,
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)
                for role in expected:
                    loaded = subprocess.run(
                        [
                            str(api_python),
                            "-c",
                            "from pms_api.core.config import Settings; assert Settings().environment == 'production'",
                        ],
                        cwd=root / role,
                        env=clean_env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(loaded.returncode, 0, f"{role}: {loaded.stderr}")

    def test_rejects_tampering_and_path_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in REQUIRED.items()}
            changed = {**REQUIRED, "platform/api/pyproject.toml": b"changed"}
            archive_at(root / "tampered.zip", changed, original_hashes)
            escaped = {**REQUIRED, "platform/../../outside": b"escape"}
            archive_at(root / "traversal.zip", escaped)
            for name in ("tampered", "traversal"):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        python_block("check_archive_and_extract"),
                        str(root / f"{name}.zip"),
                        str(root / name),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
