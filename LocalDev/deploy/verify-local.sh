#!/usr/bin/env bash
# LocalDev sandbox verification — intended for CI and pre-feature gates (e.g. TreasureService V1).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'
PASS=0
FAIL=0
WARN=0
STARTED_POSTGRES=0
BACKEND_PID=""

pass()  { PASS=$((PASS + 1)); echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { FAIL=$((FAIL + 1)); echo -e "  ${RED}✗${NC} $1"; }
warn()  { WARN=$((WARN + 1)); echo -e "  ${YELLOW}⚠${NC} $1"; }

LOCAL_DB_URL="${DATABASE_URL:-postgresql://fraternityos:localdev@localhost:5434/fraternityos}"
export DATABASE_URL="$LOCAL_DB_URL"

cleanup() {
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ "$STARTED_POSTGRES" = "1" ] && [ "${KEEP_POSTGRES:-0}" != "1" ]; then
    docker compose down >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "═══════════════════════════════════════"
echo " GreekOS LocalDev — Sandbox Verification"
echo "═══════════════════════════════════════"
echo ""

# ── 1. Prerequisites ─────────────────────────────────
echo "▸ Checking prerequisites ..."
for cmd in docker python3 npm; do
  if command -v "$cmd" &>/dev/null; then
    pass "$cmd available"
  else
    fail "$cmd not found"
  fi
done

# ── 2. Environment ───────────────────────────────────
echo "▸ Checking environment ..."
if [ ! -f .env ]; then
  cp .env.example .env
  pass "Created .env from .env.example"
fi
if python3 deploy/check-env.py >/dev/null 2>&1; then
  pass "Environment variables valid"
else
  fail "Environment check failed — run: python3 deploy/check-env.py"
fi

if [ -f fratos/lib/api-client.ts ]; then
  pass "fratos/lib/api-client.ts present"
else
  fail "fratos/lib/ missing — frontend cannot build"
fi

# ── 3. PostgreSQL ────────────────────────────────────
echo "▸ Checking PostgreSQL ..."
if ! docker compose ps --status running 2>/dev/null | grep -q postgres; then
  docker compose up -d
  STARTED_POSTGRES=1
  pass "Started PostgreSQL via Docker Compose"
else
  pass "PostgreSQL container already running"
fi

for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U fraternityos &>/dev/null; then
    pass "PostgreSQL accepting connections on :5434"
    break
  fi
  if [ "$i" -eq 30 ]; then
    fail "PostgreSQL did not become ready"
  fi
  sleep 1
done

# ── 4. Migrations ────────────────────────────────────
echo "▸ Running migrations ..."
MIGRATE_OK=0
for attempt in 1 2 3 4 5; do
  if DATABASE_URL="$LOCAL_DB_URL" python3 scripts/migrate_db.py >/tmp/localdev-migrate.log 2>&1; then
    MIGRATE_OK=1
    break
  fi
  sleep 2
done
if [ "$MIGRATE_OK" = "1" ]; then
  pass "Migrations applied (or already up to date)"
else
  fail "Migration failed — see /tmp/localdev-migrate.log"
fi

TABLE_COUNT=$(DATABASE_URL="$LOCAL_DB_URL" python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'\")
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")
if [ "$TABLE_COUNT" -gt 3 ]; then
  pass "Database has $TABLE_COUNT public tables"
else
  fail "Database schema looks empty ($TABLE_COUNT tables)"
fi

# ── 5. Supabase-compatible DB layer ──────────────────
echo "▸ Checking Supabase-compatible DB layer ..."
if python3 -c "
from api.db import get_supabase
sb = get_supabase()
sb.table('chapters').select('id').execute()
print('ok')
" >/dev/null 2>&1; then
  pass "get_supabase() + table().select() works against local Postgres"
else
  fail "Supabase-compatible query layer failed — check api/db.py and postgres_client.py"
fi

# ── 6. Backend import + health ───────────────────────
echo "▸ Checking backend ..."
if python3 -c "from api.index import app; print(len(app.routes))" >/dev/null 2>&1; then
  pass "FastAPI app imports cleanly"
else
  fail "api.index import failed"
fi

uvicorn api.index:app --host 127.0.0.1 --port 8001 &
BACKEND_PID=$!
sleep 3

if curl -sf http://127.0.0.1:8001/api/health | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('status') == 'ok', d
assert d.get('checks', {}).get('database') == 'ok', d
" >/dev/null 2>&1; then
  pass "GET /api/health returns status=ok, checks.database=ok"
else
  fail "Health endpoint failed or database unreachable"
fi

# ── 7. Frontend build ────────────────────────────────
echo "▸ Checking frontend build ..."
if [ ! -d fratos/node_modules ]; then
  (cd fratos && npm ci --prefer-offline 2>/dev/null || npm install) >/tmp/localdev-npm.log 2>&1
  pass "Installed frontend dependencies"
fi

if (cd fratos && npm run build) >/tmp/localdev-build.log 2>&1; then
  pass "next build succeeded"
else
  fail "next build failed — see /tmp/localdev-build.log"
fi

# ── Summary ─────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo -e " Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo "═══════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}Sandbox verification failed.${NC}"
  exit 1
fi

echo -e "${GREEN}LocalDev sandbox is ready for TreasureService V1 development.${NC}"
exit 0
