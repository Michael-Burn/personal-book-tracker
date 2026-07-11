"""Safe redirect target helpers."""
from __future__ import annotations


def safe_next_url(candidate: str | None, fallback: str) -> str:
    """Return ``candidate`` only if it is a same-origin relative path; else ``fallback``.

    Rejects scheme-relative URLs (``//evil``) and non-path values.
    """
    if not isinstance(candidate, str):
        return fallback
    if not candidate.startswith('/') or candidate.startswith('//'):
        return fallback
    return candidate
