"""Reusable tkinter widgets: level meter, labelled slider, colour button."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Callable, List, Optional, Sequence

MIN_DB = -80.0
MAX_DB = 0.0


def scale_of(widget: tk.Misc) -> float:
    """UI scale factor (1.0 at 96 dpi) so pixel sizes look right on high-DPI screens."""
    try:
        return max(1.0, float(widget.winfo_fpixels("1i")) / 96.0)
    except Exception:
        return 1.0


class Meter(tk.Canvas):
    """Horizontal dB meter with threshold markers for every alert level."""

    def __init__(self, parent: tk.Misc, width: int = 440, height: int = 34) -> None:
        sc = scale_of(parent)
        self.w = int(width * sc)
        self.h = int(height * sc)
        super().__init__(parent, width=self.w, height=self.h, highlightthickness=1,
                         highlightbackground="#888888", background="#12162a")
        self._shown = MIN_DB
        self._font = ("Segoe UI", max(7, int(8 * sc ** 0.5)))

    def _x(self, db: float) -> int:
        frac = (db - MIN_DB) / (MAX_DB - MIN_DB)
        return int(max(0.0, min(1.0, frac)) * (self.w - 2)) + 1

    def update_state(self, db: float, voiced: bool, thresholds: Sequence[float],
                     colors: Sequence[str]) -> None:
        # fast attack, slow release (about 24 dB per second)
        self._shown = max(db, self._shown - 1.2)
        self.delete("all")
        # bar: green under the first threshold, then one colour per alert level
        bounds = [MIN_DB] + list(thresholds) + [MAX_DB]
        seg_colors = ["#2fb36a"] + list(colors)
        if not voiced:
            seg_colors = ["#4a5578"] * len(seg_colors)
        top, bottom = int(self.h * 0.2), int(self.h * 0.8)
        for i in range(len(bounds) - 1):
            lo = bounds[i]
            hi = min(bounds[i + 1], self._shown)
            if hi > lo:
                self.create_rectangle(self._x(lo), top, self._x(hi), bottom,
                                      fill=seg_colors[min(i, len(seg_colors) - 1)], width=0)
        for i, thr in enumerate(thresholds):
            x = self._x(thr)
            self.create_line(x, 2, x, self.h - 2, fill="#ffffff", width=2)
            self.create_text(x + 3, 3, text=str(i + 1), anchor="nw", fill="#ffffff", font=self._font)
        self.create_text(self.w - 4, self.h - 3, text=f"{self._shown:5.1f} dB", anchor="se",
                         fill="#cfd5f0", font=self._font)


class LabeledScale(ttk.Frame):
    """Label + slider + live value, bound to a tk variable."""

    def __init__(self, parent: tk.Misc, text: str, variable: tk.Variable, from_: float, to: float,
                 resolution: float = 1.0, unit: str = "", label_width: int = 22,
                 command: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.var = variable
        self.res = resolution
        self.unit = unit
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text=text, width=label_width).grid(row=0, column=0, sticky="w")
        self.scale = ttk.Scale(self, from_=from_, to=to, variable=variable, orient="horizontal",
                               command=lambda _v: self._changed(command))
        self.scale.grid(row=0, column=1, sticky="ew", padx=6)
        self.value_label = ttk.Label(self, width=9, anchor="e")
        self.value_label.grid(row=0, column=2, sticky="e")
        self._changed(None)

    def _changed(self, command: Optional[Callable[[], None]]) -> None:
        try:
            raw = float(self.var.get())
        except (tk.TclError, ValueError):
            return
        snapped = round(raw / self.res) * self.res
        if abs(snapped - raw) > 1e-9:
            self.var.set(int(snapped) if isinstance(self.var, tk.IntVar) else round(snapped, 2))
        shown = int(snapped) if float(self.res).is_integer() else round(snapped, 1)
        self.value_label.config(text=f"{shown}{self.unit}")
        if command:
            command()

    def set_enabled(self, enabled: bool) -> None:
        self.scale.state(["!disabled"] if enabled else ["disabled"])


class ColorButton(tk.Button):
    """A button showing a colour swatch; click to pick another colour."""

    def __init__(self, parent: tk.Misc, color: str, title: str,
                 on_change: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(parent, width=7, relief="groove", command=self._pick)
        self._title = title
        self._on_change = on_change
        self.color = color
        self._paint()

    def _paint(self) -> None:
        r, g, b = (int(self.color[i:i + 2], 16) for i in (1, 3, 5))
        fg = "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"
        self.config(bg=self.color, activebackground=self.color, fg=fg, activeforeground=fg,
                    text=self.color)

    def set_color(self, color: str) -> None:
        self.color = color.upper()
        self._paint()

    def _pick(self) -> None:
        picked = colorchooser.askcolor(color=self.color, title=self._title, parent=self.winfo_toplevel())
        if picked and picked[1]:
            self.set_color(picked[1])
            if self._on_change:
                self._on_change(self.color)
