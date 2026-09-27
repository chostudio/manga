#!/usr/bin/env bash
#
# One-shot dev launcher for the manga search engine.
#   ./run.sh            start Postgres (Docker), backend, and frontend
#   ./run.sh backend    start Postgres + backend only
#   ./run.sh db         start Postgres only
#
# Ctrl-C stops the backend (and frontend); the Postgres container is left
# running (stop it with: docker compose down).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
MODE="${1:-all}"

log() { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# 1. Database (Docker Postgres + pgvector)
# ---------------------------------------------------------------------------
start_db() {
  log "Starting Postgres (docker compose)..."
  if ! docker info >/dev/null 2>&1; then
    err "Docker daemon isn't running. Start Docker Desktop, then re-run."
    err "  open -a Docker"
    exit 1
  fi
  ( cd "$ROOT" && docker compose up -d )
  log "Waiting for Postgres to accept connections..."
  for _ in $(seq 1 30); do
    if docker compose -f "$ROOT/docker-compose.yml" exec -T db pg_isready -U postgres >/dev/null 2>&1; then
      log "Postgres ready."
      return 0
    fi
    sleep 2
  done
  err "Postgres did not become ready in time."
  exit 1
}

# ---------------------------------------------------------------------------
# 2. Backend (Django)
# ---------------------------------------------------------------------------
start_backend() {
  log "Preparing backend..."
  cd "$BACKEND"
  if [ ! -d .venv ]; then
    log "Creating virtualenv (.venv)..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  log "Installing backend dependencies..."
  pip install -q -r requirements.txt
  log "Applying migrations..."
  python manage.py migrate
  log "Starting Django on http://127.0.0.1:8000/  (first search downloads model weights to ~/.cache/huggingface)"
  python manage.py runserver 127.0.0.1:8000
}

# ---------------------------------------------------------------------------
# 3. Frontend (Angular)
# ---------------------------------------------------------------------------
start_frontend_bg() {
  ( cd "$FRONTEND"
    # Load nvm if present so `node`/`ng` resolve to v22.
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck disable=SC1091
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null 2>&1 || true
    [ -d node_modules ] || { log "Installing frontend dependencies..."; npm install; }
    log "Starting Angular on http://localhost:4200/"
    npx ng serve --open
  ) &
  FRONTEND_PID=$!
}

cleanup() {
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

case "$MODE" in
  db)
    start_db
    ;;
  backend)
    start_db
    start_backend
    ;;
  all|"")
    start_db
    start_frontend_bg   # runs in background; blocks on the backend below
    start_backend
    ;;
  *)
    err "Unknown mode: $MODE (use: all | backend | db)"
    exit 1
    ;;
esac
