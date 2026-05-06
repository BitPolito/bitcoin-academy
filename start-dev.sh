#!/bin/bash
# BitPolito Academy — Development Server Startup

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_DIR="$PROJECT_DIR/services/ai"
QVAC_DIR="$PROJECT_DIR/workers/qvac-service"
WEB_DIR="$PROJECT_DIR/apps/web"

# ── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
echo "  BitPolito Academy — dev"
echo "  ─────────────────────────────────────────"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────────────
command -v python3 &>/dev/null || die "Python 3 is not installed"
command -v node   &>/dev/null || die "Node.js is not installed"
command -v npm    &>/dev/null || die "npm is not installed"

NODE_MAJOR=$(node --version | sed 's/v//' | cut -d. -f1)
NODE_MINOR=$(node --version | sed 's/v//' | cut -d. -f2)
if [ "$NODE_MAJOR" -lt 22 ] || { [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -lt 17 ]; }; then
    die "Node.js 22.17+ required (found $(node --version))"
fi

# ── Python deps (uv preferred, pip fallback) ─────────────────────────────────
echo "  [1/3] Python dependencies"
cd "$AI_DIR"

if command -v uv &>/dev/null; then
    # uv sync: reads pyproject.toml + uv.lock, creates .venv, instant when cached
    uv sync --quiet
    PYTHON="$AI_DIR/.venv/bin/python"
    PIP_ACTIVATE() { source "$AI_DIR/.venv/bin/activate" 2>/dev/null || true; }
    ok "uv sync complete"
else
    warn "uv not found — using pip (install uv for faster startups: curl -LsSf https://astral.sh/uv/install.sh | sh)"
    # Create venv if missing
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source "venv/bin/activate" 2>/dev/null || source "venv/Scripts/activate" 2>/dev/null \
        || die "Cannot activate virtualenv"

    # Hash-check: skip pip install if requirements.txt unchanged
    HASH_FILE="venv/.requirements_hash"
    CURRENT_HASH=$(shasum -a 256 requirements.txt 2>/dev/null || sha256sum requirements.txt | cut -d' ' -f1)
    if [ ! -f "$HASH_FILE" ] || [ "$(cat "$HASH_FILE" 2>/dev/null)" != "$CURRENT_HASH" ]; then
        echo "  Installing Python packages..."
        pip install -q -r requirements.txt
        echo "$CURRENT_HASH" > "$HASH_FILE"
        ok "pip install complete"
    else
        ok "Python packages up to date (skipped)"
    fi
    PYTHON="python"
    PIP_ACTIVATE() { source "$AI_DIR/venv/bin/activate" 2>/dev/null || true; }
fi

# ── Node deps ─────────────────────────────────────────────────────────────────
echo "  [2/3] Node dependencies"

if [ ! -d "$QVAC_DIR/node_modules" ]; then
    echo "  Installing QVAC packages..."
    npm install --prefix "$QVAC_DIR" --silent
fi

if [ ! -d "$WEB_DIR/node_modules" ]; then
    echo "  Installing web packages..."
    npm install --prefix "$WEB_DIR" --silent
fi
ok "Node packages ready"

# ── Env files ─────────────────────────────────────────────────────────────────
if [ ! -f "$AI_DIR/.env" ] && [ -f "$AI_DIR/.env.example" ]; then
    cp "$AI_DIR/.env.example" "$AI_DIR/.env"
    warn "Created services/ai/.env from example — review before production"
fi
if [ ! -f "$WEB_DIR/.env.local" ] && [ -f "$WEB_DIR/.env.example" ]; then
    cp "$WEB_DIR/.env.example" "$WEB_DIR/.env.local"
    warn "Created apps/web/.env.local from example"
fi

# ── PostgreSQL check (skipped if using SQLite) ────────────────────────────────
_db_url() { grep -E '^DATABASE_URL=' "$AI_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'"; }
_pg_running() { nc -z localhost 5432 &>/dev/null 2>&1 || pg_isready -q 2>/dev/null; }

_DB_URL="$(_db_url)"
if echo "$_DB_URL" | grep -q "^sqlite"; then
    ok "Database: SQLite (no PostgreSQL needed)"
elif ! _pg_running; then
    warn "PostgreSQL not responding on :5432"
    # 1. Try Homebrew
    if command -v brew &>/dev/null; then
        brew services start postgresql   2>/dev/null || \
        brew services start postgresql@17 2>/dev/null || \
        brew services start postgresql@16 2>/dev/null || \
        brew services start postgresql@15 2>/dev/null || true
        sleep 3
    fi
    # 2. Try Docker (starts only the postgres container)
    if ! _pg_running && command -v docker &>/dev/null; then
        warn "Trying Docker postgres container..."
        docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres 2>/dev/null || true
        sleep 5
    fi
    if ! _pg_running; then
        die "PostgreSQL is not running. Options:\n  Set DATABASE_URL=sqlite:///./bitcoin_academy.db in services/ai/.env\n  brew install postgresql@17 && brew services start postgresql@17\n  docker compose up -d postgres"
    fi
    ok "PostgreSQL ready"
fi

# ── Redis (optional — enables ARQ task queue) ─────────────────────────────────
REDIS_PID=""
ARQ_PID=""
if command -v redis-server &>/dev/null; then
    if ! redis-cli ping &>/dev/null 2>&1; then
        redis-server --daemonize no --loglevel warning > "$PROJECT_DIR/redis.log" 2>&1 &
        REDIS_PID=$!
        sleep 1
        ok "Redis started (PID $REDIS_PID)"
    else
        ok "Redis already running"
    fi
else
    warn "redis-server not found — ARQ worker disabled (install: brew install redis)"
fi

# ── Start services ────────────────────────────────────────────────────────────
echo "  [3/3] Starting servers"
echo ""
echo "  Backend   →  http://localhost:8000"
echo "  API docs  →  http://localhost:8000/docs"
echo "  QVAC      →  http://localhost:3001"
echo "  Frontend  →  http://localhost:3000"
[ -n "$REDIS_PID" ] && echo "  Redis     →  localhost:6379"
echo ""

cd "$QVAC_DIR"
node src/server.js > "$QVAC_DIR/qvac.log" 2>&1 &
QVAC_PID=$!

cd "$AI_DIR"
PIP_ACTIVATE
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > "$AI_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

# Start ARQ worker only if Redis is available
if redis-cli ping &>/dev/null 2>&1; then
    REDIS_URL=redis://localhost:6379/0 arq app.workers.arq_worker.WorkerSettings > "$AI_DIR/arq_worker.log" 2>&1 &
    ARQ_PID=$!
    ok "ARQ worker started (PID $ARQ_PID)"
fi

trap "kill $BACKEND_PID $QVAC_PID ${ARQ_PID:-} ${REDIS_PID:-} 2>/dev/null; exit" EXIT INT TERM

# ── Health checks ─────────────────────────────────────────────────────────────
_wait_http() {
    local url="$1" label="$2" max="${3:-20}"
    for i in $(seq 1 "$max"); do
        curl -sf "$url" >/dev/null 2>&1 && { ok "$label ready"; return 0; }
        sleep 1
    done
    warn "$label did not respond after ${max}s — check logs"
}

# Backend: wait synchronously (frontend needs it).
_wait_http "http://localhost:8000/api/health" "Backend" 30

# QVAC: runs in background — first load of GTE_LARGE_FP16 (670MB) can take
# several minutes. The frontend works immediately; QVAC becomes available
# once the model finishes loading.
echo "  QVAC loading embedding model (first run may take 2-5 min)..."
_wait_http "http://localhost:3001/health" "QVAC" 300 &

# ── DB seed ──────────────────────────────────────────────────────────────────
cd "$AI_DIR"
PIP_ACTIVATE
python -m app.db.init_db 2>/dev/null || true
echo ""
echo "  Test users:  admin@bitpolito.it / DevAdmin@2024!Secure"
echo "               student@bitpolito.it / DevStudent@2024!Learn"
echo ""

# ── Frontend (blocks) ────────────────────────────────────────────────────────
cd "$WEB_DIR"
npm run dev

echo ""
ok "All servers stopped"
