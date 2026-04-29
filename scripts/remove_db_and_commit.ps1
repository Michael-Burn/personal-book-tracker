# PowerShell script to remove committed SQLite DB from git index and create a prepare branch.
# Run from repo root in PowerShell with git configured.

git checkout -b prepare-render
# Keep local DB file, remove from git index
if (Test-Path "instance/books.db") {
    git rm --cached "instance/books.db"
}
# Add changes and commit
git add .gitignore requirements.txt app.py
git commit -m "Prepare app for Render: ignore DB, env-driven secrets, add security and migrations"
# Push branch to remote (ensure origin exists and you have permission)
git push -u origin prepare-render

Write-Host "Done. If you need to remove DB from history, use BFG or git filter-repo."