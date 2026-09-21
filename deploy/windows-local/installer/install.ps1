# SEO Brain - Windows local installer (idempotent: safe to re-run for updates).
# Fully self-contained and OFFLINE-capable:
#   * bundled portable Node.js                      (runtime\node-*.zip)
#   * bundled official Python, installed silently per-user if no suitable one exists (runtime\python-3.*.exe)
#   * bundled Python wheels for the backend          (runtime\wheels\*.whl  -> pip --no-index)
#   * prebuilt web UI                                (frontend-standalone\server.js -> no npm install / build)
# When a bundled piece is missing it falls back to the online path (pip / npm).
param([switch]$NoShortcut)
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

# ---------------------------------------------------------------- Python (auto-install bundled if missing)
# Offline wheels are built per CPython version: only accept a Python we have wheels for (else any 3.11 - 3.13).
$wheelDir = Join-Path $Root 'runtime\wheels'
$offline = (Test-Path $wheelDir) -and (@(Get-ChildItem $wheelDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count -gt 0)
$versions = @('3.13', '3.12', '3.11')
if ($offline) {
    $have = @()
    foreach ($v in @('3.12', '3.13', '3.11')) {
        $tag = 'cp' + $v.Replace('.', '')
        if (@(Get-ChildItem $wheelDir -Filter "*-$tag-*win_amd64.whl" -ErrorAction SilentlyContinue).Count -gt 0) { $have += $v }
    }
    if ($have.Count -gt 0) { $versions = $have }
}

function Find-Python {
    foreach ($ver in $versions) {
        try {
            $exe = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    foreach ($ver in $versions) {
        $cand = "$env:LocalAppData\Programs\Python\Python$($ver.Replace('.', ''))\python.exe"
        if (Test-Path $cand) { return $cand }
    }
    try {
        $out = @(& python -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $out.Length -ge 2 -and ($versions -contains $out[0])) { return $out[1].Trim() }
    } catch {}
    return $null
}

Step "Looking for Python ($($versions -join ' / '))"
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
    Fail "No suitable Python ($($versions -join ', ')) found and auto-install failed. Install Python 3.12 from python.org (NOT 3.14) and re-run INSTALL.bat."
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

Step "Installing the backend"
$installed = $false
if ($offline) {
    Write-Host "    offline install from runtime\wheels ..."
    & $venvPy -m pip install --quiet --disable-pip-version-check --no-index --find-links $wheelDir --upgrade --force-reinstall --no-deps seo-brain
    if ($LASTEXITCODE -eq 0) {
        & $venvPy -m pip install --quiet --disable-pip-version-check --no-index --find-links $wheelDir seo-brain
        if ($LASTEXITCODE -eq 0) { $installed = $true; Ok "Backend installed (offline)" }
    }
    if (-not $installed) { Write-Host "    offline install did not complete - falling back to the internet" -ForegroundColor Yellow }
}
if (-not $installed) {
    & $venvPy -m pip install --quiet --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (no internet?)" }
    $extra = @()
    if ($offline) { $extra = @('--find-links', $wheelDir) }
    & $venvPy -m pip install --quiet @extra (Join-Path $Root 'backend')
    if ($LASTEXITCODE -ne 0) { Fail "Backend install failed (see messages above)" }
    Ok "Backend installed (online)"
}

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

# The ads click events live in their own SQLite file. Point the backend at it, otherwise the seeded ads data (ads
# dashboard, ads IP graph) stays invisible because the API would read the empty table of the main database.
$envFile = Join-Path $Root '.env'
$adsDb = Join-Path $Root 'data\ads-events.db'
if ((Test-Path $envFile) -and (Test-Path $adsDb)) {
    $want = 'ADS_DATABASE_PATH=' + ($adsDb -replace '\\', '/')
    $lines = @(Get-Content $envFile -Encoding UTF8)
    $idx = -1
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^ADS_DATABASE_PATH=') { $idx = $i; break } }
    $current = ''
    if ($idx -ge 0) { $current = $lines[$idx].Substring('ADS_DATABASE_PATH='.Length).Trim() }
    if ($idx -lt 0) { $lines += $want }
    elseif (-not $current -or -not (Test-Path $current)) { $lines[$idx] = $want }
    [IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding $false))      # no BOM: python-dotenv reads the first key verbatim
    Ok "Ads events database: data\ads-events.db"
}

# ---------------------------------------------------------------- web UI
if (Test-Path (Join-Path $Root 'frontend-standalone\server.js')) {
    Step "Web UI"
    Ok "Prebuilt web UI found (frontend-standalone) - nothing to build"
} else {
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
}

# ---------------------------------------------------------------- shortcuts
if (-not $NoShortcut) {
    Step "Creating the Desktop and Start Menu shortcuts"
    try {
        $ws = New-Object -ComObject WScript.Shell
        $ico = Join-Path $Root 'installer\seo-brain.ico'
        foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
            $lnk = $ws.CreateShortcut((Join-Path $dir 'SEO Brain.lnk'))
            $lnk.TargetPath = Join-Path $Root 'START.bat'
            $lnk.WorkingDirectory = $Root
            $lnk.Description = 'Start SEO Brain (local)'
            if (Test-Path $ico) { $lnk.IconLocation = $ico }
            $lnk.Save()
        }
        Ok "Shortcuts created: Desktop + Start Menu (SEO Brain)"
    } catch { Write-Host "    (Could not create the shortcuts - use START.bat directly)" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " Install finished successfully." -ForegroundColor Green
Write-Host " Start with START.bat (or the Desktop shortcut)." -ForegroundColor Green
Write-Host " It opens http://localhost:3000 in your browser." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
exit 0
