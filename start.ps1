# start.ps1 — Manual Start (Development) — Windows PowerShell
# Starts frontend, backend, and QVAC service in separate windows.
#
# Usage:
#   .\start.ps1             — start all services
#   .\start.ps1 -Setup      — run first-time setup before starting
#
# Requirements: Node.js >= 22, Python 3.11, uv (https://astral.sh/uv)
# Run in PowerShell (not cmd). If you hit execution-policy errors:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Write-Step { param($msg) Write-Host "[start] $msg" -ForegroundColor Cyan }
function Write-Err  { param($msg) Write-Host "[start] ERROR: $msg" -ForegroundColor Red }

# ── prerequisites ─────────────────────────────────────────────────────────────

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Err "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js not found. Install from https://nodejs.org (>= 22)"
    exit 1
}

# ── optional first-time setup ─────────────────────────────────────────────────

if ($Setup) {
    Write-Step "Running backend setup..."
    Push-Location "$Root\services\ai"
    uv sync --locked --extra dev
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Step ".env created from .env.example"
        }
    }
    uv run --no-sync python -m app.db.init_db
    Pop-Location

    foreach ($dir in @("$Root\apps\web", "$Root\workers\qvac-service")) {
        if (-not (Test-Path "$dir\node_modules")) {
            Write-Step "npm install in $dir..."
            Push-Location $dir; npm install; Pop-Location
        }
    }
    Write-Step "Setup complete."
}

# ── kill stale processes on service ports ─────────────────────────────────────

function Stop-Port {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Step "Port $Port — killed stale process $($c.OwningProcess)"
        } catch {}
    }
    if ($conns) { Start-Sleep -Seconds 1 }
}

Stop-Port 3000
Stop-Port 8000
Stop-Port 3001

# ── create log directory ──────────────────────────────────────────────────────

$LogDir = "$Root\.logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ── start services in separate PowerShell windows ────────────────────────────

Write-Step "Starting frontend  → http://localhost:3000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$Root\apps\web'; npm run dev *> '$LogDir\frontend.log'; Read-Host 'Press Enter to close'"

Write-Step "Starting backend   → http://localhost:8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$Root\services\ai'; uv run --no-sync uvicorn app.main:app --reload --port 8000 *> '$LogDir\backend.log'; Read-Host 'Press Enter to close'"

Write-Step "Starting QVAC      → http://localhost:3001"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$Root\workers\qvac-service'; node src/server.js *> '$LogDir\qvac.log'; Read-Host 'Press Enter to close'"

Write-Host ""
Write-Host "  Bitcoin Academy — development" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend  ->  http://localhost:3000"
Write-Host "  Backend   ->  http://localhost:8000   (Swagger: /docs)"
Write-Host "  QVAC      ->  http://localhost:3001"
Write-Host ""
Write-Host "  Tail logs:  Get-Content .logs\backend.log  -Wait"
Write-Host "              Get-Content .logs\frontend.log -Wait"
Write-Host "              Get-Content .logs\qvac.log     -Wait"
Write-Host ""
Write-Host "  Close the three PowerShell windows to stop all services."
