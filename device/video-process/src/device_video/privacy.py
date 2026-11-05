"""Private local filesystem helpers; independent of the audio service."""

import csv
import re
import stat
import subprocess
import sys
from pathlib import Path


class StorageError(Exception):
    pass


def no_link(path: Path) -> None:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
    ):
        raise StorageError("unsafe_path")


def private_directory(path: Path) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        identity = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
        sid = next(csv.reader([identity.strip()]))[1]
        if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
            raise StorageError("permissions")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        pointer = ctypes.c_void_p
        api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.ULONG),
        ]
        api.GetSecurityDescriptorDacl.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.BOOL),
        ]
        api.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            pointer,
            pointer,
            pointer,
            pointer,
        ]
        api.SetNamedSecurityInfoW.restype = wintypes.DWORD
        kernel.LocalFree.argtypes = [pointer]
        kernel.LocalFree.restype = pointer
        descriptor = pointer()
        if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None
        ):
            raise StorageError("permissions")
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            dacl = pointer()
            if (
                not api.GetSecurityDescriptorDacl(
                    descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
                )
                or not present.value
            ):
                raise StorageError("permissions")
            # Replace the entire DACL: remove inherited AND explicit grants to other users.
            if api.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
                raise StorageError("permissions")
        finally:
            kernel.LocalFree(descriptor)
    else:
        path.chmod(0o600 if path.is_file() else 0o700)
