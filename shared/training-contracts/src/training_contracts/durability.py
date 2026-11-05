"""Publish already flushed files before recording their durable acknowledgement."""

import os
from pathlib import Path


def sync_directory(path: Path) -> None:
    """Persist directory entries on POSIX; Windows uses a write-through rename."""
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def durable_replace(source: Path, destination: Path) -> None:
    if source.parent != destination.parent:
        raise ValueError("Durable publication requires the same directory")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move.restype = wintypes.BOOL
        if not move(str(source), str(destination), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        source.replace(destination)
        sync_directory(destination.parent)
