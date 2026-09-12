# SEO Brain - stop the locally running backend + web UI (only processes we started).
$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$RunDir = Join-Path $Root 'run'

$stopped = 0
foreach ($name in @('frontend', 'backend')) {
    $f = Join-Path $RunDir "$name.pid"
    if (-not (Test-Path $f)) { continue }
    $procId = [int](Get-Content $f | Select-Object -First 1)
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) {
        # kill the whole tree (next/node children included)
        & taskkill /PID $procId /T /F | Out-Null
        Write-Host "Stopped $name (pid $procId)"
        $stopped++
    }
    Remove-Item $f -Force
}
if ($stopped -eq 0) { Write-Host "Nothing to stop (SEO Brain was not running)." }
else { Write-Host "SEO Brain stopped." -ForegroundColor Green }
exit 0
