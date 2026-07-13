# Changelog

All notable changes to Kwalitec Library are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Version 1.2.0

### Added

- **Export Reading History** — download a personal archive from Settings as CSV, Excel, PDF reading report, or complete JSON backup
- Optional export filters (status, author, rating, year) for CSV, Excel, and PDF
- Official **RELEASE_PROTOCOL.md** defining branch strategy, versioning, and production release steps

### Improved

- Persist book covers as database data-URIs with admin cover backfill tooling
- Theme toggle and dark-mode visibility across home snapshot, admin, and share surfaces
- Cover upload reliability (CSRF handling for large images; batched backfill)

### Fixed

- Admin Tools section visibility when nested inside modal overlay
- Home snapshot card contrast in dark mode

## Version 1.0

### Added

- **Wild Rating** — highlight exceptional books beyond a standard 1–5 score
- **Premium Library** — author-centred bookshelf with refined cards and view toggles
- **Book Covers** — upload, process and display covers across the library
- **Smart Book Entry** — metadata search while adding or editing books
- **Reading Status** — want to read, reading, finished, abandoned and paused workflows
- **Reading Timeline** — start and finish dates with duration summaries
- **Reading Goals** — annual targets with live progress on the home dashboard
- **Reading Statistics Dashboard** — personal KPIs, charts and status breakdowns
- **Home Personalization** — hero, snapshot and recently finished sections tailored to the reader
- **My Reading Year** — year-in-review narrative with exportable slides
- **Premium Share System** — public rankings plus Pillow-generated share cards
- **Admin Console** — operator hub with User Explorer, Global Library and user statistics

### Improved

- **Dashboard** — richer home experience with goals, activity and reading context
- **Library UI** — clearer status chips, wild badges and cover-forward presentation
- **Author pages** — stronger per-author browsing and reading summaries
- **Share experience** — more polished public profiles and exportable imagery
- **Metadata entry workflow** — faster cataloguing via Google Books with Open Library fallback

### Technical

- Production-safe additive Alembic migrations for covers, wild flags, reading status, timeline dates and goals
- **MediaService** — validated image processing and upload storage
- **ReadingService** — status, rating and timeline validation helpers
- **StatisticsService** — dashboard, share rankings, Reading Year and admin analytics
- **BookMetadataService** — Google Books and Open Library integration
- **ShareEngine** — multi-format Reading Year and share card rendering
