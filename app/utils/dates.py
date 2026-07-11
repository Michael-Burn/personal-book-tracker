"""Date / period helpers."""
from __future__ import annotations

from datetime import datetime, timedelta


def since_date(period: str | None) -> datetime | None:
    """Return a cutoff datetime for a period string, or None for all time.

    ``period == 'month'`` → UTC now minus 30 days (matches share page behaviour).
    """
    if period == 'month':
        return datetime.utcnow() - timedelta(days=30)
    return None
