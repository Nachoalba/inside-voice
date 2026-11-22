"""The Inside Voice mascot: a little ghost going "shh" (original artwork, drawn in code)."""
from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageChops, ImageDraw

OUTLINE = (43, 58, 103, 255)
BODY = (244, 247, 255, 255)
SHADE = (214, 222, 246, 255)
FINGER = (255, 214, 186, 255)
FINGER_EDGE = (214, 150, 120, 255)
ALERT = (255, 60, 60, 255)


def _ghost_polygon(s: float, grow: float = 0.0):
    """Outline points of the ghost body (head dome + wavy hem)."""
    cx = 0.5 * s
    left, right = 0.20 * s - grow, 0.80 * s + grow
    top = 0.10 * s - grow
    r = (right - left) / 2.0
    hem = 0.80 * s + grow
    pts = []
    # dome
    for i in range(0, 181, 6):
        a = math.radians(180 + i)
        pts.append((cx + r * math.cos(a), top + r + r * math.sin(a)))
    # right side down
    pts.append((right, hem))
    # wavy hem (right to left)
    waves = 3
    width = right - left
    steps = 36
    for i in range(steps + 1):
        u = i / steps
        x = right - u * width
        y = hem + 0.045 * s * math.sin(u * waves * 2 * math.pi + math.pi / 2) * 1.0 + 0.0
        pts.append((x, y))
    return pts


def make_icon(size: int = 256, paused: bool = False, alert: bool = False) -> Image.Image:
    ss = 4  # supersampling for smooth edges
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.polygon(_ghost_polygon(s, grow=0.035 * s), fill=OUTLINE)       # outline
    d.polygon(_ghost_polygon(s), fill=BODY)                           # body
    # soft shading on the right side
    shade = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse((0.50 * s, 0.05 * s, 1.05 * s, 1.05 * s), fill=SHADE)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(_ghost_polygon(s), fill=255)
    shade.putalpha(ImageChops.multiply(shade.getchannel("A"), mask))  # clip the shade to the body
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)

    # eyes
    for ex in (0.385, 0.615):
        d.ellipse(((ex - 0.045) * s, 0.30 * s, (ex + 0.045) * s, 0.42 * s), fill=OUTLINE)
        d.ellipse(((ex - 0.018) * s, 0.315 * s, (ex + 0.010) * s, 0.345 * s), fill=BODY)
    # cheeks
    for ex in (0.30, 0.70):
        d.ellipse(((ex - 0.04) * s, 0.45 * s, (ex + 0.04) * s, 0.50 * s), fill=(255, 190, 200, 200))
    # lips (small pill behind the finger)
    d.rounded_rectangle((0.43 * s, 0.505 * s, 0.57 * s, 0.545 * s), radius=0.02 * s, fill=OUTLINE)
    # finger on the lips ("shh")
    d.rounded_rectangle((0.455 * s, 0.44 * s, 0.545 * s, 0.76 * s), radius=0.045 * s,
                        fill=FINGER, outline=FINGER_EDGE, width=max(1, int(0.012 * s)))
    d.arc((0.465 * s, 0.50 * s, 0.535 * s, 0.56 * s), 20, 160, fill=FINGER_EDGE, width=max(1, int(0.008 * s)))

    if alert:
        d.ellipse((0.70 * s, 0.04 * s, 0.96 * s, 0.30 * s), fill=ALERT, outline=OUTLINE, width=int(0.02 * s))

    out = img.resize((size, size), Image.LANCZOS)
    if paused:
        gray = out.convert("LA").convert("RGBA")
        r, g, b, a = gray.split()
        out = Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * 0.55))))
    return out


def icon_png_base64(size: int = 64) -> str:
    """PNG as base64 text, handy for tkinter's PhotoImage(data=...)."""
    buf = io.BytesIO()
    make_icon(size).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
