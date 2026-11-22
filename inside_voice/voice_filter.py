"""Level measurement and a light-weight "is this a human voice?" filter.

No extra dependencies: a couple of FFTs per 50 ms frame.

A frame counts as voice when
  * most of its energy sits in the speech band (85-3400 Hz), and
  * it is periodic in the pitch range (70-400 Hz), i.e. voiced speech.
Keyboard/mouse clicks, door slams (broadband or impulsive), fans and
electrical hum (low frequency or noise-like) fail at least one test.
"""
from __future__ import annotations

from collections import deque

import numpy as np

SPEECH_LO_HZ = 85.0
SPEECH_HI_HZ = 3400.0
PITCH_LO_HZ = 70.0
PITCH_HI_HZ = 400.0
MIN_BAND_RATIO = 0.65
MIN_PERIODICITY = 0.30
SILENCE_DB = -62.0
EPS = 1e-10


def frame_db(samples: np.ndarray) -> float:
    """RMS level in dBFS (0 dB = full scale)."""
    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float32), dtype=np.float64)))
    return 20.0 * float(np.log10(rms + EPS))


class VoiceDetector:
    def __init__(self, samplerate: int = 16000, frame_ms: float = 50.0, hangover_frames: int = 3) -> None:
        self.samplerate = int(samplerate)
        self.frame_len = int(round(self.samplerate * frame_ms / 1000.0))
        nfft = 1
        while nfft < self.frame_len * 2:
            nfft *= 2
        self.nfft = nfft
        self._window = np.hanning(self.frame_len).astype(np.float32)
        freqs = np.fft.rfftfreq(nfft, 1.0 / self.samplerate)
        self._band = (freqs >= SPEECH_LO_HZ) & (freqs <= SPEECH_HI_HZ)
        self._above_dc = freqs >= 20.0
        self._lag_lo = max(2, int(self.samplerate / PITCH_HI_HZ))
        self._lag_hi = min(self.frame_len - 2, int(self.samplerate / PITCH_LO_HZ))
        self._recent = deque(maxlen=max(1, hangover_frames))

    # ------------------------------------------------------------------
    def raw_voiced(self, samples: np.ndarray) -> bool:
        x = np.asarray(samples, dtype=np.float32)
        n = self.frame_len
        if x.size < n:
            x = np.pad(x, (0, n - x.size))
        elif x.size > n:
            x = x[:n]
        x = x - float(np.mean(x))

        # Energy in the speech band versus everything above DC
        spec = np.abs(np.fft.rfft(x * self._window, self.nfft)) ** 2
        total = float(np.sum(spec[self._above_dc])) + EPS
        band = float(np.sum(spec[self._band]))
        if band / total < MIN_BAND_RATIO:
            return False

        # Periodicity (pitch) via autocorrelation
        power = np.abs(np.fft.rfft(x, self.nfft)) ** 2
        acf = np.fft.irfft(power, self.nfft)
        r0 = float(acf[0]) + EPS
        lags = np.arange(self._lag_lo, self._lag_hi + 1)
        comp = (n - lags) / n  # undo the natural decay of a short frame
        peak = float(np.max(acf[self._lag_lo : self._lag_hi + 1] / (r0 * comp)))
        return peak >= MIN_PERIODICITY

    def analyze(self, samples: np.ndarray):
        """Return (level_db, is_voice) for one frame."""
        db = frame_db(samples)
        voiced = db > SILENCE_DB and self.raw_voiced(samples)
        self._recent.append(bool(voiced))
        return db, any(self._recent)
