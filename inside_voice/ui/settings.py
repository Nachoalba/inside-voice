"""The settings window: microphone & calibration, alert look, monitors, night mode, general."""
from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .. import __version__
from ..audio import list_input_devices
from ..config import (BLINK_MODES, BORDER_STYLES, LANGUAGES, MAX_BLINK_HZ, MAX_LEVELS, Config,
                      hhmm_to_minutes, normalize_hhmm)
from ..i18n import NATIVE_NAMES, tr
from ..schedule import night_active
from ..winapi import CpuMeter, process_memory_mb
from .widgets import ColorButton, LabeledScale, Meter, scale_of

TAB_ORDER = ("mic", "alert", "monitors", "night", "general")


class CodeCombo:
    """Combobox that shows translated names but works with stable codes."""

    def __init__(self, parent: tk.Misc, codes: List[str], names: List[str], current: str,
                 on_change=None, width: int = 24) -> None:
        self.codes = list(codes)
        self.box = ttk.Combobox(parent, values=names, state="readonly", width=width)
        idx = self.codes.index(current) if current in self.codes else 0
        self.box.current(idx)
        if on_change:
            self.box.bind("<<ComboboxSelected>>", lambda _e: on_change())

    def get(self) -> str:
        i = self.box.current()
        return self.codes[i] if 0 <= i < len(self.codes) else self.codes[0]

    def grid(self, **kw) -> None:
        self.box.grid(**kw)


class SettingsWindow:
    def __init__(self, host, app, tab: Optional[str] = None, first_run: bool = False) -> None:
        self.host = host
        self.app = app
        self.root = host.root
        self.top = tk.Toplevel(self.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self._dead = False
        self._tick_job = None
        self._preview_level = 0
        self._preview_push_job = None
        self._preview_timeout_job = None
        self._wizard = None
        self._cpu = CpuMeter()
        self._last_slow = 0.0
        self.calibrated = app.cfg.calibrated
        self.cfg: Config = app.cfg.copy()
        sc = scale_of(self.top)
        self.top.geometry(f"{int(760 * sc)}x{int(700 * sc)}")
        self.top.minsize(int(640 * sc), int(560 * sc))
        app.hold_mic(True)
        self._build(tab or "mic")
        self._tick()
        self.top.lift()
        self.top.focus_force()
        if first_run:
            self.top.after(600, self.open_wizard)

    # ------------------------------------------------------------ lifecycle
    def alive(self) -> bool:
        if self._dead:
            return False
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def focus(self, tab: Optional[str] = None) -> None:
        try:
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
            if tab in TAB_ORDER:
                self.nb.select(TAB_ORDER.index(tab))
        except tk.TclError:
            pass

    def close(self, save_prompt: bool = True) -> None:
        if self._dead:
            return
        if save_prompt and self._is_dirty():
            answer = messagebox.askyesnocancel(tr("close.title"), tr("close.unsaved"), parent=self.top)
            if answer is None:
                return
            if answer:
                self.apply()
        self._dead = True
        for job in (self._tick_job, self._preview_push_job, self._preview_timeout_job):
            if job:
                try:
                    self.top.after_cancel(job)
                except Exception:
                    pass
        if self._wizard is not None:
            self._wizard.cancel()
        self.app.stop_preview()
        self.app.hold_mic(False)
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.host.settings_closed()

    # ----------------------------------------------------------------- build
    def _build(self, tab: str) -> None:
        for child in self.top.winfo_children():
            child.destroy()
        self.top.title(f"{tr('app.title')} - {tr('settings.title')}")
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        self.nb = ttk.Notebook(self.top)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        frames = {}
        for key in TAB_ORDER:
            f = ttk.Frame(self.nb)
            f.columnconfigure(0, weight=1)
            self.nb.add(f, text=tr(f"tab.{key}"))
            frames[key] = f
        self._build_mic(frames["mic"])
        self._build_alert(frames["alert"])
        self._build_monitors(frames["monitors"])
        self._build_night(frames["night"])
        self._build_general(frames["general"])
        self._update_level_states()

        bar = ttk.Frame(self.top)
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        bar.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var, foreground="#2a7d46").grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text=tr("btn.apply"), command=self.apply).grid(row=0, column=1, padx=3)
        ttk.Button(bar, text=tr("btn.ok"), command=self._ok).grid(row=0, column=2, padx=3)
        ttk.Button(bar, text=tr("btn.cancel"), command=lambda: self.close(save_prompt=False)).grid(
            row=0, column=3, padx=3)
        if tab in TAB_ORDER:
            self.nb.select(TAB_ORDER.index(tab))

    # ----- microphone tab -------------------------------------------------
    def _build_mic(self, f: ttk.Frame) -> None:
        cfg = self.cfg
        pad = dict(padx=10, pady=4)

        box = ttk.LabelFrame(f, text=tr("mic.device_box"))
        box.grid(row=0, column=0, sticky="ew", **pad)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text=tr("mic.device")).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self._devices = [tr("mic.default")] + list_input_devices()
        if cfg.device and cfg.device not in self._devices:
            self._devices.append(cfg.device)
        self.device_var = tk.StringVar(value=cfg.device or self._devices[0])
        ttk.Combobox(box, textvariable=self.device_var, values=self._devices, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text=tr("mic.refresh"), command=self._refresh_devices).grid(row=0, column=2, padx=6)
        self.mic_status = ttk.Label(box, text="", foreground="#b3261e", wraplength=620)
        self.mic_status.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)

        mbox = ttk.LabelFrame(f, text=tr("mic.meter_box"))
        mbox.grid(row=1, column=0, sticky="ew", **pad)
        mbox.columnconfigure(0, weight=1)
        self.meter = Meter(mbox)
        self.meter.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self.voice_label = ttk.Label(mbox, text="")
        self.voice_label.grid(row=1, column=0, sticky="w", padx=8)
        ttk.Label(mbox, text=tr("mic.meter_help"), wraplength=640, foreground="#666666").grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 6))

        sbox = ttk.LabelFrame(f, text=tr("mic.sens_box"))
        sbox.grid(row=2, column=0, sticky="ew", **pad)
        sbox.columnconfigure(0, weight=1)
        self.thr_var = tk.DoubleVar(value=cfg.threshold_db)
        self.step_var = tk.DoubleVar(value=cfg.step_db)
        self.levels_var = tk.IntVar(value=cfg.num_levels)
        self.voice_filter_var = tk.BooleanVar(value=cfg.voice_filter)
        self.hold_var = tk.IntVar(value=cfg.hold_ms)
        self.release_var = tk.IntVar(value=cfg.release_ms)
        LabeledScale(sbox, tr("mic.threshold"), self.thr_var, -70, -5, 0.5, " dB").grid(
            row=0, column=0, sticky="ew", padx=8, pady=2)
        LabeledScale(sbox, tr("mic.step"), self.step_var, 1, 15, 0.5, " dB").grid(
            row=1, column=0, sticky="ew", padx=8, pady=2)
        lv = ttk.Frame(sbox)
        lv.grid(row=2, column=0, sticky="w", padx=8, pady=2)
        ttk.Label(lv, text=tr("mic.levels"), width=22).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(lv, from_=2, to=MAX_LEVELS, width=4, textvariable=self.levels_var, state="readonly",
                    command=self._update_level_states).grid(row=0, column=1)
        ttk.Checkbutton(sbox, text=tr("mic.voice_filter"), variable=self.voice_filter_var).grid(
            row=3, column=0, sticky="w", padx=8, pady=2)
        LabeledScale(sbox, tr("mic.hold"), self.hold_var, 100, 1500, 50, " ms").grid(
            row=4, column=0, sticky="ew", padx=8, pady=2)
        LabeledScale(sbox, tr("mic.release"), self.release_var, 200, 3000, 100, " ms").grid(
            row=5, column=0, sticky="ew", padx=8, pady=2)

        self.calib_label = ttk.Label(f, text="", foreground="#666666")
        self.calib_label.grid(row=3, column=0, sticky="w", padx=12)
        ttk.Button(f, text=tr("mic.calibrate"), command=self.open_wizard).grid(
            row=4, column=0, sticky="w", padx=10, pady=6)
        self._update_calib_label()

    # ----- alert tab ------------------------------------------------------
    def _build_alert(self, f: ttk.Frame) -> None:
        cfg = self.cfg
        f.rowconfigure(99, weight=1)
        top = ttk.LabelFrame(f, text=tr("alert.look_box"))
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text=tr("alert.style")).grid(row=0, column=0, sticky="w", padx=6, pady=3)
        self.style_combo = CodeCombo(top, list(BORDER_STYLES), [tr(f"style.{s}") for s in BORDER_STYLES],
                                     cfg.border_style, on_change=self._on_alert_change)
        self.style_combo.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(top, text=tr("alert.image")).grid(row=1, column=0, sticky="w", padx=6, pady=3)
        imgf = ttk.Frame(top)
        imgf.grid(row=1, column=1, sticky="ew", padx=6)
        imgf.columnconfigure(0, weight=1)
        self.image_var = tk.StringVar(value=cfg.image_path)
        ttk.Entry(imgf, textvariable=self.image_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(imgf, text=tr("alert.browse"), command=self._browse_image).grid(row=0, column=1, padx=4)
        self.image_var.trace_add("write", lambda *_: self._on_alert_change())

        ttk.Label(top, text=tr("alert.blink")).grid(row=2, column=0, sticky="w", padx=6, pady=3)
        self.blink_combo = CodeCombo(top, list(BLINK_MODES), [tr(f"blink.{m}") for m in BLINK_MODES],
                                     cfg.blink_mode, on_change=self._on_alert_change)
        self.blink_combo.grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(top, text=tr("alert.blink_note"), foreground="#666666", wraplength=640).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

        self.lv_frames: List[ttk.LabelFrame] = []
        self.lv_color: List[ColorButton] = []
        self.lv_scales: List[List[LabeledScale]] = []
        self.lv_thick: List[tk.IntVar] = []
        self.lv_opac: List[tk.IntVar] = []
        self.lv_hz: List[tk.DoubleVar] = []
        self.lv_btn: List[ttk.Button] = []
        for i in range(MAX_LEVELS):
            st = cfg.levels[i]
            lf = ttk.LabelFrame(f, text=tr("alert.level", n=i + 1))
            lf.grid(row=1 + i, column=0, sticky="ew", padx=10, pady=2)
            lf.columnconfigure(2, weight=1)
            self.lv_frames.append(lf)
            cb = ColorButton(lf, st.color, tr("alert.pick_color"), on_change=lambda _c: self._on_alert_change())
            cb.grid(row=0, column=0, rowspan=3, padx=8, pady=4)
            self.lv_color.append(cb)
            th, op, hz = tk.IntVar(value=st.thickness), tk.IntVar(value=st.opacity), tk.DoubleVar(value=st.blink_hz)
            self.lv_thick.append(th)
            self.lv_opac.append(op)
            self.lv_hz.append(hz)
            s1 = LabeledScale(lf, tr("alert.thickness"), th, 2, 200, 1, " px", label_width=14,
                              command=self._on_alert_change)
            s2 = LabeledScale(lf, tr("alert.opacity"), op, 5, 100, 5, " %", label_width=14,
                              command=self._on_alert_change)
            s3 = LabeledScale(lf, tr("alert.speed"), hz, 0, MAX_BLINK_HZ, 0.1, " Hz", label_width=14,
                              command=self._on_alert_change)
            for r, s in enumerate((s1, s2, s3)):
                s.grid(row=r, column=1, columnspan=2, sticky="ew", padx=4)
            self.lv_scales.append([s1, s2, s3])
            btn = ttk.Button(lf, text=tr("alert.try"), command=lambda n=i + 1: self._toggle_preview(n))
            btn.grid(row=0, column=3, rowspan=3, padx=8)
            self.lv_btn.append(btn)

        sound = ttk.LabelFrame(f, text=tr("sound.box"))
        sound.grid(row=1 + MAX_LEVELS, column=0, sticky="ew", padx=10, pady=(4, 2))
        sound.columnconfigure(1, weight=1)
        self.sound_var = tk.BooleanVar(value=cfg.sound_enabled)
        self.volume_var = tk.IntVar(value=cfg.sound_volume)
        ttk.Checkbutton(sound, text=tr("sound.enable"), variable=self.sound_var).grid(
            row=0, column=0, sticky="w", padx=6)
        LabeledScale(sound, tr("sound.volume"), self.volume_var, 0, 100, 5, " %", label_width=10).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(sound, text=tr("sound.test"), command=lambda: self.app.test_sound(self.collect())).grid(
            row=0, column=2, padx=6, pady=4)
        ttk.Label(sound, text=tr("sound.note"), foreground="#666666", wraplength=640).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 4))

        self.stop_prev_btn = ttk.Button(f, text=tr("alert.stop_preview"), command=self._stop_preview)
        self.stop_prev_btn.grid(row=2 + MAX_LEVELS, column=0, sticky="w", padx=10, pady=4)

    # ----- monitors tab ---------------------------------------------------
    def _build_monitors(self, f: ttk.Frame) -> None:
        cfg = self.cfg
        ttk.Label(f, text=tr("mon.help"), wraplength=660, justify="left").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        box = ttk.LabelFrame(f, text=tr("mon.box"))
        box.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        self.mon_vars: Dict[str, tk.BooleanVar] = {}
        monitors = self.app.monitors(force=True)
        for i, m in enumerate(monitors):
            chosen = (not cfg.monitors) or (m.device in cfg.monitors)
            var = tk.BooleanVar(value=chosen)
            self.mon_vars[m.device] = var
            text = f"{m.label()}   ({tr('mon.position', x=m.x, y=m.y)})"
            if m.primary:
                text += "   ★ " + tr("mon.primary")
            ttk.Checkbutton(box, text=text, variable=var).grid(row=i, column=0, sticky="w", padx=8, pady=3)
        ttk.Label(f, text=tr("mon.note"), foreground="#666666", wraplength=660).grid(
            row=2, column=0, sticky="w", padx=12, pady=4)
        btns = ttk.Frame(f)
        btns.grid(row=3, column=0, sticky="w", padx=10, pady=6)
        ttk.Button(btns, text=tr("mon.identify"), command=self.app.identify_monitors).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text=tr("mon.refresh"), command=self._refresh_monitors).grid(row=0, column=1, padx=4)

    # ----- night tab ------------------------------------------------------
    def _build_night(self, f: ttk.Frame) -> None:
        n = self.cfg.night
        ttk.Label(f, text=tr("night.help"), wraplength=660, justify="left").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        box = ttk.LabelFrame(f, text=tr("night.box"))
        box.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        box.columnconfigure(1, weight=1)
        self.night_on = tk.BooleanVar(value=n.enabled)
        ttk.Checkbutton(box, text=tr("night.enable"), variable=self.night_on).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        self.night_start = tk.StringVar(value=n.start)
        self.night_end = tk.StringVar(value=n.end)
        ttk.Label(box, text=tr("night.from")).grid(row=1, column=0, sticky="w", padx=8)
        ttk.Entry(box, textvariable=self.night_start, width=7).grid(row=1, column=1, sticky="w")
        ttk.Label(box, text=tr("night.to")).grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(box, textvariable=self.night_end, width=7).grid(row=2, column=1, sticky="w")
        ttk.Label(box, text=tr("night.time_hint"), foreground="#666666").grid(
            row=1, column=2, rowspan=2, sticky="w", padx=8)

        days = ttk.LabelFrame(f, text=tr("night.days"))
        days.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        self.night_days = []
        for d in range(7):
            var = tk.BooleanVar(value=d in n.days)
            self.night_days.append(var)
            ttk.Checkbutton(days, text=tr(f"day.{d}"), variable=var).grid(row=0, column=d, padx=6, pady=6)

        self.night_offset = tk.DoubleVar(value=n.offset_db)
        off = ttk.LabelFrame(f, text=tr("night.offset_box"))
        off.grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        off.columnconfigure(0, weight=1)
        LabeledScale(off, tr("night.offset"), self.night_offset, -30, 0, 0.5, " dB").grid(
            row=0, column=0, sticky="ew", padx=8, pady=4)
        ttk.Label(off, text=tr("night.offset_help"), foreground="#666666", wraplength=640).grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        self.night_state = ttk.Label(f, text="")
        self.night_state.grid(row=4, column=0, sticky="w", padx=12, pady=6)

    # ----- general tab ----------------------------------------------------
    def _build_general(self, f: ttk.Frame) -> None:
        cfg = self.cfg
        box = ttk.LabelFrame(f, text=tr("gen.box"))
        box.grid(row=0, column=0, sticky="ew", padx=10, pady=(12, 4))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text=tr("gen.language")).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        names = [tr("lang.auto")] + [NATIVE_NAMES[c] for c in LANGUAGES if c != "auto"]
        self.lang_combo = CodeCombo(box, list(LANGUAGES), names, cfg.language)
        self.lang_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.autostart_var = tk.BooleanVar(value=cfg.autostart)
        ttk.Checkbutton(box, text=tr("gen.autostart"), variable=self.autostart_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        self.paused_var = tk.BooleanVar(value=cfg.paused)
        ttk.Checkbutton(box, text=tr("gen.paused"), variable=self.paused_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        diag = ttk.LabelFrame(f, text=tr("diag.box"))
        diag.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        self.diag_label = ttk.Label(diag, text="")
        self.diag_label.grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Label(diag, text=tr("diag.help"), foreground="#666666", wraplength=640).grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 6))

        about = ttk.LabelFrame(f, text=tr("about.box"))
        about.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        ttk.Label(about, text=f"Inside Voice {__version__}", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        ttk.Label(about, text=tr("app.slogan")).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))

    # ------------------------------------------------------------- helpers
    def _update_calib_label(self) -> None:
        self.calib_label.config(text=tr("mic.calibrated") if self.calibrated else tr("mic.not_calibrated"))

    def _update_level_states(self) -> None:
        try:
            n = int(self.levels_var.get())
        except (tk.TclError, ValueError):
            return
        for i, lf in enumerate(self.lv_frames):
            enabled = i < n
            for s in self.lv_scales[i]:
                s.set_enabled(enabled)
            self.lv_color[i].config(state="normal" if enabled else "disabled")
            self.lv_btn[i].state(["!disabled"] if enabled else ["disabled"])

    def _rebuild_keeping_edits(self) -> None:
        """Rebuild the window (devices/monitors changed) without losing unsaved edits."""
        try:
            self.cfg = self.collect()
        except (tk.TclError, ValueError):
            pass
        self._build(self._current_tab())

    def _refresh_devices(self) -> None:
        self._rebuild_keeping_edits()

    def _refresh_monitors(self) -> None:
        self.app.monitors(force=True)
        self._rebuild_keeping_edits()

    def _current_tab(self) -> str:
        try:
            return TAB_ORDER[self.nb.index(self.nb.select())]
        except Exception:
            return "mic"

    def _browse_image(self) -> None:
        path = filedialog.askopenfilename(parent=self.top, title=tr("alert.browse_title"),
                                          filetypes=[("PNG", "*.png"), ("*", "*.*")])
        if path:
            self.image_var.set(path)

    # ------------------------------------------------------------ preview
    def _toggle_preview(self, level: int) -> None:
        if self._preview_level == level:
            self._stop_preview()
            return
        self._preview_level = level
        self._push_preview()
        self._arm_preview_timeout()
        self._update_preview_buttons()

    def _push_preview(self) -> None:
        self._preview_push_job = None
        if self._preview_level and not self._dead:
            self.app.start_preview(self.collect(), self._preview_level)

    def _on_alert_change(self) -> None:
        if not self._preview_level or self._dead:
            return
        if self._preview_push_job:
            self.top.after_cancel(self._preview_push_job)
        self._preview_push_job = self.top.after(90, self._push_preview)
        self._arm_preview_timeout()

    def _arm_preview_timeout(self) -> None:
        if self._preview_timeout_job:
            self.top.after_cancel(self._preview_timeout_job)
        self._preview_timeout_job = self.top.after(20000, self._stop_preview)

    def _stop_preview(self) -> None:
        self._preview_level = 0
        if self._preview_timeout_job:
            try:
                self.top.after_cancel(self._preview_timeout_job)
            except Exception:
                pass
            self._preview_timeout_job = None
        self.app.stop_preview()
        if not self._dead:
            self._update_preview_buttons()

    def _update_preview_buttons(self) -> None:
        for i, btn in enumerate(self.lv_btn):
            btn.config(text=tr("alert.stop") if self._preview_level == i + 1 else tr("alert.try"))

    # ---------------------------------------------------------- collect/apply
    def collect(self) -> Config:
        """Read every control into a new, validated Config."""
        cfg = self.app.cfg.copy()
        dev = self.device_var.get()
        cfg.device = None if dev in ("", tr("mic.default")) else dev
        cfg.threshold_db = float(self.thr_var.get())
        cfg.step_db = float(self.step_var.get())
        cfg.num_levels = int(self.levels_var.get())
        cfg.voice_filter = bool(self.voice_filter_var.get())
        cfg.hold_ms = int(self.hold_var.get())
        cfg.release_ms = int(self.release_var.get())
        cfg.border_style = self.style_combo.get()
        cfg.image_path = self.image_var.get().strip()
        cfg.blink_mode = self.blink_combo.get()
        for i in range(MAX_LEVELS):
            lv = cfg.levels[i]
            lv.color = self.lv_color[i].color
            lv.thickness = int(self.lv_thick[i].get())
            lv.opacity = int(self.lv_opac[i].get())
            lv.blink_hz = float(self.lv_hz[i].get())
        cfg.sound_enabled = bool(self.sound_var.get())
        cfg.sound_volume = int(self.volume_var.get())

        chosen = [d for d, v in self.mon_vars.items() if v.get()]
        cfg.monitors = [] if len(chosen) in (0, len(self.mon_vars)) else chosen

        cfg.night.enabled = bool(self.night_on.get())
        cfg.night.start = normalize_hhmm(self.night_start.get(), self.app.cfg.night.start)
        cfg.night.end = normalize_hhmm(self.night_end.get(), self.app.cfg.night.end)
        cfg.night.days = [d for d, v in enumerate(self.night_days) if v.get()]
        cfg.night.offset_db = float(self.night_offset.get())

        cfg.language = self.lang_combo.get()
        cfg.autostart = bool(self.autostart_var.get())
        cfg.paused = bool(self.paused_var.get())
        cfg.calibrated = self.calibrated
        return Config.from_dict(cfg.to_dict())

    def _is_dirty(self) -> bool:
        try:
            return self.collect().to_dict() != self.app.cfg.to_dict()
        except Exception:
            return False

    def apply(self) -> bool:
        try:
            new = self.collect()
        except (tk.TclError, ValueError):
            self.status_var.set(tr("status.invalid"))
            return False
        lang_changed = new.language != self.app.cfg.language
        ok = self.app.apply_config(new)
        self.cfg = new.copy()
        if lang_changed:
            tab = self._current_tab()
            self._build(tab)
        self.status_var.set(tr("status.saved") if ok else tr("status.save_failed"))
        return ok

    def _ok(self) -> None:
        if self.apply():
            self.close(save_prompt=False)

    # ----------------------------------------------------------- calibration
    def open_wizard(self) -> None:
        if self._wizard is not None or self._dead:
            return
        from .wizard import CalibrationWizard

        self._stop_preview()
        self._wizard = CalibrationWizard(self)

    def wizard_closed(self) -> None:
        self._wizard = None

    def apply_calibration(self, threshold_db: float, step_db: float) -> None:
        self.thr_var.set(round(threshold_db, 1))
        self.step_var.set(round(step_db, 1))
        self.calibrated = True
        self._update_calib_label()
        self.apply()

    # ------------------------------------------------------------------ tick
    def _working_thresholds(self) -> List[float]:
        try:
            base = float(self.thr_var.get())
            step = float(self.step_var.get())
            n = int(self.levels_var.get())
            if self.night_on.get() and night_active(self.collect().night, datetime.now()):
                base += float(self.night_offset.get())
            return [base + i * step for i in range(n)]
        except Exception:
            return []

    def _tick(self) -> None:
        if self._dead:
            return
        try:
            app = self.app
            thr = self._working_thresholds()
            colors = [self.lv_color[i].color for i in range(len(thr))]
            self.meter.update_state(app.last_db, app.last_voiced, thr, colors)
            if app.last_voiced:
                self.voice_label.config(text=tr("mic.voice_yes"), foreground="#2a7d46")
            else:
                self.voice_label.config(text=tr("mic.voice_no"), foreground="#666666")
            now = time.monotonic()
            if now - self._last_slow > 1.0:
                self._last_slow = now
                err = app.mic_error
                self.mic_status.config(text=tr("mic.error", err=err) if err else "")
                self.diag_label.config(text=tr("diag.values", cpu=f"{self._cpu.sample():.1f}",
                                               ram=f"{process_memory_mb():.0f}"))
                night = night_active(self.collect().night, datetime.now())
                self.night_state.config(text=tr("night.now_on") if night else tr("night.now_off"))
        except Exception:
            pass
        self._tick_job = self.top.after(50, self._tick)
