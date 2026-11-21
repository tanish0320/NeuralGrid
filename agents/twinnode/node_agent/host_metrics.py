from __future__ import annotations

import ctypes
import os
import socket
import time
from typing import Tuple

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


def _filetime_to_int(ft: _FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


_prev_cpu_sample: tuple[int, int] | None = None


def _windows_cpu_and_memory() -> tuple[float, float]:
    global _prev_cpu_sample
    mem = _MEMORYSTATUSEX()
    mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    mem_pct = 0.0
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):  # type: ignore[attr-defined]
        mem_pct = float(mem.dwMemoryLoad)

    idle_ft, kernel_ft, user_ft = _FILETIME(), _FILETIME(), _FILETIME()
    cpu_pct = 0.0
    if ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
        ctypes.byref(idle_ft), ctypes.byref(kernel_ft), ctypes.byref(user_ft)
    ):
        idle = _filetime_to_int(idle_ft)
        total = _filetime_to_int(kernel_ft) + _filetime_to_int(user_ft)
        if _prev_cpu_sample is not None:
            prev_idle, prev_total = _prev_cpu_sample
            d_total = total - prev_total
            d_idle = idle - prev_idle
            if d_total > 0:
                cpu_pct = round(max(0.0, min(100.0, (1.0 - (d_idle / d_total)) * 100.0)), 2)
        _prev_cpu_sample = (idle, total)

    return cpu_pct, round(mem_pct, 2)


def read_host_telemetry() -> Tuple[float, float]:
    """Read real host CPU% and RAM% using psutil if installed, else OS native fallback."""
    if psutil is not None:
        cpu = float(psutil.cpu_percent(interval=None))
        mem = float(psutil.virtual_memory().percent)
        return round(cpu, 2), round(mem, 2)

    if os.name == "nt":
        try:
            return _windows_cpu_and_memory()
        except Exception:
            pass

    # POSIX fallback
    try:
        load1, _, _ = os.getloadavg()
        cpus = os.cpu_count() or 1
        cpu_est = round(min(100.0, (load1 / cpus) * 100.0), 2)
    except Exception:
        cpu_est = 0.0
    return cpu_est, 0.0


def get_hostname() -> str:
    return socket.gethostname()


def get_local_ipv4() -> str:
    """Discover best outbound private IPv4 without external traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()
