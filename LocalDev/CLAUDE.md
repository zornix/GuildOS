# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GuildOS / FraternityOS — operational software for fraternity chapters (events,
attendance, dues/fines treasury, standing, tasks, announcements, roster, RBAC).
This directory (`LocalDev/`) is the active development sandbox. The git root is
one level up. The product frontend is `LocalDev/greekos` (Vite + React).
The previous Next.js UI (fratos) was archived to the gitignored archive/ on
2026-09-15 (git tag `last-with-localdev-fratos`).

Stack: **FastAPI (Python)** backend + **Vite/React (greekos)** frontend +
**PostgreSQL** (raw SQL migrations). Local preview can use this folder's
`vercel.json` (`greekos/`). The live FraternityOS site is `Prod/` (`Prod/fratos`
is a clone of `LocalDev/greekos` — see `Prod/vercel.json`).

**Temporary:** the Vercel production `DATABASE_URL` still points at the demo
Supabase project until a prod project is created.


## Commands

Run from this directory (`LocalDev/`). `npm run *` shells out to
`../local-dev-scripts/scripts/local-dev.sh`.

```bash
npm run dev          # Supabase demo DB + migrate + FastAPI + greekos (Vite)
npm run migrate      # apply pending migrations/*.sql against demo db
npm run seed         # seed demo db only (usually unnecessary — demo has data)
npm run reset-demo   # wipe demo db, replay all migrations, reseed (-- --dry-run to test)
```

Local ports: **frontend 3000**, **backend 8001** (`/api/docs` for Swagger).
Database: **Supabase demo pooler** (`DATABASE_URL` in `.env`). Both demo and
prod are Supabase projects reached over the pooler — there is no local Docker
DB (see `docs/adr/0002-supabase-is-hosted-postgres-only.md`).

### Backend tests (pytest, run from `LocalDev/`)

```bash
python3 -m pytest                                   # full suite
python3 -m pytest tests/treasury/                   # one domain
python3 -m pytest tests/treasury/test_chunkA_receivables.py::test_name   # single test
```

`pytest.ini` sets `asyncio_mode=auto` (no per-test `@pytest.mark.asyncio`
needed). Tests connect to a **real Postgres** via `TEST_DATABASE_URL` /
`SUPABASE_DB_URL` (read from env or `LocalDev/.env`) — they need a running DB,
and treasury tests use a superuser connection that **bypasses RLS** (for
trigger/RPC tests); RLS-policy tests use a member JWT instead.

### Frontend (run from `LocalDev/greekos/`)

```bash
npm test             # node:test
npm run lint         # tsc --noEmit
npm run build        # vite build
```

## Backend architecture

### Domain-package pattern (canonical — use for all new services)

Treasury (`api/treasury/`) is the reference implementation. Every domain follows
the same shape; small domains omit files but **never invent a different layout**:

```
api/<domain>/
  api/<resource>.py  # thin route handlers: parse → service → respond
  api/schemas.py     # Pydantic v2 models, domain-local (never shared across domains)
  api/router.py      # ONLY when the domain has several sub-routers whose include
                     # order matters; otherwise index.py mounts the resource router
  services/          # business logic; pure where possible, no FastAPI imports
  core/              # domain value objects / rules with no I/O (e.g. treasury/core/money.py)
  auth.py            # domain permission-key constants + domain capability helpers
  notifications.py   # outbox enqueue helpers
```

Db plumbing is **not** per-domain: client acquisition, `call_rpc`, row
unwrapping and delivery-mode all come from `api/platform/` (below). A domain
never has a db directory for those, and never re-exports
`require_permission` — route files import it from `api.rbac.auth` directly.

Domains live one per directory under `api/<domain>/` — run `ls api/` for the
authoritative list (currently ~15: `auth`, `events`, `attendance`, `treasury`,
`tasks`, `announcements`, `memberadmin` (owns standing), `members`,
`bylaws`, `nl_controller`, `rbac`, `calendar`, `initiatives`,
`cron`, `instrumentation`, plus `platform`, which is plumbing rather than a
domain). `api/index.py` is the FastAPI app: it mounts every router and applies
CORS. Only `attendance`, `events`, `tasks` and `treasury` keep an
`api/<domain>/api/router.py` aggregator, because their include order is load-bearing (fixed
segments must be registered before parameterized ones); such a router is
append-only — sub-routers `include_router` into it and existing includes are
never removed. Domains that also expose standalone routers on their own mount
prefixes (`excuses_router`, `checkin_links_router`, `fines_router`) re-export
them for `index.py`. **Mounted URL paths are frozen**: check `greekos/src/api.ts`
before changing any prefix.

**No legacy flat modules.** Legacy routes, services and models under `api/`
are gone — every handler, service and schema lives in its domain package.

### `api/platform/` — the one database layer

There is exactly **one** database path, in every environment (ADR-0002):

```
api/platform/
  db.py         # get_db() — the lazy singleton PostgresClient. The ONLY accessor.
  postgres.py   # PostgresClient: a PostgREST-shaped query builder over psycopg2
  rpc.py        # call_rpc(name, params, *, sb=None) — RPC helper
  rows.py       # unwrap_row(result) — first row whether the result is a list or not
  delivery.py   # delivery_mode() — settings.MESSAGE_DELIVERY_MODE, never os.environ
```

A plpgsql RPC is the path for trust-boundary writes that need an audit row; `transaction()` is for multi-statement writes that do not.

```python
with get_db().transaction() as tx:      # tx is a PostgresClient bound to ONE connection
    tx.table("events").update({...}).eq("id", event_id).execute()
    call_rpc("ev_set_audience", {...}, sb=tx)
# commit on normal exit; rollback and re-raise on any exception
```

Rules for callers:
1. Every helper called inside the block must take the client as a parameter and use it; a helper that calls `get_db()` itself runs outside the transaction.
2. Never catch a database error inside the block and carry on: the transaction is already aborted, and exit raises `RuntimeError`.
3. "Insert unless it exists" inside a transaction must use `insert(..., ignore_conflict=...)`, never try/except on a unique violation.

`DATABASE_URL` selects the database (demo or prod — both Supabase pooler URLs);
`get_db()` raises at first use if it is unset, and the production boot guard in
`api/index.py` refuses to start without it. supabase-py is not a dependency and
there is no second code path: `_LocalAuth` in `api/platform/postgres.py` is *the*
JWT verifier (`sub = member.id`, HS256 over `JWT_SECRET`, `iss`/`aud` =
`guildos`) and every token carries our `ver` claim, checked against
`members.token_version` in `api/dependencies.py`. RLS policies are
defense-in-depth only — the runtime tenant guard is the RPC layer (see Hard
rules).

**RPC params typed as true SQL arrays need registration.** The client
JSON-encodes every list/dict RPC param, which is correct for JSONB-typed
params but breaks a plpgsql param declared as a real array (first case:
`in_create_initiative.p_chair_member_ids UUID[]`). Any new array-typed RPC
param must be added to `_ARRAY_TYPED_RPC_PARAMS` in `api/platform/postgres.py`.

### Migrations

`migrations/*.sql`, applied in **lexical order** by `scripts/migrate_db.py`,
tracked in a `schema_migrations` table (idempotent — only pending files run).
**Never edit an already-applied migration; always add a new numbered file.**
After adding a migration, run `python3 scripts/migration_checksums.py --update`.

## Hard rules (enforced across the backend)

- **Money is always integer cents (`BIGINT`).** Use the `Money` value object
  (`api/treasury/core/money.py`); it rejects raw floats. The only float→cents
  boundary is `Money.from_numeric`, called only by `FineToInvoice` in
  `api/treasury/api/schemas.py`, an unused compatibility DTO retained for tests.
  Live fines use integer cents through `tr_issue_event_fines`. Never add another float currency path.
- **Trust-boundary mutations go through plpgsql RPCs**
  (`api/platform/rpc.py` → `call_rpc`). RPC bodies enforce tenant guards (`chapter_id`), idempotency
  (`idempotency_keys`), and write `audit_logs` (plus `big_ledger` for anything
  financial). Don't do multi-row financial writes from Python.
- **`big_ledger` and `audit_logs` are append-only, signed-cents event logs.**
  DB triggers block `DELETE` and allow only `active → invalidated` status flips.
  Model reversals by appending a row with `reverses_entry_id`, never by mutating
  history. The `EntryType` / `AuditAction` enums are frozen — reuse existing
  values rather than widening them.
- **RLS exists on 45 tables; the app connects as the table owner, so RLS never applies at runtime; Supabase API roles hold no grants since migration 0171.**
  The runtime tenant guard is the RPC layer — the RPC body validates every
  referenced row against the caller's `chapter_id`; RLS is defense-in-depth.
- **Permissions come from `member_roles` plus an implicit `member` baseline.** The `members.role` column is
  display-only, kept in step by the RPCs. Permission checks go through `api/rbac`
  only (`require_permission(...)` / `permissions.has_permission(...)`). No inline
  `user["role"] == "officer"` string comparisons in new code.
- **Admin tier rules.** `admin` and `president` are granted or revoked only by an
  admin, and every chapter keeps at least one admin.
- **Event times are local to `chapters.timezone`.** Default is
  "America/Los_Angeles".
- **Outbox delivery.** The outbox enqueue runs after commit unless given a
  transaction client.
- **No fabricated business logic.** If a behavior isn't implemented (e.g. bylaws
  Q&A has no RAG), return an explicit `not_implemented` status — never fake an
  answer.

See `docs/ARCHITECTURE.md`, `docs/CODEMAP.md` (guided file order),
`docs/TREASURY_ARCHITECTURE.md`, and `docs/services/README.md` for the
authoritative deep dives.

## Frontend architecture

The frontend (`LocalDev/greekos/`) is a single-page React app with no router; `App.tsx` switches tabs.
- `hooks/useAppData.ts` composes the domain hooks.
- `api.ts` is the fetch client and DTO types.
- `adapters.ts` converts DTOs to the shapes in `types.ts`.
- Pure logic lives in `lib/*.ts` with a sibling `*.test.ts` run by `npm test`.
- Permissions come from `GET /api/rbac/me/permissions` and are checked with `can()`.
- Money is integer cents and is displayed through `formatMoney` in `formatters.ts`.

### Frontend rules

- A success toast only after the server answers.
- Nothing on screen that the server did not return.
- New logic goes in `lib/` with a test.

## Conventions

| Concern | Do | Do not |
|---|---|---|
| Multi-row or trust-boundary writes | Trust-boundary writes use a plpgsql RPC with chapter guards and audit/ledger rows; other multi-statement writes use `transaction()` | Sequences of autocommitted statements that must succeed together |
| Money | BIGINT cents in DB, `Money` in Python, `formatMoney`/`dollarsToCents` in TS | `NUMERIC` columns; `Decimal→float` in `_serialize` |
| Authority | `require_permission(*keys)` dependencies, `permissions.has_permission` in services, `can(permissions, key)` in the SPA | Authority inferred from display-only `members.role` or inline role-string checks |
| Identity equality | SQL query rows serialize UUIDs to strings in `QueryBuilder._serialize`; SQL RPC results retain their returned JSON shape | Assuming RPC results pass through the query-row serializer |
| Tenant scope | Session `chapter_id` passed into an RPC that re-checks every referenced row | Trusting RLS |
| Idempotency | `UNIQUE(chapter_id, operation, key)`; `tr_bulk_create_invoices` (0169) and `tr_record_payment` (0205) check `request_hash`; keys never expire | Reusing a dues-run or record-payment key after changing the payload |
| Invoice status and "owed" | `tr_refresh_invoice_status`; `remaining_by_invoice` for fine standing, reminders and open-invoice displays; `BalanceEngine` as the balance reader for treasury totals | Ignoring allocations, reversals or partially paid invoices when calculating remaining cents |
| Errors | Events/initiatives map named domain exceptions; raw database errors use fixed messages through `api/platform/errors.py::public_message` where wired | Exposing raw database exception text in HTTP responses |
| Time | Timestamp columns use timestamptz; event dates/times remain separate and resolve through chapter-timezone timing helpers | Treating a chapter-local event time as UTC |
| Notifications | Treasury enqueue runs after commit; failures log outside a transaction and raise with a transaction client. Inline SMS `dispatch_send` atomically claims pending rows before sending; the cron drain also delivers queued rows | Sending SMS without claiming rows first |
| Configuration | Typed `Settings` in `api/config.py`; `.env.example` is maintained separately | Bypassing Settings in new runtime code or documenting unused env names |
| Frontend data | Domain hooks + pure adapters; toast after `await` | Optimistic toast before the request; client-local "ledgers" |
| Frontend forms and validation | Pure `lib/*.ts` validators where extracted; return shapes vary by form (e.g. auth validators return an error string or null) | Inventing a shared validator contract that existing forms do not implement |
| Frontend permissions | `can(permissions, key)` | `isOfficer`, `isOfficerView` |
| Tests | Real DB fixtures with per-test chapters; dependency-override clients; name tests by invariant | `FakeSb`; patching `recompute_member_balance`; AST-only tests |
| Imports | Absolute `api.*` imports | Cross-domain imports of private helpers |
| Naming | `snake_case` Python; `tr_` / `ev_` / `at_` / `tk_` RPC prefixes; permission keys use two or three segments; existing DB helpers commonly take `sb` | Renaming established helper arguments as a drive-by change |
| Directory shape | `api/<domain>/{api,services,core,auth.py}` as a menu, not a mandate | Per-domain db directories, repositories directories |
| Logging | Named loggers; the global filter adds request id only; chapter/outbox context must be supplied by the caller | Assuming the request-id filter adds tenant or outbox identifiers |
| Route paths | Frozen; new collection routes without trailing slash | Mixed trailing slashes |
