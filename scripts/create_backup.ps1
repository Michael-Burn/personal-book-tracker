# Create timestamped backup zip of repository (excludes backups and .git)
if (-not (Test-Path ".\backups")) { New-Item -ItemType Directory -Path ".\backups" | Out-Null }
$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
$items = Get-ChildItem -Force | Where-Object { $_.Name -ne 'backups' -and $_.Name -ne '.git' } | ForEach-Object { $_.FullName }
Compress-Archive -LiteralPath $items -DestinationPath (Join-Path -Path ".\backups" -ChildPath ("book_tracker_backup_" + $ts + ".zip")) -Force
Write-Output ("Backup created: .\backups\book_tracker_backup_" + $ts + ".zip")
