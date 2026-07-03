#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCALDEV_ROOT="$(cd "$SCRIPT_DIR/../../LocalDev" && pwd)"
cd "$LOCALDEV_ROOT"

read_env_key() {
  grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true
}

if [ ! -f .env ]; then
  echo "error: LocalDev/.env not found — copy .env.example and set the Supabase demo pooler URL" >&2
  exit 1
fi

DB_URL="$(read_env_key TEST_DATABASE_URL)"
if [ -z "$DB_URL" ]; then
  DB_URL="$(read_env_key SUPABASE_DB_URL)"
fi
if [ -z "$DB_URL" ]; then
  DB_URL="$(read_env_key DATABASE_URL)"
fi

if [ -z "$DB_URL" ] || [[ "$DB_URL" == *"<"* ]]; then
  echo "error: set DATABASE_URL (Supabase demo pooler) in LocalDev/.env" >&2
  exit 1
fi

export DATABASE_URL="$DB_URL"
exec "$@"
