# Kwalitec Library — App Logic & Features Summary

Personal multi-user book tracker (“Kwalitec Library” / “Book Tracker”). Users rate books by author, save quotes, share public rankings, and manage their account. One admin account can oversee the whole system.

---

## 1. Architecture overview

| Layer | Choice |
|--------|--------|
| Language | Python 3 |
| Framework | Flask 3.1 (monolith) |
| ORM | Flask-SQLAlchemy + Alembic migrations |
| Auth | Flask-Login (session cookies) + Werkzeug `pbkdf2:sha256` |
| Security | CSRF (Flask-WTF), HTTPS/headers (Flask-Talisman), rate limits (Flask-Limiter) |
| Images | Pillow (avatars + share PNG cards) |
| DB (local) | SQLite (`instance/books.db`) |
| DB (prod) | PostgreSQL via `DATABASE_URL` |
| Hosting | Render + Gunicorn |
| Frontend | Jinja2 templates + vanilla JS + `static/style.css` |

Almost all server logic lives in `app.py`. There is no SPA and no separate REST API (except one JSON endpoint for a random quote).

```
Browser → Flask routes → SQLAlchemy models → SQLite / Postgres
              ↓
       Jinja templates + static CSS/JS
```

---

## 2. Data model

### User
- `username` (unique), `password_hash`, `avatar` (base64 data-URI), `is_active`
- `security_question` / `security_answer_hash` for password recovery
- `is_admin` exists but **admin access is gated by username `Admin`**, not this flag
- `plan` / `stripe_customer_id` — stubs for future billing (unused)

### Book
- `title`, `author` (plain string — no separate Author table), `rating` (1–5)
- `user_id` (owner; nullable for legacy orphaned rows), `date_added`
- Deleting a book cascades to its quotes

### Quote
- `text`, optional `page_ref`, linked to `book_id` and `user_id`

---

## 3. Features & logic

### 3.1 Authentication & accounts

| Feature | How it works |
|---------|----------------|
| **Register** | Username `^[A-Za-z0-9_]{3,30}$`, password ≥ 8 chars, confirm match, security Q&A. Rate limit 5/min. Auto-login → authors dashboard. |
| **Login** | Hash check + `is_active`. Admin → admin hub; others → `/authors`. Rate limit 10/min. Supports safe `next` redirects. |
| **Logout** | Clears session. |
| **Forgot password** | 3-step session flow: username → answer security question → set new password. Rate limit 10/min. |
| **Change password** | In settings; verifies current password, then logs out. |
| **Security question** | Updateable in settings (requires current password). |
| **Avatar** | Upload ≤ 2MB; Pillow validates, thumbnails to 400×400, stores as data-URI on the user row. |
| **Disabled users** | `before_request` logs out inactive accounts. |

### 3.2 Personal library (core product)

1. **Authors dashboard** (`/authors`)  
   Loads the current user’s books and aggregates by author (count, titles, average rating). Shows KPIs (authors, books, overall avg, most-active author). Client-side search/sort; add-book modal; random quote card via `/api/quotes/random`.

2. **Author detail** (`/author/<author>`)  
   Lists that author’s books for the signed-in user. Edit/delete books; add quotes via modal.

3. **Add / edit / delete book**  
   Title, author, rating 1–5. Ownership checked on mutate (`user_id == current_user.id` or 403). Delete cascades quotes.

### 3.3 Quotes

- Add from an author page; browse/edit/delete on `/quotes` (grouped by book).
- Random quote JSON endpoint for the dashboard sidebar (`204` if none).

### 3.4 Public sharing

- **`/share/<username>`** — public page (no login). Top 5 authors (by avg rating, then book count) and top 5 books (by rating). Period: `all` or `month` (last 30 days).
- Social: X intent, WhatsApp, copy link; Open Graph meta tags.
- **`/share/<username>/card.png`** — Pillow-generated 1080×1920 “Save for Stories” PNG (rate limit 30/min).

### 3.5 Admin hub (username `Admin` only)

- KPIs: users (active/disabled), books, quotes, most-active / newest user
- Charts (Chart.js): books per month (12 months), books per user
- Global top authors / books across all users
- Assign orphaned books (`user_id` null) to a chosen user
- Enable/disable users; delete user and cascade their books/quotes
- Cannot disable or delete self

### 3.6 Cover / landing

- `/cover` — marketing-style entry with login/register (or library/share if logged in)
- `/` redirects to login or `/authors`

---

## 4. Route map

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | — | Redirect to login or authors |
| GET/POST | `/register` | public | Sign up |
| GET/POST | `/login` | public | Sign in |
| GET/POST | `/forgot-password` | public | Reset via security question |
| GET | `/logout` | login | Sign out |
| GET | `/cover` | public | Landing / cover page |
| GET | `/authors` | login | Authors dashboard |
| GET | `/author/<author>` | login | Books for one author |
| GET/POST | `/add` | login | Add book |
| GET/POST | `/edit/<id>` | login + owner | Edit book |
| GET | `/delete/<id>` | login + owner | Delete book |
| GET | `/quotes` | login | Quotes library |
| POST | `/quotes/add` | login + book owner | Add quote |
| POST | `/quotes/<id>/edit` | login + owner | Edit quote |
| POST | `/quotes/<id>/delete` | login + owner | Delete quote |
| GET | `/api/quotes/random` | login | Random quote JSON |
| POST | `/settings/avatar` | login | Upload avatar |
| GET/POST | `/settings/password` | login | Change password |
| POST | `/settings/security-question` | login | Update security Q |
| GET | `/share/<username>` | public | Share rankings |
| GET | `/share/<username>/card.png` | public | PNG share card |
| GET | `/admin/users` | Admin | Admin dashboard |
| POST | `/admin/assign-orphaned` | Admin | Assign orphan books |
| POST | `/admin/users/<id>/toggle-active` | Admin | Enable/disable user |
| POST | `/admin/users/<id>/delete` | Admin | Delete user + data |

---

## 5. UI surface

Templates are standalone Jinja pages (no shared `base.html`), styled by one large `static/style.css`.

| Template | Role |
|----------|------|
| `index.html` | Authors dashboard, search/sort, quote card, add modal |
| `author_books.html` | Per-author book list, quote/add modals |
| `add_book.html` / `edit_book.html` | Standalone book forms |
| `quotes.html` | Grouped quotes + edit modal |
| `share.html` | Public rankings + social/export |
| `login.html` / `register.html` / `forgot_password.html` | Auth |
| `settings.html` | Password + security question |
| `admin_users.html` | Admin KPIs, charts, user management |
| `cover.html` | Visual cover / CTAs |

Client patterns: modal overlays, snackbar on `?added=1`, JSON-embedded author data for filter/sort, Chart.js on admin.

---

## 6. Ranking / aggregation logic

**Per-user top authors** (`top_authors`): group books by author string → average rating → sort by avg desc, then count desc, then name → take top N.

**Per-user top books** (`top_books`): order by rating desc, then `date_added` desc → take top N. Optional `since` filter for “past month”.

**Authors dashboard**: same author grouping, plus overall avg rating and “most active” author (most books).

**Admin global rankings**: aggregate across *all* users’ books (by author name / book title).

---

## 7. Security model

- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` in production
- CSRF tokens on forms
- Rate limits on register, login, forgot-password, share cards
- Ownership checks on book/quote mutations
- Admin = exact username `Admin` (`@admin_required`)
- `ProxyFix` for Render TLS / client IP
- Password recovery is security-question based (no email)

---

## 8. Startup & ops

On boot (non-migration CLI):

1. **Schema safety** — `create_all` if core tables missing; Postgres `_repair_db()` can `ADD COLUMN IF NOT EXISTS`
2. **Admin seed** — creates `Admin` with a one-time random password logged to stdout if missing; may assign orphaned books to user `Kwalitec` if that user exists

**Deploy (Render):** install deps → `flask db upgrade` → `gunicorn app:app`. Key env vars: `SECRET_KEY`, `DATABASE_URL`, `FLASK_DEBUG=0`. See `README_RENDER.md`.

**Scripts:** `scripts/seed_admin.py`, migration/backup/audit PowerShell helpers.

---

## 9. What is *not* implemented

- External book APIs (Open Library, Goodreads, Google Books) — all data is user-entered
- Stripe / paid plans (schema stubs only)
- Email verification or email-based password reset
- OAuth / 2FA
- Automated test suite
- Blueprints / modular package layout (single-file app)

---

## 10. Project layout (important paths)

```
app.py                 # Models, routes, helpers, startup
templates/             # All Jinja pages
static/style.css       # Full UI stylesheet
migrations/versions/   # Alembic revisions
scripts/               # Seed, backup, audit helpers
Procfile / render.yaml # Deploy config
requirements.txt       # Python dependencies
```

---

**In short:** a multi-user personal reading tracker with ratings by author, quotes, public share pages/PNG cards, account settings, and an admin analytics hub — built as a Flask + SQLAlchemy monolith aimed at Render/Postgres.
