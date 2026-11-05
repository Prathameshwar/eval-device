"""Run native ARM64 software qualification; refuse to label cross-platform tests as native."""

import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def installed_idle(status):
    return (
        isinstance(status, dict)
        and status.get("ready") is True
        and status.get("state") == "idle"
        and status.get("active") is False
        and status.get("camera_active") is False
        and status.get("video_processing") is False
        and status.get("finishing") is False
        and status.get("job") is None
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--installed", action="store_true", help="Also verify the installed systemd unit and idle service"
    )
    args = parser.parse_args()
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "native_arm64": False,
        "hardware_verified": False,
        "cloud_verified": False,
        "checks": {},
    }
    try:
        if platform.system() != "Linux" or platform.machine() not in {"aarch64", "arm64"}:
            raise RuntimeError("Run qualification on native Linux ARM64")
        if not (3, 12) <= sys.version_info[:2] < (3, 14):
            raise RuntimeError("Python 3.12/3.13 required")
        report["native_arm64"] = True
        for module in ("pi_test.service", "training_client.runtime", "sounddevice", "av", "cv2"):
            __import__(module)
        assert "tkinter" not in sys.modules
        report["version"] = importlib.metadata.version("pi-test")
        report["checks"]["native_imports"] = True
        root = Path(__file__).resolve().parents[2]
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(root / "pi-test/tests"),
                str(root / "shared/training-client/tests"),
            ],
            check=True,
            cwd=root / "pi-test",
        )
        report["checks"]["contracts_and_media_codecs"] = True
        if args.installed:
            if not shutil.which("systemd-analyze"):
                raise RuntimeError("systemd tools unavailable")
            subprocess.run(["systemd-analyze", "verify", "/etc/systemd/system/pi-test.service"], check=True)
            subprocess.run(["systemctl", "is-active", "--quiet", "pi-test.service"], check=True)
            response = subprocess.run(
                ["/opt/pi-test/current/bin/pi-test", "status"], check=True, capture_output=True, text=True
            )
            status = json.loads(response.stdout)["result"]
            if not installed_idle(status):
                raise RuntimeError("Installed service must be ready and idle for qualification")
            report["checks"]["installed_idle_service"] = True
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = type(error).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
