# PowerShell script to run a dependency audit
# Requires Python and pip available in the active environment.

pip install pip-audit
pip-audit

Write-Host "Dependency audit complete. Review findings and pin/update vulnerable packages."