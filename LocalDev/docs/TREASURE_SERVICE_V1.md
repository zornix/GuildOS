# TreasureService V1 — LocalDev Sandbox

LocalDev is the isolated sandbox for GreekOS feature work before production deploy. Use it to develop and CI-gate TreasureService V1 without touching Prod.

## What is verified

The sandbox verification script (`deploy/verify-local.sh`) confirms:

| Layer | Check |
|-------|-------|
| PostgreSQL | Docker Compose Postgres on `:5434`, migrations applied |
| DB access | `get_supabase()` + `table().select()` via `postgres_client.py` (Supabase-compatible API) |
| Backend | FastAPI imports, `/api/health` with `checks.database=ok` |
| Frontend | `fratos/lib/` present, `next build` succeeds |
| Env | `.env` + `fratos/.env.local` configured for local mode |

## Quick start

```bash
cd LocalDev

# One-shot sandbox verification (CI-equivalent)
npm run verify

# Interactive dev (Postgres + backend + frontend)
npm run dev

# With seed data
npm run dev:seed
```

## Database: Supabase-compatible local mode

Production uses `supabase-py` against Supabase Postgres. LocalDev mirrors that API surface:

- Routes call `get_supabase()` / `get_supabase_admin()` from `api/db.py`
- When `DATABASE_URL` is set, `postgres_client.PostgresClient` implements the same `table().select().eq().execute()` pattern
- When `DATABASE_URL` is unset, real `supabase-py` is used (remote Supabase)

Local connection string (Docker Compose):

```
postgresql://fraternityos:localdev@localhost:5434/fraternityos
```

## CI/CD

GitHub Actions workflow: `.github/workflows/ci.yml`

Triggers on changes under `LocalDev/`. Runs the same `deploy/verify-local.sh` gate used locally.

To add TreasureService V1 CI checks later:

1. Add migration `migrations/0004_treasure_*.sql`
2. Add `api/routes/treasure.py` + `api/services/treasure.py`
3. Extend `deploy/verify-local.sh` with treasure-specific smoke tests
4. Add Playwright specs under `fratos/e2e/treasure.spec.ts`

## TreasureService V1 — built

The backend service is implemented and green (`tests/treasury/`). It mounts at
`/api/treasury`, lives under `api/treasury/`, and uses migrations `0005`–`0080`. See
[TREASURY_ARCHITECTURE.md](TREASURY_ARCHITECTURE.md) for the full design (ledger model,
RPC mutation path, balance engine, authorization, governance controls, invariants, and
rebuild/drift detection).

A treasury **frontend** view (`fratos/views/treasury.tsx`) and e2e specs are not yet
built — that is the next increment. Keep new tables and routes in LocalDev first; promote
to Prod only after `npm run verify` and e2e pass.
