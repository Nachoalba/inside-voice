"""Application controller: wires audio -> detector -> overlay and owns the config."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from . import __version__
from .alert_sound import AlertSound
from .audio import FRAME_MS, AudioEngine
from .config import Config, config_exists, load_config, save_config
from .detector import Detector
from .i18n import i18n, tr
from .overlay import OverlayManager, OverlayTarget
from .render import hex_to_rgb, scale_thickness
from .schedule import effective_threshold, night_active
from .winapi import MonitorInfo, list_monitors, set_autostart

FrameListener = Callable[[float, bool], None]


class App:
    def __init__(self, minimized: bool = False) -> None:
        existed = config_exists()
        self.cfg: Config = load_config()
        self.first_run = (not existed) or (not self.cfg.calibrated)
        self.minimized = minimized
        i18n.set_language(self.cfg.language)

        self.detector = Detector(FRAME_MS)
        self.overlay = OverlayManager()
        self.sound = AlertSound()
        self.engine = AudioEngine(self._on_frame)
        self.engine.voice_filter = self.cfg.voice_filter

        self.ui = None      # set by main()
        self.tray = None    # set by main()

        self.last_db = -120.0
        self.last_voiced = False
        self.level = 0
        self.mic_error: Optional[str] = None

        self._listeners: List[FrameListener] = []
        self._suppress = 0               # >0 while calibrating
        self._preview_level = 0
        self._mic_holds = 0              # settings/wizard open: keep the mic on for the meter
        self._monitors: List[MonitorInfo] = []
        self._monitors_at = 0.0
        self._thr_at = 0.0
        self._last_health = 0.0
        self._lock = threading.RLock()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.overlay.start()
        self._configure_detector(force=True)
        self._sync_engine()
        if self.cfg.autostart:
            set_autostart(True)

    def shutdown(self) -> None:
        try:
            self.engine.stop()
        finally:
            self.overlay.clear()
            self.overlay.stop()

    # -------------------------------------------------------------- monitors
    def monitors(self, force: bool = False) -> List[MonitorInfo]:
        now = time.monotonic()
        if force or not self._monitors or now - self._monitors_at > 3.0:
            try:
                self._monitors = list_monitors()
            except Exception:
                pass
            self._monitors_at = now
        return self._monitors

    def selected_monitors(self, cfg: Optional[Config] = None) -> List[MonitorInfo]:
        cfg = cfg or self.cfg
        all_m = self.monitors()
        chosen = [m for m in all_m if not cfg.monitors or m.device in cfg.monitors]
        return chosen or all_m  # a saved monitor that is gone: fall back to all

    def targets_for(self, cfg: Config, level: int) -> List[OverlayTarget]:
        level = max(1, min(level, cfg.num_levels))
        style = cfg.levels[level - 1]
        return [
            OverlayTarget(
                monitor=m,
                color=hex_to_rgb(style.color),
                thickness_px=scale_thickness(style.thickness, m.h),
                opacity=style.opacity,
                blink_hz=style.blink_hz,
                blink_mode=cfg.blink_mode,
                border_style=cfg.border_style,
                image_path=cfg.image_path,
            )
            for m in self.selected_monitors(cfg)
        ]

    # ----------------------------------------------------------- audio frames
    def add_listener(self, fn: FrameListener) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)

    def remove_listener(self, fn: FrameListener) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _configure_detector(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._thr_at < 1.0:
            return
        self._thr_at = now
        cfg = self.cfg
        self.detector.configure(
            threshold_db=effective_threshold(cfg, datetime.now()),
            step_db=cfg.step_db,
            num_levels=cfg.num_levels,
            hold_ms=cfg.hold_ms,
            release_ms=cfg.release_ms,
        )

    def current_thresholds(self) -> List[float]:
        self._configure_detector()
        return self.detector.level_thresholds()

    def night_now(self) -> bool:
        return night_active(self.cfg.night, datetime.now())

    def _on_frame(self, db: float, voiced: bool) -> None:  # audio thread
        self.last_db = db
        self.last_voiced = voiced
        for fn in list(self._listeners):
            try:
                fn(db, voiced)
            except Exception:
                pass
        if self._suppress or self.cfg.paused:
            return
        self._configure_detector()
        level = self.detector.update(db, voiced)
        if level != self.level:
            old, self.level = self.level, level
            if not self._preview_level:
                self._show_level(level, old)

    def _show_level(self, level: int, old: int = 0) -> None:
        if level <= 0:
            self.overlay.clear()
        else:
            self.overlay.show(self.targets_for(self.cfg, level))
            if level > old and self.cfg.sound_enabled:
                self.sound.play(level, self.cfg.sound_volume)
        if self.tray:
            self.tray.set_alert(level > 0)

    # -------------------------------------------------------------- engine
    def _wants_mic(self) -> bool:
        return (not self.cfg.paused) or self._mic_holds > 0

    def _sync_engine(self) -> None:
        with self._lock:
            if self._wants_mic():
                if not self.engine.running:
                    ok = self.engine.start(self.cfg.device)
                    self.mic_error = None if ok else (self.engine.last_error or "unknown")
            else:
                self.engine.stop()
                self.detector.reset()
                self.level = 0
                self.overlay.clear()

    def hold_mic(self, hold: bool) -> None:
        """Keep the microphone open while a window with a live meter is shown."""
        self._mic_holds = max(0, self._mic_holds + (1 if hold else -1))
        self._sync_engine()

    def check_health(self) -> None:
        """Called every few seconds from the UI loop: reopen the mic if it was lost."""
        now = time.monotonic()
        if now - self._last_health < 5.0:
            return
        self._last_health = now
        if self._wants_mic() and (not self.engine.running or
                                  (self.engine.last_frame_time and now - self.engine.last_frame_time > 3.0)):
            self.engine.stop()
            self._sync_engine()
        # also refresh the monitor list so plugging a screen in/out is noticed
        self.monitors(force=True)

    # --------------------------------------------------------------- config
    def apply_config(self, new: Config, save: bool = True) -> bool:
        """Apply a new configuration. Returns False if it could not be saved."""
        old = self.cfg
        self.cfg = new
        self.engine.voice_filter = new.voice_filter
        if new.language != old.language:
            i18n.set_language(new.language)
        if new.autostart != old.autostart:
            set_autostart(new.autostart)
        self._configure_detector(force=True)
        if new.device != old.device and self.engine.running:
            self.engine.stop()
        self._sync_engine()
        if new.paused != old.paused:
            self.detector.reset()
            self.level = 0
            self.overlay.clear()
        saved = save_config(new) if save else True
        if self.tray:
            self.tray.refresh()
        return saved

    def set_paused(self, paused: bool) -> None:
        cfg = self.cfg.copy()
        cfg.paused = bool(paused)
        self.apply_config(cfg)

    def toggle_paused(self) -> None:
        self.set_paused(not self.cfg.paused)

    # ------------------------------------------------------------- previews
    def start_preview(self, cfg: Config, level: int) -> None:
        """Show the alert for a given level using `cfg` (not saved)."""
        self._preview_level = max(1, level)
        self.overlay.show(self.targets_for(cfg, self._preview_level))

    def stop_preview(self) -> None:
        if not self._preview_level:
            return
        self._preview_level = 0
        if self.level:
            self._show_level(self.level, self.level)  # restore the real alert (no sound)
        else:
            self.overlay.clear()

    def test_sound(self, cfg: Config) -> None:
        self.sound.play(3, cfg.sound_volume, force=True)

    def identify_monitors(self) -> None:
        self.overlay.identify(self.monitors(force=True), 2.5)

    # ----------------------------------------------------------- calibration
    def begin_calibration(self) -> None:
        self._suppress += 1
        self.stop_preview()
        self.overlay.clear()
        self.hold_mic(True)

    def end_calibration(self) -> None:
        self._suppress = max(0, self._suppress - 1)
        self.detector.reset()
        self.level = 0
        self.hold_mic(False)

    # ---------------------------------------------------------------- quit
    def quit(self) -> None:
        if self.tray:
            self.tray.stop()
        if self.ui:
            self.ui.post(self.ui.quit)
