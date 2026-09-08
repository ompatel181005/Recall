<#
.SYNOPSIS
    Start Recall and open it in its own window.

.DESCRIPTION
    Runs the whole app as one process: the backend serves the built frontend, so
    there is no separate dev server. The UI opens in a Chrome app window — its
    own taskbar entry, no tabs or address bar — which keeps every browser
    capability the app depends on, including microphone and tab-audio capture.

    The window is given its own Chrome profile. That is not cosmetic: launching
    Chrome while it is already running otherwise hands off to the existing
    process and exits immediately, which would make this script think the app
    had been closed the moment it opened.

.PARAMETER Stop
    Stop a running Recall backend and exit.

.PARAMETER NoWindow
    Start the backend but do not open the UI.
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$NoWindow
)

$ErrorActionPreference = 'Stop'

$Root       = Split-Path -Parent $PSScriptRoot
$Python     = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$Dist       = Join-Path $Root 'frontend\dist'
$Port       = 8000
$BaseUrl    = "http://127.0.0.1:$Port"
$ProfileDir = Join-Path $env:LOCALAPPDATA 'Recall\chrome-profile'

function Test-Backend {
    try {
        $null = Invoke-RestMethod "$BaseUrl/api/health" -TimeoutSec 3
        return $true
    } catch {
        return $false
    }
}

function Get-BackendProcess {
    # The uvicorn process is identified by its command line rather than a pid
    # file, so a backend left over from a previous launch is still found.
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*uvicorn*app.main:app*' }
}

function Stop-Backend {
    foreach ($proc in Get-BackendProcess) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if ($Stop) {
    if (Test-Backend) {
        Stop-Backend
        Write-Host 'Recall stopped.'
    } else {
        Write-Host 'Recall was not running.'
    }
    return
}

# ---------------------------------------------------------------- prerequisites
if (-not (Test-Path $Python)) {
    Write-Warning "Recall is not set up yet — $Python is missing."
    Write-Host    'Run this once, from the repo root:'
    Write-Host    '    cd backend; python -m venv .venv; .venv\Scripts\pip install -e .'
    Write-Host    '    cd ..\frontend; npm install'
    Read-Host 'Press Enter to close'
    return
}

# ------------------------------------------------------------------- frontend
# The backend serves frontend/dist, so it has to exist and not be stale.
$needsBuild = -not (Test-Path (Join-Path $Dist 'index.html'))
if (-not $needsBuild) {
    $sources = Get-ChildItem (Join-Path $Root 'frontend\src') -Recurse -File -ErrorAction SilentlyContinue
    $sources += Get-ChildItem (Join-Path $Root 'frontend') -File -Filter '*.ts' -ErrorAction SilentlyContinue
    $sources += Get-ChildItem (Join-Path $Root 'frontend') -File -Filter 'index.html' -ErrorAction SilentlyContinue
    if ($sources) {
        $newestSource = ($sources | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
        $built = (Get-Item (Join-Path $Dist 'index.html')).LastWriteTime
        if ($newestSource -gt $built) { $needsBuild = $true }
    }
}

if ($needsBuild) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host 'Building the interface (first run, or sources changed)...'
        Push-Location (Join-Path $Root 'frontend')
        try { & npm run build | Out-Null } finally { Pop-Location }
    } elseif (-not (Test-Path (Join-Path $Dist 'index.html'))) {
        Write-Warning 'The interface is not built and npm was not found. Install Node, then run: cd frontend; npm run build'
        Read-Host 'Press Enter to close'
        return
    }
}

# --------------------------------------------------------------------- ollama
# Best effort. The tutor and the search index use it; notes may be routed to a
# cloud model instead, so a missing Ollama is not fatal.
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if ((Test-Path $ollama) -and -not (Get-Process 'ollama' -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
}

# -------------------------------------------------------------------- backend
$startedBackend = $false
if (Test-Backend) {
    Write-Host 'Recall is already running — opening the window.'
} else {
    Stop-Backend   # clear a half-dead process holding the port
    Start-Process -FilePath $Python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port" `
        -WorkingDirectory (Join-Path $Root 'backend') -WindowStyle Hidden
    $startedBackend = $true

    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Backend)) {
        if ((Get-Date) -gt $deadline) {
            Write-Warning "The backend did not start within 90 seconds. Run it by hand to see why:"
            Write-Host    "    cd backend; .venv\Scripts\python -m uvicorn app.main:app --port $Port"
            Read-Host 'Press Enter to close'
            return
        }
        Start-Sleep -Milliseconds 400
    }
}

if ($NoWindow) {
    Write-Host "Recall is running at $BaseUrl"
    return
}

# --------------------------------------------------------------------- window
$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) {
    # No Chrome: fall back to whatever handles http. Recording still works, it
    # just opens as an ordinary tab.
    Start-Process $BaseUrl
    Write-Host "Recall is running at $BaseUrl"
    return
}

$window = Start-Process -FilePath $chrome -PassThru -ArgumentList @(
    "--app=$BaseUrl",
    "--user-data-dir=$ProfileDir",
    '--no-first-run',
    '--no-default-browser-check'
)

Wait-Process -Id $window.Id

# ------------------------------------------------------------------- shutdown
# Only tidy up what this launcher started, and never while work is in flight:
# job state lives in memory, so killing the backend mid-transcription would
# throw away the recording's transcript.
if (-not $startedBackend) { return }

$waited = 0
while ($waited -lt 3600) {
    try { $health = Invoke-RestMethod "$BaseUrl/api/health" -TimeoutSec 3 } catch { break }
    if (-not $health.busy) { break }
    if ($waited -eq 0) { Write-Host 'Finishing transcription before shutting down...' }
    Start-Sleep -Seconds 5
    $waited += 5
}

Stop-Backend
