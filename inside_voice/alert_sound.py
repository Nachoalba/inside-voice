"""Optional soft alert sound (generated in memory, played asynchronously)."""
from __future__ import annotations

import io
import math
import struct
import sys
import time
import wave

SAMPLE_RATE = 22050


def _tone(freq: float, ms: int, volume: float) -> list:
    n = int(SAMPLE_RATE * ms / 1000)
    fade = max(1, int(n * 0.25))
    out = []
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        out.append(volume * env * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
    return out


def build_wav(level: int, volume_pct: int) -> bytes:
    """A short rising 'chime'. Higher alert levels add more notes."""
    volume = max(0.0, min(1.0, volume_pct / 100.0)) * 0.6
    notes = [(660, 110), (880, 140)]
    if level >= 2:
        notes.insert(0, (523, 100))
    if level >= 3:
        notes.append((1175, 160))
    samples: list = []
    for freq, ms in notes:
        samples += _tone(freq, ms, volume)
        samples += [0.0] * int(SAMPLE_RATE * 0.015)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))
    return buf.getvalue()


class AlertSound:
    MIN_INTERVAL_S = 1.5

    def __init__(self) -> None:
        self._last = 0.0

    def play(self, level: int, volume_pct: int, force: bool = False) -> bool:
        if sys.platform != "win32" or volume_pct <= 0:
            return False
        now = time.monotonic()
        if not force and now - self._last < self.MIN_INTERVAL_S:
            return False
        self._last = now
        try:
            import winsound

            winsound.PlaySound(build_wav(level, volume_pct), winsound.SND_MEMORY | winsound.SND_ASYNC)
            return True
        except Exception:
            return False
