# SEO Brain - Windows local installer (idempotent: safe to re-run for updates).
# Fully self-contained: uses the BUNDLED Node.js runtime (runtime\node-*.zip) and,
# if no suitable Python exists, silently installs the BUNDLED official Python
# (per-user, no admin needed). Then: venv + backend, seed DB, npm install/build,
# Desktop shortcut.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $Root

function Fail($msg) { Write-Host "`n[X] $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }

Write-Host "SEO Brain - local install" -ForegroundColor Yellow
Write-Host "Folder: $Root"

# ---------------------------------------------------------------- bundled Node.js (portable, no install)
Step "Preparing Node.js (bundled)"
$nodeDir = $null
$nodeZip = Get-ChildItem (Join-Path $Root 'runtime') -Filter 'node-*-win-x64.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($nodeZip) {
    $extracted = Join-Path $Root ('runtime\' + $nodeZip.BaseName)
    if (-not (Test-Path (Join-Path $extracted 'node.exe'))) {
        Write-Host "    extracting $($nodeZip.Name)..."
        Expand-Archive -Path $nodeZip.FullName -DestinationPath (Join-Path $Root 'runtime') -Force
    }
    if (Test-Path (Join-Path $extracted 'node.exe')) { $nodeDir = $extracted }
}
if ($nodeDir) {
    $env:Path = "$nodeDir;$env:Path"
    Ok "Bundled Node: $(& node --version)"
} else {
    try { $nv = & node --version 2>$null } catch { $nv = $null }
    if ($nv -and $nv -match '^v(\d+)' -and [int]$Matches[1] -ge 18) { Ok "System Node: $nv" }
    else { Fail "No bundled runtime\node-*.zip and no system Node.js 18+. Re-download the full package." }
}

# ---------------------------------------------------------------- Python 3.11 - 3.13 (auto-install bundled if missing)
function Find-Python {
    foreach ($ver in @('3.13', '3.12', '3.11')) {
        try {
            $exe = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    foreach ($cand in @("$env:LocalAppData\Programs\Python\Python313\python.exe",
                        "$env:LocalAppData\Programs\Python\Python312\python.exe",
                        "$env:LocalAppData\Programs\Python\Python311\python.exe")) {
        if (Test-Path $cand) { return $cand }
    }
    try {
        $out = @(& python -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $out.Length -ge 2 -and $out[0] -match '^3\.(11|12|13)$') { return $out[1].Trim() }
    } catch {}
    return $null
}

Step "Looking for Python 3.11 - 3.13"
$python = Find-Python
if (-not $python) {
    $pyExe = Get-ChildItem (Join-Path $Root 'runtime') -Filter 'python-3.*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyExe) {
        Step "Installing the bundled Python silently (per-user, ~2 minutes, no admin needed)"
        $p = Start-Process -FilePath $pyExe.FullName -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_test=0','SimpleInstall=1' -Wait -PassThru
        if ($p.ExitCode -ne 0) { Fail "Python installer exited with code $($p.ExitCode)" }
        $python = Find-Python
    }
}
if (-not $python) {
    Fail "Python 3.11 - 3.13 not found and auto-install failed. Install it manually from python.org (3.12 recommended, NOT 3.14) and re-run INSTALL.bat."
}
Ok "Python: $python"

# ---------------------------------------------------------------- backend venv
Step "Creating the Python environment (.venv)"
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    & $python -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Fail "Could not create .venv" }
}
Ok ".venv ready"

Step "Installing the backend (a few minutes on first run)"
& $venvPy -m pip install --quiet --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed" }
& $venvPy -m pip install --quiet (Join-Path $Root 'backend')
if ($LASTEXITCODE -ne 0) { Fail "Backend install failed (see messages above)" }
Ok "Backend installed"

# ---------------------------------------------------------------- seed data (optional)
$seedDb = Join-Path $Root 'seed\seo.db'
$dataDb = Join-Path $Root 'data\seo.db'
if ((Test-Path $seedDb) -and -not (Test-Path $dataDb)) {
    Step "Copying the starter database (your sites and SEO data)"
    New-Item -ItemType Directory -Force (Join-Path $Root 'data') | Out-Null
    Copy-Item $seedDb $dataDb
    $seedAds = Join-Path $Root 'seed\ads-events.db'
    if (Test-Path $seedAds) { Copy-Item $seedAds (Join-Path $Root 'data\ads-events.db') }
    Ok "Database seeded"
}

Step "Preparing folders, .env and the database schema"
$env:SEO_KG_ROOT = $Root
& $venvPy (Join-Path $Root 'backend\cli\setup.py') --env --db --vault
if ($LASTEXITCODE -ne 0) { Fail "Database setup failed" }
Ok "Database ready"

# ---------------------------------------------------------------- frontend
Step "Installing web UI packages (npm - several minutes on first run)"
Push-Location (Join-Path $Root 'frontend')
try {
    & npm install --no-audit --no-fund --loglevel=error
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed" }
    Ok "Packages installed"

    Step "Building the web UI (a few minutes)"
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail "Web UI build failed" }
    Ok "Web UI built"
} finally { Pop-Location }

# ---------------------------------------------------------------- desktop shortcut
Step "Creating the Desktop shortcut"
try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path $desktop 'SEO Brain.lnk'))
    $lnk.TargetPath = Join-Path $Root 'START.bat'
    $lnk.WorkingDirectory = $Root
    $lnk.Description = 'Start SEO Brain (local)'
    $lnk.Save()
    Ok "Shortcut created: Desktop\SEO Brain"
} catch { Write-Host "    (Could not create the shortcut - use START.bat directly)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " Install finished successfully." -ForegroundColor Green
Write-Host " Start with START.bat (or the Desktop shortcut)." -ForegroundColor Green
Write-Host " It opens http://localhost:3000 in your browser." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
exit 0
