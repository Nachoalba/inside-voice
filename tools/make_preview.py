"""Generates assets/preview.png: a simulation of the three alert levels (for the README).

Run from the repository root:  python tools/make_preview.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from inside_voice.config import default_levels  # noqa: E402
from inside_voice.render import hex_to_rgb, render_border, scale_thickness  # noqa: E402

W, H = 640, 360


def fake_scene() -> np.ndarray:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = 25 + 40 * (x / W) + 20 * (y / H)
    g = 35 + 50 * (1 - y / H)
    b = 70 + 90 * (1 - x / W)
    return np.dstack([r, g, b])


def main() -> None:
    levels = default_levels()
    sheet = Image.new("RGB", (W * 3 + 40, H + 70), (17, 21, 38))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    for i in range(3):
        st = levels[i]
        bgra = render_border(W, H, "glow", hex_to_rgb(st.color), scale_thickness(st.thickness, H))
        a = bgra[:, :, 3:4].astype(np.float32) / 255.0 * st.opacity / 100.0
        premult = bgra[:, :, 2::-1].astype(np.float32) * st.opacity / 100.0   # BGR -> RGB
        out = fake_scene() * (1 - a) + premult
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
        sheet.paste(img, (10 + i * (W + 10), 10))
        d.text((10 + i * (W + 10) + 8, H + 24), f"Level {i + 1}", font=font, fill=(255, 255, 255))
    sheet.save(os.path.join(ROOT, "assets", "preview.png"))
    print("written assets/preview.png")


if __name__ == "__main__":
    main()
