"""Night mode: a time window (and weekdays) with a lower threshold."""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import Config, NightConfig, hhmm_to_minutes


def night_active(night: NightConfig, now: datetime) -> bool:
    """True when `now` falls inside the configured night window.

    Days refer to the day the window STARTS (Mon=0). A window such as
    23:00-08:00 that started on Friday still counts at 02:00 on Saturday.
    """
    if not night.enabled or not night.days:
        return False
    start = hhmm_to_minutes(night.start)
    end = hhmm_to_minutes(night.end)
    minute = now.hour * 60 + now.minute

    if start == end:  # whole day on the selected days
        return now.weekday() in night.days
    if start < end:
        return start <= minute < end and now.weekday() in night.days
    # Crosses midnight
    if minute >= start:
        return now.weekday() in night.days
    if minute < end:
        yesterday = (now - timedelta(days=1)).weekday()
        return yesterday in night.days
    return False


def effective_threshold(cfg: Config, now: datetime) -> float:
    """Base threshold plus the night offset when night mode applies."""
    if night_active(cfg.night, now):
        return cfg.threshold_db + cfg.night.offset_db
    return cfg.threshold_db
