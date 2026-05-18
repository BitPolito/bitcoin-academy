#!/usr/bin/env bash
# seed_demo.sh — Populate a fresh BitPolito Academy instance with demo content.
#
# Usage:
#   ./scripts/seed_demo.sh [API_URL] [ADMIN_EMAIL] [ADMIN_PASSWORD]
#
# Defaults:
#   API_URL=http://localhost:8000
#   ADMIN_EMAIL=admin@bitpolito.it
#   ADMIN_PASSWORD=BitPolitoAdmin2024!
#
# The script:
#   1. Registers (or logs in) the admin account
#   2. Creates a "Bitcoin Standard — Demo" course
#   3. Uploads the Bitcoin whitepaper PDF (downloads it if not present)
#   4. Polls until the document reaches 'ready' status (max 10 min)
#
# Requires: curl, jq

set -euo pipefail

API="${1:-http://localhost:8000}"
EMAIL="${2:-admin@bitpolito.it}"
PASSWORD="${3:-BitPolitoAdmin2024!}"
WHITEPAPER_URL="https://bitcoin.org/bitcoin.pdf"
WHITEPAPER_FILE="/tmp/bitcoin_whitepaper.pdf"
MAX_POLL_SECONDS=600
POLL_INTERVAL=5

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[seed]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { error "Required tool '$1' not found. Install it and retry."; exit 1; }
}

require curl
require jq

# ── 1. Authenticate ──────────────────────────────────────────────────────────

log "Attempting registration of $EMAIL …"
REG=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$API/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"display_name\":\"Demo Admin\"}")

if [[ "$REG" == "201" ]]; then
  log "Admin account created."
elif [[ "$REG" == "409" ]]; then
  warn "Account already exists — logging in."
else
  warn "Registration returned HTTP $REG — attempting login."
fi

log "Logging in as $EMAIL …"
LOGIN_RESP=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // empty')
if [[ -z "$TOKEN" ]]; then
  error "Login failed. Response: $LOGIN_RESP"
  exit 1
fi
log "Authenticated. Token obtained."

AUTH="-H \"Authorization: Bearer $TOKEN\""

call() {
  local method="$1"; shift
  local path="$1"; shift
  curl -s -X "$method" "$API$path" \
    -H "Authorization: Bearer $TOKEN" \
    "$@"
}

# ── 2. Create demo course ────────────────────────────────────────────────────

log "Creating demo course …"
COURSE_RESP=$(call POST /api/courses \
  -H "Content-Type: application/json" \
  -d '{"title":"Bitcoin Standard — Demo","description":"Corso demo basato sul whitepaper di Satoshi Nakamoto (dominio pubblico)."}')

COURSE_ID=$(echo "$COURSE_RESP" | jq -r '.id // empty')
if [[ -z "$COURSE_ID" ]]; then
  # Course may already exist — list and pick first one with matching title
  warn "Could not create course (may already exist). Looking for existing …"
  COURSE_ID=$(call GET /api/courses | jq -r '.[] | select(.title == "Bitcoin Standard — Demo") | .id' | head -1)
fi

if [[ -z "$COURSE_ID" ]]; then
  error "Failed to create or find demo course. Response: $COURSE_RESP"
  exit 1
fi
log "Course ID: $COURSE_ID"

# ── 3. Download whitepaper ───────────────────────────────────────────────────

if [[ ! -f "$WHITEPAPER_FILE" ]]; then
  log "Downloading Bitcoin whitepaper …"
  curl -sL "$WHITEPAPER_URL" -o "$WHITEPAPER_FILE"
  log "Downloaded to $WHITEPAPER_FILE ($(du -sh "$WHITEPAPER_FILE" | cut -f1))."
else
  log "Using cached whitepaper at $WHITEPAPER_FILE."
fi

# ── 4. Upload document ───────────────────────────────────────────────────────

log "Uploading whitepaper to course $COURSE_ID …"
UPLOAD_RESP=$(call POST "/api/courses/$COURSE_ID/documents" \
  -F "file=@$WHITEPAPER_FILE;type=application/pdf")

DOC_ID=$(echo "$UPLOAD_RESP" | jq -r '.id // empty')
if [[ -z "$DOC_ID" ]]; then
  error "Upload failed. Response: $UPLOAD_RESP"
  exit 1
fi
log "Document ID: $DOC_ID — waiting for ingestion …"

# ── 5. Poll until ready ──────────────────────────────────────────────────────

ELAPSED=0
while [[ $ELAPSED -lt $MAX_POLL_SECONDS ]]; do
  STATUS_RESP=$(call GET "/api/courses/$COURSE_ID/documents")
  DOC_STATUS=$(echo "$STATUS_RESP" | jq -r ".[] | select(.id == \"$DOC_ID\") | .status" 2>/dev/null || echo "unknown")

  if [[ "$DOC_STATUS" == "ready" ]]; then
    log "Document ingested and indexed successfully."
    break
  elif [[ "$DOC_STATUS" == "error" ]]; then
    error "Document ingestion failed. Check service logs."
    exit 1
  fi

  printf "\r${YELLOW}[seed]${NC} Status: %-12s  elapsed: %ds …" "$DOC_STATUS" "$ELAPSED"
  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [[ $ELAPSED -ge $MAX_POLL_SECONDS ]]; then
  warn "Timed out waiting for ingestion. The document may still be processing."
fi

echo ""
log "Done! Demo content loaded:"
log "  Course: Bitcoin Standard — Demo (id: $COURSE_ID)"
log "  Document: bitcoin_whitepaper.pdf (id: $DOC_ID)"
log ""
log "Open the platform at http://localhost:3000 and start exploring."
