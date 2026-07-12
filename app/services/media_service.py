"""Reusable media infrastructure for validated image uploads.

Book covers are the first consumer; the same helpers serve future
upload types (avatars on disk, author images) without putting Pillow
logic in routes.
"""
from __future__ import annotations

import io
import uuid
import base64
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from config.media_settings import MediaSettings


class MediaValidationError(Exception):
    """Raised when an upload fails validation. ``message`` is user-safe."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class MediaService:
    """Validate, process, store, and delete uploaded media files."""

    def __init__(
        self,
        settings: MediaSettings | None = None,
        upload_root: str | Path | None = None,
    ):
        if settings is None:
            if upload_root is not None:
                settings = MediaSettings(upload_root=Path(upload_root))
            else:
                settings = MediaSettings()
        self.settings = settings
        self.upload_root = settings.upload_root

        # Ensure known media directories exist (books today; avatars/authors ready)
        for directory in (
            settings.books_dir,
            settings.avatars_dir,
            settings.authors_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # ── Settings accessors (avoid hard-coded paths in routes) ─

    @property
    def books_dir(self) -> Path:
        return self.settings.books_dir

    @property
    def avatars_dir(self) -> Path:
        return self.settings.avatars_dir

    @property
    def authors_dir(self) -> Path:
        return self.settings.authors_dir

    @property
    def ALLOWED_EXTENSIONS(self) -> frozenset[str]:
        return self.settings.allowed_extensions

    @property
    def ALLOWED_PIL_FORMATS(self) -> frozenset[str]:
        return self.settings.allowed_pil_formats

    @property
    def MAX_BYTES(self) -> int:
        return self.settings.cover_max_bytes

    @property
    def MAX_EDGE(self) -> int:
        return self.settings.cover_max_edge

    @property
    def WEBP_QUALITY(self) -> int:
        return self.settings.cover_webp_quality

    @property
    def BOOK_COVER_DIRNAME(self) -> str:
        return self.settings.books_dirname

    # ── Public API ────────────────────────────────────────────

    def validate_image(
        self,
        file_storage: FileStorage,
        *,
        max_bytes: int | None = None,
        allowed_formats: frozenset[str] | None = None,
        size_error: str | None = None,
    ) -> Image.Image:
        """Validate extension, size, and decodability. Returns a loaded Pillow image."""
        max_bytes = max_bytes if max_bytes is not None else self.MAX_BYTES
        allowed_formats = allowed_formats or self.ALLOWED_PIL_FORMATS
        size_error = size_error or 'Cover image must be 5 MB or smaller.'

        if file_storage is None or not file_storage.filename:
            raise MediaValidationError('Please choose an image file to upload.')

        ext = self._extension(file_storage.filename)
        ext_ok = ext in self.ALLOWED_EXTENSIONS
        if 'GIF' in allowed_formats and ext == 'gif':
            ext_ok = True
        if not ext_ok:
            if allowed_formats == self.settings.avatar_pil_formats:
                raise MediaValidationError(
                    'Unsupported image format. Please upload a JPG, PNG, GIF, or WEBP file.'
                )
            raise MediaValidationError(
                'Unsupported image format. Please upload a JPG, PNG, or WEBP file.'
            )

        raw = file_storage.read(max_bytes + 1)
        if not raw:
            raise MediaValidationError('The uploaded file is empty.')
        if len(raw) > max_bytes:
            raise MediaValidationError(size_error)

        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except UnidentifiedImageError as exc:
            raise MediaValidationError(
                'That file looks corrupt or unreadable. Please upload a valid JPG, PNG, GIF, or WEBP image.'
                if allowed_formats == self.settings.avatar_pil_formats
                else 'Could not read that image. Please upload a valid JPG, PNG, or WEBP file.'
            ) from exc
        except OSError as exc:
            raise MediaValidationError(
                'Could not process that image. Please try a different file.'
            ) from exc

        fmt = (img.format or '').upper()
        if fmt not in allowed_formats:
            if allowed_formats == self.settings.avatar_pil_formats:
                raise MediaValidationError(
                    'Unsupported image format. Please upload a JPG, PNG, GIF, or WEBP file.'
                )
            raise MediaValidationError(
                'Unsupported image format. Please upload a JPG, PNG, or WEBP file.'
            )

        return img

    def generate_filename(self, prefix: str = 'cover') -> str:
        """Return a unique WEBP filename (stored in DB; not a full path)."""
        safe_prefix = secure_filename(prefix) or 'cover'
        return f'{safe_prefix}_{uuid.uuid4().hex}.webp'

    def resize_image(
        self,
        img: Image.Image,
        *,
        max_edge: int | None = None,
    ) -> Image.Image:
        """Resize so the longest edge is at most max_edge; preserve aspect ratio."""
        max_edge = max_edge if max_edge is not None else self.MAX_EDGE
        w, h = img.size
        longest = max(w, h)
        if longest <= max_edge:
            return img
        scale = max_edge / float(longest)
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        return img.resize(new_size, Image.Resampling.LANCZOS)

    def resize_cover(self, img: Image.Image) -> Image.Image:
        """Resize a book cover (alias for resize_image with cover settings)."""
        return self.resize_image(img, max_edge=self.MAX_EDGE)

    def to_rgb_webp_ready(self, img: Image.Image) -> Image.Image:
        """Flatten transparency onto white and convert to RGB for WEBP output."""
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            rgba = img.convert('RGBA')
            background = Image.new('RGB', rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            return background
        if img.mode != 'RGB':
            return img.convert('RGB')
        return img

    def save_processed_image(
        self,
        img: Image.Image,
        *,
        kind: str = 'books',
        prefix: str = 'cover',
    ) -> str:
        """Write a processed RGB image as WEBP under the given media kind directory.

        Returns the filename only (for storage in the DB).
        """
        img = self.to_rgb_webp_ready(img)
        filename = self.generate_filename(prefix)
        dest = self._safe_path(kind, filename, must_exist=False)
        if dest is None:
            raise MediaValidationError('Could not store the image. Please try again.')
        img.save(dest, format='WEBP', quality=self.WEBP_QUALITY, method=6)
        return filename

    def save_book_cover(self, file_storage: FileStorage) -> str:
        """Validate, resize, convert to WEBP, write under uploads/books/.

        Returns the filename only (for Book.cover_filename).
        """
        img = self.validate_image(
            file_storage,
            max_bytes=self.settings.cover_max_bytes,
            size_error='Cover image must be 5 MB or smaller.',
        )
        img = self.resize_cover(img)
        return self.save_processed_image(img, kind='books', prefix='cover')

    def save_book_cover_from_bytes(self, raw: bytes, *, filename_hint: str = 'cover.jpg') -> str:
        """Validate raw image bytes (e.g. provider cover download), store as WEBP.

        Returns the filename only (for Book.cover_filename).
        """
        if not raw:
            raise MediaValidationError('The cover image is empty.')
        storage = FileStorage(stream=io.BytesIO(raw), filename=filename_hint)
        return self.save_book_cover(storage)

    def process_avatar_to_data_uri(self, file_storage: FileStorage) -> str:
        """Validate, resize, and encode an avatar as a WEBP data-URI for User.avatar.

        Accepts JPEG / PNG / GIF / WEBP input. Always stores a compact WEBP data-URI
        so the DB TEXT column stays well within limits. Does not touch the database.
        """
        img = self.validate_image(
            file_storage,
            max_bytes=self.settings.avatar_max_bytes,
            allowed_formats=self.settings.avatar_pil_formats,
            size_error='Image must be under 2 MB.',
        )
        img = self.resize_image(img, max_edge=self.settings.avatar_max_edge)
        img = self.to_rgb_webp_ready(img)
        out = io.BytesIO()
        try:
            img.save(out, format='WEBP', quality=85, method=6)
        except OSError as exc:
            raise MediaValidationError(
                'Could not process that image. Please try a different file.'
            ) from exc
        data = out.getvalue()
        if not data:
            raise MediaValidationError(
                'Could not process that image. Please try a different file.'
            )
        return f'data:image/webp;base64,{base64.b64encode(data).decode("ascii")}'

    def save_avatar_file(self, file_storage: FileStorage) -> str:
        """Validate and store an avatar under uploads/avatars/ (future file-based avatars).

        Current production still stores avatars as data-URIs on User.avatar;
        this helper is ready when that storage moves to disk.
        """
        img = self.validate_image(
            file_storage,
            max_bytes=self.settings.avatar_max_bytes,
            allowed_formats=self.settings.avatar_pil_formats,
            size_error='Image must be under 2 MB.',
        )
        img = self.resize_image(img, max_edge=self.settings.avatar_max_edge)
        return self.save_processed_image(img, kind='avatars', prefix='avatar')

    def save_author_image(self, file_storage: FileStorage) -> str:
        """Validate and store an author image under uploads/authors/ (future use)."""
        img = self.validate_image(
            file_storage,
            max_bytes=self.settings.cover_max_bytes,
            size_error='Author image must be 5 MB or smaller.',
        )
        img = self.resize_image(img, max_edge=self.MAX_EDGE)
        return self.save_processed_image(img, kind='authors', prefix='author')

    def delete_book_cover(self, filename: str | None) -> None:
        """Delete a stored cover if present. No-op for missing/invalid names."""
        self.delete_media('books', filename)

    def delete_media(self, kind: str, filename: str | None) -> None:
        """Delete a stored media file. No-op for missing/invalid names."""
        if not filename:
            return
        path = self._safe_path(kind, filename, must_exist=False)
        if path is None:
            return
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            # Deletion must never break book/user flows
            pass

    def resolve_book_cover_path(self, filename: str | None) -> Path | None:
        """Return absolute path for a cover filename, or None if invalid/missing."""
        return self.resolve_media_path('books', filename)

    def resolve_media_path(self, kind: str, filename: str | None) -> Path | None:
        """Return absolute path for a media filename, or None if invalid/missing."""
        if not filename:
            return None
        return self._safe_path(kind, filename, must_exist=True)

    # ── Internals ─────────────────────────────────────────────

    @staticmethod
    def _extension(filename: str) -> str:
        name = secure_filename(filename) or ''
        if '.' not in name:
            # Fall back to raw extension when secure_filename strips unusual names
            raw = filename.rsplit('.', 1)
            return raw[-1].lower() if len(raw) == 2 else ''
        return name.rsplit('.', 1)[-1].lower()

    def _safe_path(
        self,
        kind: str,
        filename: str,
        must_exist: bool = True,
    ) -> Path | None:
        """Resolve filename inside a media kind directory; reject path traversal."""
        if not filename or '/' in filename or '\\' in filename or '..' in filename:
            return None
        safe = secure_filename(filename)
        if not safe or safe != filename:
            return None
        try:
            base = self.settings.dir_for(kind).resolve()
        except ValueError:
            return None
        path = (base / safe).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            return None
        if must_exist and not path.is_file():
            return None
        return path

    def _safe_book_path(self, filename: str, must_exist: bool = True) -> Path | None:
        """Backward-compatible alias for book cover path resolution."""
        return self._safe_path('books', filename, must_exist=must_exist)
