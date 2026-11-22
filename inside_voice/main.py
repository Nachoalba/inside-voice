"""Starts the application: DPI awareness, single instance, tray, UI loop."""
from __future__ import annotations

import sys

from .winapi import acquire_single_instance, message_box, set_dpi_aware


def run_app(minimized: bool = False) -> int:
    set_dpi_aware()  # before any window exists
    from .i18n import tr

    guard = acquire_single_instance()
    if guard is None:
        message_box("Inside Voice", tr("main.already_running"))
        return 0

    from .app import App
    from .tray import Tray
    from .ui.host import UIHost

    app = App(minimized=minimized)
    ui = UIHost(app)
    app.ui = ui
    app.start()

    tray = Tray(app)
    app.tray = tray
    tray_ok = tray.start()

    # Open the window on first run, when there is no tray icon to find it, or when asked to.
    if app.first_run or not tray_ok or not minimized:
        ui.post(ui.open_settings, "mic", app.first_run)

    try:
        ui.run()
    finally:
        tray.stop()
        app.shutdown()
        del guard
    return 0


if __name__ == "__main__":
    sys.exit(run_app())
