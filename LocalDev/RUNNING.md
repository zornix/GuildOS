# Running FraternityOS Locally

## Prerequisites

- Python 3.11+
- Node.js 20+
- **A Supabase "demo" project** (primary path) — or Docker & Docker Compose for the offline fallback

## Database modes

The backend (`api/db.py`) picks its client from your `.env`:

| Mode | `.env` setup | Client used |
|------|--------------|-------------|
| **Supabase demo** (default, matches prod) | `SUPABASE_URL` + keys set, `DATABASE_URL` empty | `supabase-py` over PostgREST |
| **Docker fallback** (offline) | `DATABASE_URL` set, run with `USE_DOCKER_DB=1` | local psycopg shim |

Treasury V1 and prod both run on Supabase, and atomic multi-write operations are `plpgsql` RPCs invoked via `sb.rpc(...)` — so develop against the Supabase demo project whenever possible so RPC + RLS behavior is faithful.

### One-time Supabase demo setup

1. Create a new (empty) Supabase project to act as the demo DB.
2. `cp .env.example .env` and fill in `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (Project Settings → API) and `SUPABASE_DB_URL` (Project Settings → Database → Connection string, session pooler). Leave `DATABASE_URL` commented out.
3. Migrations are applied to the demo project's Postgres connection — never to prod (prod is read-only).

## Sandbox verification (CI gate)

```bash
npm run verify
# or: bash deploy/verify-local.sh
```

Confirms migrations, the Supabase-compatible DB layer, backend health, and frontend build.

## Automated Start

```bash
# Supabase demo (default — requires SUPABASE_URL + SUPABASE_DB_URL in .env):
bash deploy/local-dev.sh

# Offline Docker Postgres fallback:
USE_DOCKER_DB=1 bash deploy/local-dev.sh
```

This applies migrations, installs dependencies, and launches both backend (:8001) and frontend (:3000). In Supabase mode it skips Docker and migrates the demo project; in Docker mode it boots local Postgres.

## Manual Start

### 1. Database

**Supabase demo** — apply migrations (incl. `plpgsql` RPC functions) to the demo project:

```bash
DATABASE_URL="$SUPABASE_DB_URL" python scripts/migrate_db.py
```

**Docker fallback** — local Postgres:

```bash
docker compose up -d
# Wait for Postgres to be ready, then:
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos \
  python scripts/migrate_db.py
```

### 2. Seed test data (optional)

```bash
# Supabase demo:
DATABASE_URL="$SUPABASE_DB_URL" python -m scripts.seed
# Docker fallback:
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos \
  python -m scripts.seed
```

This creates a chapter, 8 members, 5 events, attendance records, excuses, and fines. The officer login is `jake@tke.org`.

### 3. Backend (terminal 1)

```bash
pip install -r requirements.txt
cp .env.example .env  # edit if needed
uvicorn api.index:app --reload --host 0.0.0.0 --port 8001
```

API docs: http://localhost:8001/api/docs

### 4. Frontend (terminal 2)

```bash
cd fratos
npm install
# fratos/.env.local should contain:
#   NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001
npm run dev
```

App: http://localhost:3000

## E2E Tests

```bash
cd fratos
npx playwright install chromium
npm run test:e2e
```

## Smoke Test Checklist

- [ ] Log in as `jake@tke.org` (officer)
- [ ] Members page loads with roster
- [ ] Create a new event (required, with fine)
- [ ] Open check-in link on event
- [ ] Visit `/c/<code>` on phone, enter phone `555111002` (Ryan)
- [ ] Verify attendance recorded on event detail
- [ ] Close check-in link
- [ ] Submit an excuse for an event (log in as member)
- [ ] Officer approves/denies excuse
- [ ] Process fines (button on past required event detail, or `/api/cron/process-fines`)
- [ ] Fines page shows fines, pay/waive works
- [ ] Standing page shows member standings
