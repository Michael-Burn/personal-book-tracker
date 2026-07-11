# Kwalitec Library

Kwalitec Library is a premium personal reading companion designed to help readers collect, remember and celebrate the books that matter most. It turns a private library into a living record of what you read, how you felt about it, and the moments worth sharing.

---

## Features

### Library

- **Smart Book Entry** — search and fill title, author and cover from trusted sources
- **Google Books integration** — primary metadata lookup while adding or editing books
- **Open Library fallback** — automatic backup when Google Books has no match
- **Premium bookshelf** — author-first library with grid and list views
- **Book cover uploads** — local covers processed and stored safely for the shelf
- **Responsive design** — a polished experience on desktop and mobile

### Reading

- **Reading Status** — track books as want to read, reading, finished, abandoned or paused
- **Reading Timeline** — start and finish dates with duration insights
- **Wild Rating** — mark the books that stood out beyond a standard score
- **Quotes** — save and revisit favourite lines from your collection
- **Reading Goals** — set an annual target and watch progress accumulate

### Insights

- **Personal dashboard** — a home view shaped around your current reading life
- **Reading statistics** — counts, averages and status breakdowns at a glance
- **Reading snapshots** — concise summaries of recent activity and momentum
- **Reading goal progress** — clear progress against your yearly target
- **My Reading Year** — a narrative look back at a year of reading

### Sharing

- **Premium share cards** — image cards ready for stories and social posts
- **Public profile** — share top authors and books without requiring a login
- **Reading Year export** — export My Reading Year slides in multiple formats

### Administration

- **Admin Console** — system-wide overview for the operator account
- **User Explorer** — inspect individual libraries and account activity
- **Global Library** — browse and filter books across all users
- **User Statistics** — charts and KPIs for growth and engagement

---

## Technology

- **Python** & **Flask** — application server
- **SQLAlchemy** & **PostgreSQL** — persistence (SQLite supported locally)
- **Jinja2** & custom CSS — server-rendered UI
- **Chart.js** — dashboard and admin charts
- **Pillow** — covers, avatars and share imagery
- **Render** — production hosting with Gunicorn

---

## Screenshots

![Dashboard](docs/images/dashboard.png)

![Library](docs/images/library.png)

![My Reading Year](docs/images/reading-year.png)

![Share Card](docs/images/share-card.png)

---

## Installation

```bash
git clone https://github.com/your-org/personal-book-tracker.git
cd personal-book-tracker

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env        # set SECRET_KEY (and DATABASE_URL if needed)

export FLASK_APP=app.py
flask db upgrade
flask run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## Deployment

Production is intended for **Render** with **PostgreSQL**.

1. Connect the repository as a Render Web Service (`gunicorn app:app`).
2. Attach a managed Postgres instance and set `DATABASE_URL`.
3. Set `SECRET_KEY` and `FLASK_DEBUG=0`.
4. Run `flask db upgrade` after deploy.
5. Mount a **persistent disk** for uploads (`UPLOAD_ROOT`) so book covers and media survive redeploys.

See `README_RENDER.md` for additional deployment notes.

---

## Vision

Kwalitec Library is built around the idea that every reader deserves a beautiful place to preserve their reading journey.
