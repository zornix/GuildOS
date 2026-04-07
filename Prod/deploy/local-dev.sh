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

# ── 2. Docker / PostgreSQL ──────────────────────────
echo "▸ Starting PostgreSQL via Docker Compose ..."
if ! command -v docker &>/dev/null; then
  echo -e "${RED}Docker not found. Install Docker first.${NC}"
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

# ── 3. Python dependencies ──────────────────────────
echo "▸ Checking Python dependencies ..."
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "  Installing Python dependencies ..."
  pip install -r requirements.txt -q
fi
echo -e "  ${GREEN}Python deps OK${NC}"

# ── 4. Migrations ───────────────────────────────────
echo "▸ Running database migrations ..."
DATABASE_URL="$LOCAL_DB_URL" python scripts/migrate_db.py
echo -e "  ${GREEN}Migrations OK${NC}"

# ── 5. Seed (first run only) ────────────────────────
DB_HAS_DATA=$(DATABASE_URL="$LOCAL_DB_URL" python3 -c "
import psycopg2
conn = psycopg2.connect('$LOCAL_DB_URL')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM members')
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")

if [ "$DB_HAS_DATA" = "0" ]; then
  echo "▸ Seeding database with demo data ..."
  DATABASE_URL="$LOCAL_DB_URL" python -m scripts.seed
  echo -e "  ${GREEN}Seed OK${NC}"
else
  echo -e "  ${GREEN}Database already has data — skipping seed${NC}"
  echo "▸ Ensuring officer role for jake@tke.org ..."
  DATABASE_URL="$LOCAL_DB_URL" python3 -c "
import psycopg2
conn = psycopg2.connect('$LOCAL_DB_URL')
conn.autocommit = True
cur = conn.cursor()
cur.execute(\"UPDATE members SET role = 'officer' WHERE email = 'jake@tke.org'\")
cur.close()
conn.close()
"
  echo -e "  ${GREEN}Officer role restored${NC}"
fi

# ── 6. Node dependencies ───────────────────────────
echo "▸ Checking Node dependencies ..."
if [ ! -d fratos/node_modules ]; then
  echo "  Installing frontend dependencies ..."
  (cd fratos && npm install)
fi
echo -e "  ${GREEN}Node deps OK${NC}"

# ── 7. Frontend env ────────────────────────────────
if [ ! -f fratos/.env.local ]; then
  echo "NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001" > fratos/.env.local
  echo -e "  ${GREEN}Created fratos/.env.local${NC}"
fi

# ── 8. Start backend ───────────────────────────────
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

# ── 9. Start frontend ──────────────────────────────
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
echo "  Database:  localhost:5434 (fraternityos/localdev)"
echo ""
echo "  Login:  jake@tke.org  (officer)"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "═══════════════════════════════════════"

wait
