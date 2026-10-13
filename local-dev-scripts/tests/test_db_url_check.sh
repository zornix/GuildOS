#!/usr/bin/env bash
# Run: bash local-dev-scripts/tests/test_db_url_check.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../LocalDev"
source "$HERE/../scripts/db-url-check.sh"

fail=0
expect() { # expect placeholder|real URL
  if is_placeholder_db_url "$2"; then got=placeholder; else got=real; fi
  if [ "$got" = "$1" ]; then echo "ok   $1: $2"; else echo "FAIL want $1, got $got: $2"; fail=1; fi
}

example="$(grep -E '^DATABASE_URL=' .env.example | tail -n1 | cut -d= -f2-)"
expect placeholder ""
expect placeholder "postgresql://postgres.<demo-ref>:x@h:6543/postgres"
expect placeholder "$example"
expect placeholder "postgresql://postgres.PROJECT_REF:other@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
expect real "postgresql://postgres.abcdefghijklmnopqrst:s3cret@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
exit $fail
