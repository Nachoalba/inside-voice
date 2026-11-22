"""Turns a stream of (level_db, is_voice) frames into an alert level 0..N.

Pure logic, no audio or GUI, so it is easy to test.
"""
from __future__ import annotations

import math
import threading


class Detector:
    def __init__(self, frame_ms: float = 50.0) -> None:
        self.frame_ms = float(frame_ms)
        self._lock = threading.Lock()
        self.threshold_db = -28.0
        self.step_db = 5.0
        self.num_levels = 3
        self.hysteresis_db = 2.0
        self._attack_frames = 8
        self._relevel_frames = 4
        self._release_frames = 14
        self.level = 0
        self._up = 0
        self._down = 0

    # ------------------------------------------------------------------
    def configure(
        self,
        threshold_db: float,
        step_db: float,
        num_levels: int,
        hold_ms: float,
        release_ms: float,
    ) -> None:
        with self._lock:
            self.threshold_db = float(threshold_db)
            self.step_db = max(0.5, float(step_db))
            self.num_levels = max(1, int(num_levels))
            self._attack_frames = max(1, math.ceil(hold_ms / self.frame_ms))
            self._relevel_frames = max(1, math.ceil(hold_ms / 2 / self.frame_ms))
            self._release_frames = max(1, math.ceil(release_ms / self.frame_ms))
            if self.level > self.num_levels:
                self.level = self.num_levels

    def level_thresholds(self) -> list:
        """dB value where each level (1..N) starts."""
        return [self.threshold_db + i * self.step_db for i in range(self.num_levels)]

    def reset(self) -> None:
        with self._lock:
            self.level = 0
            self._up = 0
            self._down = 0

    # ------------------------------------------------------------------
    def _candidate(self, db: float, is_voice: bool) -> int:
        if not is_voice:
            return 0
        cand = 0
        for k in range(1, self.num_levels + 1):
            thr = self.threshold_db + (k - 1) * self.step_db
            if k <= self.level:
                thr -= self.hysteresis_db  # stay in a level a bit longer
            if db >= thr:
                cand = k
        return cand

    def update(self, db: float, is_voice: bool) -> int:
        """Feed one frame; returns the (possibly new) alert level."""
        with self._lock:
            cand = self._candidate(db, is_voice)
            if cand > self.level:
                self._down = 0
                self._up += 1
                needed = self._attack_frames if self.level == 0 else self._relevel_frames
                if self._up >= needed:
                    self.level = cand
                    self._up = 0
            elif cand < self.level:
                self._up = 0
                self._down += 1
                if self._down >= self._release_frames:
                    self.level = cand
                    self._down = 0
            else:
                self._up = 0
                self._down = 0
            return self.level
