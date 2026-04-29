# PowerShell helper to install deps and run Flask-Migrate locally (Windows).
# Run from repo root with your virtualenv activated or adjust paths.

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "No .venv found. Activate your Python venv or adjust script.";
}

# Activate virtualenv (if named .venv)
. .venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Set environment variables for Flask CLI
$env:FLASK_APP = "app.py"
$env:DATABASE_URL = "sqlite:///instance/books.db"
$env:SECRET_KEY = "dev-secret"

# Initialize migrations if not already present
if (-not (Test-Path "migrations")) {
    flask db init
}

flask db migrate -m "init"
flask db upgrade

Write-Host "Migrations applied. If you plan to use Postgres in production, set DATABASE_URL accordingly and run migrate/upgrade on the server."