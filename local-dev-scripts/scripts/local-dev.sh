#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCALDEV_ROOT="$(cd "$SCRIPT_DIR/../../LocalDev" && pwd)"
cd "$LOCALDEV_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "═══════════════════════════════════════"
echo " FraternityOS — Local Development"
echo "═══════════════════════════════════════"
echo ""
BACKEND_PID=""
FRONTEND_PID=""

ensure_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"

  if [ ! -f "$file" ]; then
    printf "%s=%s\n" "$key" "$value" > "$file"
    return
  fi

  if awk -F= -v key="$key" '$1 == key { found=1; exit } END { exit !found }' "$file"; then
    return
  fi

  if [ -s "$file" ] && [ -n "$(tail -c1 "$file" 2>/dev/null || true)" ]; then
    printf "\n" >> "$file"
  fi
  printf "%s=%s\n" "$key" "$value" >> "$file"
}

read_env_key() {
  grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true
}

pids_on_port() {
  local port="$1"
  if command -v lsof &>/dev/null; then
    lsof -ti ":$port" 2>/dev/null || true
    return
  fi
  if command -v fuser &>/dev/null; then
    fuser "$port/tcp" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
    return
  fi
  if command -v ss &>/dev/null; then
    ss -lptn "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true
  fi
}

kill_process_tree() {
  local pid="$1"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_process_tree "$child"
  done

  kill "$pid" 2>/dev/null || true
}

force_kill_process_tree() {
  local pid="$1"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    force_kill_process_tree "$child"
  done

  kill -9 "$pid" 2>/dev/null || true
}

stop_pids() {
  local label="$1"
  shift
  local pids=("$@")
  local pid still_running=()

  if [ "${#pids[@]}" -eq 0 ]; then
    return
  fi

  echo -e "${YELLOW}  Stopping existing $label (PIDs: ${pids[*]}) ...${NC}"
  for pid in "${pids[@]}"; do
    kill_process_tree "$pid"
  done
  sleep 1

  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      still_running+=("$pid")
    fi
  done

  if [ "${#still_running[@]}" -gt 0 ]; then
    for pid in "${still_running[@]}"; do
      force_kill_process_tree "$pid"
    done
    sleep 1
  fi
}

kill_listeners_on_port() {
  local port="$1"
  local label="$2"
  local pid
  local -a pids=()

  while IFS= read -r pid; do
    [ -n "$pid" ] && pids+=("$pid")
  done < <(pids_on_port "$port")

  stop_pids "$label on :$port" "${pids[@]}"
}

kill_existing_backend() {
  local pid
  local -a pids=()

  kill_listeners_on_port 8001 "backend"

  while IFS= read -r pid; do
    [ -n "$pid" ] && pids+=("$pid")
  done < <(pgrep -f "uvicorn api.index:app" 2>/dev/null || true)

  stop_pids "backend (uvicorn)" "${pids[@]}"
}

kill_existing_frontend() {
  local pid
  local -a pids=()

  while IFS= read -r pid; do
    [ -n "$pid" ] && pids+=("$pid")
  done < <(pgrep -f "${LOCALDEV_ROOT}/greekos.*vite" 2>/dev/null || true)

  stop_pids "frontend (vite)" "${pids[@]}"
  kill_listeners_on_port 3000 "frontend"
  kill_listeners_on_port 3001 "frontend"
}

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down ...${NC}"
  if [ -n "$BACKEND_PID" ]; then
    kill_process_tree "$BACKEND_PID"
  fi
  if [ -n "$FRONTEND_PID" ]; then
    kill_process_tree "$FRONTEND_PID"
  fi
  echo "Done."
}
trap cleanup EXIT INT TERM

# ── 1. .env file ────────────────────────────────────
if [ ! -f .env ]; then
  echo -e "${YELLOW}No .env found — creating from .env.example${NC}"
  cp .env.example .env
  echo -e "${RED}Fill in DATABASE_URL with your Supabase demo pooler URL, then re-run.${NC}"
  exit 1
fi

ensure_env_key .env "FEATURE_VP_OPERATIONS" "1"
ensure_env_key .env "FEATURE_SECRETARY_COMMS" "1"
ensure_env_key .env "MESSAGE_DELIVERY_MODE" "dry_run"
ensure_env_key .env "ESCALATION_DELAY_MINUTES" "120"
ensure_env_key .env "MESSAGE_WEBHOOK_SECRET" "local-webhook-secret-change-in-prod"

# ── 2. Resolve Supabase demo DB ─────────────────────
DATABASE_URL_VAL="$(read_env_key DATABASE_URL)"
TEST_DATABASE_URL_VAL="$(read_env_key TEST_DATABASE_URL)"
SUPABASE_DB_URL_VAL="$(read_env_key SUPABASE_DB_URL)"

MIGRATE_DB_URL="${TEST_DATABASE_URL_VAL:-${SUPABASE_DB_URL_VAL:-$DATABASE_URL_VAL}}"
if [ -z "$MIGRATE_DB_URL" ] || [[ "$MIGRATE_DB_URL" == *"<"* ]]; then
  echo -e "${RED}Supabase demo DATABASE_URL is missing or still a placeholder in .env.${NC}"
  echo "  Copy .env.example → .env and set the pooler URL (Session mode)."
  exit 1
fi
echo "▸ Using Supabase demo database (direct Postgres via pooler)"
DB_SUMMARY="Supabase demo pooler"

# ── 3. Migrations ───────────────────────────────────
echo "▸ Running database migrations ..."
DATABASE_URL="$MIGRATE_DB_URL" python3 scripts/migrate_db.py
echo -e "  ${GREEN}Migrations OK${NC}"

# ── 4. Python dependencies ──────────────────────────
echo "▸ Checking Python dependencies ..."
REQ_HASH="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' requirements.txt)"
if [ ! -f .deps-stamp ] || [ "$(cat .deps-stamp)" != "$REQ_HASH" ]; then
  echo "  Installing Python dependencies (requirements.txt changed) ..."
  pip install -r requirements.txt -q
  echo "$REQ_HASH" > .deps-stamp
fi
echo -e "  ${GREEN}Python deps OK${NC}"

# ── 5. Node dependencies ───────────────────────────
echo "▸ Checking Node dependencies ..."
if [ ! -d greekos/node_modules ]; then
  echo "  Installing frontend dependencies ..."
  (cd greekos && npm install)
fi
echo -e "  ${GREEN}Node deps OK${NC}"

# ── 6. Start backend ───────────────────────────────
echo ""
echo "▸ Clearing existing dev servers ..."
kill_existing_backend
kill_existing_frontend

echo "▸ Starting FastAPI backend on :8001 ..."
uvicorn api.index:app --reload --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!
sleep 2

if kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo -e "  ${GREEN}Backend running (PID $BACKEND_PID)${NC}"
else
  echo -e "  ${RED}Backend failed to start${NC}"
  exit 1
fi

# ── 7. Start frontend ──────────────────────────────
echo "▸ Starting GreekOS frontend on :3000 ..."
(cd greekos && npm run dev) &
FRONTEND_PID=$!
sleep 3

echo ""
echo "═══════════════════════════════════════"
echo -e " ${GREEN}Local dev environment is up${NC}"
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8001"
echo "  API docs:  http://localhost:8001/api/docs"
echo "  Database:  $DB_SUMMARY"
echo "  Seed data: npm run seed"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "═══════════════════════════════════════"

wait
