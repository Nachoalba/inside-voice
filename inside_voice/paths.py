"""Filesystem locations used by the app."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Folder where the config is stored (created on demand)."""
    override = os.environ.get("INSIDE_VOICE_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "InsideVoice"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "InsideVoice"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return app_data_dir() / "config.json"


def locales_dir() -> Path:
    """Works both from source and inside a PyInstaller bundle."""
    return Path(__file__).resolve().parent / "locales"
