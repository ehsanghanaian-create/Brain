# SEO Brain - uninstall the local copy. Your DATA is kept unless you answer 'yes' to purge.
$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

Write-Host "Stopping SEO Brain (if running)..."
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop.ps1') | Out-Null

Write-Host "Removing the installed pieces (.venv, node_modules, build output)..."
foreach ($d in @('.venv', 'frontend\node_modules', 'frontend\.next', 'run')) {
    $p = Join-Path $Root $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Host "  removed $d" }
}

$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SEO Brain.lnk'
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "  removed the Desktop shortcut" }

Write-Host ""
Write-Host "Your data (the 'data' folder with the SEO database) was KEPT." -ForegroundColor Yellow
$ans = Read-Host "Delete the data too? Type 'yes' to delete it permanently"
if ($ans -eq 'yes') {
    Remove-Item (Join-Path $Root 'data') -Recurse -Force
    Write-Host "Data deleted."
}
Write-Host "Uninstall done. You can now delete this folder entirely." -ForegroundColor Green
exit 0
