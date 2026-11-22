"""System tray icon (pystray). Runs in its own thread; actions are forwarded to the UI thread."""
from __future__ import annotations

from typing import Optional

from .icon import make_icon
from .i18n import tr


class Tray:
    def __init__(self, app) -> None:
        self.app = app
        self.icon = None
        self._alert = False

    def _image(self):
        return make_icon(64, paused=self.app.cfg.paused, alert=self._alert)

    def _post(self, fn, *args) -> None:
        ui = self.app.ui
        if ui is not None:
            ui.post(fn, *args)

    def start(self) -> bool:
        try:
            import pystray
        except Exception:
            return False

        app = self.app
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: tr("tray.open"), lambda icon, item: self._post(app.ui.open_settings),
                             default=True),
            pystray.MenuItem(lambda item: tr("tray.pause"), lambda icon, item: self._post(app.toggle_paused),
                             checked=lambda item: app.cfg.paused),
            pystray.MenuItem(lambda item: tr("tray.test"), lambda icon, item: self._post(app.ui.run_test_alert)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: tr("tray.quit"), lambda icon, item: app.quit()),
        )
        self.icon = pystray.Icon("InsideVoice", self._image(), self._title(), menu)
        self.icon.run_detached()
        return True

    def _title(self) -> str:
        return "Inside Voice - " + (tr("tray.paused") if self.app.cfg.paused else tr("tray.active"))

    def refresh(self) -> None:
        if self.icon is None:
            return
        try:
            self.icon.icon = self._image()
            self.icon.title = self._title()
            self.icon.update_menu()
        except Exception:
            pass

    def set_alert(self, alert: bool) -> None:
        if alert == self._alert:
            return
        self._alert = alert
        self.refresh()

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
