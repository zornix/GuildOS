# Sourced by local-dev.sh and with-demo-db.sh. Run from LocalDev/.
# True when the DB URL is empty or still the .env.example placeholder.
is_placeholder_db_url() {
  local example
  example="$(grep -E '^DATABASE_URL=' .env.example 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  [ -z "$1" ] || [[ "$1" == *"<"* ]] || [[ "$1" == *PROJECT_REF* ]] || [ "$1" = "$example" ]
}
