"""Reading timeline helpers — date validation, duration, and UI visibility.

Routes should call this service rather than embedding timeline business rules.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from domain.reading_status import ReadingStatus


class ReadingValidationError(Exception):
    """Raised when timeline dates fail validation. ``message`` is user-safe."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ReadingService:
    """Validate and summarize reading timeline dates for a book."""

    # Statuses where the start-date field is shown in forms.
    _SHOW_START = frozenset({
        'want_to_read',
        'reading',
        'finished',
        'dnf',
        'rereading',
    })

    # Statuses where the finish-date field is shown in forms.
    _SHOW_FINISH = frozenset({
        'want_to_read',
        'finished',
        'dnf',
        'rereading',
    })

    @staticmethod
    def parse_date(raw: Any) -> date | None:
        """Parse a form date string (YYYY-MM-DD) or pass through a date. Empty → None."""
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        text = str(raw).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ReadingValidationError(
                'Please enter dates in YYYY-MM-DD format.'
            ) from exc

    def validate_dates(
        self,
        status: str,
        started_raw: Any = None,
        finished_raw: Any = None,
    ) -> tuple[date | None, date | None]:
        """Validate timeline consistency for a reading status.

        Rules:
        - Finished: finish date required
        - Reading: start date recommended (not required)
        - Want to Read / DNF / Re-reading: dates optional
        - Finish date must not precede start date
        - Never invent or overwrite dates — only parse what the user sent
        """
        started = self.parse_date(started_raw)
        finished = self.parse_date(finished_raw)

        if status == 'finished' and finished is None:
            raise ReadingValidationError(
                'A finish date is required for finished books.'
            )

        if started is not None and finished is not None and finished < started:
            raise ReadingValidationError(
                'Finish date cannot be before the start date.'
            )

        return started, finished

    def parse_timeline_dates(
        self,
        form: Any,
        status: str,
    ) -> tuple[date | None, date | None, str | None]:
        """Parse/validate timeline dates from a form-like mapping.

        Returns (started, finished, error_message). On success error_message is None.
        Does not invent or overwrite dates — only what the user submitted.
        """
        try:
            started, finished = self.validate_dates(
                status,
                form.get('started_reading_at'),
                form.get('finished_reading_at'),
            )
        except ReadingValidationError as exc:
            return None, None, exc.message
        return started, finished, None

    def parse_status_and_rating(
        self,
        form: Any,
    ) -> tuple[str | None, int | None, str | None]:
        """Validate reading_status + rating from a form-like mapping.

        Returns (status, rating, error_message). On success error_message is None.
        Finished books require a 1–5 rating. Other statuses may omit a rating;
        omitted ratings are stored as 0 (unrated) so the column stays NOT NULL
        without altering existing schema constraints.
        """
        status = (form.get('reading_status') or ReadingStatus.FINISHED).strip()
        if not ReadingStatus.is_valid(status):
            return None, None, 'Please choose a valid reading status.'

        raw = form.get('rating', '')
        if raw is None or str(raw).strip() == '':
            rating = None
        else:
            try:
                rating = int(raw)
            except (TypeError, ValueError):
                return None, None, 'Rating must be a number between 1 and 5.'
            if rating < 1 or rating > 5:
                return None, None, 'Rating must be between 1 and 5.'

        if ReadingStatus.requires_rating(status):
            if rating is None:
                return None, None, 'A rating is required for finished books.'
        elif rating is None:
            rating = 0  # unrated sentinel — existing 1–5 values unchanged

        return status, rating, None

    @staticmethod
    def calculate_duration(
        started: date | None,
        finished: date | None,
    ) -> int | None:
        """Return inclusive reading duration in days, or None if either date is missing.

        Same-day start and finish counts as 1 day.
        """
        if started is None or finished is None:
            return None
        if finished < started:
            return None
        return (finished - started).days + 1

    @staticmethod
    def elapsed_days(started: date | None, as_of: date | None = None) -> int | None:
        """Days since start (inclusive of today), for currently-reading books."""
        if started is None:
            return None
        today = as_of or date.today()
        if today < started:
            return 0
        return (today - started).days + 1

    def timeline_summary(
        self,
        status: str,
        started: date | None,
        finished: date | None,
        *,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Build a display-ready summary for templates and dashboard widgets."""
        duration = self.calculate_duration(started, finished)
        elapsed = self.elapsed_days(started, as_of=as_of) if status == 'reading' else None
        return {
            'started_reading_at': started,
            'finished_reading_at': finished,
            'duration_days': duration,
            'elapsed_days': elapsed,
            'has_duration': duration is not None,
            'show_start': self.should_show_start_date(status),
            'show_finish': self.should_show_finish_date(status),
            'finish_required': status == 'finished',
            'start_recommended': status == 'reading',
        }

    def book_reading_summary(self, book: Any, *, as_of: date | None = None) -> dict[str, Any]:
        """Timeline summary for a Book-like object (status + date columns)."""
        status = getattr(book, 'reading_status', None) or ReadingStatus.FINISHED
        if not ReadingStatus.is_valid(status):
            status = ReadingStatus.FINISHED
        return self.timeline_summary(
            status,
            getattr(book, 'started_reading_at', None),
            getattr(book, 'finished_reading_at', None),
            as_of=as_of,
        )

    def should_show_start_date(self, status: str) -> bool:
        """Whether the start-date field should appear for this status."""
        return status in self._SHOW_START

    def should_show_finish_date(self, status: str) -> bool:
        """Whether the finish-date field should appear for this status."""
        return status in self._SHOW_FINISH

    @staticmethod
    def _activity_sort_ts(event_date: Any) -> datetime:
        """Normalize date / datetime for chronological sorting."""
        if isinstance(event_date, datetime):
            return event_date
        if isinstance(event_date, date):
            return datetime.combine(event_date, datetime.min.time())
        return datetime.min

    # Tie-break priority when events share a timestamp (higher = newer in feed).
    _ACTIVITY_KIND_RANK = {
        'finished': 4,
        'started': 3,
        'wild': 2,
        'added': 1,
    }

    def recent_activity(
        self,
        books: list[Any],
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Chronological activity feed for the reading dashboard.

        Event kinds (existing fields only):
        - started  → started_reading_at
        - finished → finished_reading_at
        - added    → date_added
        - wild     → is_wild books, dated with date_added (no separate wild timestamp)

        Sorted newest-first. Entries without a usable date are omitted.
        """
        events: list[dict[str, Any]] = []
        for book in books:
            started = getattr(book, 'started_reading_at', None)
            finished = getattr(book, 'finished_reading_at', None)
            added = getattr(book, 'date_added', None)
            is_wild = bool(getattr(book, 'is_wild', False))

            if finished is not None:
                events.append({
                    'kind': 'finished',
                    'book': book,
                    'event_date': finished,
                })
            if started is not None:
                events.append({
                    'kind': 'started',
                    'book': book,
                    'event_date': started,
                })
            if added is not None:
                events.append({
                    'kind': 'added',
                    'book': book,
                    'event_date': added,
                })
                if is_wild:
                    # No wild_marked_at column — surface wild flag via date_added.
                    events.append({
                        'kind': 'wild',
                        'book': book,
                        'event_date': added,
                    })

        events.sort(
            key=lambda e: (
                self._activity_sort_ts(e['event_date']),
                self._ACTIVITY_KIND_RANK.get(e['kind'], 0),
                getattr(e['book'], 'id', 0) or 0,
            ),
            reverse=True,
        )
        return events[:limit]

    def currently_reading(self, books: list[Any]) -> list[dict[str, Any]]:
        """Books with status 'reading', enriched with start date and elapsed days."""
        today = date.today()
        items: list[dict[str, Any]] = []
        for book in books:
            status = getattr(book, 'reading_status', None) or 'finished'
            if status != 'reading':
                continue
            started = getattr(book, 'started_reading_at', None)
            items.append({
                'book': book,
                'started_reading_at': started,
                'elapsed_days': self.elapsed_days(started, as_of=today),
            })
        # Prefer recently started first; undated at the end
        items.sort(
            key=lambda x: (
                x['started_reading_at'] is None,
                -(x['started_reading_at'].toordinal() if x['started_reading_at'] else 0),
            )
        )
        return items
