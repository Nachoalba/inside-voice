"""Persistent configuration (JSON in %APPDATA%\\InsideVoice\\config.json)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .paths import config_path

MAX_LEVELS = 4
MIN_LEVELS = 2
MAX_BLINK_HZ = 4.0  # photosensitivity-friendly cap

BORDER_STYLES = ("glow", "solid", "gradient", "corners", "image")
BLINK_MODES = ("soft", "hard", "off")
LANGUAGES = ("auto", "es", "en")

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _num(value: Any, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v


def normalize_hhmm(value: Any, default: str) -> str:
    """Return 'HH:MM' (zero padded) or the default when invalid."""
    if isinstance(value, str):
        m = _HHMM_RE.match(value.strip())
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                return f"{h:02d}:{mi:02d}"
    return default


def hhmm_to_minutes(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


@dataclass
class LevelStyle:
    color: str = "#FF1E1E"
    thickness: int = 40      # pixels at 1080p height; scaled per monitor
    opacity: int = 70        # percent
    blink_hz: float = 1.5    # 0 = steady

    @classmethod
    def from_dict(cls, data: Any, default: "LevelStyle") -> "LevelStyle":
        if not isinstance(data, dict):
            return default
        color = data.get("color", default.color)
        if not isinstance(color, str) or not _COLOR_RE.match(color):
            color = default.color
        return cls(
            color=color.upper(),
            thickness=int(clamp(_num(data.get("thickness"), default.thickness), 2, 300)),
            opacity=int(clamp(_num(data.get("opacity"), default.opacity), 5, 100)),
            blink_hz=round(clamp(_num(data.get("blink_hz"), default.blink_hz), 0.0, MAX_BLINK_HZ), 2),
        )


def default_levels() -> List[LevelStyle]:
    return [
        LevelStyle("#FFC800", 36, 55, 1.0),
        LevelStyle("#FF7A00", 60, 72, 1.8),
        LevelStyle("#FF1E1E", 90, 88, 2.6),
        LevelStyle("#FF0033", 120, 96, 3.6),
    ]


@dataclass
class NightConfig:
    enabled: bool = False
    start: str = "23:00"
    end: str = "08:00"
    days: List[int] = field(default_factory=lambda: list(range(7)))  # 0 = Monday
    offset_db: float = -6.0  # added to the threshold while night mode is active

    @classmethod
    def from_dict(cls, data: Any) -> "NightConfig":
        d = cls()
        if not isinstance(data, dict):
            return d
        days = data.get("days", d.days)
        if isinstance(days, list):
            days = sorted({int(x) for x in days if isinstance(x, (int, float)) and 0 <= int(x) <= 6})
        else:
            days = d.days
        return cls(
            enabled=bool(data.get("enabled", d.enabled)),
            start=normalize_hhmm(data.get("start"), d.start),
            end=normalize_hhmm(data.get("end"), d.end),
            days=days,
            offset_db=round(clamp(_num(data.get("offset_db"), d.offset_db), -30.0, 0.0), 1),
        )


@dataclass
class Config:
    version: int = 1
    language: str = "auto"
    device: Optional[str] = None          # input device name; None = system default
    threshold_db: float = -28.0           # level where the first alert level starts
    step_db: float = 5.0                  # dB between alert levels
    num_levels: int = 3
    hold_ms: int = 400                    # loud speech must last this long before alerting
    release_ms: int = 700                 # quiet time needed before the alert fades
    voice_filter: bool = True
    border_style: str = "glow"
    image_path: str = ""
    blink_mode: str = "soft"
    levels: List[LevelStyle] = field(default_factory=default_levels)
    monitors: List[str] = field(default_factory=list)  # device names; empty = all
    sound_enabled: bool = False
    sound_volume: int = 35
    paused: bool = False
    autostart: bool = False
    calibrated: bool = False
    night: NightConfig = field(default_factory=NightConfig)

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: Any) -> "Config":
        d = cls()
        if not isinstance(data, dict):
            return d
        defaults = default_levels()
        raw_levels = data.get("levels")
        levels: List[LevelStyle] = []
        for i in range(MAX_LEVELS):
            raw = raw_levels[i] if isinstance(raw_levels, list) and i < len(raw_levels) else None
            levels.append(LevelStyle.from_dict(raw, defaults[i]))

        language = data.get("language", d.language)
        if language not in LANGUAGES:
            language = d.language
        style = data.get("border_style", d.border_style)
        if style not in BORDER_STYLES:
            style = d.border_style
        blink = data.get("blink_mode", d.blink_mode)
        if blink not in BLINK_MODES:
            blink = d.blink_mode
        device = data.get("device")
        if not isinstance(device, str) or not device:
            device = None
        monitors = data.get("monitors", [])
        if not isinstance(monitors, list):
            monitors = []
        image_path = data.get("image_path", "")
        if not isinstance(image_path, str):
            image_path = ""

        return cls(
            version=1,
            language=language,
            device=device,
            threshold_db=round(clamp(_num(data.get("threshold_db"), d.threshold_db), -80.0, -3.0), 1),
            step_db=round(clamp(_num(data.get("step_db"), d.step_db), 1.0, 15.0), 1),
            num_levels=int(clamp(_num(data.get("num_levels"), d.num_levels), MIN_LEVELS, MAX_LEVELS)),
            hold_ms=int(clamp(_num(data.get("hold_ms"), d.hold_ms), 50, 3000)),
            release_ms=int(clamp(_num(data.get("release_ms"), d.release_ms), 100, 5000)),
            voice_filter=bool(data.get("voice_filter", d.voice_filter)),
            border_style=style,
            image_path=image_path,
            blink_mode=blink,
            levels=levels,
            monitors=[m for m in monitors if isinstance(m, str)],
            sound_enabled=bool(data.get("sound_enabled", d.sound_enabled)),
            sound_volume=int(clamp(_num(data.get("sound_volume"), d.sound_volume), 0, 100)),
            paused=bool(data.get("paused", d.paused)),
            autostart=bool(data.get("autostart", d.autostart)),
            calibrated=bool(data.get("calibrated", d.calibrated)),
            night=NightConfig.from_dict(data.get("night")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def copy(self) -> "Config":
        return Config.from_dict(self.to_dict())


def load_config(path: Optional[str] = None) -> "Config":
    """Load the config; any problem falls back to defaults (never raises)."""
    p = str(path) if path else str(config_path())
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return Config.from_dict(json.load(fh))
    except (OSError, ValueError):
        return Config()


def config_exists(path: Optional[str] = None) -> bool:
    return os.path.exists(str(path) if path else str(config_path()))


def save_config(cfg: Config, path: Optional[str] = None) -> bool:
    """Atomic save. Returns False if the disk write failed."""
    p = str(path) if path else str(config_path())
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg.to_dict(), fh, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except OSError:
        return False
