"""Owns the (hidden) Tk root and the main loop. Other threads talk to it via post()."""
from __future__ import annotations

import queue
import tkinter as tk
from typing import Optional

from ..icon import icon_png_base64
from ..i18n import tr
from .settings import SettingsWindow


class UIHost:
    POLL_MS = 150

    def __init__(self, app) -> None:
        self.app = app
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Inside Voice")
        try:
            self._icon = tk.PhotoImage(data=icon_png_base64(64))
            self.root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self.settings: Optional[SettingsWindow] = None
        self.root.after(self.POLL_MS, self._poll)

    # --------------------------------------------------------------- threads
    def post(self, fn, *args) -> None:
        """Run fn(*args) on the UI thread (safe to call from any thread)."""
        self._q.put((fn, args))

    def _poll(self) -> None:
        while True:
            try:
                fn, args = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception as exc:  # keep the app alive whatever a callback does
                print("UI callback error:", repr(exc))
        try:
            self.app.check_health()
        except Exception:
            pass
        self.root.after(self.POLL_MS, self._poll)

    # --------------------------------------------------------------- windows
    def open_settings(self, tab: Optional[str] = None, first_run: bool = False) -> None:
        if self.settings is not None and self.settings.alive():
            self.settings.focus(tab)
            return
        self.settings = SettingsWindow(self, self.app, tab=tab, first_run=first_run)

    def settings_closed(self) -> None:
        self.settings = None

    def run_test_alert(self) -> None:
        """Tray 'test alert': show the strongest level for two seconds."""
        app = self.app
        app.start_preview(app.cfg, app.cfg.num_levels)
        self.root.after(2500, app.stop_preview)

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        try:
            if self.settings is not None and self.settings.alive():
                self.settings.close(save_prompt=False)
        except Exception:
            pass
        self.root.quit()
