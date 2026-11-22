"""Generates assets/icon.ico, assets/icon.png and assets/banner.png from the code-drawn mascot.

Run from the repository root:  python tools/make_icon.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from inside_voice.icon import make_icon  # noqa: E402

ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)


def main() -> None:
    big = make_icon(512)
    big.save(os.path.join(ASSETS, "icon.png"))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    make_icon(256).save(os.path.join(ASSETS, "icon.ico"), sizes=sizes)

    # Small banner for the README
    banner = Image.new("RGBA", (900, 260), (17, 21, 38, 255))
    banner.alpha_composite(make_icon(200), (40, 30))
    d = ImageDraw.Draw(banner)

    def font(px):
        for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                continue
        return ImageFont.load_default()

    d.text((270, 80), "Inside Voice", font=font(78), fill=(255, 255, 255, 255))
    d.text((274, 175), "Shh... they can hear you.", font=font(34), fill=(255, 200, 0, 255))
    banner.convert("RGB").save(os.path.join(ASSETS, "banner.png"))
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
