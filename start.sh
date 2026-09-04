#!/usr/bin/env bash
# Manual Start (Development)
# Starts frontend, backend, and QVAC service in parallel.
#
# Usage:
#   ./start.sh            — start all services
#   ./start.sh --setup    — run setup-dev.sh before starting (first run, or after dep changes)

set -uo pipefail

# Ensure uv and other user-local binaries are on PATH (not sourced in non-interactive bash).
# shellcheck source=/dev/null
[[ -s "$HOME/.local/bin/env" ]] && source "$HOME/.local/bin/env"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

# ── helpers ──────────────────────────────────────────────────────────────────

log() { printf '\033[1;34m[start]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[start]\033[0m ERROR: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

load_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck source=/dev/null
    [[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh"
    command -v node &>/dev/null || die "Node.js not found. Install via: nvm install 22 && nvm alias default 22"
}

# ── args ─────────────────────────────────────────────────────────────────────

RUN_SETUP=false
for arg in "$@"; do
    case "$arg" in
        --setup) RUN_SETUP=true ;;
        *) die "Unknown argument: $arg\nUsage: ./start.sh [--setup]" ;;
    esac
done

# ── prerequisites ─────────────────────────────────────────────────────────────

command -v uv &>/dev/null || die "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
load_nvm

# ── npm install helper (only runs when node_modules is missing) ───────────────

npm_install_if_needed() {
    local dir="$1"
    if [[ ! -d "$dir/node_modules" ]]; then
        log "node_modules missing in $dir — running npm install..."
        (cd "$dir" && npm install) || die "npm install failed in $dir"
    fi
}

# ── optional backend setup (first run) ───────────────────────────────────────

if $RUN_SETUP; then
    log "Running backend setup (setup-dev.sh)..."
    (cd "$ROOT/services/ai" && bash setup-dev.sh) || die "setup-dev.sh failed."
    log "Setup complete."
    npm_install_if_needed "$ROOT/apps/web"
    npm_install_if_needed "$ROOT/workers/qvac-service"
fi

# ── kill stale processes on service ports (leftover from previous runs) ──────

kill_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti :"$port" -n -P 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        log "Port $port in use — killing stale process(es): $pids"
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
    fi
}

kill_port 3000   # frontend
kill_port 8000   # backend
kill_port 3001   # QVAC

# ── cleanup on exit ───────────────────────────────────────────────────────────

PIDS=()

cleanup() {
    echo ""
    log "Shutting down all services..."
    for pid in "${PIDS[@]:-}"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    log "All services stopped."
}
trap cleanup EXIT INT TERM

# ── 1. frontend ───────────────────────────────────────────────────────────────

log "Starting frontend  → http://localhost:3000  (log: .logs/frontend.log)"
(
    cd "$ROOT/apps/web"
    exec npm run dev
) > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)

# ── 2. backend ────────────────────────────────────────────────────────────────

log "Starting backend   → http://localhost:8000  (log: .logs/backend.log)"
(
    cd "$ROOT/services/ai"
    exec uv run --no-sync uvicorn app.main:app --reload --port 8000
) > "$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)

# ── 3. QVAC service ───────────────────────────────────────────────────────────

log "Starting QVAC      → http://localhost:3001  (log: .logs/qvac.log)"
(
    cd "$ROOT/workers/qvac-service"
    exec node src/server.js
) > "$LOG_DIR/qvac.log" 2>&1 &
PIDS+=($!)

# ── summary ───────────────────────────────────────────────────────────────────

echo ""
echo "  Bitcoin Academy — development"
echo ""
echo "  Frontend  →  http://localhost:3000"
echo "  Backend   →  http://localhost:8000   (Swagger: /docs)"
echo "  QVAC      →  http://localhost:3001"
echo ""
echo "  Tail logs:  tail -f .logs/backend.log"
echo "              tail -f .logs/frontend.log"
echo "              tail -f .logs/qvac.log"
echo ""
echo "  Press Ctrl+C to stop all services."
echo ""

# keep script alive so trap fires on Ctrl+C
wait
