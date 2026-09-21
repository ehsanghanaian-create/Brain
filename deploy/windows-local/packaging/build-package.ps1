# Build the OFFLINE Windows installer from the committed tree (git HEAD):
#
#   <OutRoot>\SEO-Brain-Setup-<version>.exe      single-file wizard (stub + ZIP payload, see Setup.cs)
#   <OutRoot>\SEO-Brain-Portable-<version>.zip   same files as a plain ZIP (unpack + INSTALL.bat) - fallback when an
#                                                antivirus / SmartScreen policy refuses unsigned EXEs
#
# Everything the target machine needs is inside: portable Node.js, the official Python installer, every backend wheel
# (per bundled CPython version), the prebuilt Next.js standalone web UI and (optionally) a starter database.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows-local\packaging\build-package.ps1
#   ... -NoSeed                      ship without your data (clean package for someone else)
#   ... -RuntimeDir D:\somewhere     folder holding node-v*-win-x64.zip and python-3.*-amd64.exe
param(
    [string]$OutRoot = 'D:\seo-brain-dist',
    [string]$RuntimeDir = '',
    [string]$SeedFrom = '',
    [switch]$NoSeed,
    [string[]]$PythonVersions = @('3.12', '3.13'),
    [string]$Version = (Get-Date -Format 'yyyyMMdd'),
    [switch]$StubOnly,         # only recompile Setup.cs and re-attach the existing <stage>\payload.zip (seconds instead of minutes)
    [switch]$RepackOnly        # installer scripts / README changed: refresh them in the existing stage and re-create payload, portable ZIP and Setup.exe (~3 min)
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not $RuntimeDir) { $RuntimeDir = Join-Path $OutRoot 'runtime' }
if (-not $SeedFrom)   { $SeedFrom = Join-Path $Repo 'data' }
$Stage = Join-Path $OutRoot "build-$Version"
$Pkg   = Join-Path $Stage 'SEO-Brain'
$Py    = Join-Path $Repo '.venv\Scripts\python.exe'
$SevenZip = 'C:\Program Files\7-Zip\7z.exe'
$Csc   = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" } }
function Robo($src, $dst) { & robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null; if ($LASTEXITCODE -ge 8) { throw "robocopy $src -> $dst failed ($LASTEXITCODE)" }; $global:LASTEXITCODE = 0 }

function New-SetupExe {
    Step "Setup.exe (stub + payload)"
    $stub = Join-Path $Stage 'stub.exe'
    $cscArgs = @('/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/codepage:65001', "/win32manifest:$PSScriptRoot\app.manifest",
                 '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll',
                 "/out:$stub", (Join-Path $PSScriptRoot 'Setup.cs'))
    $icoOut = Join-Path $Pkg 'installer\seo-brain.ico'
    if (Test-Path $icoOut) { $cscArgs = @("/win32icon:$icoOut") + $cscArgs }
    & $Csc @cscArgs; Check 'csc'
    $out = [IO.File]::Create($exe)
    try {
        foreach ($part in @($stub, $payload)) { $in = [IO.File]::OpenRead($part); try { $in.CopyTo($out) } finally { $in.Close() } }
        $out.Write([BitConverter]::GetBytes([int64](Get-Item $payload).Length), 0, 8)
        $magic = [Text.Encoding]::ASCII.GetBytes('SBSETUP1'); $out.Write($magic, 0, 8)
    } finally { $out.Close() }
}

foreach ($need in @($Py, $SevenZip, $Csc)) { if (-not (Test-Path $need)) { throw "missing build tool: $need" } }
$nodeZip = Get-ChildItem $RuntimeDir -Filter 'node-*-win-x64.zip' | Select-Object -First 1
$pyExe   = Get-ChildItem $RuntimeDir -Filter 'python-3.*-amd64.exe' | Select-Object -First 1
if (-not $nodeZip -or -not $pyExe) { throw "put node-v*-win-x64.zip and python-3.*-amd64.exe into $RuntimeDir" }

$payload = Join-Path $Stage 'payload.zip'
$exe = Join-Path $OutRoot "SEO-Brain-Setup-$Version.exe"
if ($StubOnly) {
    if (-not (Test-Path $payload)) { throw "no $payload - run a full build first" }
    New-SetupExe
    Write-Host ("    {0}  {1:N1} MB  sha256={2}" -f $exe, ((Get-Item $exe).Length / 1MB), (Get-FileHash $exe -Algorithm SHA256).Hash)
    exit 0
}

# keep temp files off a (small) system drive
$tmp = Join-Path $OutRoot 'tmp'; New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp; $env:TMP = $tmp
$pipCache = Join-Path $OutRoot 'pip-cache'

$commit = (& git -C $Repo rev-parse --short HEAD).Trim()
if ($RepackOnly) {
    if (-not (Test-Path (Join-Path $Pkg 'frontend-standalone\server.js'))) { throw "no staged package at $Pkg - run a full build first" }
    Step "Repack: refreshing installer scripts in the existing stage ($Pkg)"
} else {
    Step "Staging the committed tree (git HEAD) -> $Pkg"
    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force $Pkg | Out-Null
    & git -C $Repo archive --format=zip -o (Join-Path $Stage 'src.zip') HEAD; Check 'git archive'
    & tar -xf (Join-Path $Stage 'src.zip') -C $Pkg; Check 'extract source'
    Remove-Item (Join-Path $Stage 'src.zip') -Force
    foreach ($drop in @('backend\tests', '.github', '.claude', 'docker-compose.yml', 'start-docker.bat', 'start.bat', 'obsidian', 'tokens', '.gitignore', '.gitattributes', '.dockerignore')) {
        $p = Join-Path $Pkg $drop; if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
}
Robo (Join-Path $Repo 'deploy\windows-local\installer') (Join-Path $Pkg 'installer')
foreach ($f in @('INSTALL.bat', 'START.bat', 'STOP.bat', 'UNINSTALL.bat', 'README-FA.md')) { Copy-Item (Join-Path $Repo "deploy\windows-local\$f") (Join-Path $Pkg $f) -Force }
$ico = Join-Path $Pkg 'frontend\src\app\favicon.ico'
if (Test-Path $ico) { Copy-Item $ico (Join-Path $Pkg 'installer\seo-brain.ico') -Force }
Set-Content -Path (Join-Path $Pkg 'VERSION.txt') -Value @("$Version ($commit)", "built $(Get-Date -Format 'yyyy-MM-dd HH:mm')") -Encoding ascii

if (-not $RepackOnly) {
Step "Runtimes: $($nodeZip.Name) + $($pyExe.Name)"
New-Item -ItemType Directory -Force (Join-Path $Pkg 'runtime') | Out-Null
Copy-Item $nodeZip.FullName (Join-Path $Pkg 'runtime') -Force
Copy-Item $pyExe.FullName (Join-Path $Pkg 'runtime') -Force

Step "Backend wheels for CPython $($PythonVersions -join ', ') (win_amd64)"
$wheels = Join-Path $Pkg 'runtime\wheels'; New-Item -ItemType Directory -Force $wheels | Out-Null
& $Py -m pip wheel --quiet --disable-pip-version-check --no-deps --cache-dir $pipCache -w $wheels (Join-Path $Pkg 'backend'); Check 'pip wheel backend'
$appWheel = (Get-ChildItem $wheels -Filter 'seo_brain-*.whl' | Select-Object -First 1).FullName
foreach ($v in $PythonVersions) {
    $abi = 'cp' + $v.Replace('.', '')
    $target = @('--only-binary=:all:', '--platform', 'win_amd64', '--implementation', 'cp', '--python-version', $v, '--abi', $abi, '--abi', 'abi3', '--abi', 'none')
    & $Py -m pip download --quiet --disable-pip-version-check --cache-dir $pipCache --dest $wheels @target $appWheel; Check "pip download ($v)"
    # prove the offline set is complete for this interpreter
    $dry = Join-Path $Stage "dry-$abi"
    & $Py -m pip install --quiet --disable-pip-version-check --dry-run --ignore-installed --no-index --find-links $wheels @target --target $dry seo-brain; Check "offline resolution check ($v)"
    if (Test-Path $dry) { Remove-Item $dry -Recurse -Force }
}
Write-Host ("    {0} wheels, {1:N1} MB" -f @(Get-ChildItem $wheels -Filter *.whl).Count, ((Get-ChildItem $wheels | Measure-Object Length -Sum).Sum / 1MB))

Step "Web UI: Next.js standalone production build (no .env.local -> nothing machine-specific is baked in)"
$fe = Join-Path $Stage 'frontend-src'
Move-Item (Join-Path $Pkg 'frontend') $fe
Push-Location $fe
try {
    $env:CI = 'true'; $env:NEXT_TELEMETRY_DISABLED = '1'
    & corepack pnpm install --frozen-lockfile; Check 'pnpm install'
    $env:BUILD_STANDALONE = 'true'
    & corepack pnpm build; Check 'next build'
} finally { Pop-Location; Remove-Item Env:\BUILD_STANDALONE -ErrorAction SilentlyContinue }
$sa = Join-Path $Pkg 'frontend-standalone'
Robo (Join-Path $fe '.next\standalone') $sa
Robo (Join-Path $fe '.next\static') (Join-Path $sa '.next\static')
if (Test-Path (Join-Path $fe 'public')) { Robo (Join-Path $fe 'public') (Join-Path $sa 'public') }
if (-not (Test-Path (Join-Path $sa 'server.js'))) { throw 'standalone build has no server.js at its root (nested output?)' }
Get-ChildItem $sa -Filter '.env*' -Force -ErrorAction SilentlyContinue | Remove-Item -Force

if (-not $NoSeed) {
    Step "Starter data: consistent snapshots of $SeedFrom\*.db"
    $seed = Join-Path $Pkg 'seed'; New-Item -ItemType Directory -Force $seed | Out-Null
    foreach ($db in @('seo.db', 'ads-events.db')) {
        $src = Join-Path $SeedFrom $db
        if (Test-Path $src) {
            & $Py -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('VACUUM INTO ?', (sys.argv[2],)); c.close()" $src (Join-Path $seed $db); Check "snapshot $db"
        }
    }
    # API keys live in the machine-bound SecretStore and are NOT shipped: drop the dangling references and the stale
    # test/health state so the target machine starts with a clean "paste your key -> connected" experience
    $seedMain = Join-Path $seed 'seo.db'
    if (Test-Path $seedMain) {
        & $Py -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE ai_providers SET secret_ref=NULL, key_hint=NULL, key_set_at=NULL, key_expires_at=NULL, last_test=NULL'); c.execute('DELETE FROM ai_provider_health'); c.commit(); c.execute('VACUUM'); c.close()" $seedMain; Check 'sanitize seed'
    }
}
}   # end of the full-build-only steps (-RepackOnly skips runtimes, wheels, web UI build and seed)

Step "Longest path inside the package"
$longest = Get-ChildItem $Pkg -Recurse -File | ForEach-Object { $_.FullName.Substring($Pkg.Length + 1) } | Sort-Object Length -Descending | Select-Object -First 1
Write-Host "    $($longest.Length) chars: $longest"
if ($longest.Length -gt 200) { Write-Host '    WARNING: > 200 chars - installs into deep folders may hit the 260-char limit' -ForegroundColor Yellow }

Step "Payload ZIP + portable ZIP"
if (Test-Path -LiteralPath $payload) { [IO.File]::Delete($payload) }      # never update an old archive in place: removed files would survive
& $SevenZip a -tzip -mx=5 -bso0 -bsp0 $payload (Join-Path $Pkg '*'); Check '7z payload'
$portable = Join-Path $OutRoot "SEO-Brain-Portable-$Version.zip"
if (Test-Path $portable) { Remove-Item $portable -Force }
& $SevenZip a -tzip -mx=5 -bso0 -bsp0 $portable $Pkg; Check '7z portable'

New-SetupExe

Step "Done"
foreach ($f in @($exe, $portable)) {
    $h = (Get-FileHash $f -Algorithm SHA256).Hash
    Write-Host ("    {0}  {1:N1} MB  sha256={2}" -f $f, ((Get-Item $f).Length / 1MB), $h)
}
Write-Host "    staged tree kept at $Pkg (delete $Stage when no longer needed)"
