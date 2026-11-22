"""Controller logic with a fake overlay (runs on any OS, no microphone needed)."""
import time

import pytest

from inside_voice.app import App
from inside_voice.overlay import NullOverlay
from inside_voice.winapi import MonitorInfo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIDE_VOICE_HOME", str(tmp_path))
    a = App()
    a.overlay = NullOverlay()
    # one fake 1080p monitor, so the tests behave the same on every machine
    a._monitors = [MonitorInfo(1, "DISPLAY1", 0, 0, 1920, 1080, True)]
    a._monitors_at = time.monotonic() + 1e9
    cfg = a.cfg.copy()
    cfg.threshold_db = -30
    cfg.step_db = 5
    cfg.num_levels = 3
    cfg.hold_ms = 100      # 2 frames
    cfg.release_ms = 200   # 4 frames
    a.cfg = cfg
    a._configure_detector(force=True)
    return a


def feed(app, db, frames, voiced=True):
    for _ in range(frames):
        app._on_frame(db, voiced)


def test_first_run_flag(app):
    assert app.first_run is True


def test_alert_levels_reach_the_overlay(app):
    feed(app, -50, 10)
    assert app.overlay.shown == []
    feed(app, -28, 3)
    assert len(app.overlay.shown) == 1 and app.level == 1
    assert app.overlay.shown[0].color == (255, 200, 0)     # level 1 colour
    feed(app, -15, 3)
    assert app.level == 3
    assert app.overlay.shown[0].color == (255, 30, 30)     # level 3 colour
    feed(app, -60, 10)
    assert app.level == 0 and app.overlay.shown == []


def test_paused_never_alerts(app):
    app.cfg.paused = True
    feed(app, -5, 20)
    assert app.overlay.shown == []


def test_selected_monitors_and_fallback(app):
    app.cfg.monitors = ["DISPLAY1"]
    assert [m.device for m in app.selected_monitors()] == ["DISPLAY1"]
    app.cfg.monitors = ["gone"]
    assert len(app.selected_monitors()) == 1   # unknown monitor -> all


def test_thickness_scales_per_monitor(app):
    targets = app.targets_for(app.cfg, 1)
    assert targets[0].thickness_px == 36       # 1080p reference (level 1 default)


def test_preview_overrides_and_restores(app):
    feed(app, -50, 5)
    app.start_preview(app.cfg, 2)
    assert app.overlay.shown
    feed(app, -50, 5)                          # real level 0 must not hide the preview
    assert app.overlay.shown
    app.stop_preview()
    assert app.overlay.shown == []


def test_calibration_suppresses_alerts(app):
    app.begin_calibration()
    feed(app, -5, 20)
    assert app.overlay.shown == []
    app.end_calibration()
    feed(app, -5, 5)
    assert app.overlay.shown


def test_listeners_receive_frames(app):
    got = []
    app.add_listener(lambda db, v: got.append((db, v)))
    app._on_frame(-20.0, True)
    assert got == [(-20.0, True)]


def test_apply_config_saves_and_pauses(app, tmp_path):
    new = app.cfg.copy()
    new.threshold_db = -40
    new.paused = True
    assert app.apply_config(new)
    assert (tmp_path / "config.json").exists()
    assert app.detector.threshold_db == -40
    feed(app, -5, 20)
    assert app.overlay.shown == []


def test_night_mode_lowers_threshold(app):
    from inside_voice.config import NightConfig

    app.cfg.night = NightConfig(enabled=True, start="00:00", end="00:00", days=list(range(7)), offset_db=-10)
    app._configure_detector(force=True)
    assert app.detector.threshold_db == -40
