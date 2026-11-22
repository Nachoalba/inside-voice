import numpy as np
import pytest

from inside_voice.render import (
    blink_alpha,
    hex_to_rgb,
    render_border,
    scale_thickness,
)
from inside_voice.voice_filter import VoiceDetector, frame_db

SR = 16000
N = 800  # 50 ms


def vowel(f0=120, amp=0.2, n=N, sr=SR):
    """Crude vowel: harmonics of f0 with a speech-like spectral tilt."""
    t = np.arange(n) / sr
    x = np.zeros(n)
    for k in range(1, 20):
        f = f0 * k
        if f > 3000:
            break
        x += np.sin(2 * np.pi * f * t + k) / k
    return (amp * x / np.max(np.abs(x))).astype(np.float32)


# ------------------------------------------------------------ voice filter
def test_db_of_full_scale_sine():
    t = np.arange(N) / SR
    x = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    assert abs(frame_db(x) - (-3.01)) < 0.1


def test_voice_is_detected():
    vd = VoiceDetector(SR)
    for f0 in (100, 120, 180, 220):
        assert vd.raw_voiced(vowel(f0)), f0


def test_white_noise_is_rejected():
    vd = VoiceDetector(SR)
    rng = np.random.default_rng(0)
    for _ in range(5):
        assert not vd.raw_voiced((0.2 * rng.standard_normal(N)).astype(np.float32))


def test_mains_hum_is_rejected():
    vd = VoiceDetector(SR)
    t = np.arange(N) / SR
    hum = 0.3 * np.sin(2 * np.pi * 50 * t) + 0.1 * np.sin(2 * np.pi * 100 * t)
    assert not vd.raw_voiced(hum.astype(np.float32))


def test_click_is_rejected():
    vd = VoiceDetector(SR)
    x = np.zeros(N, dtype=np.float32)
    x[300:306] = [0.9, -0.8, 0.6, -0.4, 0.2, -0.1]
    assert not vd.raw_voiced(x)


def test_silence_is_not_voice():
    vd = VoiceDetector(SR)
    db, voiced = vd.analyze(np.zeros(N, dtype=np.float32))
    assert db < -100 and not voiced


def test_hangover_bridges_short_gaps():
    vd = VoiceDetector(SR, hangover_frames=3)
    assert vd.analyze(vowel())[1]
    rng = np.random.default_rng(3)
    noise = (0.2 * rng.standard_normal(N)).astype(np.float32)
    assert vd.analyze(noise)[1]      # still inside the hangover
    assert vd.analyze(noise)[1]
    assert not vd.analyze(noise)[1]  # gap lasted too long


def test_other_samplerate():
    vd = VoiceDetector(48000)
    assert vd.frame_len == 2400
    assert vd.raw_voiced(vowel(130, n=2400, sr=48000))


# ----------------------------------------------------------------- render
@pytest.mark.parametrize("style", ["solid", "glow", "gradient", "corners"])
def test_border_shapes(style):
    w, h, t = 640, 360, 40
    img = render_border(w, h, style, (255, 0, 0), t)
    assert img.shape == (h, w, 4) and img.dtype == np.uint8
    alpha = img[:, :, 3]
    assert alpha[h // 2, w // 2] == 0                # centre fully transparent
    assert alpha[h // 2, 0] > 0 or style == "corners"  # edge visible
    # Premultiplied: red channel (index 2) can never exceed alpha
    assert np.all(img[:, :, 2] <= alpha)
    assert np.all(img[:, :, 0] == 0) and np.all(img[:, :, 1] == 0)


def test_glow_fades_inwards():
    img = render_border(400, 300, "glow", (255, 255, 255), 50)
    row = img[150, :60, 3].astype(int)
    assert row[0] > row[10] > row[30] >= row[49]
    assert row[55] == 0


def test_solid_is_flat_then_cut():
    img = render_border(400, 300, "solid", (255, 255, 255), 20)
    row = img[150, :30, 3]
    assert row[0] == 255 and row[10] == 255
    assert row[25] == 0


def test_corners_only_near_corners():
    img = render_border(600, 400, "corners", (255, 0, 0), 40)
    assert img[2, 2, 3] > 200            # corner strong
    assert img[200, 2, 3] == 0           # middle of the left edge empty


def test_image_style_uses_png_alpha():
    from PIL import Image

    im = Image.new("RGBA", (10, 10), (0, 255, 0, 0))
    for x in range(10):
        im.putpixel((x, 0), (0, 255, 0, 255))
    out = render_border(100, 100, "image", (255, 0, 0), 10, image=im)
    assert out[0, 50, 3] == 255 and out[0, 50, 1] == 255   # green top row
    assert out[50, 50, 3] == 0


def test_thickness_scales_with_resolution():
    assert scale_thickness(40, 1080) == 40
    assert scale_thickness(40, 1440) == 53
    assert scale_thickness(40, 2160) == 80
    assert scale_thickness(1, 1080) == 2


def test_blink_alpha_ranges():
    for mode in ("soft", "hard", "off"):
        for i in range(100):
            a = blink_alpha(i * 0.013, 2.5, mode, 80)
            assert 0 <= a <= int(255 * 0.8) + 1
    assert blink_alpha(1.23, 0, "soft", 50) == blink_alpha(0.1, 3, "off", 50)


def test_hard_blink_is_capped_at_3hz():
    # 10 Hz request must behave exactly like 3 Hz
    for t in (0.01, 0.12, 0.2, 0.31, 0.77):
        assert blink_alpha(t, 4.0, "hard", 100) == blink_alpha(t, 3.0, "hard", 100)


def test_hex_to_rgb():
    assert hex_to_rgb("#FF8000") == (255, 128, 0)
    assert hex_to_rgb("nonsense") == (255, 30, 30)
