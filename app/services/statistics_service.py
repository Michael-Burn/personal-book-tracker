"""Dashboard, share, author, and admin aggregation calculations.

Routes should call this service and pass results to templates — no ranking
or KPI math belongs in route handlers.
"""
from __future__ import annotations

import calendar
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from domain.reading_status import ReadingStatus
from utils.ratings import has_rating


class StatisticsService:
    """Reusable statistics and ranking calculations over Book / User / Quote rows."""

    # ── Status KPIs ───────────────────────────────────────────

    def status_counts(self, books: list[Any]) -> dict[str, int]:
        """Return a dict of reading_status → count for KPI cards."""
        counts = {status: 0 for status in ReadingStatus.ORDER}
        for b in books:
            key = (
                b.reading_status
                if ReadingStatus.is_valid(b.reading_status)
                else ReadingStatus.FINISHED
            )
            counts[key] = counts.get(key, 0) + 1
        return counts

    # ── Public share rankings ─────────────────────────────────

    def top_authors(
        self,
        books: list[Any],
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Rank authors from a pre-filtered book list (PUBLIC statuses applied by caller)."""
        author_map: dict[str, dict[str, Any]] = {}
        for b in books:
            entry = author_map.setdefault(
                b.author,
                {
                    'name': b.author,
                    'book_count': 0,
                    'rating_sum': 0,
                    'rating_count': 0,
                    'wild_count': 0,
                },
            )
            entry['book_count'] += 1
            if has_rating(b):
                entry['rating_sum'] += b.rating
                entry['rating_count'] += 1
            if b.is_wild:
                entry['wild_count'] += 1

        result = []
        for a in author_map.values():
            avg = (
                round(a['rating_sum'] / a['rating_count'], 2)
                if a['rating_count']
                else 0
            )
            result.append({
                'name': a['name'],
                'avg_rating': avg,
                'book_count': a['book_count'],
                'wild_count': a['wild_count'],
            })
        result.sort(key=lambda x: (-x['avg_rating'], -x['book_count'], x['name']))
        return result[:limit]

    def top_books(
        self,
        books: list[Any],
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Serialize top books already ordered by the caller (rating desc, date_added desc)."""
        return [
            {
                'title': b.title,
                'author': b.author,
                'rating': b.rating,
                'is_wild': bool(b.is_wild),
                'cover_filename': b.cover_filename,
                'reading_status': b.reading_status,
            }
            for b in books[:limit]
        ]

    def fetch_public_books_for_user(self, Book, user_id, since=None):
        """Books eligible for public share rankings for one user."""
        query = Book.query.filter(
            Book.user_id == user_id,
            Book.reading_status.in_(tuple(ReadingStatus.PUBLIC)),
        )
        if since:
            query = query.filter(Book.date_added >= since)
        return query.all()

    def fetch_top_books_for_user(self, Book, user_id, since=None, limit=5):
        """Top N rated public books for one user (same order as before)."""
        query = (
            Book.query
            .filter(
                Book.user_id == user_id,
                Book.reading_status.in_(tuple(ReadingStatus.PUBLIC)),
                Book.rating >= 1,
            )
            .order_by(Book.rating.desc(), Book.date_added.desc())
        )
        if since:
            query = query.filter(Book.date_added >= since)
        return query.limit(limit).all()

    def share_rankings(self, Book, user_id, since=None, limit=5):
        """Authors + books for the public share page / PNG card."""
        authors = self.top_authors(
            self.fetch_public_books_for_user(Book, user_id, since=since),
            limit=limit,
        )
        books = self.top_books(
            self.fetch_top_books_for_user(Book, user_id, since=since, limit=limit),
            limit=limit,
        )
        return authors, books

    # ── Authors dashboard ─────────────────────────────────────

    def dashboard_stats(self, books: list[Any]) -> dict[str, Any]:
        """Aggregate authors dashboard KPIs and per-author rows from a user's books."""
        author_map: dict[str, dict[str, Any]] = {}
        total_books = 0
        total_rating_sum = 0
        total_rating_count = 0
        wild_count = 0

        for b in books:
            total_books += 1
            if has_rating(b):
                total_rating_sum += b.rating
                total_rating_count += 1
            if b.is_wild:
                wild_count += 1
            status = (
                b.reading_status
                if ReadingStatus.is_valid(b.reading_status)
                else ReadingStatus.FINISHED
            )
            entry = author_map.setdefault(
                b.author,
                {
                    'name': b.author,
                    'bookCount': 0,
                    'titles': [],
                    'ratingSum': 0,
                    'ratingCount': 0,
                    'wildCount': 0,
                    'statuses': [],
                },
            )
            entry['bookCount'] += 1
            entry['titles'].append(b.title)
            entry['statuses'].append(status)
            if has_rating(b):
                entry['ratingSum'] += b.rating
                entry['ratingCount'] += 1
            if b.is_wild:
                entry['wildCount'] += 1

        authors = []
        for a in author_map.values():
            avg = round(
                (a['ratingSum'] / a['ratingCount']) if a['ratingCount'] else 0,
                2,
            )
            authors.append({
                'name': a['name'],
                'bookCount': a['bookCount'],
                'titles': a['titles'],
                'avgRating': avg,
                'ratingCount': a['ratingCount'],
                'wildCount': a['wildCount'],
                'statuses': a['statuses'],
            })

        overall_avg = (
            round((total_rating_sum / total_rating_count), 2)
            if total_rating_count
            else 0
        )
        most_active = (
            max(authors, key=lambda x: x['bookCount'])['name'] if authors else ''
        )
        authors = sorted(authors, key=lambda x: x['name'] or '')

        return {
            'authors': authors,
            'total_books': total_books,
            'overall_avg': overall_avg,
            'most_active': most_active,
            'wild_count': wild_count,
            'status_counts': self.status_counts(books),
        }

    def reading_dashboard(
        self,
        books: list[Any],
        reading_service: Any,
        *,
        now: datetime | None = None,
        activity_limit: int = 12,
        top_authors_limit: int = 5,
    ) -> dict[str, Any]:
        """Build the full Reading Statistics Dashboard payload in one pass.

        Loads nothing from the DB — works from a pre-fetched ``books`` list so
        the route issues a single query. Includes author list, KPIs, Chart.js
        payloads, reading-duration summary, currently reading, and activity.
        """
        now = now or datetime.utcnow()
        today = now.date() if isinstance(now, datetime) else now
        base = self.dashboard_stats(books)
        status_counts = base['status_counts']

        # ── KPI cards ─────────────────────────────────────────
        has_any_rating = any(has_rating(b) for b in books)
        rated_avg = base['overall_avg'] if has_any_rating else None
        kpis = {
            'books_finished': status_counts.get(ReadingStatus.FINISHED, 0),
            'currently_reading': status_counts.get(ReadingStatus.READING, 0),
            'want_to_read': status_counts.get(ReadingStatus.WANT_TO_READ, 0),
            'average_rating': rated_avg,
            'average_rating_display': (
                f'{rated_avg:.1f}' if rated_avg is not None else None
            ),
            'wild_books': base['wild_count'],
            'favourite_author': base['most_active'] or None,
        }

        # ── Charts (last 12 months finished; rating 1–5; top authors) ──
        month_keys: list[str] = []
        month_labels: list[str] = []
        for i in range(11, -1, -1):
            y = now.year + (now.month - 1 - i) // 12
            m = (now.month - 1 - i) % 12 + 1
            month_keys.append(f'{y}-{m:02d}')
            month_labels.append(datetime(y, m, 1).strftime('%b %y'))

        finished_month_counts: dict[str, int] = defaultdict(int)
        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        author_book_counts: dict[str, int] = defaultdict(int)

        # Duration / year summary accumulators (timeline dates only)
        duration_rows: list[dict[str, Any]] = []
        finished_this_year = 0

        for b in books:
            status = (
                b.reading_status
                if ReadingStatus.is_valid(b.reading_status)
                else ReadingStatus.FINISHED
            )
            finished_at = getattr(b, 'finished_reading_at', None)
            started_at = getattr(b, 'started_reading_at', None)

            if status == ReadingStatus.FINISHED and finished_at is not None:
                finished_month_counts[finished_at.strftime('%Y-%m')] += 1
                if finished_at.year == today.year:
                    finished_this_year += 1

            if has_rating(b):
                rating_counts[int(b.rating)] = rating_counts.get(int(b.rating), 0) + 1

            author_book_counts[b.author] += 1

            duration = reading_service.calculate_duration(started_at, finished_at)
            if duration is not None:
                duration_rows.append({
                    'title': b.title,
                    'author': b.author,
                    'days': duration,
                    'started_reading_at': started_at,
                    'finished_reading_at': finished_at,
                })

        top_author_pairs = sorted(
            author_book_counts.items(),
            key=lambda x: (-x[1], x[0]),
        )[:top_authors_limit]

        finished_month_data = [finished_month_counts.get(k, 0) for k in month_keys]
        rating_dist_data = [rating_counts[i] for i in range(1, 6)]
        top_author_counts = [count for _, count in top_author_pairs]
        charts = {
            'finished_per_month': {
                'labels_js': json.dumps(month_labels),
                'data_js': json.dumps(finished_month_data),
                'has_data': any(finished_month_data),
            },
            'rating_distribution': {
                'labels_js': json.dumps(['1★', '2★', '3★', '4★', '5★']),
                'data_js': json.dumps(rating_dist_data),
                'has_data': any(rating_dist_data),
            },
            'top_authors': {
                'labels_js': json.dumps([name for name, _ in top_author_pairs]),
                'data_js': json.dumps(top_author_counts),
                'has_data': any(top_author_counts),
            },
        }

        # ── Reading summary (timeline dates required) ─────────
        if duration_rows:
            avg_days = round(
                sum(r['days'] for r in duration_rows) / len(duration_rows),
                1,
            )
            fastest = min(duration_rows, key=lambda r: (r['days'], r['title']))
            longest = max(duration_rows, key=lambda r: (r['days'], r['title']))
        else:
            avg_days = None
            fastest = None
            longest = None

        reading_summary = {
            'average_duration_days': avg_days,
            'fastest': fastest,
            'longest': longest,
            'finished_this_year': finished_this_year,
            'sample_count': len(duration_rows),
        }

        # ── Currently reading + activity (reuse ReadingService) ─
        currently_reading = reading_service.currently_reading(books)
        recent_activity = reading_service.recent_activity(
            books, limit=activity_limit
        )

        return {
            **base,
            'kpis': kpis,
            'charts': charts,
            'reading_summary': reading_summary,
            'currently_reading': currently_reading,
            'recent_activity': recent_activity,
            'is_empty': base['total_books'] == 0,
        }

    # ── Home personalization (no schema; existing fields only) ─

    def recently_finished(
        self,
        books: list[Any],
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Finished books with a finish date, newest first."""
        rows: list[dict[str, Any]] = []
        for book in books:
            status = (
                book.reading_status
                if ReadingStatus.is_valid(book.reading_status)
                else ReadingStatus.FINISHED
            )
            finished_at = getattr(book, 'finished_reading_at', None)
            if status != ReadingStatus.FINISHED or finished_at is None:
                continue
            rows.append({
                'book': book,
                'finished_reading_at': finished_at,
                'started_reading_at': getattr(book, 'started_reading_at', None),
            })
        rows.sort(
            key=lambda r: (
                r['finished_reading_at'],
                getattr(r['book'], 'id', 0) or 0,
            ),
            reverse=True,
        )
        return rows[:limit]

    def home_hero(
        self,
        *,
        username: str,
        currently_reading: list[dict[str, Any]],
        reading_goal: dict[str, Any],
        is_empty: bool,
    ) -> dict[str, Any]:
        """Pick one personalized hero scenario from existing dashboard data.

        Priority: Goal Achieved → Currently Reading → Close To Goal → No Active Book.
        """
        name = (username or 'Reader').strip() or 'Reader'
        active = currently_reading[0] if currently_reading else None
        goal_exists = bool(reading_goal.get('exists'))
        goal_met = bool(reading_goal.get('goal_met'))
        target = reading_goal.get('target')
        completed = int(reading_goal.get('completed') or 0)
        remaining = reading_goal.get('remaining')
        percent = int(reading_goal.get('percent') or 0)

        close_to_goal = False
        if goal_exists and not goal_met and target:
            rem = int(remaining) if remaining is not None else max(0, int(target) - completed)
            close_to_goal = rem <= 3 or percent >= 80

        if goal_exists and goal_met:
            return {
                'scenario': 'goal_achieved',
                'eyebrow': f'{reading_goal.get("year")} goal',
                'title': f'You did it, {name}.',
                'message': (
                    f'{completed} of {target} books finished — your reading year '
                    f'is already a story worth sharing.'
                ),
                'cta_label': 'My Reading Year',
                'cta_anchor': 'reading_year',
                'book': None,
            }

        if active:
            book = active['book']
            days = active.get('elapsed_days')
            started = active.get('started_reading_at')
            if days:
                day_bit = f'Day {days} with this one'
            elif started:
                day_bit = f'Started Reading {started.strftime("%b %d")}'
            else:
                day_bit = 'In progress'
            return {
                'scenario': 'currently_reading',
                'eyebrow': 'Reading Journey',
                'title': book.title,
                'message': (
                    f'{day_bit} · by {book.author}. Record where you are in the journey.'
                ),
                'cta_label': 'Update Progress',
                'cta_anchor': 'continue',
                'book': book,
                'elapsed_days': days,
                'started_reading_at': started,
            }

        if close_to_goal:
            rem = int(remaining) if remaining is not None else 0
            book_word = 'book' if rem == 1 else 'books'
            return {
                'scenario': 'close_to_goal',
                'eyebrow': f'{reading_goal.get("year")} goal',
                'title': f'Almost there — {rem} {book_word} to go.',
                'message': (
                    f'You\'re at {percent}% of your {target}-book goal. '
                    f'One more finish could tip the year.'
                ),
                'cta_label': 'Reading Goal',
                'cta_anchor': 'goal',
                'book': None,
            }

        if is_empty:
            return {
                'scenario': 'no_active_book',
                'eyebrow': 'Welcome',
                'title': f'Your library is waiting, {name}.',
                'message': (
                    'Add your first book and Home will begin reflecting '
                    'your reading journey.'
                ),
                'cta_label': 'Add Book',
                'cta_anchor': 'add',
                'book': None,
            }

        return {
            'scenario': 'no_active_book',
            'eyebrow': 'Ready when you are',
            'title': 'Nothing on the nightstand.',
            'message': (
                'Mark a book as Currently Reading, or pull one from your Want to Read list.'
            ),
            'cta_label': 'Add Book',
            'cta_anchor': 'add',
            'book': None,
        }

    def reading_snapshot(
        self,
        *,
        kpis: dict[str, Any],
        reading_summary: dict[str, Any],
        reading_goal: dict[str, Any],
        currently_reading: list[dict[str, Any]],
        today: date | None = None,
    ) -> dict[str, Any] | None:
        """One short contextual insight; rotates daily among available facts."""
        today = today or date.today()
        candidates: list[dict[str, Any]] = []

        finished_year = int(reading_summary.get('finished_this_year') or 0)
        if reading_goal.get('exists') and reading_goal.get('target'):
            if reading_goal.get('goal_met'):
                candidates.append({
                    'kind': 'goal_met',
                    'label': 'Reading goal',
                    'text': (
                        f'Goal complete — {reading_goal["completed"]} of '
                        f'{reading_goal["target"]} books this year.'
                    ),
                })
            else:
                candidates.append({
                    'kind': 'goal_progress',
                    'label': 'Progress toward goal',
                    'text': (
                        f'{reading_goal["completed"]} of {reading_goal["target"]} '
                        f'books finished toward your {reading_goal["year"]} goal '
                        f'({reading_goal["percent"]}%).'
                    ),
                })
        elif finished_year > 0:
            candidates.append({
                'kind': 'finished_year',
                'label': 'This year',
                'text': (
                    f'{finished_year} book{"s" if finished_year != 1 else ""} '
                    f'finished in {today.year} so far.'
                ),
            })

        fav = kpis.get('favourite_author')
        if fav:
            candidates.append({
                'kind': 'favourite_author',
                'label': 'Favourite author',
                'text': f'{fav} leads your shelves by book count.',
            })

        wild = int(kpis.get('wild_books') or 0)
        if wild > 0:
            candidates.append({
                'kind': 'wild',
                'label': 'Wild books',
                'text': (
                    f'{wild} wild book{"s" if wild != 1 else ""} — unexpected '
                    f'picks that shaped your library.'
                ),
            })

        if currently_reading:
            item = currently_reading[0]
            days = item.get('elapsed_days')
            title = item['book'].title
            if days:
                candidates.append({
                    'kind': 'streak',
                    'label': 'In progress',
                    'text': (
                        f'You\'ve been with "{title}" for {days} '
                        f'day{"s" if days != 1 else ""}.'
                    ),
                })

        avg = reading_summary.get('average_duration_days')
        if avg is not None and reading_summary.get('sample_count', 0) > 0:
            candidates.append({
                'kind': 'pace',
                'label': 'Your pace',
                'text': (
                    f'On average you finish a book in {avg} '
                    f'day{"s" if avg != 1 else ""}.'
                ),
            })

        want = int(kpis.get('want_to_read') or 0)
        if want > 0 and not currently_reading:
            candidates.append({
                'kind': 'tbr',
                'label': 'Want to read',
                'text': (
                    f'{want} book{"s" if want != 1 else ""} waiting on your '
                    f'Want to Read list.'
                ),
            })

        if not candidates:
            return None

        pick = candidates[today.timetuple().tm_yday % len(candidates)]
        return pick

    def home_personalization(
        self,
        *,
        username: str,
        books: list[Any],
        kpis: dict[str, Any],
        reading_summary: dict[str, Any],
        currently_reading: list[dict[str, Any]],
        reading_goal: dict[str, Any],
        is_empty: bool,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Bundle hero, snapshot, and recently finished for the home dashboard."""
        today = today or date.today()
        return {
            'hero': self.home_hero(
                username=username,
                currently_reading=currently_reading,
                reading_goal=reading_goal,
                is_empty=is_empty,
            ),
            'snapshot': self.reading_snapshot(
                kpis=kpis,
                reading_summary=reading_summary,
                reading_goal=reading_goal,
                currently_reading=currently_reading,
                today=today,
            ),
            'recently_finished': self.recently_finished(books, limit=5),
        }

    def annual_goal_progress(
        self,
        goal: Any | None,
        finished_this_year: int,
        *,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Build dashboard payload for the current year's reading goal.

        Progress counts finished books with ``finished_reading_at`` in the
        current calendar year (same rule as ``finished_this_year``).
        Projection extrapolates the current daily finish rate to year-end
        and estimates when the target would be reached.
        """
        today = today or date.today()
        year = today.year
        empty = {
            'exists': False,
            'year': year,
            'target': None,
            'completed': finished_this_year,
            'remaining': None,
            'percent': 0,
            'on_pace': False,
            'projected_total': None,
            'projected_date': None,
            'goal_met': False,
            'pace_label': None,
            'projection_label': None,
        }
        if goal is None:
            return empty

        target = int(goal.target_count)
        completed = max(0, int(finished_this_year))
        remaining = max(0, target - completed)
        percent = min(100, round((completed / target) * 100)) if target > 0 else 0
        goal_met = completed >= target

        day_num = today.timetuple().tm_yday
        days_total = 366 if calendar.isleap(year) else 365
        year_end = date(year, 12, 31)

        if completed == 0:
            projected_total = 0
            projected_date = None
            on_pace = False
            pace_label = 'Finish a book with a finish date to start tracking pace.'
            projection_label = 'Projection appears after your first finish this year.'
        else:
            rate = completed / day_num
            projected_total = int(round(rate * days_total))
            on_pace = projected_total >= target or goal_met
            if goal_met:
                projected_date = today
                pace_label = 'Goal reached — nice work.'
                projection_label = f'You\'ve finished {completed} of {target} books.'
            else:
                days_needed = math.ceil(remaining / rate)
                projected_date = today + timedelta(days=days_needed)
                if projected_date > year_end:
                    projection_label = (
                        f'At this pace, about {projected_total} books by Dec 31 '
                        f'(goal is {target}).'
                    )
                    pace_label = 'Behind pace for this year.'
                elif on_pace:
                    projection_label = (
                        f'On pace for ~{projected_total} by year end. '
                        f'Goal around {projected_date.strftime("%b %d")}.'
                    )
                    pace_label = 'On pace.'
                else:
                    projection_label = (
                        f'At this pace, about {projected_total} books by Dec 31 '
                        f'(goal is {target}).'
                    )
                    pace_label = 'Behind pace for this year.'

        return {
            'exists': True,
            'year': year,
            'target': target,
            'completed': completed,
            'remaining': remaining,
            'percent': percent,
            'on_pace': on_pace,
            'projected_total': projected_total,
            'projected_date': projected_date,
            'goal_met': goal_met,
            'pace_label': pace_label,
            'projection_label': projection_label,
        }

    # ── My Reading Year (narrative / Wrapped) ─────────────────

    SLIDE_IDS = (
        'cover',
        'library',
        'book',
        'author',
        'journey',
        'goal',
        'quote',
        'closing',
    )

    def books_finished_in_year(self, books: list[Any], year: int) -> list[Any]:
        """Finished books with ``finished_reading_at`` in the given calendar year.

        Same year rule as annual goal progress — no date invention for legacy rows.
        """
        finished = []
        for b in books:
            status = (
                b.reading_status
                if ReadingStatus.is_valid(b.reading_status)
                else ReadingStatus.FINISHED
            )
            finished_at = getattr(b, 'finished_reading_at', None)
            if status == ReadingStatus.FINISHED and finished_at is not None:
                if finished_at.year == year:
                    finished.append(b)
        return finished

    def available_reading_years(
        self,
        books: list[Any],
        goals: list[Any] | None = None,
        *,
        today: date | None = None,
    ) -> list[int]:
        """Years that have finish dates, goals, or the current calendar year."""
        today = today or date.today()
        years: set[int] = {today.year}
        for b in books:
            finished_at = getattr(b, 'finished_reading_at', None)
            if finished_at is not None:
                years.add(finished_at.year)
            started_at = getattr(b, 'started_reading_at', None)
            if started_at is not None:
                years.add(started_at.year)
        for g in goals or []:
            if getattr(g, 'year', None) is not None:
                years.add(int(g.year))
        return sorted(years, reverse=True)

    def _serialize_year_book(self, book: Any) -> dict[str, Any]:
        return {
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'rating': book.rating if has_rating(book) else None,
            'is_wild': bool(book.is_wild),
            'cover_filename': book.cover_filename,
            'cover_data': getattr(book, 'cover_data', None),
            'started_reading_at': getattr(book, 'started_reading_at', None),
            'finished_reading_at': getattr(book, 'finished_reading_at', None),
        }

    def reading_year(
        self,
        books: list[Any],
        quotes: list[Any],
        goal: Any | None,
        reading_service: Any,
        *,
        year: int,
        username: str,
        available_years: list[int] | None = None,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Build the eight-slide My Reading Year narrative payload.

        Pure in-memory aggregation from existing Book / Quote / ReadingGoal rows.
        """
        today = today or date.today()
        year_books = self.books_finished_in_year(books, year)
        year_books_sorted = sorted(
            year_books,
            key=lambda b: (
                -(b.rating if has_rating(b) else 0),
                -int(bool(b.is_wild)),
                b.finished_reading_at or date.min,
                b.title or '',
            ),
        )

        rated = [b for b in year_books if has_rating(b)]
        avg_rating = (
            round(sum(b.rating for b in rated) / len(rated), 1) if rated else None
        )
        wild_count = sum(1 for b in year_books if b.is_wild)
        authors = {b.author for b in year_books}

        # Cover collage — prefer books with covers, highest rated first
        # Each entry is a dict with cover_filename and cover_data so the
        # share engine can load from DB (cover_data) or disk (cover_filename).
        covers: list[dict[str, Any]] = []
        seen_covers: set[str] = set()
        for b in year_books_sorted:
            cover_data = getattr(b, 'cover_data', None)
            cover_filename = b.cover_filename
            key = cover_data or cover_filename
            if key and key not in seen_covers:
                seen_covers.add(key)
                covers.append({'cover_filename': cover_filename, 'cover_data': cover_data})
            if len(covers) >= 8:
                break

        # Book of the Year — top rated finish; ties favour wild then finish date
        book_of_year = (
            self._serialize_year_book(year_books_sorted[0])
            if year_books_sorted
            else None
        )

        # Favourite author — most finishes this year, then avg rating
        author_map: dict[str, dict[str, Any]] = {}
        for b in year_books:
            entry = author_map.setdefault(
                b.author,
                {
                    'name': b.author,
                    'book_count': 0,
                    'rating_sum': 0,
                    'rating_count': 0,
                    'titles': [],
                    'covers': [],
                },
            )
            entry['book_count'] += 1
            entry['titles'].append(b.title)
            if has_rating(b):
                entry['rating_sum'] += b.rating
                entry['rating_count'] += 1
            cover_data = getattr(b, 'cover_data', None)
            if (cover_data or b.cover_filename) and len(entry['covers']) < 4:
                entry['covers'].append({
                    'cover_filename': b.cover_filename,
                    'cover_data': cover_data,
                })

        favourite_author = None
        if author_map:
            ranked = []
            for a in author_map.values():
                avg = (
                    round(a['rating_sum'] / a['rating_count'], 1)
                    if a['rating_count']
                    else 0
                )
                ranked.append({
                    'name': a['name'],
                    'book_count': a['book_count'],
                    'avg_rating': avg,
                    'titles': a['titles'],
                    'covers': a['covers'],
                })
            ranked.sort(key=lambda x: (-x['book_count'], -x['avg_rating'], x['name']))
            favourite_author = ranked[0]

        # Reading journey — monthly finishes + duration extremes
        month_counts = [0] * 12
        duration_rows: list[dict[str, Any]] = []
        for b in year_books:
            finished_at = b.finished_reading_at
            if finished_at is not None:
                month_counts[finished_at.month - 1] += 1
            duration = reading_service.calculate_duration(
                getattr(b, 'started_reading_at', None),
                finished_at,
            )
            if duration is not None:
                duration_rows.append({
                    'title': b.title,
                    'author': b.author,
                    'days': duration,
                    'cover_filename': b.cover_filename,
                })

        month_labels = [
            calendar.month_abbr[i] for i in range(1, 13)
        ]
        months = [
            {'label': month_labels[i], 'count': month_counts[i], 'month': i + 1}
            for i in range(12)
        ]
        busiest = max(months, key=lambda m: (m['count'], -m['month']))
        max_month_count = max((m['count'] for m in months), default=0)
        if duration_rows:
            avg_days = round(
                sum(r['days'] for r in duration_rows) / len(duration_rows),
                1,
            )
            fastest = min(duration_rows, key=lambda r: (r['days'], r['title']))
            longest = max(duration_rows, key=lambda r: (r['days'], r['title']))
        else:
            avg_days = None
            fastest = None
            longest = None

        journey = {
            'months': months,
            'max_month_count': max_month_count,
            'busiest_month': busiest if busiest['count'] > 0 else None,
            'avg_duration_days': avg_days,
            'fastest': fastest,
            'longest': longest,
            'sample_count': len(duration_rows),
        }

        # Goal for the selected year (not always "today")
        finished_count = len(year_books)
        if goal is not None:
            # Reuse pace math but pin "today" to year-end when viewing a past year
            goal_today = today if today.year == year else date(year, 12, 31)
            goal_slide = self.annual_goal_progress(
                goal,
                finished_count,
                today=goal_today,
            )
            goal_slide['year'] = year
        else:
            goal_slide = {
                'exists': False,
                'year': year,
                'target': None,
                'completed': finished_count,
                'remaining': None,
                'percent': 0,
                'on_pace': False,
                'projected_total': None,
                'projected_date': None,
                'goal_met': False,
                'pace_label': None,
                'projection_label': None,
            }

        # Favourite Quote — user-marked only (never random / heuristic)
        quote_of_year = None
        favourite_q = next(
            (q for q in quotes if getattr(q, 'is_favourite', False)),
            None,
        )
        if favourite_q is not None:
            book = next((b for b in books if b.id == favourite_q.book_id), None)
            quote_of_year = {
                'text': favourite_q.text,
                'page_ref': favourite_q.page_ref,
                'book_title': book.title if book else None,
                'book_author': book.author if book else None,
                'cover_filename': book.cover_filename if book else None,
                'cover_data': getattr(book, 'cover_data', None) if book else None,
                'rating': (
                    book.rating if book is not None and has_rating(book) else None
                ),
                'is_favourite': True,
            }

        is_empty = finished_count == 0
        closing = {
            'finished_count': finished_count,
            'author_count': len(authors),
            'wild_count': wild_count,
            'avg_rating': avg_rating,
            'book_title': book_of_year['title'] if book_of_year else None,
            'author_name': favourite_author['name'] if favourite_author else None,
            'goal_met': bool(goal_slide.get('goal_met')),
            'has_goal': bool(goal_slide.get('exists')),
            'tagline': (
                f'{finished_count} book{"s" if finished_count != 1 else ""} · '
                f'{year}'
                if finished_count
                else f'Your {year} story is waiting to be written.'
            ),
        }

        return {
            'year': year,
            'username': username,
            'available_years': available_years or [year],
            'is_empty': is_empty,
            'slide_ids': list(self.SLIDE_IDS),
            'cover': {
                'year': year,
                'username': username,
                'finished_count': finished_count,
            },
            'library': {
                'finished_count': finished_count,
                'author_count': len(authors),
                'wild_count': wild_count,
                'avg_rating': avg_rating,
                'covers': covers,
                'books': [self._serialize_year_book(b) for b in year_books_sorted[:12]],
            },
            'book_of_year': book_of_year,
            'favourite_author': favourite_author,
            'journey': journey,
            'goal': goal_slide,
            'quote_of_year': quote_of_year,
            'closing': closing,
        }

    # ── Author detail page ────────────────────────────────────

    def author_page_stats(self, books: list[Any]) -> dict[str, Any]:
        """Stats for a single-author book list (in-memory; no extra queries)."""
        rated = [b for b in books if has_rating(b)]
        avg_rating = (
            round(sum(b.rating for b in rated) / len(rated), 1) if rated else None
        )
        currently_reading = sum(
            1
            for b in books
            if (
                b.reading_status
                if ReadingStatus.is_valid(b.reading_status)
                else ReadingStatus.FINISHED
            )
            == ReadingStatus.READING
        )
        return {
            'author_count': len(books),
            'wild_count': sum(1 for b in books if b.is_wild),
            'avg_rating': avg_rating,
            'currently_reading_count': currently_reading,
        }

    # ── Admin hub ─────────────────────────────────────────────

    def admin_dashboard(
        self,
        *,
        users: list[Any],
        books: list[Any],
        total_quotes: int,
        admin_username: str,
        orphaned_count: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Build all admin hub KPIs, chart payloads, and global rankings."""
        now = now or datetime.utcnow()
        non_admin = [u for u in users if u.username != admin_username]

        total_users = len(users)
        active_users = sum(1 for u in users if u.is_active)
        disabled_users = total_users - active_users
        total_books = len(books)
        wild_count = sum(1 for b in books if b.is_wild)
        currently_reading = sum(
            1
            for b in books
            if (b.reading_status or ReadingStatus.FINISHED) == ReadingStatus.READING
        )
        week_ago = now - timedelta(days=7)
        books_added_this_week = sum(
            1 for b in books if b.date_added is not None and b.date_added >= week_ago
        )

        most_active = max(non_admin, key=lambda u: len(u.books), default=None)
        newest_user = max(non_admin, key=lambda u: u.created_at, default=None)

        month_keys: list[str] = []
        month_labels: list[str] = []
        for i in range(11, -1, -1):
            y = now.year + (now.month - 1 - i) // 12
            m = (now.month - 1 - i) % 12 + 1
            month_keys.append(f'{y}-{m:02d}')
            month_labels.append(datetime(y, m, 1).strftime('%b %y'))

        counts: dict[str, int] = defaultdict(int)
        for b in books:
            if b.date_added:
                counts[b.date_added.strftime('%Y-%m')] += 1
        books_per_month = json.dumps([counts.get(k, 0) for k in month_keys])
        month_labels_js = json.dumps(month_labels)

        users_labels_js = json.dumps([u.username for u in non_admin])
        users_books_js = json.dumps([len(u.books) for u in non_admin])

        author_counts: dict[str, dict[str, Any]] = defaultdict(
            lambda: {'count': 0, 'rating_sum': 0, 'rating_count': 0}
        )
        for b in books:
            author_counts[b.author]['count'] += 1
            if has_rating(b):
                author_counts[b.author]['rating_sum'] += b.rating
                author_counts[b.author]['rating_count'] += 1
        top_authors_global = sorted(
            [
                {
                    'name': a,
                    'count': v['count'],
                    'avg_rating': (
                        round(v['rating_sum'] / v['rating_count'], 1)
                        if v['rating_count']
                        else 0
                    ),
                }
                for a, v in author_counts.items()
            ],
            key=lambda x: (-x['count'], -x['avg_rating']),
        )[:5]

        book_agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {'count': 0, 'rating_sum': 0, 'rating_count': 0, 'author': ''}
        )
        for b in books:
            key = b.title
            book_agg[key]['count'] += 1
            if has_rating(b):
                book_agg[key]['rating_sum'] += b.rating
                book_agg[key]['rating_count'] += 1
            book_agg[key]['author'] = b.author
        top_books_global = sorted(
            [
                {
                    'title': t,
                    'author': v['author'],
                    'count': v['count'],
                    'avg_rating': (
                        round(v['rating_sum'] / v['rating_count'], 1)
                        if v['rating_count']
                        else 0
                    ),
                }
                for t, v in book_agg.items()
            ],
            key=lambda x: (-x['avg_rating'], -x['count']),
        )[:5]

        return {
            'non_admin': non_admin,
            'total_users': total_users,
            'active_users': active_users,
            'disabled_users': disabled_users,
            'total_books': total_books,
            'total_quotes': total_quotes,
            'wild_count': wild_count,
            'currently_reading': currently_reading,
            'books_added_this_week': books_added_this_week,
            'most_active': most_active,
            'newest_user': newest_user,
            'month_labels_js': month_labels_js,
            'books_per_month': books_per_month,
            'users_labels_js': users_labels_js,
            'users_books_js': users_books_js,
            'top_authors_global': top_authors_global,
            'top_books_global': top_books_global,
            'orphaned_count': orphaned_count,
        }

    def admin_user_explorer(
        self,
        users: list[Any],
        *,
        q: str = '',
        sort: str = 'books',
        order: str = 'desc',
    ) -> list[dict[str, Any]]:
        """Build searchable/sortable user rows for the admin User Explorer.

        Each row includes book, quote, wild, and currently-reading counts
        derived from existing relationships — no extra schema.
        """
        needle = (q or '').strip().lower()
        rows: list[dict[str, Any]] = []
        for user in users:
            books = list(getattr(user, 'books', None) or [])
            quotes = list(getattr(user, 'quotes', None) or [])
            wild_count = sum(1 for b in books if b.is_wild)
            reading_count = sum(
                1
                for b in books
                if (b.reading_status or ReadingStatus.FINISHED) == ReadingStatus.READING
            )
            if needle and needle not in (user.username or '').lower():
                continue
            rows.append({
                'user': user,
                'book_count': len(books),
                'quote_count': len(quotes),
                'wild_count': wild_count,
                'reading_count': reading_count,
            })

        sort_key = (sort or 'books').lower()
        reverse = (order or 'desc').lower() != 'asc'
        key_fns = {
            'username': lambda r: (r['user'].username or '').lower(),
            'joined': lambda r: r['user'].created_at or datetime.min,
            'books': lambda r: r['book_count'],
            'quotes': lambda r: r['quote_count'],
            'wild': lambda r: r['wild_count'],
            'reading': lambda r: r['reading_count'],
            'status': lambda r: 1 if r['user'].is_active else 0,
        }
        key_fn = key_fns.get(sort_key, key_fns['books'])
        rows.sort(key=key_fn, reverse=reverse)
        return rows

    def admin_group_quotes(
        self,
        quotes: list[Any],
    ) -> list[dict[str, Any]]:
        """Group quotes by book for admin user-detail (same shape as /quotes)."""
        by_book: dict[int, dict[str, Any]] = {}
        for q in quotes:
            book = getattr(q, 'book', None)
            if book is None:
                continue
            entry = by_book.setdefault(
                book.id,
                {'book': book, 'quotes': []},
            )
            entry['quotes'].append(q)
        groups = list(by_book.values())
        for g in groups:
            g['quotes'].sort(
                key=lambda x: x.date_added or datetime.min,
                reverse=True,
            )
        groups.sort(
            key=lambda g: (
                max(
                    (q.date_added or datetime.min for q in g['quotes']),
                    default=datetime.min,
                )
            ),
            reverse=True,
        )
        return groups
