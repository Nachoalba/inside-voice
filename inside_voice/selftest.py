"""Built-in smoke test:  python -m inside_voice --selftest [--out result.txt]

Used by the CI on a real Windows machine and handy for support ("does it work here?").
It needs no microphone. Exit code 0 = everything fine.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from typing import Callable, List, Optional, Tuple


def run(out_path: Optional[str] = None) -> int:
    os.environ.setdefault("INSIDE_VOICE_HOME", tempfile.mkdtemp(prefix="inside-voice-selftest-"))
    lines: List[str] = []
    failures: List[str] = []

    def log(text: str) -> None:
        lines.append(text)
        if out_path is None:
            print(text, flush=True)

    def check(name: str, fn: Callable[[], Optional[str]]) -> None:
        try:
            info = fn()
            log(f"OK    {name}" + (f"  [{info}]" if info else ""))
        except _Skip as skip:
            log(f"SKIP  {name}  [{skip}]")
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            log(f"FAIL  {name}  [{exc!r}]")
            log(traceback.format_exc())

    from . import __version__
    from .winapi import IS_WIN, set_dpi_aware

    set_dpi_aware()
    log(f"Inside Voice {__version__} selftest on {sys.platform}, Python {sys.version.split()[0]}"
        f"{' (frozen)' if getattr(sys, 'frozen', False) else ''}")

    # ---- pure logic ------------------------------------------------------
    def t_i18n() -> str:
        import json

        from .paths import locales_dir

        keysets = {}
        for code in ("es", "en"):
            with open(locales_dir() / f"{code}.json", encoding="utf-8") as fh:
                keysets[code] = set(json.load(fh))
        if keysets["es"] != keysets["en"]:
            raise AssertionError(f"locale keys differ: {sorted(keysets['es'] ^ keysets['en'])[:5]}")
        from .i18n import I18n

        assert I18n("es").t("tab.mic") != "tab.mic"
        assert I18n("en").t("tab.mic") != "tab.mic"
        return f"{len(keysets['en'])} texts"

    def t_config() -> None:
        from .config import Config, load_config, save_config

        path = os.path.join(os.environ["INSIDE_VOICE_HOME"], "selftest.json")
        cfg = Config()
        cfg.threshold_db = -33.0
        assert save_config(cfg, path)
        assert load_config(path).threshold_db == -33.0

    def t_render() -> str:
        from .render import render_border

        img = render_border(1920, 1080, "glow", (255, 0, 0), 60)
        assert img.shape == (1080, 1920, 4)
        assert img[540, 960, 3] == 0 and img[540, 0, 3] > 0
        return "1920x1080 glow"

    def t_voice() -> None:
        import numpy as np

        from .voice_filter import VoiceDetector

        vd = VoiceDetector(16000)
        t = np.arange(800) / 16000
        vowel = sum(np.sin(2 * np.pi * 120 * k * t) / k for k in range(1, 15)).astype(np.float32) * 0.1
        assert vd.raw_voiced(vowel)
        noise = (np.random.default_rng(0).standard_normal(800) * 0.1).astype(np.float32)
        assert not vd.raw_voiced(noise)

    def t_sound() -> None:
        from .alert_sound import build_wav

        assert build_wav(3, 40)[:4] == b"RIFF"

    def t_icon() -> None:
        from .icon import make_icon

        assert make_icon(64).size == (64, 64)

    check("translations", t_i18n)
    check("config", t_config)
    check("border rendering", t_render)
    check("voice filter", t_voice)
    check("alert sound", t_sound)
    check("icon", t_icon)

    # ---- libraries / system ---------------------------------------------
    def t_audio_lib() -> str:
        try:
            import sounddevice as sd  # noqa: F401
        except Exception as exc:
            raise _Skip(f"sounddevice not usable: {exc}")
        from .audio import list_input_devices

        return f"{len(list_input_devices())} input device(s)"

    def t_pystray() -> None:
        import pystray  # noqa: F401

    def t_monitors() -> str:
        from .winapi import list_monitors

        mons = list_monitors()
        assert mons, "no monitors"
        return "; ".join(f"{m.label()}@{m.x},{m.y}" for m in mons)

    check("audio library", t_audio_lib)
    check("tray library", t_pystray)
    check("monitors", t_monitors)

    # ---- Windows overlay ---------------------------------------------------
    def t_overlay() -> str:
        if not IS_WIN:
            raise _Skip("Windows only")
        from .overlay import OverlayManager, OverlayTarget
        from .winapi import list_monitors

        mons = list_monitors()
        mgr = OverlayManager()
        mgr.start()
        if mgr.error:
            raise RuntimeError(mgr.error)
        targets = [OverlayTarget(m, (255, 30, 30), 40, 70, 2.0, "soft", "glow") for m in mons]
        mgr.show(targets)
        time.sleep(0.7)
        shown = len(mgr._wins)
        mgr.identify(mons, 0.5)
        time.sleep(0.4)
        idents = len(mgr._ident)
        # every style must render and display without errors
        for style in ("solid", "gradient", "corners"):
            mgr.show([OverlayTarget(mons[0], (255, 200, 0), 30, 60, 0.0, "off", style)])
            time.sleep(0.25)
        mgr.clear()
        time.sleep(0.3)
        left = len(mgr._wins)
        err = mgr.error
        mgr.stop()
        if err:
            raise RuntimeError(err)
        assert shown == len(mons), f"expected {len(mons)} windows, got {shown}"
        assert idents == len(mons), f"expected {len(mons)} identify badges, got {idents}"
        assert left == 0, "windows were not released"
        return f"{shown} window(s) shown and released"

    check("overlay windows", t_overlay)

    # ---- GUI --------------------------------------------------------------
    def t_gui() -> str:
        try:
            import tkinter  # noqa: F401
        except Exception as exc:
            raise _Skip(f"tkinter missing: {exc}")
        from .app import App
        from .ui.host import UIHost

        app = App()
        ui = UIHost(app)
        app.ui = ui
        try:
            ui.open_settings("mic")
            ui.root.update()
            win = ui.settings
            assert win is not None and win.alive()
            for tab in ("alert", "monitors", "night", "general", "mic"):
                win.focus(tab)
                ui.root.update()
            cfg = win.collect()
            assert cfg.num_levels in (2, 3, 4)
            # open the calibration wizard and walk its first screens
            win.open_wizard()
            ui.root.update()
            assert win._wizard is not None
            win._wizard.cancel()
            ui.root.update()
            # language switch rebuilds the window in the other language
            win.lang_combo.box.current(2)
            win.apply()
            ui.root.update()
            win.lang_combo.box.current(1)
            win.apply()
            ui.root.update()
            win.close(save_prompt=False)
            ui.root.update()
        finally:
            try:
                ui.root.destroy()
            except Exception:
                pass
        return "settings window, tabs and wizard"

    check("settings window", t_gui)

    log("")
    if failures:
        log(f"SELFTEST FAILED: {', '.join(failures)}")
    else:
        log("SELFTEST OK")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 1 if failures else 0


class _Skip(Exception):
    pass
