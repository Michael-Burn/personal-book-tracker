"""Authoritative reading-status values for Book.reading_status."""


class ReadingStatus:
    """Canonical reading journey statuses stored on Book.reading_status."""

    WANT_TO_READ = 'want_to_read'
    READING = 'reading'
    FINISHED = 'finished'
    DNF = 'dnf'
    REREADING = 'rereading'

    ALL = frozenset({
        WANT_TO_READ,
        READING,
        FINISHED,
        DNF,
        REREADING,
    })

    # Statuses included in public share rankings by default.
    PUBLIC = frozenset({FINISHED, REREADING})

    LABELS = {
        WANT_TO_READ: 'Want to Read',
        READING: 'Currently Reading',
        FINISHED: 'Finished',
        DNF: 'DNF',
        REREADING: 'Re-reading',
    }

    # Short labels for compact status chips.
    CHIP_LABELS = {
        WANT_TO_READ: 'Want to Read',
        READING: 'Reading',
        FINISHED: 'Finished',
        DNF: 'DNF',
        REREADING: 'Re-reading',
    }

    # Display order for KPI cards and filter controls.
    ORDER = (
        READING,
        WANT_TO_READ,
        FINISHED,
        DNF,
        REREADING,
    )

    @classmethod
    def is_valid(cls, value):
        return value in cls.ALL

    @classmethod
    def requires_rating(cls, value):
        return value == cls.FINISHED

    @classmethod
    def label(cls, value):
        return cls.LABELS.get(value, value)

    @classmethod
    def chip_label(cls, value):
        return cls.CHIP_LABELS.get(value, value)

    @classmethod
    def choices(cls):
        """Ordered (value, label) pairs for form selects."""
        return [(status, cls.LABELS[status]) for status in cls.ORDER]
