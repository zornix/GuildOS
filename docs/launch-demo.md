# Launch the demo

Run the GuildOS demo chapter locally: FastAPI + the greekos UI against the
shared **demo** Supabase database. There is no local Docker Postgres.

When it is up: frontend at http://localhost:3000, API at
http://localhost:8001, Swagger at http://localhost:8001/api/docs.

## Prerequisites

- Node.js (for the Vite frontend)
- Python 3 with `pip` (for FastAPI / uvicorn)
- A `DATABASE_URL` for the **demo** Supabase pooler. Get this from a teammate;
  it is a secret and is not in the repo.

Copy `LocalDev/.env.example` → `LocalDev/.env` if you do not already have
`.env`. Set at least:

```
DATABASE_URL=postgresql://postgres.<demo-ref>:...@...pooler.supabase.com:6543/postgres
```

Use the **transaction pooler** URL (port 6543), not the direct
`db.<ref>.supabase.co` host. How to copy it from the dashboard is in
[LocalDev/docs/DATABASE.md](../LocalDev/docs/DATABASE.md).

Leave `JWT_SECRET` as the example value for local. Keep `DEV_AUTH_BYPASS`
false unless you want the local one-click officer login (see below).

## Launch

From `LocalDev/`:

```bash
cd LocalDev
npm run dev
```

That script (`local-dev-scripts/scripts/local-dev.sh`) will:

1. Refuse to start if `.env` is missing or `DATABASE_URL` is still a
   placeholder.
2. Apply pending `migrations/*.sql` to the demo database.
3. Install Python deps (`requirements.txt`) if FastAPI is missing, and
   `greekos/node_modules` if needed.
4. Stop anything already listening on `:8001` / `:3000`.
5. Start FastAPI on **8001** and greekos (Vite) on **3000**. Vite proxies
   `/api` to the backend.

Ctrl+C stops both.

## Sign in

The demo chapter is **Delta Mu / TKE**. Use the seeded officer:

| Field    | Value             |
|----------|-------------------|
| Email    | `jake@tke.org`    |
| Password | `demo-officer-pw` |

That officer has `admin`, `president`, and `treasurer` roles, so the
permission-gated screens (events, treasury, roster, …) are usable.

Seeded members (`ryan@tke.org`, `tyler@tke.org`, …) use the same password.
Use those accounts to see the member-side UI.

**Local only:** every `vite dev` build shows **Local only: sign in as seeded
officer** on the login page; `DEV_AUTH_BYPASS=1` in `LocalDev/.env` is what
decides whether the button actually signs you in. The endpoint is 404 on any
Vercel deploy. Do not enable the bypass on a machine that is reachable from
the network.

## Optional commands

Still from `LocalDev/`:

```bash
npm run migrate   # apply pending migrations only
npm run seed      # wipe and recreate the demo chapter's seed rows
```

**Do not run `npm run seed` against a database that already has chapter
data you care about.** Seed deletes the demo chapter's members, events,
ledger rows, and related data, then re-inserts fixtures. The shared demo
project is already seeded; you usually do not need this. A 2026-07-17 reseed
wiped operational rows and had to be restored by hand.

## Checks if it failed

| Symptom | What to do |
|---------|------------|
| Script exits asking to fill `DATABASE_URL` | Copy `.env.example` → `.env` and set the demo pooler URL, then re-run. |
| Guard refuses the database | `DATABASE_URL` is not the checked-in demo project. Point `.env` at demo, never prod. |
| Port already in use | `npm run dev` tries to kill listeners on 8001/3000; if it still fails, stop the leftover process and retry. |
| Frontend loads, API 404s | Backend did not come up. Check the uvicorn log in the same terminal; Swagger should be at `/api/docs`. |
| Login rejected for Jake | Demo already has data; do not reseed unless you intend to wipe it. Confirm you are on the demo URL, not prod. |

## What this is not

- Not a second stack. `Prod/` is the Vercel root; it uses the same demo
  database until a real prod project exists. Launching locally is
  `LocalDev/` only.
- Not the old Next.js app. `LocalDev/fratos` is left behind; greekos is the
  UI `npm run dev` starts.
- Not a local database. Both demo and prod are hosted Supabase Postgres
  (see [ADR-0002](adr/0002-supabase-is-hosted-postgres-only.md)).
