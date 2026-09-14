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
    # Killing is not instant: a process holding a GPU context can keep the port
    # for a while, and a new backend started before then fails to bind.
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) -and
           (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 300
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
# One launcher at a time: a second click would otherwise stop the first
# launcher's still-booting backend and start its own.
$mutex = New-Object System.Threading.Mutex($false, 'Local\RecallLauncher')
try { $owned = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { return }

$startedBackend = $false

# A generous timeout: under memory pressure health can take several seconds, and
# treating a slow backend as dead would kill it mid-transcription below.
$running = $false
try { $health = Invoke-RestMethod "$BaseUrl/api/health" -TimeoutSec 15; $running = $true } catch {}

# A backend left running from before a code update keeps serving the old API.
# Restart it when the code on disk is newer, unless it is busy.
if ($running -and -not $health.busy) {
    $proc = Get-BackendProcess | Sort-Object CreationDate | Select-Object -First 1
    $code = @(Get-ChildItem (Join-Path $Root 'backend\app') -Recurse -Filter '*.py') +
            @(Get-Item (Join-Path $Root 'config.yaml'))
    $newest = ($code | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    if ($proc -and $newest -gt $proc.CreationDate) {
        Write-Host 'Code changed since the backend started — restarting it.'
        Stop-Backend
        Start-Sleep -Seconds 1
        $running = $false
    }
}

if ($running) {
    Write-Host 'Recall is already running — opening the window.'
} else {
    Stop-Backend   # clear a half-dead process holding the port

    # A backend stuck in the GPU driver cannot be killed and keeps the port.
    # Only a Windows restart clears that, so say so instead of a bind error.
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Port $Port is still held by an earlier Recall backend that could not be stopped. " +
            "This usually means the GPU driver is stuck. Restart Windows, then open Recall again.",
            'Recall', 'OK', 'Error') | Out-Null
        return
    }

    $logDir = Join-Path $env:LOCALAPPDATA 'Recall'
    New-Item -ItemType Directory -Force $logDir | Out-Null
    $log = Join-Path $logDir 'backend.log'
    $backend = Start-Process -FilePath $Python -PassThru `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port" `
        -WorkingDirectory (Join-Path $Root 'backend') -WindowStyle Hidden `
        -RedirectStandardError $log -RedirectStandardOutput (Join-Path $logDir 'backend.out.log')
    $startedBackend = $true

    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Backend)) {
        if ($backend.HasExited -or (Get-Date) -gt $deadline) {
            # The launcher window is minimised, so a console prompt would go
            # unseen. Show the actual error instead.
            $tail = (Get-Content $log -Tail 12 -ErrorAction SilentlyContinue) -join "`n"
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                "Recall's backend failed to start.`n`n$tail`n`nFull log: $log",
                'Recall', 'OK', 'Error') | Out-Null
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
