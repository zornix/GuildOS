# Supabase is hosted Postgres only — the app owns its client and its auth

Both databases (production and demo) are Supabase projects, but the app talks
to them exclusively through its own psycopg2 client (`api/platform/postgres.py`)
over the transaction-mode connection pooler, and authenticates users with its
own HS256 JWTs (`sub = member.id`, signed with `JWT_SECRET`, validated
in-process). supabase-py, PostgREST, GoTrue, and the Data API are deliberately
unused; the Data API is disabled in both projects' settings.

Decided 2026-07-11, when we discovered the supabase-py branch of `api/db.py`
had never carried traffic anywhere — deployed prod, local dev, and pytest all
already ran the psycopg client against a Supabase pooler. Standardising on the
path that actually serves production was pure deletion; standardising on
supabase-py would have meant a first-ever bring-up of PostgREST semantics,
GoTrue auth (which rejects app-issued tokens), and an untested RLS surface.

## Consequences

- One `DATABASE_URL` per environment selects the database (demo pooler
  locally, prod pooler on Vercel). No mode switch, no `use_local_db`, no
  offline Docker fallback. `PROD_DATABASE_URL` exists solely for
  `npm run migrate:prod`.
- `JWT_SECRET` is required with no default — a missing value fails at boot
  rather than issuing forgeable tokens.
- RLS stays enabled on tenant tables as defense-in-depth, but is unexercised
  at runtime (the client connects as the table owner) and untested. It is not
  the security boundary; the backend is.
- pytest refuses to run against a URL containing the prod project ref —
  `big_ledger`/`audit_logs` are append-only, so test garbage in prod would be
  permanent.
- Do not "fix" the absence of supabase-py: it was removed on purpose. If the
  Data API is ever re-enabled, the RLS policies must get real tests first.
