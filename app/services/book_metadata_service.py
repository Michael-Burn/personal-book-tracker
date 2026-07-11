"""External book metadata lookup — Google Books primary, Open Library fallback.

Routes call this service for search/detail; they must not embed provider HTTP.
Failures return empty results so manual Add Book always remains available.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Hosts allowed when downloading a provider cover (SSRF guard).
COVER_HOST_ALLOWLIST = frozenset({
    'books.google.com',
    'www.books.google.com',
    'books.googleusercontent.com',
    'encrypted-tbn0.gstatic.com',
    'encrypted-tbn1.gstatic.com',
    'encrypted-tbn2.gstatic.com',
    'encrypted-tbn3.gstatic.com',
    'covers.openlibrary.org',
    'ia600200.us.archive.org',
    'archive.org',
    'www.archive.org',
})


class BookMetadataService:
    """Search and fetch book metadata from external catalogs."""

    GOOGLE_SEARCH = 'https://www.googleapis.com/books/v1/volumes'
    GOOGLE_VOLUME = 'https://www.googleapis.com/books/v1/volumes/{volume_id}'
    OPEN_LIBRARY_SEARCH = 'https://openlibrary.org/search.json'
    OPEN_LIBRARY_WORK = 'https://openlibrary.org{work_key}.json'
    OPEN_LIBRARY_COVER = 'https://covers.openlibrary.org/b/id/{cover_id}-M.jpg'

    DEFAULT_TIMEOUT = 3.0
    DEFAULT_LIMIT = 8
    CACHE_TTL_SECONDS = 300
    CACHE_MAX_ENTRIES = 64

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get('GOOGLE_BOOKS_API_KEY', '').strip() or None
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._http = session or requests.Session()
        self._http.headers.setdefault(
            'User-Agent',
            'KwalitecLibrary/3.2 (personal book tracker; metadata search)',
        )
        # In-process cache for repeated lookups in this worker session
        self._cache: dict[str, tuple[float, Any]] = {}

    # ── Public API ────────────────────────────────────────────

    def search_books(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return normalized search hits for ``query``. Empty list on failure."""
        q = (query or '').strip()
        if len(q) < 2:
            return []

        limit = max(1, min(int(limit or self.DEFAULT_LIMIT), 20))
        cache_key = f'search:{q.lower()}:{limit}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        results = self._search_google(q, limit)
        if not results:
            results = self._search_open_library(q, limit)

        self._cache_set(cache_key, results)
        return results

    def get_book(self, book_id: str) -> dict[str, Any] | None:
        """Return one normalized book by prefixed id (``gb:…`` / ``ol:…``)."""
        raw_id = (book_id or '').strip()
        if not raw_id:
            return None

        cache_key = f'get:{raw_id}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        provider, native_id = self._split_id(raw_id)
        result: dict[str, Any] | None = None
        if provider == 'gb':
            result = self._get_google(native_id)
        elif provider == 'ol':
            result = self._get_open_library(native_id)
        else:
            # Unknown prefix — try Google then Open Library with the raw id
            result = self._get_google(raw_id) or self._get_open_library(raw_id)

        if result is not None:
            self._cache_set(cache_key, result)
        return result

    def normalize_result(
        self,
        raw: dict[str, Any],
        *,
        provider: str,
    ) -> dict[str, Any] | None:
        """Map a provider payload into the shared result shape."""
        if not isinstance(raw, dict):
            return None
        if provider == 'google_books':
            return self._normalize_google(raw)
        if provider == 'open_library':
            return self._normalize_open_library(raw)
        return None

    def is_allowed_cover_url(self, url: str | None) -> bool:
        """True when ``url`` is https/http to an allowlisted cover host."""
        if not url or not isinstance(url, str):
            return False
        try:
            parsed = urlparse(url.strip())
        except ValueError:
            return False
        if parsed.scheme not in ('http', 'https'):
            return False
        host = (parsed.hostname or '').lower()
        if not host:
            return False
        if host in COVER_HOST_ALLOWLIST:
            return True
        # Allow Google Books content hosts under *.google.com / *.gstatic.com
        if host.endswith('.google.com') or host.endswith('.googleapis.com'):
            return True
        if host.endswith('.gstatic.com'):
            return True
        if host.endswith('.archive.org'):
            return True
        return False

    def fetch_cover_bytes(self, url: str, *, max_bytes: int = 5_242_880) -> bytes | None:
        """Download cover image bytes from an allowlisted URL. None on failure."""
        if not self.is_allowed_cover_url(url):
            return None
        fetch_url = url.strip()
        if fetch_url.startswith('http://'):
            fetch_url = 'https://' + fetch_url[len('http://'):]
        try:
            resp = self._http.get(fetch_url, timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                return None
            content_type = (resp.headers.get('Content-Type') or '').lower()
            if content_type and not content_type.startswith('image/') and 'octet-stream' not in content_type:
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
            data = b''.join(chunks)
            return data or None
        except requests.RequestException as exc:
            logger.info('Cover download failed: %s', exc)
            return None

    # ── Google Books ──────────────────────────────────────────

    def _search_google(self, query: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            'q': query,
            'maxResults': limit,
            'printType': 'books',
        }
        if self.api_key:
            params['key'] = self.api_key
        data = self._get_json(self.GOOGLE_SEARCH, params=params)
        if not data:
            return []
        items = data.get('items') or []
        results: list[dict[str, Any]] = []
        for item in items:
            normalized = self.normalize_result(item, provider='google_books')
            if normalized:
                results.append(normalized)
        return results

    def _get_google(self, volume_id: str) -> dict[str, Any] | None:
        volume_id = volume_id.strip()
        if not volume_id:
            return None
        params = {}
        if self.api_key:
            params['key'] = self.api_key
        data = self._get_json(self.GOOGLE_VOLUME.format(volume_id=volume_id), params=params or None)
        if not data:
            return None
        return self.normalize_result(data, provider='google_books')

    def _normalize_google(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        info = raw.get('volumeInfo') or {}
        title = (info.get('title') or '').strip()
        if not title:
            return None
        authors = [a.strip() for a in (info.get('authors') or []) if isinstance(a, str) and a.strip()]
        published = (info.get('publishedDate') or '').strip()
        year = published[:4] if len(published) >= 4 and published[:4].isdigit() else None
        images = info.get('imageLinks') or {}
        cover = (
            images.get('thumbnail')
            or images.get('smallThumbnail')
            or images.get('small')
            or images.get('medium')
        )
        if isinstance(cover, str) and cover.startswith('http://'):
            cover = 'https://' + cover[len('http://'):]
        volume_id = (raw.get('id') or '').strip()
        if not volume_id:
            return None
        return {
            'id': f'gb:{volume_id}',
            'title': title,
            'author': ', '.join(authors) if authors else '',
            'authors': authors,
            'year': year,
            'cover_url': cover if isinstance(cover, str) else None,
            'provider': 'google_books',
        }

    # ── Open Library ──────────────────────────────────────────

    def _search_open_library(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get_json(
            self.OPEN_LIBRARY_SEARCH,
            params={'q': query, 'limit': limit, 'fields': 'key,title,author_name,first_publish_year,cover_i'},
        )
        if not data:
            return []
        docs = data.get('docs') or []
        results: list[dict[str, Any]] = []
        for doc in docs:
            normalized = self.normalize_result(doc, provider='open_library')
            if normalized:
                results.append(normalized)
        return results

    def _get_open_library(self, work_id: str) -> dict[str, Any] | None:
        work_id = work_id.strip()
        if not work_id:
            return None
        if work_id.startswith('/works/'):
            work_key = work_id
        elif work_id.startswith('OL') and work_id.endswith('W'):
            work_key = f'/works/{work_id}'
        elif work_id.startswith('works/'):
            work_key = f'/{work_id}'
        else:
            work_key = f'/works/{work_id}'

        data = self._get_json(self.OPEN_LIBRARY_WORK.format(work_key=work_key))
        if not data:
            return None

        # Work payloads differ from search docs — shape a minimal doc
        title = (data.get('title') or '').strip()
        if not title:
            return None
        authors: list[str] = []
        for entry in data.get('authors') or []:
            if isinstance(entry, dict):
                name = entry.get('name')
                if isinstance(name, str) and name.strip():
                    authors.append(name.strip())
                else:
                    author_key = (entry.get('author') or {}).get('key') if isinstance(entry.get('author'), dict) else None
                    if author_key:
                        authors.append(author_key.rsplit('/', 1)[-1])
        covers = data.get('covers') or []
        cover_i = covers[0] if covers else None
        year = None
        first = data.get('first_publish_date')
        if not first and isinstance(data.get('created'), dict):
            first = data.get('created', {}).get('value')
        if isinstance(first, str) and len(first) >= 4 and first[:4].isdigit():
            year = first[:4]
        doc = {
            'key': work_key,
            'title': title,
            'author_name': authors,
            'first_publish_year': int(year) if year and year.isdigit() else None,
            'cover_i': cover_i,
        }
        return self.normalize_result(doc, provider='open_library')

    def _normalize_open_library(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        title = (raw.get('title') or '').strip()
        if not title:
            return None
        key = (raw.get('key') or '').strip()
        if not key:
            return None
        olid = key.rsplit('/', 1)[-1]
        authors = [a.strip() for a in (raw.get('author_name') or []) if isinstance(a, str) and a.strip()]
        year_val = raw.get('first_publish_year')
        year = str(year_val) if year_val not in (None, '') else None
        cover_i = raw.get('cover_i')
        cover_url = None
        if cover_i not in (None, ''):
            cover_url = self.OPEN_LIBRARY_COVER.format(cover_id=cover_i)
        return {
            'id': f'ol:{olid}',
            'title': title,
            'author': ', '.join(authors) if authors else '',
            'authors': authors,
            'year': year,
            'cover_url': cover_url,
            'provider': 'open_library',
        }

    # ── HTTP / cache helpers ──────────────────────────────────

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        try:
            resp = self._http.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                logger.info('Metadata HTTP %s for %s', resp.status_code, url)
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (requests.RequestException, ValueError) as exc:
            logger.info('Metadata request failed for %s: %s', url, exc)
            return None

    @staticmethod
    def _split_id(book_id: str) -> tuple[str | None, str]:
        if ':' in book_id:
            prefix, rest = book_id.split(':', 1)
            prefix = prefix.lower().strip()
            rest = rest.strip()
            if prefix in ('gb', 'ol') and rest:
                return prefix, rest
        return None, book_id

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self.CACHE_MAX_ENTRIES:
            # Drop oldest half by expiry
            ordered = sorted(self._cache.items(), key=lambda kv: kv[1][0])
            for old_key, _ in ordered[: max(1, self.CACHE_MAX_ENTRIES // 2)]:
                self._cache.pop(old_key, None)
        self._cache[key] = (time.monotonic() + self.CACHE_TTL_SECONDS, value)
