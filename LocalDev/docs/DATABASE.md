# Database connections & migrations — runbook

Two databases, both Supabase projects, one app client (see ADR-0002,
`/docs/adr/0002-supabase-is-hosted-postgres-only.md`):

| Environment | Supabase project | Who connects | How |
|---|---|---|---|
| **Prod** | production project | the deployed Vercel app | direct Postgres via the project's connection pooler |
| **Localdev** | demo project | `npm run dev`, pytest, migrate script | direct Postgres via the demo pooler |

There is no local Postgres. The app never uses PostgREST, GoTrue, or the
Data API — Supabase is hosted Postgres only. Connection strings are secrets;
they live in `LocalDev/.env` (gitignored) and in Vercel env vars, never in
code or docs.

## Getting a connection URL from Supabase

Supabase Dashboard → project → **Connect** → *Connection pooling* →
**Transaction mode** (port 6543). The URL shape is:

```
postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Use the pooler host, not the direct `db.<ref>.supabase.co` host — direct
connection slots are scarce and the pooler multiplexes them.

## Connect to localdev (demo project)

1. Ensure `LocalDev/.env` has the demo pooler URL:

   ```
   DATABASE_URL=postgresql://postgres.<demo-ref>:...@...pooler.supabase.com:6543/postgres
   ```

2. Run the stack from `LocalDev/`:

   ```bash
   npm run dev        # migrates the demo DB, then starts FastAPI :8001 + Next.js :3000
   ```

For raw SQL against the demo DB:

```bash
psql "$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-)"
```

> **Until the ADR-0002 cleanup lands:** `.env` also carries `SUPABASE_DB_URL`
> and `TEST_DATABASE_URL` (pytest and `npm run migrate` read those first, via
> `with-demo-db.sh`). Keep all three pointed at the same demo pooler URL.
> After the cleanup, `DATABASE_URL` is the only name.

## Connect to prod

**The deployed app** connects on its own: the Vercel project's env provides
the prod connection string. Today the deployed code reads
`POSTGRES_URL_NON_POOLING` (injected by the Vercel↔Supabase integration);
per ADR-0002 the target is an explicit `DATABASE_URL` set to the prod
**transaction pooler** URL. When cutting over, also set `JWT_SECRET` in
Vercel (keep the value the app currently signs with, so sessions survive).

**You**, for inspection or manual SQL, connect with psql and the prod pooler
URL from the production project's dashboard:

```bash
psql "postgresql://postgres.<prod-ref>:...@...pooler.supabase.com:6543/postgres"
```

Treat prod as read-mostly at the console: `big_ledger` and `audit_logs` are
append-only (DELETE-blocked by trigger), so mistakes are permanent. Mutations
belong to the app's RPCs, not ad-hoc SQL.

**Never point `LocalDev/.env`'s `DATABASE_URL` at prod.** If it happens
anyway, the guards in `scripts/db_guard.py` fail closed: pytest,
`npm run seed`, `npm run migrate`, and the `npm run dev` auto-migrate all
refuse any URL that is not the checked-in demo project ref or a local
database — the run aborts before a connection is opened. Fix `.env` and
re-run.

## Migrations

Migrations are plain SQL files in `LocalDev/migrations/*.sql`, applied in
lexical order by `scripts/migrate_db.py`, tracked in the `schema_migrations`
table of whichever database `DATABASE_URL` points at. Each file runs in its
own transaction; only pending files run (idempotent). **Never edit an
already-applied migration — always add a new numbered file.**

### On localdev (demo)

Either is fine:

```bash
npm run dev        # migrates automatically on startup
npm run migrate    # migrations only
```

### On prod

Prod migration is a separate, deliberate command. It reads
**`PROD_DATABASE_URL`** (from the environment or `LocalDev/.env`) and never
`DATABASE_URL`:

```bash
npm run migrate:prod
```

The script verifies the URL matches a known prod project ref
(`PROD_PROJECT_REFS` in `scripts/db_guard.py`), prints the pending
migrations, and requires you to type the prod project ref before applying
anything. For CI, `python3 scripts/migrate_db.py --prod --yes` skips the
prompt.

The old one-off `DATABASE_URL="<prod URL>" python3 scripts/migrate_db.py`
no longer works: the default path allowlists the demo and refuses
everything else.

Deploy ritual: `git push` (Vercel deploys), then migrate prod. Only migrate
prod when the deployed code expects the new schema.

Before a first prod migration run, check what prod believes is applied:

```sql
SELECT name FROM schema_migrations ORDER BY name DESC LIMIT 5;
```

If that lags far behind `LocalDev/migrations/`, stop and reconcile — the live
deployment may be running the older `Prod/` codebase against an older schema,
and applying months of pending migrations under it is not a routine operation.

## Quick reference

| Task | Command |
|---|---|
| Start local stack (migrates demo) | `npm run dev` |
| Migrate demo only | `npm run migrate` |
| Migrate prod | `npm run migrate:prod` (reads `PROD_DATABASE_URL`; typed confirmation) |
| psql into demo | `psql "<demo pooler URL>"` |
| psql into prod | `psql "<prod pooler URL>"` |
| Seed demo with fake data | `npm run seed` |
| Check prod health | `python3 scripts/check_prod_status.py` |
