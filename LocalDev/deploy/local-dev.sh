#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

LOCAL_DB_URL="postgresql://fraternityos:localdev@localhost:5434/fraternityos"

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

  # Ensure the file ends with a newline before appending a new key.
  if [ -s "$file" ] && [ -n "$(tail -c1 "$file" 2>/dev/null || true)" ]; then
    printf "\n" >> "$file"
  fi
  printf "%s=%s\n" "$key" "$value" >> "$file"
}

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down ...${NC}"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

# ── 1. .env file ────────────────────────────────────
if [ ! -f .env ]; then
  echo -e "${YELLOW}No .env found — creating from .env.example${NC}"
  cp .env.example .env
  echo -e "${GREEN}Created .env with local defaults${NC}"
fi

ensure_env_key .env "FEATURE_VP_OPERATIONS" "1"
ensure_env_key .env "FEATURE_SECRETARY_COMMS" "1"
ensure_env_key .env "MESSAGE_DELIVERY_MODE" "dry_run"
ensure_env_key .env "ESCALATION_DELAY_MINUTES" "120"
ensure_env_key .env "MESSAGE_WEBHOOK_SECRET" "local-webhook-secret-change-in-prod"

# ── 2. Select DB mode (Supabase demo vs local Docker) ──
read_env_key() {
  # Read KEY=value from .env without executing the file (values may contain < > @ : /).
  grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'
}

SUPABASE_URL_VAL="$(read_env_key SUPABASE_URL)"
SUPABASE_DB_URL_VAL="$(read_env_key SUPABASE_DB_URL)"

if [ "${USE_DOCKER_DB:-0}" = "1" ] || [ -z "$SUPABASE_URL_VAL" ]; then
  DB_MODE="docker"
else
  DB_MODE="supabase"
fi

if [ "$DB_MODE" = "supabase" ]; then
  echo "▸ Using Supabase demo project (supabase-py / PostgREST)"
  case "$SUPABASE_URL_VAL" in
    *"<your-demo-ref>"*|"")
      echo -e "${RED}SUPABASE_URL in .env is still a placeholder.${NC}"
      echo    "  Fill in your Supabase demo project, or run: USE_DOCKER_DB=1 bash deploy/local-dev.sh"
      exit 1;;
  esac
  case "$SUPABASE_DB_URL_VAL" in
    *"<your-demo-ref>"*|"")
      echo -e "${RED}SUPABASE_DB_URL in .env is required to apply migrations to the demo project.${NC}"
      echo    "  Supabase → Project Settings → Database → Connection string (session pooler)."
      exit 1;;
  esac
  if [ -n "$(read_env_key DATABASE_URL)" ]; then
    echo -e "${YELLOW}  Note: DATABASE_URL is set in .env — the app will use the local psycopg shim, not Supabase.${NC}"
    echo    "  Comment DATABASE_URL out so the app talks to the Supabase demo project."
  fi
  MIGRATE_DB_URL="$SUPABASE_DB_URL_VAL"
  DB_SUMMARY="Supabase demo ($SUPABASE_URL_VAL)"
else
  echo "▸ Using local Docker PostgreSQL (offline fallback)"
  # The app reads .env; DATABASE_URL must be set so it uses the local psycopg shim.
  ensure_env_key .env "DATABASE_URL" "$LOCAL_DB_URL"
  if ! command -v docker &>/dev/null; then
    echo -e "${RED}Docker not found. Install Docker, or configure SUPABASE_URL for the demo DB.${NC}"
    exit 1
  fi
  docker compose up -d
  echo "  Waiting for PostgreSQL to be ready ..."
  for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U fraternityos &>/dev/null; then
      echo -e "  ${GREEN}PostgreSQL ready${NC}"
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo -e "  ${RED}PostgreSQL did not start in time${NC}"
      exit 1
    fi
    sleep 1
  done
  MIGRATE_DB_URL="$LOCAL_DB_URL"
  DB_SUMMARY="localhost:5434 (fraternityos/localdev)"
fi

# ── 3. Migrations ───────────────────────────────────
echo "▸ Running database migrations ..."
DATABASE_URL="$MIGRATE_DB_URL" python3 scripts/migrate_db.py
echo -e "  ${GREEN}Migrations OK${NC}"

if [ "${SEED_LOCAL_DB:-0}" = "1" ]; then
  echo "▸ Seeding test data ..."
  DATABASE_URL="$MIGRATE_DB_URL" python3 -m scripts.seed
  echo -e "  ${GREEN}Seed data OK${NC}"
fi

# ── 4. Python dependencies ──────────────────────────
echo "▸ Checking Python dependencies ..."
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "  Installing Python dependencies ..."
  pip install -r requirements.txt -q
fi
echo -e "  ${GREEN}Python deps OK${NC}"

# ── 5. Node dependencies ───────────────────────────
echo "▸ Checking Node dependencies ..."
if [ ! -d fratos/node_modules ]; then
  echo "  Installing frontend dependencies ..."
  (cd fratos && npm install)
fi
echo -e "  ${GREEN}Node deps OK${NC}"

# ── 6. Frontend env ────────────────────────────────
ensure_env_key fratos/.env.local "NEXT_PUBLIC_API_BASE" "http://127.0.0.1:8001"
ensure_env_key fratos/.env.local "NEXT_PUBLIC_ENABLE_VP_MODULE" "1"
ensure_env_key fratos/.env.local "NEXT_PUBLIC_ENABLE_SECRETARY_MODULE" "1"
echo -e "  ${GREEN}Checked fratos/.env.local${NC}"

# ── 7. Start backend ───────────────────────────────
echo ""
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

# ── 8. Start frontend ──────────────────────────────
echo "▸ Starting Next.js frontend on :3000 ..."
(cd fratos && npm run dev) &
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
echo "  Seed data: SEED_LOCAL_DB=1 bash deploy/local-dev.sh"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "═══════════════════════════════════════"

wait
