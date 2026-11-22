"""Tiny translation layer: JSON files in inside_voice/locales (es.json, en.json).

To add a language, copy en.json to <code>.json, translate the values and add the
code to SUPPORTED. Missing keys fall back to English, then to the key itself.
"""
from __future__ import annotations

import json
from typing import Dict

from .paths import locales_dir
from .winapi import windows_ui_language

SUPPORTED = ("es", "en")
NATIVE_NAMES = {"es": "Español", "en": "English"}


def _load(code: str) -> Dict[str, str]:
    try:
        with open(locales_dir() / f"{code}.json", "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


class I18n:
    def __init__(self, language: str = "auto") -> None:
        self.code = "en"
        self._strings: Dict[str, str] = {}
        self._fallback: Dict[str, str] = _load("en")
        self.set_language(language)

    def resolve(self, language: str) -> str:
        if language in SUPPORTED:
            return language
        detected = windows_ui_language()
        return detected if detected in SUPPORTED else "en"

    def set_language(self, language: str) -> None:
        self.code = self.resolve(language)
        self._strings = _load(self.code)

    def t(self, key: str, **kwargs) -> str:
        text = self._strings.get(key) or self._fallback.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text


i18n = I18n()


def tr(key: str, **kwargs) -> str:
    return i18n.t(key, **kwargs)
