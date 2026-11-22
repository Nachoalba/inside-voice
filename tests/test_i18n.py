import json
import re
from pathlib import Path

import pytest

from inside_voice.config import BLINK_MODES, BORDER_STYLES
from inside_voice.i18n import I18n

PKG = Path(__file__).resolve().parent.parent / "inside_voice"


def load(code):
    return json.loads((PKG / "locales" / f"{code}.json").read_text(encoding="utf-8"))


def test_same_keys_in_both_languages():
    assert set(load("es")) == set(load("en"))


def test_placeholders_match():
    en, es = load("en"), load("es")
    for key in en:
        assert set(re.findall(r"{(\w+)}", en[key])) == set(re.findall(r"{(\w+)}", es[key])), key


def test_every_used_key_exists():
    en = load("en")
    used = set()
    for path in PKG.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\btr\(\s*(f?)([\"'])([^\"']+)\2", src):
            is_f, key = m.group(1), m.group(3)
            if is_f:
                continue
            used.add(key)
    # dynamic keys built with f-strings
    used |= {f"tab.{k}" for k in ("mic", "alert", "monitors", "night", "general")}
    used |= {f"style.{s}" for s in BORDER_STYLES}
    used |= {f"blink.{m}" for m in BLINK_MODES}
    used |= {f"day.{d}" for d in range(7)}
    missing = sorted(k for k in used if k not in en)
    assert not missing, missing


def test_no_empty_texts():
    for code in ("es", "en"):
        for key, value in load(code).items():
            assert value.strip(), (code, key)


@pytest.mark.parametrize("code", ["es", "en"])
def test_translator(code):
    tr = I18n(code)
    assert tr.code == code
    assert tr.t("alert.level", n=2).endswith("2")
    assert tr.t("does.not.exist") == "does.not.exist"


def test_auto_resolves_to_supported():
    assert I18n("auto").code in ("es", "en")
