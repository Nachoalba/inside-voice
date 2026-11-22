"""Microphone capture (shared mode, never exclusive) and per-frame analysis.

Mono 16 kHz blocks of 50 ms are enough to measure speech level and keep CPU use
well under 1 %. Pausing closes the stream completely, so a paused app uses no
audio resources at all.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

import numpy as np

from .voice_filter import VoiceDetector

FRAME_MS = 50
PREFERRED_RATE = 16000

FrameCallback = Callable[[float, bool], None]


def _sd():
    """Import sounddevice lazily: it needs PortAudio, which may be missing in tests."""
    import sounddevice as sd  # noqa: WPS433

    return sd


def list_input_devices() -> List[str]:
    """Names of input devices on the default host API (avoids Windows duplicates)."""
    try:
        sd = _sd()
        host = sd.query_hostapis(sd.default.hostapi) if sd.default.hostapi is not None else None
        names: List[str] = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            if host is not None and dev.get("hostapi") != sd.default.hostapi:
                continue
            name = str(dev["name"])
            if name not in names:
                names.append(name)
        return names
    except Exception:
        return []


def _find_device(name: Optional[str]):
    """Index for a device name on the default host API, or None for the system default."""
    if not name:
        return None
    try:
        sd = _sd()
        for idx, dev in enumerate(sd.query_devices()):
            if (dev.get("max_input_channels", 0) > 0 and str(dev["name"]) == name
                    and dev.get("hostapi") == sd.default.hostapi):
                return idx
    except Exception:
        pass
    return None


class AudioEngine:
    def __init__(self, on_frame: FrameCallback) -> None:
        self._on_frame = on_frame
        self._stream = None
        self._detector: Optional[VoiceDetector] = None
        self._lock = threading.Lock()
        self.voice_filter = True
        self.device_name: Optional[str] = None
        self.samplerate = PREFERRED_RATE
        self.last_error: Optional[str] = None
        self.last_frame_time = 0.0

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self, device_name: Optional[str] = None) -> bool:
        """Open the microphone. Returns False (and sets last_error) on failure."""
        with self._lock:
            self._close_locked()
            self.device_name = device_name
            self.last_error = None
            try:
                sd = _sd()
            except Exception as exc:
                self.last_error = f"audio library unavailable: {exc}"
                return False

            device = _find_device(device_name)
            rates = [PREFERRED_RATE]
            try:
                info = sd.query_devices(device if device is not None else sd.default.device[0])
                default_rate = int(info["default_samplerate"])
                if default_rate not in rates:
                    rates.append(default_rate)
            except Exception:
                pass

            for rate in rates:
                try:
                    self._detector = VoiceDetector(rate, FRAME_MS)
                    self.samplerate = rate
                    self._stream = sd.InputStream(
                        samplerate=rate,
                        channels=1,
                        dtype="float32",
                        blocksize=self._detector.frame_len,
                        device=device,
                        callback=self._callback,
                        latency="low",
                    )
                    self._stream.start()
                    return True
                except Exception as exc:
                    self.last_error = str(exc)
                    self._close_locked()
            return False

    def stop(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:  # audio thread
        try:
            det = self._detector
            if det is None:
                return
            samples = np.asarray(indata[:, 0], dtype=np.float32)
            if self.voice_filter:
                db, voiced = det.analyze(samples)
            else:
                from .voice_filter import frame_db

                db, voiced = frame_db(samples), True
            self.last_frame_time = time.monotonic()
            self._on_frame(db, voiced)
        except Exception:
            pass  # never raise inside the audio callback
