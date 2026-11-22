"""Click-through, always-on-top border windows (one per monitor) using Win32 layered windows.

Design for low overhead:
  * windows exist only while an alert is showing (memory is freed afterwards);
  * the border bitmap is rendered once per alert level, blinking only changes the
    window transparency (UpdateLayeredWindow with a new blend value);
  * a ~30 Hz timer runs only while something is visible and blinking.

All Win32 work happens in one dedicated thread that owns the windows and runs the
message loop. Other threads talk to it through a queue.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .render import blink_alpha, load_image, render_border
from .winapi import MonitorInfo

IS_WIN = sys.platform == "win32"


@dataclass(frozen=True)
class OverlayTarget:
    """Everything needed to draw the border on one monitor."""
    monitor: MonitorInfo
    color: Tuple[int, int, int]
    thickness_px: int
    opacity: int          # percent
    blink_hz: float
    blink_mode: str
    border_style: str
    image_path: str = ""


class NullOverlay:
    """Used on non-Windows systems and in tests. Records what it was asked to show."""

    def __init__(self) -> None:
        self.shown: List[OverlayTarget] = []
        self.identified: List[MonitorInfo] = []

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def show(self, targets: List[OverlayTarget]) -> None:
        self.shown = list(targets)

    def clear(self) -> None:
        self.shown = []

    def identify(self, monitors: List[MonitorInfo], seconds: float = 2.5) -> None:
        self.identified = list(monitors)


if not IS_WIN:
    OverlayManager = NullOverlay  # type: ignore[misc,assignment]
else:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    WS_POPUP = 0x80000000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    SW_SHOWNOACTIVATE = 4
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
    ULW_ALPHA = 0x2
    AC_SRC_OVER, AC_SRC_ALPHA = 0, 1
    BI_RGB, DIB_RGB_COLORS = 0, 0
    WM_TIMER, WM_APP = 0x0113, 0x8000
    WM_WAKE, WM_QUIT_LOOP = WM_APP + 1, WM_APP + 2
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_MESSAGE = wintypes.HWND(-3)
    TIMER_ID = 1
    TICK_MS = 33
    CLASS_NAME = "InsideVoiceOverlay"

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
            ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
            ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
        ]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]

    # --- prototypes (essential on 64-bit Windows: handles are pointer sized)
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
        wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
        ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
    ]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    # ------------------------------------------------------------------
    class _Win:
        """One layered window showing a BGRA bitmap."""

        def __init__(self, hinst) -> None:
            self.hwnd = None
            self.hdc_mem = None
            self.hbm = None
            self.old = None
            self.rect = (0, 0, 0, 0)
            self.alpha = 255
            self.key: object = None          # what was rendered (to detect changes)
            self.blink: Tuple[float, str, int] = (0.0, "off", 100)
            self.expires: Optional[float] = None
            self._null_blend_ok = True
            ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            self.hwnd = user32.CreateWindowExW(ex, CLASS_NAME, "Inside Voice", WS_POPUP,
                                               0, 0, 0, 0, None, None, hinst, None)

        def ok(self) -> bool:
            return bool(self.hwnd)

        def set_bitmap(self, bgra, x: int, y: int, alpha: int) -> None:
            h, w = bgra.shape[0], bgra.shape[1]
            screen = user32.GetDC(None)
            try:
                self._free_bitmap()
                self.hdc_mem = gdi32.CreateCompatibleDC(screen)
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = w
                bmi.bmiHeader.biHeight = -h  # top-down
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = BI_RGB
                bits = ctypes.c_void_p()
                self.hbm = gdi32.CreateDIBSection(self.hdc_mem, ctypes.byref(bmi), DIB_RGB_COLORS,
                                                  ctypes.byref(bits), None, 0)
                if not self.hbm or not bits.value:
                    return
                ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
                self.old = gdi32.SelectObject(self.hdc_mem, self.hbm)
                self.rect = (x, y, w, h)
                self.alpha = alpha
                pt_dst = wintypes.POINT(x, y)
                size = wintypes.SIZE(w, h)
                pt_src = wintypes.POINT(0, 0)
                blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha, AC_SRC_ALPHA)
                user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(pt_dst), ctypes.byref(size),
                                           self.hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)
                user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
                self.raise_topmost()
            finally:
                user32.ReleaseDC(None, screen)

        def set_alpha(self, alpha: int) -> None:
            alpha = max(0, min(255, int(alpha)))
            if alpha == self.alpha or not self.hdc_mem:
                return
            self.alpha = alpha
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha, AC_SRC_ALPHA)
            if self._null_blend_ok:
                ok = user32.UpdateLayeredWindow(self.hwnd, None, None, None, None, None, 0,
                                                ctypes.byref(blend), ULW_ALPHA)
                if ok:
                    return
                self._null_blend_ok = False  # fall back to the full call below
            x, y, w, h = self.rect
            screen = user32.GetDC(None)
            try:
                pt_dst = wintypes.POINT(x, y)
                size = wintypes.SIZE(w, h)
                pt_src = wintypes.POINT(0, 0)
                user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(pt_dst), ctypes.byref(size),
                                           self.hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)
            finally:
                user32.ReleaseDC(None, screen)

        def raise_topmost(self) -> None:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

        def _free_bitmap(self) -> None:
            if self.hdc_mem:
                if self.old:
                    gdi32.SelectObject(self.hdc_mem, self.old)
                    self.old = None
                if self.hbm:
                    gdi32.DeleteObject(self.hbm)
                    self.hbm = None
                gdi32.DeleteDC(self.hdc_mem)
                self.hdc_mem = None

        def destroy(self) -> None:
            self._free_bitmap()
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None

    # ------------------------------------------------------------------
    _MANAGER: Optional["OverlayManager"] = None

    def _wndproc(hwnd, msg, wparam, lparam):
        mgr = _MANAGER
        if mgr is not None:
            try:
                if msg == WM_WAKE:
                    mgr._drain()
                    return 0
                if msg == WM_TIMER:
                    mgr._tick()
                    return 0
                if msg == WM_QUIT_LOOP:
                    mgr._shutdown()
                    return 0
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    _WNDPROC_REF = WNDPROC(_wndproc)  # keep alive for the lifetime of the process

    class OverlayManager:
        def __init__(self) -> None:
            self._q: "queue.Queue[tuple]" = queue.Queue()
            self._thread: Optional[threading.Thread] = None
            self._ready = threading.Event()
            self._ctrl = None
            self._hinst = None
            self._wins: Dict[str, _Win] = {}
            self._ident: List[_Win] = []
            self._timer_on = False
            self._last_raise = 0.0
            self._image_cache: Tuple[str, object] = ("", None)
            self.error: Optional[str] = None

        # ----- public API (thread safe) ---------------------------------
        def start(self) -> None:
            global _MANAGER
            if self._thread:
                return
            _MANAGER = self
            self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
            self._thread.start()
            self._ready.wait(5.0)

        def stop(self) -> None:
            if self._thread and self._ctrl:
                user32.PostMessageW(self._ctrl, WM_QUIT_LOOP, 0, 0)
                self._thread.join(2.0)
            self._thread = None

        def show(self, targets: List[OverlayTarget]) -> None:
            self._send(("show", list(targets)))

        def clear(self) -> None:
            self._send(("clear",))

        def identify(self, monitors: List[MonitorInfo], seconds: float = 2.5) -> None:
            self._send(("ident", list(monitors), float(seconds)))

        # ----- internals ------------------------------------------------
        def _send(self, cmd: tuple) -> None:
            if not self._thread or not self._ctrl:
                return
            self._q.put(cmd)
            user32.PostMessageW(self._ctrl, WM_WAKE, 0, 0)

        def _run(self) -> None:
            try:
                self._hinst = kernel32.GetModuleHandleW(None)
                wc = WNDCLASSW()
                wc.lpfnWndProc = _WNDPROC_REF
                wc.hInstance = self._hinst
                wc.lpszClassName = CLASS_NAME
                user32.RegisterClassW(ctypes.byref(wc))  # fine if it already exists
                self._ctrl = user32.CreateWindowExW(0, CLASS_NAME, "ivctl", 0, 0, 0, 0, 0,
                                                    HWND_MESSAGE, None, self._hinst, None)
            except Exception as exc:  # pragma: no cover - environment specific
                self.error = repr(exc)
            finally:
                self._ready.set()
            if not self._ctrl:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self._destroy_all()

        def _shutdown(self) -> None:
            self._destroy_all()
            user32.PostQuitMessage(0)

        def _destroy_all(self) -> None:
            self._set_timer(False)
            for w in list(self._wins.values()) + self._ident:
                w.destroy()
            self._wins.clear()
            self._ident.clear()

        def _drain(self) -> None:
            while True:
                try:
                    cmd = self._q.get_nowait()
                except queue.Empty:
                    break
                try:
                    if cmd[0] == "show":
                        self._do_show(cmd[1])
                    elif cmd[0] == "clear":
                        self._do_clear()
                    elif cmd[0] == "ident":
                        self._do_ident(cmd[1], cmd[2])
                except Exception as exc:  # never let a drawing error kill the loop
                    self.error = repr(exc)
            self._update_timer()

        def _image(self, path: str):
            if self._image_cache[0] != path:
                self._image_cache = (path, load_image(path))
            return self._image_cache[1]

        def _do_show(self, targets: List[OverlayTarget]) -> None:
            wanted = {t.monitor.device: t for t in targets}
            for dev in [d for d in self._wins if d not in wanted]:
                self._wins.pop(dev).destroy()
            now = time.monotonic()
            for dev, t in wanted.items():
                win = self._wins.get(dev)
                key = (t.monitor.x, t.monitor.y, t.monitor.w, t.monitor.h, t.color, t.thickness_px,
                       t.border_style, t.image_path)
                alpha = blink_alpha(now, t.blink_hz, t.blink_mode, t.opacity)
                if win is None or not win.ok():
                    win = _Win(self._hinst)
                    if not win.ok():
                        continue
                    self._wins[dev] = win
                    win.key = None
                if win.key != key:
                    img = self._image(t.image_path) if t.border_style == "image" else None
                    bgra = render_border(t.monitor.w, t.monitor.h, t.border_style, t.color, t.thickness_px, img)
                    win.set_bitmap(bgra, t.monitor.x, t.monitor.y, alpha)
                    win.key = key
                    del bgra
                win.blink = (t.blink_hz, t.blink_mode, t.opacity)
                win.set_alpha(alpha)

        def _do_clear(self) -> None:
            for w in self._wins.values():
                w.destroy()
            self._wins.clear()

        def _do_ident(self, monitors: List[MonitorInfo], seconds: float) -> None:
            for w in self._ident:
                w.destroy()
            self._ident = []
            for m in monitors:
                win = _Win(self._hinst)
                if not win.ok():
                    continue
                size = max(260, min(m.w, m.h) // 3)
                bgra = _ident_bitmap(size, str(m.index), f"{m.w}×{m.h}")
                win.set_bitmap(bgra, m.x + (m.w - size) // 2, m.y + (m.h - size) // 2, 235)
                win.expires = time.monotonic() + seconds
                self._ident.append(win)

        def _tick(self) -> None:
            now = time.monotonic()
            for w in self._wins.values():
                hz, mode, op = w.blink
                w.set_alpha(blink_alpha(now, hz, mode, op))
            if self._ident:
                keep = []
                for w in self._ident:
                    if w.expires is not None and now >= w.expires:
                        w.destroy()
                    else:
                        keep.append(w)
                self._ident = keep
            if (self._wins or self._ident) and now - self._last_raise > 2.0:
                self._last_raise = now
                for w in list(self._wins.values()) + self._ident:
                    w.raise_topmost()
            self._update_timer()

        def _needs_timer(self) -> bool:
            if self._ident:
                return True
            return any(w.blink[1] != "off" and w.blink[0] > 0 for w in self._wins.values())

        def _update_timer(self) -> None:
            self._set_timer(self._needs_timer())

        def _set_timer(self, on: bool) -> None:
            if on and not self._timer_on and self._ctrl:
                user32.SetTimer(self._ctrl, TIMER_ID, TICK_MS, None)
                self._timer_on = True
            elif not on and self._timer_on and self._ctrl:
                user32.KillTimer(self._ctrl, TIMER_ID)
                self._timer_on = False


def _ident_bitmap(size: int, number: str, subtitle: str):
    """Rounded dark badge with a big monitor number (premultiplied BGRA)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, size - 5, size - 5), radius=size // 8, fill=(20, 24, 40, 235),
                        outline=(255, 200, 0, 255), width=max(3, size // 60))

    def font(px: int):
        for name in ("segoeuib.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                continue
        try:
            return ImageFont.load_default(px)
        except Exception:
            return ImageFont.load_default()

    big, small = font(int(size * 0.55)), font(int(size * 0.11))
    d.text((size / 2, size * 0.45), number, font=big, fill=(255, 255, 255, 255), anchor="mm")
    d.text((size / 2, size * 0.86), subtitle, font=small, fill=(200, 205, 230, 255), anchor="mm")
    arr = np.asarray(img, dtype=np.uint16)
    a = arr[:, :, 3]
    out = np.empty((size, size, 4), dtype=np.uint8)
    out[:, :, 0] = (arr[:, :, 2] * a // 255).astype(np.uint8)
    out[:, :, 1] = (arr[:, :, 1] * a // 255).astype(np.uint8)
    out[:, :, 2] = (arr[:, :, 0] * a // 255).astype(np.uint8)
    out[:, :, 3] = a.astype(np.uint8)
    return np.ascontiguousarray(out)
