# start.ps1 - Manual Start (Development) - Windows PowerShell
# Starts frontend, backend, and QVAC service in separate windows.
#
# Usage:
#   .\start.ps1        - start all services
#   .\start.ps1 -Setup - run first-time setup before starting
#
# Requirements: Node.js >= 22, Python 3.11, uv (https://astral.sh/uv)
# Run in PowerShell (not cmd). If you hit execution-policy errors:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
# Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less UTF-8 as
# the ANSI code page, and non-ASCII characters break parsing.

param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
# Force UTF-8 for Python: the Windows default code page (cp1252) breaks file reads.
$env:PYTHONUTF8 = 1
$Root = $PSScriptRoot

function Write-Step { param($msg) Write-Host "[start] $msg" -ForegroundColor Cyan }
function Write-Err  { param($msg) Write-Host "[start] ERROR: $msg" -ForegroundColor Red }

# -- prerequisites -------------------------------------------------------------

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Err "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js not found. Install from https://nodejs.org (>= 22)"
    exit 1
}

# -- optional first-time setup -------------------------------------------------

if ($Setup) {
    Write-Step "Running backend setup..."
    Push-Location "$Root\services\ai"
    uv sync
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Step ".env created from .env.example"
        }
    }
    uv run python -m app.db.init_db
    Pop-Location

    foreach ($dir in @("$Root\apps\web", "$Root\workers\qvac-service")) {
        if (-not (Test-Path "$dir\node_modules")) {
            Write-Step "npm install in $dir..."
            Push-Location $dir
            npm install
            Pop-Location
        }
    }
    Write-Step "Setup complete."
}

# -- kill stale processes on service ports -------------------------------------

function Stop-Port {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Step "Port $Port - killed stale process $($c.OwningProcess)"
        } catch {}
    }
    if ($conns) { Start-Sleep -Seconds 1 }
}

Stop-Port 3000
Stop-Port 8000
Stop-Port 3001

# -- create log directory ------------------------------------------------------

# QVAC and the backend must share one ingest directory. Without this, QVAC
# falls back to /qvac_ingest (the Docker path) and every dense-index ingest fails.
if (-not $env:QVAC_INGEST_DIR) { $env:QVAC_INGEST_DIR = "$Root\services\ai\qvac_ingest" }
New-Item -ItemType Directory -Force -Path $env:QVAC_INGEST_DIR | Out-Null

$LogDir = "$Root\.logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# -- start services in separate PowerShell windows -----------------------------

$cmdWeb = "cd \`"$Root\apps\web\`"; npm run dev *> \`"$LogDir\frontend.log\`"; Read-Host 'Press Enter to close'"
Write-Step "Starting frontend -> http://localhost:3000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdWeb

$cmdApi = "cd \`"$Root\services\ai\`"; uv run uvicorn app.main:app --reload --port 8000 *> \`"$LogDir\backend.log\`"; Read-Host 'Press Enter to close'"
Write-Step "Starting backend -> http://localhost:8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdApi

$cmdQvac = "cd \`"$Root\workers\qvac-service\`"; node src/server.js *> \`"$LogDir\qvac.log\`"; Read-Host 'Press Enter to close'"
Write-Step "Starting QVAC -> http://localhost:3001"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdQvac

# -- start arq worker (optional) -----------------------------------------------

$RedisUrl = $env:REDIS_URL
if ([string]::IsNullOrWhiteSpace($RedisUrl) -and (Test-Path "$Root\services\ai\.env")) {
    $redisLine = Get-Content "$Root\services\ai\.env" | Where-Object { $_ -match '^\s*REDIS_URL\s*=' } | Select-Object -Last 1
    if ($redisLine) {
        $RedisUrl = ($redisLine -replace '^\s*REDIS_URL\s*=\s*', '' -replace '\s+#.*$', '').Trim().Trim('"', "'")
    }
}

if (-not [string]::IsNullOrWhiteSpace($RedisUrl)) {
    $cmdArq = "cd \`"$Root\services\ai\`"; uv run arq app.workers.arq_worker.WorkerSettings *> \`"$LogDir\arq.log\`"; Read-Host 'Press Enter to close'"
    Write-Step "Starting ARQ worker -> Redis queue (REDIS_URL is set)"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdArq
}

Write-Host ""
Write-Host "  Bitcoin Academy - development" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend -> http://localhost:3000"
Write-Host "  Backend  -> http://localhost:8000 (Swagger: /docs)"
Write-Host "  QVAC     -> http://localhost:3001"
if ($RedisUrl) { Write-Host "  ARQ      -> Active (Redis queue)" }
Write-Host ""
Write-Host "  Tail logs: Get-Content .logs\backend.log -Wait"
Write-Host "             Get-Content .logs\frontend.log -Wait"
Write-Host "             Get-Content .logs\qvac.log -Wait"
if ($RedisUrl) { Write-Host "             Get-Content .logs\arq.log -Wait" }
Write-Host ""
Write-Host "  Close the PowerShell windows to stop all services."
