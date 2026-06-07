# GreekOS LocalDev

LocalDev is the local development sandbox for GreekOS. Use it to build and CI-gate features (including **TreasureService V1**) before promoting changes to `Prod/`.

## What This Folder Contains

- `api/` - FastAPI backend (auth, events, attendance, excuses, fines, members, check-in links, cron, standing, operations)
- `fratos/` - Next.js frontend (dashboard, events, fines, members, standing, active check-ins)
- `migrations/` - SQL migrations
- `scripts/` - migration, seed, and operational helpers (`check_prod_status.py`, `set_officer_password.py`)
- `tests/` - backend tests
- `deploy/` - local-dev and deploy scripts
- `docs/` - implementation audits and feature preparation docs
- `deferred/` - intentionally deferred work outside active MVP runtime

LocalDev mirrors `Prod/` application logic and layers local-only infrastructure on top:
dual local-Postgres/Supabase config (`api/config.py`, `api/db.py`), Docker Postgres, dev
scripts, seed data, the operations engine, and e2e tests.

## Authentication

Mirrors Prod: officers use password-based login (bcrypt `password_hash`), with a grace
first-login that prompts password setup (`/api/auth/set-password`); members use email-only
login. JWTs are signed with `JWT_SECRET` (see `.env`). Use `scripts/set_officer_password.py`
to set an officer password directly against the DB.

## Local Development

```bash
# Verify sandbox (CI-equivalent gate)
npm run verify

# Start Postgres + backend + frontend
npm run dev

# Start with seed data (officer login: jake@tke.org)
npm run dev:seed
```

Services:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8001`
- API docs: `http://localhost:8001/api/docs`
- Database: Supabase demo project (default) — or `localhost:5434` (`fraternityos` / `localdev`) in Docker fallback mode

### DB access (Supabase-first)

Routes use `get_supabase()` from `api/db.py`. The default and prod-faithful path points at a real Supabase **demo** project via `supabase-py` (PostgREST) — set `SUPABASE_URL` + keys in `.env` and leave `DATABASE_URL` empty. Setting `DATABASE_URL` instead switches LocalDev to `postgres_client.PostgresClient`, a drop-in for the `supabase-py` query API against local Docker Postgres (offline fallback, run with `USE_DOCKER_DB=1`).

Treasury V1 atomic multi-write operations are `plpgsql` functions invoked with `sb.rpc(...)` — the only path that is atomic on PostgREST. See `treasury-v1-implementation-plan.md` (§2, Slice 0) and `treasury-v1-agent-chunks.md`.

See `docs/TREASURE_SERVICE_V1.md` for the TreasureService V1 sandbox plan and CI layout.

## Website and Feature Planning Docs

- Website audit: `docs/WEBSITE_AUDIT.md`
- VP + Secretary prep: `docs/VP_SECRETARY_FEATURE_PREP.md`
- Deployment details: `deploy/README.md`
