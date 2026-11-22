"""Small Windows helpers (monitors, DPI, single instance, autostart, process stats).

Every function has a harmless fallback on other systems so the rest of the app
(and the unit tests) can run anywhere.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

IS_WIN = sys.platform == "win32"
AUTOSTART_NAME = "InsideVoice"


@dataclass(frozen=True)
class MonitorInfo:
    index: int       # 1-based, ordered left to right
    device: str      # stable-ish id such as \\.\DISPLAY2
    x: int
    y: int
    w: int
    h: int
    primary: bool

    def label(self) -> str:
        return f"{self.index}: {self.w}\u00d7{self.h}"


if IS_WIN:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(_RECT), wintypes.LPARAM
    )
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(_RECT), _MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


# ---------------------------------------------------------------------------
def set_dpi_aware() -> None:
    """Make the process per-monitor DPI aware so coordinates are real pixels.

    Must run before any window (including Tk) is created.
    """
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def list_monitors() -> List[MonitorInfo]:
    """All attached monitors ordered left to right (then top to bottom)."""
    if not IS_WIN:
        return [MonitorInfo(1, "DISPLAY1", 0, 0, 1920, 1080, True)]

    found: List[Tuple[str, int, int, int, int, bool]] = []

    def _cb(hmon, hdc, lprect, lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append((info.szDevice, r.left, r.top, r.right - r.left, r.bottom - r.top,
                          bool(info.dwFlags & 1)))
        return True

    cb = _MONITORENUMPROC(_cb)
    try:
        user32.EnumDisplayMonitors(None, None, cb, 0)
    except Exception:
        found = []
    if not found:
        w = user32.GetSystemMetrics(0) or 1920
        h = user32.GetSystemMetrics(1) or 1080
        found = [("DISPLAY1", 0, 0, w, h, True)]
    found.sort(key=lambda m: (m[1], m[2]))
    return [MonitorInfo(i + 1, d, x, y, w, h, p) for i, (d, x, y, w, h, p) in enumerate(found)]


def acquire_single_instance(name: str = "Local\\InsideVoiceSingleton"):
    """Returns a handle (keep it alive) or None when another copy is running."""
    if not IS_WIN:
        return object()
    handle = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183 or not handle:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def windows_ui_language() -> str:
    """Two-letter UI language code of Windows ('es', 'en', ...)."""
    try:
        if IS_WIN:
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = langid & 0x3FF
            return {0x0A: "es", 0x09: "en"}.get(primary, "en")
    except Exception:
        pass
    try:
        import locale

        loc = locale.getlocale()[0] or os.environ.get("LANG", "") or ""
        return "es" if loc.lower().startswith("es") else "en"
    except Exception:
        return "en"


def message_box(title: str, text: str) -> None:
    if IS_WIN:
        try:
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
            return
        except Exception:
            pass
    print(f"{title}: {text}")


# --------------------------------------------------------------- autostart
def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            exe = pythonw
    return f'"{exe}" -m inside_voice --minimized'


def set_autostart(enabled: bool) -> bool:
    """Add/remove the app from the current user's Windows startup. Returns success."""
    if not IS_WIN:
        return False
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


# ------------------------------------------------------------ own resources
def process_memory_mb() -> float:
    """Working set (RAM actually used) of this process, in MB."""
    try:
        if IS_WIN:
            counters = _PMC()
            counters.cb = ctypes.sizeof(_PMC)
            handle = kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb)
            if ok:
                return counters.WorkingSetSize / (1024 * 1024)
        else:
            with open("/proc/self/statm") as fh:
                pages = int(fh.read().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except Exception:
        pass
    return 0.0


class CpuMeter:
    """CPU use of this process (percent of the whole machine) between calls."""

    def __init__(self) -> None:
        self._cpu = time.process_time()
        self._wall = time.monotonic()
        self._n = os.cpu_count() or 1

    def sample(self) -> float:
        cpu, wall = time.process_time(), time.monotonic()
        dc, dw = cpu - self._cpu, wall - self._wall
        self._cpu, self._wall = cpu, wall
        if dw <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * dc / dw / self._n))
