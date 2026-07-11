"""Reusable share-image engine for story, portrait, and square cards.

Future share surfaces (rankings, reading year, custom cards) should render
through ShareEngine so format sizes, palette, fonts, and export stay consistent.
"""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont


class ShareFormat:
    """Named canvas sizes for social export."""

    STORY = 'story'          # 9:16 — Instagram / Stories
    PORTRAIT = 'portrait'    # 4:5 — feed portrait
    SQUARE = 'square'        # 1:1 — feed square

    SIZES = {
        STORY: (1080, 1920),
        PORTRAIT: (1080, 1350),
        SQUARE: (1080, 1080),
    }

    ALL = frozenset(SIZES.keys())

    @classmethod
    def is_valid(cls, value: str | None) -> bool:
        return value in cls.ALL

    @classmethod
    def size(cls, name: str) -> tuple[int, int]:
        if name not in cls.SIZES:
            raise ValueError(f'Unknown share format: {name!r}')
        return cls.SIZES[name]


class ShareEngine:
    """Pillow canvas helpers + card renderers.

    Colour palette mirrors ``static/style.css`` so web slides and PNG exports
    feel like one editorial system.
    """

    PRIMARY = (108, 99, 255)
    PRIMARY_DARK = (79, 70, 229)
    ACCENT = (34, 197, 94)
    RATING = (246, 200, 95)
    TEXT1 = (17, 24, 39)
    TEXT2 = (107, 114, 128)
    BORDER = (229, 231, 235)
    BG = (248, 250, 252)
    WHITE = (255, 255, 255)
    INK = (15, 17, 26)
    CREAM = (252, 251, 248)

    _BOLD_PATHS = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        'C:/Windows/Fonts/arialbd.ttf',
    ]
    _REG_PATHS = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        'C:/Windows/Fonts/arial.ttf',
    ]

    def __init__(
        self,
        *,
        cover_resolver: Callable[[str | None], Path | None] | None = None,
        brand: str = 'Kwalitec Library',
        site_url: str = 'https://personal-book-tracker-8xij.onrender.com',
    ):
        self.cover_resolver = cover_resolver
        self.brand = brand
        self.site_url = site_url
        self._font_cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}

    # ── Public API ────────────────────────────────────────────

    def canvas(self, format_name: str = ShareFormat.STORY, *, fill=None) -> Image.Image:
        w, h = ShareFormat.size(format_name)
        return Image.new('RGB', (w, h), fill or self.CREAM)

    def font(self, size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        key = (int(size), bool(bold))
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        paths = self._BOLD_PATHS if bold else self._REG_PATHS
        font = None
        for path in paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    break
                except OSError:
                    continue
        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
        self._font_cache[key] = font
        return font
    def to_png(self, img: Image.Image) -> io.BytesIO:
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf

    def render_reading_year_slide(
        self,
        slide_id: str,
        year_data: dict[str, Any],
        *,
        format_name: str = ShareFormat.STORY,
    ) -> io.BytesIO:
        """Render one My Reading Year slide as PNG bytes."""
        if not ShareFormat.is_valid(format_name):
            format_name = ShareFormat.STORY
        renderers = {
            'cover': self._slide_cover,
            'library': self._slide_library,
            'book': self._slide_book,
            'author': self._slide_author,
            'journey': self._slide_journey,
            'goal': self._slide_goal,
            'quote': self._slide_quote,
            'closing': self._slide_closing,
        }
        renderer = renderers.get(slide_id)
        if renderer is None:
            raise ValueError(f'Unknown reading-year slide: {slide_id!r}')
        img = renderer(year_data, format_name)
        return self.to_png(img)

    # ── Layout helpers ────────────────────────────────────────

    def _pad(self, format_name: str) -> int:
        w, _ = ShareFormat.size(format_name)
        return 56 if format_name == ShareFormat.SQUARE else 64

    def _scale(self, format_name: str, story_size: int) -> int:
        """Scale typography from story baseline to other formats."""
        _, h = ShareFormat.size(format_name)
        story_h = ShareFormat.SIZES[ShareFormat.STORY][1]
        return max(14, int(round(story_size * (h / story_h))))

    def _text_width(self, draw: ImageDraw.ImageDraw, text: str, font) -> int:
        return int(draw.textlength(text, font=font))

    def _wrap(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        max_width: int,
        *,
        max_lines: int = 6,
    ) -> list[str]:
        words = (text or '').split()
        if not words:
            return ['']
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f'{current} {word}'
            if self._text_width(draw, trial, font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if len(lines) < max_lines:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if len(' '.join(words)) > len(' '.join(lines)):
            # Truncate last line with ellipsis when overflowed
            last = lines[-1]
            while last and self._text_width(draw, last + '…', font) > max_width:
                last = last[:-1]
            lines[-1] = (last.rstrip() + '…') if last else '…'
        return lines

    def _draw_eyebrow(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        label: str,
        font,
    ) -> None:
        draw.text((x, y), label.upper(), fill=self.PRIMARY, font=font)

    def _draw_footer(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        format_name: str,
        *,
        year: int | None = None,
    ) -> None:
        w, h = img.size
        pad = self._pad(format_name)
        fn = self.font(self._scale(format_name, 22), bold=True)
        fn_s = self.font(self._scale(format_name, 18))
        y = h - pad - self._scale(format_name, 48)
        draw.rectangle([(0, y - 24), (w, y - 23)], fill=self.BORDER)
        brand = self.brand
        if year:
            brand = f'{self.brand}  ·  {year}'
        draw.text((pad, y), brand, fill=self.PRIMARY, font=fn)
        mark = 'My Reading Year'
        mw = self._text_width(draw, mark, fn_s)
        draw.text((w - pad - mw, y + 4), mark, fill=self.TEXT2, font=fn_s)

    def _load_cover(self, filename: str | None, size: tuple[int, int]) -> Image.Image | None:
        if not filename or self.cover_resolver is None:
            return None
        path = self.cover_resolver(filename)
        if path is None or not path.is_file():
            return None
        try:
            cover = Image.open(path).convert('RGB')
            cover = self._cover_fit(cover, size)
            return cover
        except OSError:
            return None

    @staticmethod
    def _cover_fit(cover: Image.Image, size: tuple[int, int]) -> Image.Image:
        tw, th = size
        cw, ch = cover.size
        scale = max(tw / cw, th / ch)
        nw, nh = int(cw * scale), int(ch * scale)
        cover = cover.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - tw) // 2
        top = (nh - th) // 2
        return cover.crop((left, top, left + tw, top + th))

    def _placeholder_cover(self, size: tuple[int, int], title: str = '') -> Image.Image:
        cover = Image.new('RGB', size, self.PRIMARY_DARK)
        draw = ImageDraw.Draw(cover)
        fn = self.font(max(18, size[0] // 12), bold=True)
        label = (title or 'Book')[:18]
        tw = self._text_width(draw, label, fn)
        draw.text(
            ((size[0] - tw) // 2, size[1] // 2 - 12),
            label,
            fill=self.WHITE,
            font=fn,
        )
        return cover

    def _paste_cover(
        self,
        img: Image.Image,
        filename: str | None,
        box: tuple[int, int, int, int],
        *,
        title: str = '',
        radius: int = 18,
    ) -> None:
        x0, y0, x1, y1 = box
        size = (x1 - x0, y1 - y0)
        cover = self._load_cover(filename, size) or self._placeholder_cover(size, title)
        if radius > 0:
            mask = Image.new('L', size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
            img.paste(cover, (x0, y0), mask)
        else:
            img.paste(cover, (x0, y0))

    def _stars(self, draw: ImageDraw.ImageDraw, x: int, y: int, rating: int | None, size: int = 18) -> None:
        if not rating:
            return
        for i in range(5):
            cx = x + i * (size + 8) + size // 2
            fill = self.RATING if i < rating else self.BORDER
            draw.polygon(self._star_pts(cx, y + size // 2, size // 2, size // 4.5), fill=fill)

    @staticmethod
    def _star_pts(cx, cy, outer_r, inner_r):
        pts = []
        for k in range(10):
            angle = math.radians(-90 + k * 36)
            r = outer_r if k % 2 == 0 else inner_r
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts

    # ── Slide renderers ───────────────────────────────────────

    def _slide_cover(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name, fill=self.INK)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)

        # Soft primary wash
        overlay = Image.new('RGB', (w, h // 2), self.PRIMARY_DARK)
        img.paste(overlay, (0, 0))
        draw.rectangle([(0, h // 2 - 2), (w, h)], fill=self.INK)

        cover = data.get('cover') or {}
        year = cover.get('year') or data.get('year')
        username = cover.get('username') or data.get('username') or ''
        finished = cover.get('finished_count', 0)

        fn_eye = self.font(self._scale(format_name, 28), bold=True)
        fn_year = self.font(self._scale(format_name, 160), bold=True)
        fn_title = self.font(self._scale(format_name, 56), bold=True)
        fn_sub = self.font(self._scale(format_name, 30))

        draw.text((pad, pad + 40), 'KWALITEC LIBRARY', fill=(200, 196, 255), font=fn_eye)
        year_s = str(year)
        yw = self._text_width(draw, year_s, fn_year)
        draw.text(((w - yw) // 2, h * 0.28), year_s, fill=self.WHITE, font=fn_year)

        title = 'My Reading Year'
        tw = self._text_width(draw, title, fn_title)
        draw.text(((w - tw) // 2, h * 0.52), title, fill=self.WHITE, font=fn_title)

        sub = f"{username}'s year in books"
        if finished:
            sub = f"{username}  ·  {finished} finished"
        sw = self._text_width(draw, sub, fn_sub)
        draw.text(((w - sw) // 2, h * 0.60), sub, fill=(180, 184, 196), font=fn_sub)

        draw.rectangle([(pad, h - pad - 8), (w - pad, h - pad)], fill=self.PRIMARY)
        return img

    def _slide_library(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        lib = data.get('library') or {}
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 64), bold=True)
        fn_num = self.font(self._scale(format_name, 72), bold=True)
        fn_lbl = self.font(self._scale(format_name, 24))
        fn_body = self.font(self._scale(format_name, 28))

        self._draw_eyebrow(draw, pad, pad + 20, f'Reading Year {year}', fn_eye)
        draw.text((pad, pad + 70), 'Your library\nthis year', fill=self.TEXT1, font=fn_h)

        stats = [
            (str(lib.get('finished_count') or 0), 'Books finished'),
            (str(lib.get('author_count') or 0), 'Authors'),
            (str(lib.get('wild_count') or 0), 'Wild picks'),
        ]
        if lib.get('avg_rating') is not None:
            stats.append((f"{lib['avg_rating']:.1f}", 'Avg rating'))

        y0 = int(h * 0.32)
        col_w = (w - pad * 2) // 2
        for i, (num, label) in enumerate(stats[:4]):
            cx = pad + (i % 2) * col_w
            cy = y0 + (i // 2) * self._scale(format_name, 140)
            draw.text((cx, cy), num, fill=self.PRIMARY, font=fn_num)
            draw.text((cx, cy + self._scale(format_name, 80)), label, fill=self.TEXT2, font=fn_lbl)

        # Cover strip
        covers = lib.get('covers') or []
        if covers:
            strip_y = h - pad - self._scale(format_name, 220)
            cover_h = self._scale(format_name, 160)
            cover_w = int(cover_h * 0.68)
            gap = 14
            for i, filename in enumerate(covers[:6]):
                x = pad + i * (cover_w + gap)
                if x + cover_w > w - pad:
                    break
                self._paste_cover(img, filename, (x, strip_y, x + cover_w, strip_y + cover_h), radius=12)
        else:
            draw.text(
                (pad, h - pad - self._scale(format_name, 100)),
                'Add covers to books for a richer year story.',
                fill=self.TEXT2,
                font=fn_body,
            )

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_book(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        book = data.get('book_of_year')
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 52), bold=True)
        fn_title = self.font(self._scale(format_name, 48), bold=True)
        fn_meta = self.font(self._scale(format_name, 28))

        self._draw_eyebrow(draw, pad, pad + 20, f'Book of the Year · {year}', fn_eye)
        draw.text((pad, pad + 70), 'The one that\ndefined the year', fill=self.TEXT1, font=fn_h)

        if not book:
            draw.text(
                (pad, int(h * 0.45)),
                'Finish a book with a finish date\nto crown your Book of the Year.',
                fill=self.TEXT2,
                font=fn_meta,
            )
            self._draw_footer(img, draw, format_name, year=year)
            return img

        cover_h = int(h * (0.38 if format_name == ShareFormat.STORY else 0.32))
        cover_w = int(cover_h * 0.68)
        cx = (w - cover_w) // 2
        cy = int(h * 0.28)
        self._paste_cover(
            img,
            book.get('cover_filename'),
            (cx, cy, cx + cover_w, cy + cover_h),
            title=book.get('title') or '',
            radius=20,
        )

        text_y = cy + cover_h + self._scale(format_name, 40)
        title_lines = self._wrap(draw, book.get('title') or '', fn_title, w - pad * 2, max_lines=3)
        for line in title_lines:
            tw = self._text_width(draw, line, fn_title)
            draw.text(((w - tw) // 2, text_y), line, fill=self.TEXT1, font=fn_title)
            text_y += self._scale(format_name, 56)

        author = f"by {book.get('author') or ''}"
        aw = self._text_width(draw, author, fn_meta)
        draw.text(((w - aw) // 2, text_y + 8), author, fill=self.TEXT2, font=fn_meta)
        if book.get('rating'):
            self._stars(
                draw,
                (w - 5 * 26) // 2,
                text_y + self._scale(format_name, 50),
                book['rating'],
                size=self._scale(format_name, 20),
            )
        if book.get('is_wild'):
            wild = 'WILD'
            ww = self._text_width(draw, wild, fn_eye)
            draw.text(
                ((w - ww) // 2, text_y + self._scale(format_name, 90)),
                wild,
                fill=self.ACCENT,
                font=fn_eye,
            )

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_author(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        author = data.get('favourite_author')
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 52), bold=True)
        fn_name = self.font(self._scale(format_name, 56), bold=True)
        fn_meta = self.font(self._scale(format_name, 28))

        self._draw_eyebrow(draw, pad, pad + 20, f'Favourite Author · {year}', fn_eye)
        draw.text((pad, pad + 70), 'The voice you\nreturned to', fill=self.TEXT1, font=fn_h)

        if not author:
            draw.text(
                (pad, int(h * 0.45)),
                'Your favourite author appears\nonce you finish books this year.',
                fill=self.TEXT2,
                font=fn_meta,
            )
            self._draw_footer(img, draw, format_name, year=year)
            return img

        name_lines = self._wrap(draw, author.get('name') or '', fn_name, w - pad * 2, max_lines=3)
        y = int(h * 0.38)
        for line in name_lines:
            draw.text((pad, y), line, fill=self.PRIMARY, font=fn_name)
            y += self._scale(format_name, 64)

        count = author.get('book_count') or 0
        meta = f"{count} book{'s' if count != 1 else ''} finished"
        if author.get('avg_rating'):
            meta += f"  ·  {author['avg_rating']:.1f} avg"
        draw.text((pad, y + 20), meta, fill=self.TEXT2, font=fn_meta)

        titles = author.get('titles') or []
        if titles:
            y2 = y + self._scale(format_name, 90)
            draw.text((pad, y2), 'Including', fill=self.TEXT2, font=fn_eye)
            y2 += self._scale(format_name, 40)
            for title in titles[:4]:
                lines = self._wrap(draw, title, fn_meta, w - pad * 2, max_lines=1)
                draw.text((pad, y2), lines[0], fill=self.TEXT1, font=fn_meta)
                y2 += self._scale(format_name, 40)

        covers = author.get('covers') or []
        if covers:
            strip_y = h - pad - self._scale(format_name, 200)
            cover_h = self._scale(format_name, 140)
            cover_w = int(cover_h * 0.68)
            for i, filename in enumerate(covers[:4]):
                x = pad + i * (cover_w + 14)
                self._paste_cover(img, filename, (x, strip_y, x + cover_w, strip_y + cover_h), radius=12)

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_journey(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        journey = data.get('journey') or {}
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 52), bold=True)
        fn_meta = self.font(self._scale(format_name, 26))
        fn_num = self.font(self._scale(format_name, 40), bold=True)

        self._draw_eyebrow(draw, pad, pad + 20, f'Reading Journey · {year}', fn_eye)
        draw.text((pad, pad + 70), 'How the year\nunfolded', fill=self.TEXT1, font=fn_h)

        months = journey.get('months') or []
        max_count = max((m.get('count') or 0 for m in months), default=0) or 1
        chart_top = int(h * 0.30)
        chart_bottom = int(h * (0.58 if format_name == ShareFormat.STORY else 0.55))
        chart_h = chart_bottom - chart_top
        bar_area_w = w - pad * 2
        gap = 8
        bar_w = max(12, (bar_area_w - gap * 11) // 12)

        for i, month in enumerate(months):
            count = month.get('count') or 0
            bh = int((count / max_count) * (chart_h - 40)) if count else 4
            x0 = pad + i * (bar_w + gap)
            y0 = chart_bottom - bh
            color = self.PRIMARY if count else self.BORDER
            draw.rounded_rectangle([(x0, y0), (x0 + bar_w, chart_bottom)], radius=6, fill=color)
            lbl = (month.get('label') or '')[:1]
            lw = self._text_width(draw, lbl, fn_meta)
            draw.text((x0 + (bar_w - lw) // 2, chart_bottom + 12), lbl, fill=self.TEXT2, font=fn_meta)

        y = chart_bottom + self._scale(format_name, 70)
        if journey.get('busiest_month') and journey['busiest_month'].get('count'):
            bm = journey['busiest_month']
            draw.text(
                (pad, y),
                f"Busiest month  ·  {bm['label']} ({bm['count']})",
                fill=self.TEXT1,
                font=fn_num,
            )
            y += self._scale(format_name, 55)

        if journey.get('avg_duration_days') is not None:
            draw.text(
                (pad, y),
                f"Average read  ·  {journey['avg_duration_days']} days",
                fill=self.TEXT2,
                font=fn_meta,
            )
            y += self._scale(format_name, 40)

        if journey.get('fastest'):
            f = journey['fastest']
            draw.text(
                (pad, y),
                f"Fastest  ·  {f['title'][:36]} ({f['days']}d)",
                fill=self.TEXT2,
                font=fn_meta,
            )
            y += self._scale(format_name, 36)

        if journey.get('longest'):
            lg = journey['longest']
            draw.text(
                (pad, y),
                f"Longest  ·  {lg['title'][:36]} ({lg['days']}d)",
                fill=self.TEXT2,
                font=fn_meta,
            )

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_goal(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        goal = data.get('goal') or {}
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 52), bold=True)
        fn_num = self.font(self._scale(format_name, 96), bold=True)
        fn_meta = self.font(self._scale(format_name, 28))

        self._draw_eyebrow(draw, pad, pad + 20, f'Reading Goal · {year}', fn_eye)
        draw.text((pad, pad + 70), 'The target\nyou set', fill=self.TEXT1, font=fn_h)

        completed = goal.get('completed') or 0
        if not goal.get('exists'):
            draw.text(
                (pad, int(h * 0.42)),
                f'You finished {completed} book{"s" if completed != 1 else ""}.\n'
                'Set a yearly goal from your library\nto track this slide next time.',
                fill=self.TEXT2,
                font=fn_meta,
            )
            self._draw_footer(img, draw, format_name, year=year)
            return img

        target = goal.get('target') or 0
        percent = goal.get('percent') or 0
        ratio = f'{completed} / {target}'
        rw = self._text_width(draw, ratio, fn_num)
        draw.text(((w - rw) // 2, int(h * 0.36)), ratio, fill=self.PRIMARY, font=fn_num)

        # Progress bar
        bar_y = int(h * 0.52)
        bar_h = 28
        draw.rounded_rectangle(
            [(pad, bar_y), (w - pad, bar_y + bar_h)],
            radius=14,
            fill=self.BORDER,
        )
        fill_w = int((w - pad * 2) * min(100, percent) / 100)
        if fill_w > 0:
            draw.rounded_rectangle(
                [(pad, bar_y), (pad + max(fill_w, 28), bar_y + bar_h)],
                radius=14,
                fill=self.ACCENT if goal.get('goal_met') else self.PRIMARY,
            )

        status = 'Goal reached' if goal.get('goal_met') else f'{percent}% of the way'
        sw = self._text_width(draw, status, fn_meta)
        draw.text(((w - sw) // 2, bar_y + 56), status, fill=self.TEXT1, font=fn_meta)

        if goal.get('pace_label'):
            pl = goal['pace_label']
            pw = self._text_width(draw, pl, fn_eye)
            draw.text(((w - pw) // 2, bar_y + 110), pl, fill=self.TEXT2, font=fn_eye)

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_quote(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        quote = data.get('quote_of_year')
        year = data.get('year')

        fn_eye = self.font(self._scale(format_name, 24), bold=True)
        fn_h = self.font(self._scale(format_name, 48), bold=True)
        fn_quote = self.font(self._scale(format_name, 40), bold=True)
        fn_meta = self.font(self._scale(format_name, 26))

        self._draw_eyebrow(draw, pad, pad + 20, f'Quote of the Year · {year}', fn_eye)
        draw.text((pad, pad + 70), 'Words that\nstayed with you', fill=self.TEXT1, font=fn_h)

        if not quote:
            draw.text(
                (pad, int(h * 0.45)),
                'Mark a passage ★ Favourite in Quotes\nto feature it as your Favourite Quote.',
                fill=self.TEXT2,
                font=fn_meta,
            )
            self._draw_footer(img, draw, format_name, year=year)
            return img

        mark = '“'
        draw.text((pad, int(h * 0.32)), mark, fill=self.PRIMARY, font=self.font(self._scale(format_name, 120), bold=True))

        lines = self._wrap(
            draw,
            quote.get('text') or '',
            fn_quote,
            w - pad * 2,
            max_lines=8 if format_name == ShareFormat.STORY else 6,
        )
        y = int(h * 0.42)
        for line in lines:
            draw.text((pad, y), line, fill=self.TEXT1, font=fn_quote)
            y += self._scale(format_name, 52)

        attribution = ''
        if quote.get('book_title'):
            attribution = quote['book_title']
            if quote.get('book_author'):
                attribution += f"  ·  {quote['book_author']}"
        if quote.get('page_ref'):
            attribution += f"  ·  p. {quote['page_ref']}"
        if attribution:
            draw.text((pad, min(y + 30, h - pad - 100)), attribution, fill=self.TEXT2, font=fn_meta)

        self._draw_footer(img, draw, format_name, year=year)
        return img

    def _slide_closing(self, data: dict[str, Any], format_name: str) -> Image.Image:
        img = self.canvas(format_name, fill=self.INK)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        pad = self._pad(format_name)
        closing = data.get('closing') or {}
        year = data.get('year')
        username = data.get('username') or ''

        fn_eye = self.font(self._scale(format_name, 26), bold=True)
        fn_h = self.font(self._scale(format_name, 64), bold=True)
        fn_body = self.font(self._scale(format_name, 32))
        fn_tag = self.font(self._scale(format_name, 28))

        draw.text((pad, pad + 40), 'KWALITEC LIBRARY', fill=(200, 196, 255), font=fn_eye)
        draw.text((pad, int(h * 0.28)), 'Until next\nchapter.', fill=self.WHITE, font=fn_h)

        lines = []
        if closing.get('finished_count'):
            lines.append(
                f"{closing['finished_count']} book"
                f"{'s' if closing['finished_count'] != 1 else ''} finished"
            )
        if closing.get('author_name'):
            lines.append(f"Favourite author · {closing['author_name']}")
        if closing.get('book_title'):
            lines.append(f"Book of the year · {closing['book_title']}")
        if closing.get('goal_met'):
            lines.append('Reading goal reached')

        y = int(h * 0.52)
        for line in lines[:4]:
            wrapped = self._wrap(draw, line, fn_body, w - pad * 2, max_lines=2)
            for wl in wrapped:
                draw.text((pad, y), wl, fill=(190, 194, 210), font=fn_body)
                y += self._scale(format_name, 42)
            y += 8

        tag = closing.get('tagline') or f'{username} · {year}'
        draw.text((pad, h - pad - self._scale(format_name, 60)), tag, fill=self.PRIMARY, font=fn_tag)
        return img
