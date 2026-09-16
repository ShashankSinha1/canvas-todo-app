from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def week_of(dt: datetime) -> str:
    """Return the ISO date (YYYY-MM-DD) of the Monday starting dt's week."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")
