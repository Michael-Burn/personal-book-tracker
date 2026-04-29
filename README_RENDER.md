Render deployment and secure setup

Overview
- Connect this GitHub repo to Render as a Web Service.
- Use the existing `Procfile` (`web: gunicorn app:app`) to start the app.

Environment variables to set on Render
- `DATABASE_URL` — Render Postgres connection string (recommended for production).
- `SECRET_KEY` — long random value for session security.
- `FLASK_DEBUG` — set to `0` in production.

Deployment steps
1. Push code to GitHub on a branch (e.g., `prepare-render`).
2. On Render, create a new Web Service and connect to the GitHub repo/branch.
3. Create a Managed Postgres on Render and copy the connection string into `DATABASE_URL`.
4. In Render dashboard, set `SECRET_KEY` and `FLASK_DEBUG=0` in Environment.
5. After the first deploy, run a one-off Shell on Render and run:
   ```bash
   export FLASK_APP=app.py
   flask db upgrade
   ```
   or
   ```bash
   python -c "from app import db; db.create_all()"
   ```

Security notes
- Do not use the committed SQLite DB in production. Remove it from the repo index and history.
- Rotate any secrets if they were accidentally committed.
- Enable 2FA on GitHub and Render accounts and limit access to env vars.
- Run dependency audits regularly (see `scripts/dependency_audit.ps1`).

Local migration & verification
- Activate virtualenv and run `scripts/setup_migrations.ps1` (PowerShell), or run the commands manually.

If you want, I can run the git steps to remove the DB from index and create the branch, or produce a BFG/git-filter-repo command to wipe the file from history.