"""Verify Windows job descendants exit before model replacement is allowed."""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from process_guard import ProcessGuard  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows process ownership")
class ProcessReleaseTests(unittest.TestCase):
    def test_owned_parent_and_descendant_are_stopped_before_return(self):
        with TemporaryDirectory() as directory:
            marker = Path(directory) / "child.json"
            gate = Path(directory) / "go"
            script = Path(directory) / "parent.py"
            script.write_text(
                "import json, pathlib, subprocess, sys, time\n"
                "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(.01)\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], creationflags=subprocess.CREATE_NO_WINDOW)\n"
                "marker = pathlib.Path(sys.argv[2]); temporary = marker.with_suffix('.tmp')\n"
                "temporary.write_text(json.dumps({'pid':child.pid})); temporary.replace(marker)\n"
                "time.sleep(120)\n"
            )
            process = subprocess.Popen(
                [sys.executable, str(script), str(gate), str(marker)],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            guard = ProcessGuard(process)
            try:
                gate.touch()
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                child = json.loads(marker.read_text())["pid"]
                import ctypes
                from ctypes import wintypes

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x00100000, False, child)
                self.assertTrue(handle)
                try:
                    guard.terminate_and_wait()
                    self.assertIsNone(guard.handle)
                    self.assertIsNotNone(process.poll())
                    self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0)
                finally:
                    kernel.CloseHandle(handle)
            finally:
                guard.close()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
