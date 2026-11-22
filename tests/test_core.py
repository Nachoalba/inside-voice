from datetime import datetime

import numpy as np

from inside_voice.calibration import compute_threshold
from inside_voice.config import Config, NightConfig, load_config, save_config
from inside_voice.detector import Detector
from inside_voice.schedule import effective_threshold, night_active


# ----------------------------------------------------------------- config
def test_config_roundtrip(tmp_path):
    cfg = Config()
    cfg.threshold_db = -33.3
    cfg.num_levels = 4
    cfg.levels[1].color = "#00ff00"
    cfg.monitors = ["\\\\.\\DISPLAY2"]
    cfg.night.enabled = True
    path = str(tmp_path / "c.json")
    assert save_config(cfg, path)
    back = load_config(path)
    assert back.threshold_db == -33.3
    assert back.num_levels == 4
    assert back.levels[1].color == "#00FF00"
    assert back.monitors == ["\\\\.\\DISPLAY2"]
    assert back.night.enabled is True


def test_config_survives_garbage(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_config(str(p)).num_levels == 3
    p.write_text('{"threshold_db": "abc", "num_levels": 99, "levels": [1, "x"], "border_style": "zzz"}', encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.threshold_db == Config().threshold_db
    assert cfg.num_levels == 4          # clamped
    assert cfg.border_style == "glow"   # invalid -> default
    assert len(cfg.levels) == 4


def test_config_clamps_blink_and_colors():
    cfg = Config.from_dict({"levels": [{"blink_hz": 50, "color": "red", "thickness": 9999, "opacity": 0}]})
    lv = cfg.levels[0]
    assert lv.blink_hz <= 4.0
    assert lv.color.startswith("#") and len(lv.color) == 7
    assert lv.thickness <= 300
    assert lv.opacity >= 5


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(str(tmp_path / "nope.json")).calibrated is False


# --------------------------------------------------------------- detector
def make_detector(**kw):
    d = Detector(frame_ms=50)
    d.configure(
        threshold_db=kw.get("thr", -30),
        step_db=kw.get("step", 5),
        num_levels=kw.get("levels", 3),
        hold_ms=kw.get("hold", 400),
        release_ms=kw.get("release", 700),
    )
    return d


def feed(d, db, frames, voice=True):
    out = d.level
    for _ in range(frames):
        out = d.update(db, voice)
    return out


def test_quiet_speech_never_alerts():
    d = make_detector()
    assert feed(d, -40, 100) == 0


def test_short_burst_is_ignored():
    d = make_detector()
    assert feed(d, -20, 4) == 0       # 200 ms < 400 ms hold
    assert feed(d, -50, 30) == 0


def test_sustained_loud_triggers_and_scales():
    d = make_detector()
    assert feed(d, -28, 8) == 1       # just over the threshold
    assert feed(d, -23, 4) == 2       # +5 dB
    assert feed(d, -18, 4) == 3       # +10 dB
    assert feed(d, -5, 20) == 3       # capped at the number of levels


def test_release_after_silence():
    d = make_detector()
    feed(d, -20, 20)
    assert d.level == 3
    assert feed(d, -60, 5) == 3       # not yet
    assert feed(d, -60, 20) == 0


def test_non_voice_never_alerts():
    d = make_detector()
    assert feed(d, -5, 100, voice=False) == 0


def test_hysteresis_keeps_level():
    d = make_detector()
    feed(d, -28, 10)
    assert d.level == 1
    # 1 dB under the threshold: inside the hysteresis band, must stay
    assert feed(d, -31, 40) == 1


def test_two_levels_only():
    d = make_detector(levels=2)
    assert feed(d, 0, 30) == 2


# --------------------------------------------------------------- schedule
def test_night_window_crossing_midnight():
    night = NightConfig(enabled=True, start="23:00", end="08:00", days=[4])  # Friday start
    assert night_active(night, datetime(2026, 11, 20, 23, 30))   # Fri 23:30
    assert night_active(night, datetime(2026, 11, 21, 2, 0))     # Sat 02:00 (started Fri)
    assert not night_active(night, datetime(2026, 11, 21, 23, 30))  # Sat 23:30 (Sat not selected)
    assert not night_active(night, datetime(2026, 11, 20, 12, 0))
    assert not night_active(night, datetime(2026, 11, 20, 8, 0))  # end is exclusive


def test_night_same_day_window_and_disabled():
    night = NightConfig(enabled=True, start="13:00", end="15:00", days=list(range(7)))
    assert night_active(night, datetime(2026, 11, 22, 14, 0))
    assert not night_active(night, datetime(2026, 11, 22, 16, 0))
    night.enabled = False
    assert not night_active(night, datetime(2026, 11, 22, 14, 0))


def test_effective_threshold_uses_offset():
    cfg = Config()
    cfg.threshold_db = -25
    cfg.night = NightConfig(enabled=True, start="00:00", end="00:00", days=list(range(7)), offset_db=-8)
    assert effective_threshold(cfg, datetime(2026, 11, 22, 12, 0)) == -33
    cfg.night.enabled = False
    assert effective_threshold(cfg, datetime(2026, 11, 22, 12, 0)) == -25


# ------------------------------------------------------------ calibration
def test_calibration_normal_case():
    rng = np.random.default_rng(1)
    normal = rng.normal(-32, 2, 100)
    loud = rng.normal(-20, 2, 100)
    res = compute_threshold(normal, loud, 3)
    assert res.ok and res.reason == ""
    # threshold sits just above normal speech peaks and below the loud speech
    assert np.percentile(normal, 90) < res.threshold_db < np.percentile(loud, 50)
    top = res.threshold_db + 2 * res.step_db
    assert abs(top - np.percentile(loud, 90)) < 3.0


def test_calibration_needs_voice():
    assert compute_threshold([], [-20] * 50).reason == "no_voice_normal"
    assert compute_threshold([-30] * 50, [-20] * 3).reason == "no_voice_loud"


def test_calibration_too_close_still_usable():
    res = compute_threshold([-30.0] * 50, [-29.5] * 50)
    assert res.ok and res.reason == "too_close"
    assert res.threshold_db > -30.0
