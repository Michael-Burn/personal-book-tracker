"""Date / period helpers."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, List


def since_date(period: str | None) -> datetime | None:
    """Return a cutoff datetime for a period string, or None for all time.

    ``period == 'month'`` → UTC now minus 30 days (matches share page behaviour).
    """
    if period == 'month':
        return datetime.utcnow() - timedelta(days=30)
    return None


def sort_books_by_date_added(books: Iterable[Any]) -> List[Any]:
    """Return books sorted by ``date_added`` newest-first; NULL dates last.

    Safe for legacy rows where ``date_added`` is None — never compares
    ``None`` to ``datetime``, so Jinja ``|sort(attribute='date_added')``
    is unnecessary and must not be used.
    """
    def _key(book: Any) -> tuple:
        dt = getattr(book, 'date_added', None)
        if dt is None:
            return (1, 0)
        return (0, -dt.timestamp())

    return sorted(books, key=_key)
