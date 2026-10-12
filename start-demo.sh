#!/usr/bin/env bash
# Start the local demo: FastAPI on :8001 + greekos on :3000 against the demo
# Supabase database. See docs/launch-demo.md.
set -euo pipefail

cd "$(dirname "$0")/LocalDev"
exec npm run dev
