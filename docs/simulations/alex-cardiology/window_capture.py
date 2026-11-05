"""Capture only the selected test window; no desktop-wide screenshots."""

import ctypes
from ctypes import wintypes


def save_window(hwnd, path):
    import cv2
    import numpy as np

    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    for function, arguments, result in (
        (
            user.GetWindowRect,
            [wintypes.HWND, ctypes.POINTER(wintypes.RECT)],
            wintypes.BOOL,
        ),
        (user.GetWindowDC, [wintypes.HWND], wintypes.HDC),
        (user.ReleaseDC, [wintypes.HWND, wintypes.HDC], ctypes.c_int),
        (user.PrintWindow, [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
        (gdi.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC),
        (
            gdi.CreateCompatibleBitmap,
            [wintypes.HDC, ctypes.c_int, ctypes.c_int],
            wintypes.HBITMAP,
        ),
        (gdi.SelectObject, [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
        (gdi.DeleteObject, [wintypes.HGDIOBJ], wintypes.BOOL),
        (gdi.DeleteDC, [wintypes.HDC], wintypes.BOOL),
        (
            gdi.GetDIBits,
            [
                wintypes.HDC,
                wintypes.HBITMAP,
                wintypes.UINT,
                wintypes.UINT,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.UINT,
            ],
            ctypes.c_int,
        ),
    ):
        function.argtypes, function.restype = arguments, result
    rectangle = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rectangle)):
        raise OSError("Could not locate the test window")
    width, height = rectangle.right - rectangle.left, rectangle.bottom - rectangle.top
    if not 1 <= width <= 4096 or not 1 <= height <= 4096:
        raise OSError("Unexpected test window size")
    dc = user.GetWindowDC(hwnd)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    previous = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(hwnd, memory, 2):
            raise OSError("Could not capture the test window")
        import struct

        info = ctypes.create_string_buffer(
            struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        )
        pixels = ctypes.create_string_buffer(width * height * 4)
        if not gdi.GetDIBits(memory, bitmap, 0, height, pixels, info, 0):
            raise OSError("Could not read the test window image")
        image = np.frombuffer(pixels, dtype=np.uint8).reshape((height, width, 4))[
            :, :, :3
        ]
        if not cv2.imwrite(str(path), image):
            raise OSError("Could not save the test window image")
    finally:
        gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd, dc)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        import tkinter as tk

        root = tk.Tk()
        root.title("Screenshot self-test (no live inference)")
        root.geometry("420x120")
        tk.Label(root, text="Native screenshot self-test", font=("Segoe UI", 16)).pack(
            pady=35
        )
        root.update()
        try:
            save_window(root.winfo_id(), sys.argv[2])
        finally:
            root.destroy()
        print("Native capture self-test passed")
        raise SystemExit(0)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    handle = user.FindWindowW(None, "Alex - LIVE 25-question audio failure collection")
    if not handle:
        raise SystemExit("Test window is not open")
    save_window(handle, sys.argv[1])
