"""Private filesystem paths and a minimal environment for owned subprocesses."""

import csv
import ctypes
import os
import re
import stat
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LOCAL_ROOT.parent


def checked(path, root=None):
    if ".." in Path(path).parts:
        raise ValueError("Parent traversal is not allowed")
    path = Path(path).absolute()
    if root is not None and not path.is_relative_to(Path(root).absolute()):
        raise ValueError("Path outside managed storage")
    for item in (*reversed(path.parents), path):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked paths are not allowed")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("Hard-linked files are not allowed")
    return path


def identity():
    if sys.platform != "win32":
        return str(os.getuid())
    output = subprocess.check_output(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=5,
    )
    sid = next(csv.reader([output.strip()]))[1]
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise RuntimeError("Unable to determine Windows identity")
    return sid


def protect(path, operator=None, *, allow_service=False):
    """Replace the DACL, including explicit grants, before writing any secret bytes."""
    checked(path)
    if sys.platform != "win32":
        path.chmod(0o600 if path.is_file() else 0o700)
        return
    sid = operator or identity()
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise ValueError("Invalid operator identity")
    sids = {sid, "S-1-5-18"}
    if allow_service:
        sids.add("S-1-5-19")
    descriptor_text = "D:P" + "".join(f"(A;OICI;FA;;;{s})" for s in sorted(sids))
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(pointer),
        ctypes.POINTER(wintypes.ULONG),
    )
    api.GetSecurityDescriptorDacl.argtypes = (
        pointer,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(pointer),
        ctypes.POINTER(wintypes.BOOL),
    )
    api.SetNamedSecurityInfoW.argtypes = (
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        pointer,
        pointer,
        pointer,
        pointer,
    )
    api.SetNamedSecurityInfoW.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = (pointer,)
    descriptor = pointer()
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        descriptor_text, 1, ctypes.byref(descriptor), None
    ):
        raise OSError("Unable to protect local state")
    try:
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), pointer()
        if not api.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
        ):
            raise OSError("Unable to read local permissions")
        if not present.value or api.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
            raise OSError("Unable to protect local state")
    finally:
        kernel.LocalFree(descriptor)


def environment():
    # No platform/provider/database/model-server credentials, proxy secrets or saved HF tokens.
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "LOCALAPPDATA",
        "APPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
    }
    values = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    values.update(PYTHONUTF8="1", HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
    return values


def hidden_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
