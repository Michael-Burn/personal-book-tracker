"""Centralized upload / media settings.

Values can be overridden via environment variables or Flask config.
Defaults match the production behaviour already in use.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    # app/config/media_settings.py → parents[2] = project root
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MediaSettings:
    """Upload roots, size limits, and allowed formats for all media kinds."""

    upload_root: Path = field(default_factory=lambda: (
        Path(os.environ['UPLOAD_ROOT'])
        if os.environ.get('UPLOAD_ROOT')
        else _project_root() / 'uploads'
    ))

    # Subdirectories under upload_root (filename stored in DB; path is never hardcoded in routes)
    books_dirname: str = 'books'
    avatars_dirname: str = 'avatars'      # reserved for future file-based avatars
    authors_dirname: str = 'authors'      # reserved for future author images

    # Book covers (current production limits)
    cover_max_bytes: int = 5 * 1024 * 1024
    cover_max_edge: int = 600
    cover_webp_quality: int = 90

    # Avatar uploads currently stored as data-URI on User.avatar (≤ 2 MB in route)
    avatar_max_bytes: int = 2 * 1024 * 1024
    avatar_max_edge: int = 400

    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({'jpg', 'jpeg', 'png', 'webp'})
    )
    allowed_pil_formats: frozenset[str] = field(
        default_factory=lambda: frozenset({'JPEG', 'PNG', 'WEBP'})
    )
    # Avatar route also accepts GIF today — keep that allow-list separate
    avatar_pil_formats: frozenset[str] = field(
        default_factory=lambda: frozenset({'JPEG', 'PNG', 'GIF', 'WEBP'})
    )

    @classmethod
    def from_mapping(cls, mapping: dict | None = None) -> MediaSettings:
        """Build settings from a Flask config dict / env-backed mapping."""
        mapping = mapping or {}
        root = mapping.get('UPLOAD_ROOT') or os.environ.get('UPLOAD_ROOT')
        kwargs: dict = {}
        if root:
            kwargs['upload_root'] = Path(root)
        if mapping.get('MEDIA_COVER_MAX_BYTES') is not None:
            kwargs['cover_max_bytes'] = int(mapping['MEDIA_COVER_MAX_BYTES'])
        if mapping.get('MEDIA_COVER_MAX_EDGE') is not None:
            kwargs['cover_max_edge'] = int(mapping['MEDIA_COVER_MAX_EDGE'])
        if mapping.get('MEDIA_AVATAR_MAX_BYTES') is not None:
            kwargs['avatar_max_bytes'] = int(mapping['MEDIA_AVATAR_MAX_BYTES'])
        return cls(**kwargs)

    @property
    def books_dir(self) -> Path:
        return self.upload_root / self.books_dirname

    @property
    def avatars_dir(self) -> Path:
        return self.upload_root / self.avatars_dirname

    @property
    def authors_dir(self) -> Path:
        return self.upload_root / self.authors_dirname

    def dir_for(self, kind: str) -> Path:
        """Resolve a media kind ('books'|'avatars'|'authors') to its directory."""
        mapping = {
            'books': self.books_dir,
            'avatars': self.avatars_dir,
            'authors': self.authors_dir,
        }
        try:
            return mapping[kind]
        except KeyError as exc:
            raise ValueError(f'Unknown media kind: {kind!r}') from exc
