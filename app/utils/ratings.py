"""Rating helpers — shared by statistics and form validation."""
from __future__ import annotations

from typing import Any


def has_rating(book_or_rating: Any) -> bool:
    """True when a stored rating is a real 1–5 score (not the unrated sentinel 0)."""
    rating = (
        book_or_rating.rating
        if hasattr(book_or_rating, 'rating')
        else book_or_rating
    )
    return rating is not None and rating >= 1
