"""Guided calibration: talk normally, then talk loudly; the threshold is computed for you."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from ..calibration import MIN_VOICE_FRAMES, CalibrationResult, compute_threshold
from ..i18n import tr
from .widgets import Meter, scale_of

DURATION_S = 6.0
COUNTDOWN_S = 3
MIN_DB_FOR_SAMPLE = -65.0


class CalibrationWizard:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.app = settings.app
        self.top = tk.Toplevel(settings.top)
        self.top.title(tr("wiz.title"))
        self.top.transient(settings.top)
        sc = scale_of(self.top)
        self.top.geometry(f"{int(560 * sc)}x{int(400 * sc)}")
        self.top.resizable(False, False)
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)

        self._closed = False
        self._job: Optional[str] = None
        self._state = "intro"      # intro | countdown | collect | between | result
        self._phase = "normal"     # normal | loud
        self._t0 = 0.0
        self._samples = {"normal": [], "loud": []}  # type: dict
        self._collecting: Optional[str] = None
        self._result: Optional[CalibrationResult] = None
        self._thr: List[float] = []
        self._colors: List[str] = []

        self.top.columnconfigure(0, weight=1)
        self.heading = ttk.Label(self.top, text="", font=("Segoe UI", 12, "bold"), wraplength=int(520 * sc))
        self.heading.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self.body = ttk.Label(self.top, text="", wraplength=int(520 * sc), justify="left")
        self.body.grid(row=1, column=0, sticky="w", padx=16, pady=4)
        self.meter = Meter(self.top, width=520)
        self.meter.grid(row=2, column=0, padx=16, pady=8)
        self.progress = ttk.Progressbar(self.top, maximum=100, length=int(520 * sc))
        self.progress.grid(row=3, column=0, padx=16, pady=4)
        self.note = ttk.Label(self.top, text="", wraplength=int(520 * sc), foreground="#b3261e")
        self.note.grid(row=4, column=0, sticky="w", padx=16)
        bar = ttk.Frame(self.top)
        bar.grid(row=5, column=0, sticky="e", padx=16, pady=12)
        self.btn_main = ttk.Button(bar, text="", command=lambda: None)
        self.btn_main.grid(row=0, column=0, padx=4)
        self.btn_alt = ttk.Button(bar, text="", command=lambda: None)
        self.btn_alt.grid(row=0, column=1, padx=4)
        ttk.Button(bar, text=tr("btn.cancel"), command=self.cancel).grid(row=0, column=2, padx=4)

        self.app.begin_calibration()
        self.app.add_listener(self._on_frame)
        self._show_intro()
        self._tick()
        try:
            self.top.after(100, self._grab)
        except tk.TclError:
            pass

    # ----------------------------------------------------------------- misc
    def _grab(self) -> None:
        try:
            self.top.grab_set()
            self.top.focus_set()
        except tk.TclError:
            pass

    def _on_frame(self, db: float, voiced: bool) -> None:  # audio thread
        phase = self._collecting
        if phase and voiced and db > MIN_DB_FOR_SAMPLE:
            self._samples[phase].append(db)

    def cancel(self) -> None:
        self._finish()

    def _finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._job:
            try:
                self.top.after_cancel(self._job)
            except Exception:
                pass
        self.app.remove_listener(self._on_frame)
        self.app.end_calibration()
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.settings.wizard_closed()

    def _set_buttons(self, main_text: str, main_cmd, alt_text: str = "", alt_cmd=None) -> None:
        self.btn_main.config(text=main_text, command=main_cmd, state="normal" if main_cmd else "disabled")
        if alt_text:
            self.btn_alt.config(text=alt_text, command=alt_cmd)
            self.btn_alt.grid()
        else:
            self.btn_alt.grid_remove()

    # --------------------------------------------------------------- screens
    def _show_intro(self) -> None:
        self._state = "intro"
        self._collecting = None
        self._samples = {"normal": [], "loud": []}
        dev = self.app.cfg.device or tr("mic.default")
        self.heading.config(text=tr("wiz.intro_title"))
        self.body.config(text=tr("wiz.intro", mic=dev))
        self.note.config(text="")
        self.progress.config(value=0)
        self._thr, self._colors = [], []
        self._set_buttons(tr("wiz.start"), lambda: self._begin_countdown("normal"))

    def _begin_countdown(self, phase: str) -> None:
        self._phase = phase
        self._state = "countdown"
        self._collecting = None
        self._t0 = time.monotonic()
        self.note.config(text="")
        self.heading.config(text=tr("wiz.normal_title") if phase == "normal" else tr("wiz.loud_title"))
        self.body.config(text=tr("wiz.normal_help") if phase == "normal" else tr("wiz.loud_help"))
        self._set_buttons(tr("btn.cancel"), self.cancel)

    def _begin_collect(self) -> None:
        self._state = "collect"
        self._samples[self._phase] = []
        self._collecting = self._phase
        self._t0 = time.monotonic()
        self.heading.config(text=tr("wiz.speak_normal") if self._phase == "normal" else tr("wiz.speak_loud"))
        self._set_buttons("...", None)

    def _end_collect(self) -> None:
        phase = self._phase
        self._collecting = None
        samples = list(self._samples[phase])
        self.progress.config(value=100)
        if len(samples) < MIN_VOICE_FRAMES:
            self._state = "between"
            self.heading.config(text=tr("wiz.no_voice_title"))
            self.body.config(text=tr("wiz.no_voice"))
            self.note.config(text="")
            self._set_buttons(tr("wiz.retry"), lambda: self._begin_countdown(phase))
            return
        if phase == "normal":
            self._state = "between"
            self.heading.config(text=tr("wiz.ok_normal_title"))
            self.body.config(text=tr("wiz.ok_normal"))
            self._set_buttons(tr("wiz.next"), lambda: self._begin_countdown("loud"),
                              tr("wiz.retry"), lambda: self._begin_countdown("normal"))
            return
        # loud finished: compute
        levels = int(self.settings.levels_var.get())
        res = compute_threshold(self._samples["normal"], self._samples["loud"], levels)
        self._result = res
        if not res.ok:
            self._state = "between"
            self.heading.config(text=tr("wiz.no_voice_title"))
            self.body.config(text=tr("wiz.no_voice"))
            self._set_buttons(tr("wiz.retry"), lambda: self._begin_countdown("loud"))
            return
        self._state = "result"
        self.heading.config(text=tr("wiz.result_title"))
        self.body.config(text=tr("wiz.result", thr=f"{res.threshold_db:.1f}", step=f"{res.step_db:.1f}",
                                 normal=f"{res.normal_db:.1f}", loud=f"{res.loud_db:.1f}"))
        self.note.config(text=tr("wiz.too_close") if res.reason == "too_close" else "")
        self._thr = [res.threshold_db + i * res.step_db for i in range(levels)]
        self._colors = [self.settings.lv_color[i].color for i in range(levels)]
        self._set_buttons(tr("wiz.accept"), self._accept, tr("wiz.redo"), self._show_intro)

    def _accept(self) -> None:
        res = self._result
        if res and res.ok:
            self.settings.apply_calibration(res.threshold_db, res.step_db)
        self._finish()

    # ------------------------------------------------------------------ tick
    def _tick(self) -> None:
        if self._closed:
            return
        try:
            now = time.monotonic()
            self.meter.update_state(self.app.last_db, self.app.last_voiced, self._thr, self._colors)
            if self._state == "countdown":
                left = COUNTDOWN_S - (now - self._t0)
                if left <= 0:
                    self._begin_collect()
                else:
                    self.progress.config(value=0)
                    self.note.config(text=tr("wiz.get_ready", n=int(left) + 1), foreground="#666666")
            elif self._state == "collect":
                frac = (now - self._t0) / DURATION_S
                self.progress.config(value=min(100, frac * 100))
                self.note.config(text=tr("wiz.voice_frames", n=len(self._samples[self._phase])),
                                 foreground="#666666")
                if frac >= 1.0:
                    self._end_collect()
        except Exception:
            pass
        self._job = self.top.after(50, self._tick)
