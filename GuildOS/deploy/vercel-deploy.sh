#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

PROD_FLAG=""
SKIP_PREFLIGHT=false

for arg in "$@"; do
  case $arg in
    --prod)       PROD_FLAG="--prod" ;;
    --skip-checks) SKIP_PREFLIGHT=true ;;
    *)            echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

echo "═══════════════════════════════════════"
echo " FraternityOS — Vercel Deploy"
if [ -n "$PROD_FLAG" ]; then
  echo -e " ${RED}*** PRODUCTION ***${NC}"
else
  echo "  (preview deployment)"
fi
echo "═══════════════════════════════════════"
echo ""

# ── 1. Verify Vercel CLI ───────────────────────────
if ! command -v vercel &>/dev/null; then
  echo -e "${RED}Vercel CLI not found. Install: npm i -g vercel${NC}"
  exit 1
fi

# ── 2. Verify project is linked ────────────────────
if [ ! -d .vercel ]; then
  echo -e "${YELLOW}Project not linked. Running 'vercel link' ...${NC}"
  vercel link
fi

# ── 3. Preflight checks ───────────────────────────
if [ "$SKIP_PREFLIGHT" = false ]; then
  echo "▸ Running preflight checks ..."
  echo ""
  if bash deploy/preflight.sh; then
    echo ""
    echo -e "${GREEN}Preflight passed.${NC}"
  else
    echo ""
    echo -e "${RED}Preflight failed. Fix issues or use --skip-checks to bypass.${NC}"
    exit 1
  fi
else
  echo -e "${YELLOW}Skipping preflight checks (--skip-checks)${NC}"
fi

# ── 4. Verify critical Vercel env vars ─────────────
echo ""
echo "▸ Checking Vercel environment variables ..."
echo ""

MISSING_VARS=()

check_vercel_env() {
  local var_name=$1
  if vercel env ls 2>/dev/null | grep -q "$var_name"; then
    echo -e "  ${GREEN}✓${NC} $var_name"
  else
    echo -e "  ${RED}✗${NC} $var_name — not found in Vercel env"
    MISSING_VARS+=("$var_name")
  fi
}

check_vercel_env "DATABASE_URL"
check_vercel_env "JWT_SECRET"
check_vercel_env "FRONTEND_URL"
check_vercel_env "BASE_URL"
check_vercel_env "SUPABASE_URL"
check_vercel_env "SUPABASE_ANON_KEY"
check_vercel_env "SUPABASE_SERVICE_ROLE_KEY"

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
  echo ""
  echo -e "${YELLOW}Missing ${#MISSING_VARS[@]} env var(s) in Vercel.${NC}"
  echo "  Add them at: Vercel Dashboard → Settings → Environment Variables"
  echo "  See deploy/README.md for the full secrets matrix."
  echo ""
  read -rp "  Continue anyway? [y/N] " response
  if [[ ! "$response" =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# ── 5. Confirm production deploy ───────────────────
if [ -n "$PROD_FLAG" ]; then
  echo ""
  echo -e "${RED}You are about to deploy to PRODUCTION.${NC}"
  read -rp "  Type 'deploy' to confirm: " confirm
  if [ "$confirm" != "deploy" ]; then
    echo "Aborted."
    exit 0
  fi
fi

# ── 6. Deploy ─────────────────────────────────────
echo ""
echo "▸ Deploying ..."
echo ""

DEPLOY_URL=$(vercel $PROD_FLAG 2>&1 | tee /dev/stderr | grep -oP 'https://[^\s]+' | tail -1)

echo ""
echo "═══════════════════════════════════════"
echo -e " ${GREEN}Deployment complete${NC}"
if [ -n "$DEPLOY_URL" ]; then
  echo "  URL: $DEPLOY_URL"
fi
echo ""
echo "  Post-deploy checks:"
echo "    curl ${DEPLOY_URL:-<url>}/api/health"
echo "    Open ${DEPLOY_URL:-<url>} in browser"
echo "═══════════════════════════════════════"
