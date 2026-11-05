"""Bounded installers whose descendants are owned by the background manager."""

import subprocess
import sys

from .errors import ManagerError
from .security import LOCAL_ROOT, environment, hidden_flags


def run_owned(args, timeout, env=None):
    process = subprocess.Popen(
        args,
        env=env or environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=hidden_flags(),
    )
    guard = None
    try:
        if sys.platform == "win32":
            from .assets import load_script

            guard = load_script(
                LOCAL_ROOT / "scripts/process_guard.py", "manager_install_guard"
            ).ProcessGuard(process)
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ManagerError(
            "installer_timeout",
            "Installer exceeded its deadline; verified existing assets were preserved",
            409,
        ) from None
    finally:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        finally:
            if guard:
                guard.close()
