#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'
PASS=0
FAIL=0
WARN=0

pass()  { ((PASS++)); echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { ((FAIL++)); echo -e "  ${RED}✗${NC} $1"; }
warn()  { ((WARN++)); echo -e "  ${YELLOW}⚠${NC} $1"; }

echo "═══════════════════════════════════════"
echo " FraternityOS — Pre-Deploy Preflight"
echo "═══════════════════════════════════════"
echo ""

# ── 1. vercel.json syntax ────────────────────────────
echo "▸ Checking vercel.json ..."
if [ -f vercel.json ]; then
  if python3 -c "import json; json.load(open('vercel.json'))" 2>/dev/null; then
    pass "vercel.json is valid JSON"
  else
    fail "vercel.json has syntax errors"
  fi
else
  fail "vercel.json not found"
fi

# ── 2. Python dependencies ───────────────────────────
echo "▸ Checking Python dependencies ..."
if [ -f requirements.txt ]; then
  pass "requirements.txt exists"
else
  fail "requirements.txt missing — Vercel Python build will fail"
fi

# ── 3. FastAPI import check ──────────────────────────
echo "▸ Checking FastAPI app imports ..."
if python3 -c "from api.index import app; print('loaded', len(app.routes), 'routes')" 2>/dev/null; then
  pass "api.index imports cleanly"
else
  fail "api.index has import errors — run: python3 -c 'from api.index import app'"
fi

# ── 4. Migration files ──────────────────────────────
echo "▸ Checking migrations ..."
MIGRATION_COUNT=$(find migrations -name '*.sql' 2>/dev/null | wc -l)
if [ "$MIGRATION_COUNT" -gt 0 ]; then
  pass "Found $MIGRATION_COUNT migration file(s)"
else
  fail "No migration files in migrations/"
fi

# ── 5. Frontend build ───────────────────────────────
echo "▸ Checking frontend build ..."
if [ -d fratos/node_modules ]; then
  pass "fratos/node_modules exists"
else
  warn "fratos/node_modules missing — run: cd fratos && npm install"
fi

if [ -f fratos/package.json ]; then
  echo "  Running next build (this may take a moment) ..."
  if (cd fratos && npm run build) > /tmp/fratos-build.log 2>&1; then
    pass "next build succeeded"
  else
    fail "next build failed — check /tmp/fratos-build.log"
  fi
else
  fail "fratos/package.json missing"
fi

# ── 6. Frontend lint ────────────────────────────────
echo "▸ Running frontend lint ..."
if (cd fratos && npm run lint) > /tmp/fratos-lint.log 2>&1; then
  pass "ESLint passed"
else
  warn "ESLint issues — check /tmp/fratos-lint.log"
fi

# ── 7. Environment validation ───────────────────────
echo "▸ Checking environment variables ..."
if python3 deploy/check-env.py 2>/dev/null; then
  pass "Environment variables look good"
else
  warn "Environment variable issues — run: python3 deploy/check-env.py"
fi

# ── 8. Local health check (optional) ────────────────
echo "▸ Checking local API health (optional) ..."
if curl -sf http://localhost:8001/api/health > /dev/null 2>&1; then
  pass "Local API is running and healthy"
else
  warn "Local API not reachable on :8001 (ok if not running)"
fi

# ── 9. Git status ───────────────────────────────────
echo "▸ Checking git status ..."
if git diff --quiet 2>/dev/null; then
  pass "Working tree clean"
else
  warn "Uncommitted changes — consider committing before deploy"
fi

# ── Summary ─────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo -e " Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo "═══════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}Fix failures before deploying.${NC}"
  exit 1
fi

if [ "$WARN" -gt 0 ]; then
  echo -e "${YELLOW}Warnings present — review before deploying.${NC}"
  exit 0
fi

echo -e "${GREEN}All clear. Ready to deploy.${NC}"
