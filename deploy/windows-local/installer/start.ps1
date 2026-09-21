# SEO Brain - start the local app (backend + web UI) and open the browser.
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $Root
$RunDir = Join-Path $Root 'run'
New-Item -ItemType Directory -Force $RunDir | Out-Null

function Fail($msg) { Write-Host "`n[X] $msg" -ForegroundColor Red; exit 1 }

# prefer the bundled Node runtime when present (fully self-contained package)
$nodeDir = Get-ChildItem (Join-Path $Root 'runtime') -Directory -Filter 'node-*-win-x64' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($nodeDir -and (Test-Path (Join-Path $nodeDir.FullName 'node.exe'))) { $env:Path = "$($nodeDir.FullName);$env:Path" }

$venvPy     = Join-Path $Root '.venv\Scripts\python.exe'
$standalone = Join-Path $Root 'frontend-standalone\server.js'      # prebuilt web UI (installer package)
$nextBin    = Join-Path $Root 'frontend\node_modules\next\dist\bin\next'
$built      = Join-Path $Root 'frontend\.next\BUILD_ID'
if (-not (Test-Path $venvPy)) { Fail "Not installed yet - run INSTALL.bat first." }
if (-not (Test-Path $standalone) -and (-not (Test-Path $nextBin) -or -not (Test-Path $built))) { Fail "Web UI is not built - run INSTALL.bat first." }

$env:SEO_KG_ROOT = $Root
$env:SEO_BRAIN_API_URL = "http://127.0.0.1:$ApiPort"

function Test-Health([string]$url, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -lt 500) { return $true }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

function Read-Pid([string]$name) {
    $f = Join-Path $RunDir "$name.pid"
    if (-not (Test-Path $f)) { return $null }
    $procId = Get-Content $f | Select-Object -First 1
    try { return (Get-Process -Id ([int]$procId) -ErrorAction Stop) } catch { return $null }
}

# ---------------------------------------------------------------- backend
$apiHealth = "http://127.0.0.1:$ApiPort/api/v1/health"
$backendUp = Test-Health $apiHealth 1
if (-not $backendUp) {
    if (Read-Pid 'backend') { Fail "Backend process exists but is not answering yet - wait a moment or run STOP.bat first." }
    Write-Host "Starting the backend (port $ApiPort)..."
    $p = Start-Process -FilePath $venvPy `
        -ArgumentList @((Join-Path $Root 'backend\cli\api.py'), '--host', '127.0.0.1', '--port', "$ApiPort") `
        -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $RunDir 'backend.log') `
        -RedirectStandardError (Join-Path $RunDir 'backend.err.log')
    Set-Content -Path (Join-Path $RunDir 'backend.pid') -Value $p.Id
    if (-not (Test-Health $apiHealth 90)) {
        Fail "Backend did not come up. See logs: run\backend.err.log"
    }
}
Write-Host "Backend is up:  http://127.0.0.1:$ApiPort" -ForegroundColor Green

# ---------------------------------------------------------------- web UI
$webUrl    = "http://localhost:$WebPort"
$webHealth = "http://127.0.0.1:$WebPort"
$frontUp = Test-Health $webHealth 1
if (-not $frontUp) {
    Write-Host "Starting the web UI (port $WebPort)..."
    if (Test-Path $standalone) {
        # Next.js standalone server: port/host come from the environment; bound to loopback only (the UI has no login)
        $env:PORT = "$WebPort"
        $env:HOSTNAME = '127.0.0.1'
        $env:NODE_ENV = 'production'
        $env:NEXT_TELEMETRY_DISABLED = '1'
        $p = Start-Process -FilePath 'node' -ArgumentList @($standalone) `
            -WorkingDirectory (Join-Path $Root 'frontend-standalone') -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $RunDir 'frontend.log') `
            -RedirectStandardError (Join-Path $RunDir 'frontend.err.log')
    } else {
        $p = Start-Process -FilePath 'node' `
            -ArgumentList @($nextBin, 'start', '-p', "$WebPort") `
            -WorkingDirectory (Join-Path $Root 'frontend') -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $RunDir 'frontend.log') `
            -RedirectStandardError (Join-Path $RunDir 'frontend.err.log')
    }
    Set-Content -Path (Join-Path $RunDir 'frontend.pid') -Value $p.Id
    if (-not (Test-Health $webHealth 60)) {
        Fail "Web UI did not come up. See logs: run\frontend.err.log"
    }
}
Write-Host "Web UI is up:   $webUrl" -ForegroundColor Green

if (-not $NoBrowser) { Start-Process $webUrl }
Write-Host ""
Write-Host "SEO Brain is running. Close it later with STOP.bat." -ForegroundColor Yellow
exit 0
