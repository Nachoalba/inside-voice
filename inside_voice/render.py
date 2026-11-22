"""Draws the alert border as a premultiplied BGRA bitmap (numpy) and the blink curve.

Nothing here touches Windows, so it is fully testable on any OS.
The bitmap is rendered only when an alert starts or its style changes; blinking
afterwards only changes the window transparency, which costs almost nothing.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np

MAX_BLINK_HZ = 4.0
MAX_HARD_BLINK_HZ = 3.0  # hard on/off flashing is capped lower (photosensitivity)
REF_HEIGHT = 1080


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        return (255, 30, 30)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return (255, 30, 30)


def scale_thickness(base_px: float, monitor_height: int) -> int:
    """Thickness is defined at 1080p and scaled so every monitor looks alike."""
    return max(2, int(round(base_px * monitor_height / REF_HEIGHT)))


def blink_alpha(t: float, hz: float, mode: str, opacity_pct: float) -> int:
    """Window alpha (0..255) at time t seconds."""
    base = max(0.0, min(100.0, float(opacity_pct))) / 100.0
    hz = max(0.0, min(MAX_BLINK_HZ, float(hz)))
    if mode == "off" or hz <= 0.0:
        factor = 1.0
    elif mode == "hard":
        hz = min(hz, MAX_HARD_BLINK_HZ)
        factor = 1.0 if (t * hz) % 1.0 < 0.5 else 0.12
    else:  # soft fade
        factor = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2.0 * math.pi * hz * t - math.pi / 2.0))
    return int(round(255.0 * base * factor))


# ---------------------------------------------------------------------------
def _profile(style: str, t: int) -> np.ndarray:
    """Alpha (0..255) as a function of the distance in pixels from the edge."""
    d = np.arange(t + 1, dtype=np.float32)
    x = np.minimum((d + 0.5) / float(t), 1.0)
    if style == "solid":
        prof = np.ones(t + 1, dtype=np.float32)
        fade = min(2, t)  # 1-2 px of anti-aliasing on the inner side
        for i in range(fade):
            prof[t - 1 - i] = (i + 1) / (fade + 1)
    elif style == "gradient":
        prof = 1.0 - x
    else:  # glow: soft, quick fall-off
        prof = (1.0 - x) ** 1.6
    prof[t] = 0.0
    prof = np.clip(prof, 0.0, 1.0)
    return np.round(prof * 255.0).astype(np.uint8)


def _edge_distance(w: int, h: int, cap: int) -> np.ndarray:
    dx = np.minimum(np.arange(w), np.arange(w)[::-1])
    dy = np.minimum(np.arange(h), np.arange(h)[::-1])
    d = np.minimum(dy[:, None], dx[None, :])
    return np.minimum(d, cap).astype(np.uint16)


def _premultiply(alpha: np.ndarray, rgb: Tuple[int, int, int]) -> np.ndarray:
    h, w = alpha.shape
    out = np.empty((h, w, 4), dtype=np.uint8)
    a16 = alpha.astype(np.uint16)
    r, g, b = rgb
    out[:, :, 0] = (a16 * b // 255).astype(np.uint8)
    out[:, :, 1] = (a16 * g // 255).astype(np.uint8)
    out[:, :, 2] = (a16 * r // 255).astype(np.uint8)
    out[:, :, 3] = alpha
    return out


def load_image(path: str):
    """Load a PNG for the custom 'image' style. Returns a PIL image or None."""
    if not path:
        return None
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.convert("RGBA").copy()
    except Exception:
        return None


def render_border(
    w: int,
    h: int,
    style: str,
    color_rgb: Tuple[int, int, int],
    thickness: int,
    image=None,
) -> np.ndarray:
    """Return an (h, w, 4) uint8 premultiplied BGRA array at full opacity."""
    w = max(4, int(w))
    h = max(4, int(h))
    t = max(2, min(int(thickness), min(w, h) // 2))

    if style == "image" and image is not None:
        from PIL import Image

        im = image.resize((w, h), Image.BILINEAR)
        arr = np.asarray(im, dtype=np.uint16)
        a = arr[:, :, 3]
        out = np.empty((h, w, 4), dtype=np.uint8)
        out[:, :, 0] = (arr[:, :, 2] * a // 255).astype(np.uint8)
        out[:, :, 1] = (arr[:, :, 1] * a // 255).astype(np.uint8)
        out[:, :, 2] = (arr[:, :, 0] * a // 255).astype(np.uint8)
        out[:, :, 3] = a.astype(np.uint8)
        return out

    if style == "corners":
        prof = _profile("glow", t)
        alpha = prof[_edge_distance(w, h, t)]
        reach = max(8.0, min(w, h) * 0.30)
        dx = np.minimum(np.arange(w), np.arange(w)[::-1]).astype(np.float32)
        dy = np.minimum(np.arange(h), np.arange(h)[::-1]).astype(np.float32)
        corner = np.hypot(dx[None, :], dy[:, None])
        weight = np.clip(1.0 - corner / reach, 0.0, 1.0)
        alpha = np.round(alpha.astype(np.float32) * weight).astype(np.uint8)
        return _premultiply(alpha, color_rgb)

    if style not in ("solid", "gradient", "glow"):
        style = "glow"
    prof = _profile(style, t)
    alpha = prof[_edge_distance(w, h, t)]
    return _premultiply(alpha, color_rgb)
