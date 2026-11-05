"""Close the owned Windows inference process when its launcher exits."""

import ctypes
import os
import time
from ctypes import wintypes


class ProcessGuard:
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return

        class Basic(ctypes.Structure):
            _fields_ = [
                ("ProcessTime", ctypes.c_int64),
                ("JobTime", ctypes.c_int64),
                ("Flags", wintypes.DWORD),
                ("MinWorking", ctypes.c_size_t),
                ("MaxWorking", ctypes.c_size_t),
                ("ActiveLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("Priority", wintypes.DWORD),
                ("Scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOp",
                    "WriteOp",
                    "OtherOp",
                    "ReadBytes",
                    "WriteBytes",
                    "OtherBytes",
                )
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("Basic", Basic),
                ("IO", IO),
                ("ProcessMemory", ctypes.c_size_t),
                ("JobMemory", ctypes.c_size_t),
                ("PeakProcess", ctypes.c_size_t),
                ("PeakJob", ctypes.c_size_t),
            ]

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateJobObjectW(None, None)
        limits = Extended()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not api.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            if handle:
                api.CloseHandle(handle)
            raise RuntimeError("Could not initialize inference process cleanup")
        if not api.AssignProcessToJobObject(handle, int(process._handle)):
            api.CloseHandle(handle)
            raise RuntimeError("Could not attach inference process cleanup")
        self.api, self.handle = api, handle

    def terminate_and_wait(self, timeout=10):
        """Confirm every owned descendant has exited before another model is loaded."""
        if not self.handle:
            return

        class Accounting(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_int64)
                for name in ("UserTime", "KernelTime", "PeriodUserTime", "PeriodKernelTime")
            ] + [
                (name, wintypes.DWORD)
                for name in ("PageFaults", "TotalProcesses", "ActiveProcesses", "TerminatedProcesses")
            ]

        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]

        class ProcessIds(ctypes.Structure):
            _fields_ = [
                ("Assigned", wintypes.DWORD),
                ("Count", wintypes.DWORD),
                ("Ids", ctypes.c_size_t * 256),
            ]

        ids = ProcessIds()
        if not self.api.QueryInformationJobObject(
            self.handle, 3, ctypes.byref(ids), ctypes.sizeof(ids), None
        ):
            raise RuntimeError("Could not enumerate the owned process group")
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handles = []
        try:
            for pid in ids.Ids[: ids.Count]:
                handle = self.api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                if handle:
                    handles.append(handle)
                elif ctypes.get_last_error() != 87:  # A process which already exited has no PID to open.
                    raise RuntimeError("Could not verify an owned child process")
            if not self.api.TerminateJobObject(self.handle, 1):
                raise RuntimeError("Could not stop the owned process group")
            deadline = time.monotonic() + timeout
            # Job accounting can reach zero before process handles are signaled. Wait
            # on each captured process too, including the native GPU server child.
            for handle in handles:
                milliseconds = max(0, int((deadline - time.monotonic()) * 1000))
                if self.api.WaitForSingleObject(handle, milliseconds) != 0:
                    raise RuntimeError("Owned model process did not exit; replacement load blocked")
            while True:
                info = Accounting()
                if not self.api.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None
                ):
                    raise RuntimeError("Could not verify owned process group exit")
                if info.ActiveProcesses == 0:
                    self.close()
                    return
                if time.monotonic() >= deadline:
                    raise RuntimeError("Owned model processes did not exit; replacement load blocked")
                time.sleep(0.05)
        finally:
            for handle in handles:
                self.api.CloseHandle(handle)

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise RuntimeError("Could not release inference process cleanup handle")
            self.handle = None
