"""Computes the alert threshold from two guided recordings.

Step 1: the user talks normally.   Step 2: the user talks loudly (but not shouting).
Only frames detected as voice are used, so keyboard clicks or fans do not skew it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

MIN_VOICE_FRAMES = 12      # ~0.6 s of voice at 50 ms frames
MIN_GAP_DB = 3.0


@dataclass
class CalibrationResult:
    ok: bool
    reason: str = ""            # "", "no_voice_normal", "no_voice_loud", "too_close"
    threshold_db: float = -28.0
    step_db: float = 5.0
    normal_db: float = 0.0      # reference level of normal speech (90th percentile)
    loud_db: float = 0.0        # reference level of loud speech (90th percentile)


def compute_threshold(
    normal_db: Sequence[float],
    loud_db: Sequence[float],
    num_levels: int = 3,
) -> CalibrationResult:
    """Return the threshold and step so that normal speech stays below level 1
    and the user's loud speech reaches the top level."""
    normal = np.asarray(list(normal_db), dtype=np.float64)
    loud = np.asarray(list(loud_db), dtype=np.float64)

    if normal.size < MIN_VOICE_FRAMES:
        return CalibrationResult(False, "no_voice_normal")
    if loud.size < MIN_VOICE_FRAMES:
        return CalibrationResult(False, "no_voice_loud")

    normal_ref = float(np.percentile(normal, 90))
    loud_ref = float(np.percentile(loud, 90))
    threshold = normal_ref + 1.0
    levels = max(2, int(num_levels))

    gap = loud_ref - normal_ref
    if gap < MIN_GAP_DB:
        # Loud and normal were almost the same: still give a usable result,
        # but tell the UI so it can suggest redoing the loud part.
        return CalibrationResult(
            True, "too_close", round(threshold, 1), 2.0, round(normal_ref, 1), round(loud_ref, 1)
        )

    step = (loud_ref - threshold) / (levels - 1)
    step = min(10.0, max(2.0, step))
    return CalibrationResult(
        True, "", round(threshold, 1), round(step, 1), round(normal_ref, 1), round(loud_ref, 1)
    )
