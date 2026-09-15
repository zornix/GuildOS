# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GuildOS / FraternityOS — operational software for fraternity chapters (events,
attendance, dues/fines treasury, standing, tasks, announcements, roster, RBAC).
This directory (`LocalDev/`) is the active development sandbox. The git root is
one level up at `/home/mshi/GuildOS`. The product frontend is `LocalDev/greekos`
(Vite + React). The previous Next.js UI (`LocalDev/fratos`) was archived to the
gitignored `archive/` on 2026-09-15 (git tag `last-with-localdev-fratos`).

Stack: **FastAPI (Python)** backend + **Vite/React (greekos)** frontend +
**PostgreSQL** (raw SQL migrations). Local preview can use this folder's
`vercel.json` (`greekos/`). The live FraternityOS site is `Prod/` (`fratos/`
is a clone of greekos — see `Prod/vercel.json`).

**Temporary:** the Vercel production `DATABASE_URL` still points at the demo
Supabase project until a prod project is created.

## Commands

Run from this directory (`LocalDev/`). `npm run *` shells out to
`../local-dev-scripts/scripts/local-dev.sh`.

```bash
npm run dev          # Supabase demo DB + migrate + FastAPI + greekos (Vite)
npm run migrate      # apply pending migrations/*.sql against demo db
npm run seed         # seed demo db only (usually unnecessary — demo has data)
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
  notifications.py   # transactional outbox enqueue helpers
```

Db plumbing is **not** per-domain: client acquisition, `call_rpc`, row
unwrapping and delivery-mode all come from `api/platform/` (below). A domain
never has a `db/` directory for those, and never re-exports
`require_permission` — route files import it from `api.rbac.auth` directly.

Domains live one per directory under `api/<domain>/` — run `ls api/` for the
authoritative list (currently ~16: `auth`, `events`, `attendance`, `treasury`,
`tasks`, `announcements`, `memberadmin` (owns standing), `members`,
`recruitment`, `bylaws`, `nl_controller`, `rbac`, `calendar`, `initiatives`,
`cron`, `instrumentation`, plus `platform`, which is plumbing rather than a
domain). `api/index.py` is the FastAPI app: it mounts every router and applies
CORS. Only `attendance`, `events`, `tasks` and `treasury` keep an
`api/router.py` aggregator, because their include order is load-bearing (fixed
segments must be registered before parameterized ones); such a router is
append-only — sub-routers `include_router` into it and existing includes are
never removed. Domains that also expose standalone routers on their own mount
prefixes (`excuses_router`, `checkin_links_router`, `fines_router`) re-export
them for `index.py`. **Mounted URL paths are frozen**: check `greekos/src/api.ts`
before changing any prefix.

**No legacy flat modules.** `api/routes/`, `api/services/` and `api/models/`
are gone — every handler, service and schema lives in its domain package.

### `api/platform/` — the one database layer

There is exactly **one** database path, in every environment (ADR-0002):

```
api/platform/
  db.py         # get_db() — the lazy singleton PostgresClient. The ONLY accessor.
  postgres.py   # PostgresClient: a PostgREST-shaped query builder over psycopg2
  rpc.py        # call_rpc(name, params, *, sb=None) — the ONLY multi-write path
  rows.py       # unwrap_row(result) — first row whether the result is a list or not
  delivery.py   # delivery_mode() — settings.MESSAGE_DELIVERY_MODE, never os.environ
```

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

## Hard rules (enforced across the backend)

- **Money is always integer cents (`BIGINT`).** Use the `Money` value object
  (`api/treasury/core/money.py`); it rejects raw floats. The only float→cents
  boundary is `Money.from_numeric`, used solely by the legacy
  `events.fine_amount` → invoices import. Never add another float currency path.
- **Trust-boundary mutations go through plpgsql RPCs**
  (`api/platform/rpc.py` → `call_rpc`). RPC bodies enforce tenant guards (`chapter_id`), idempotency
  (`idempotency_keys`), and write `audit_logs` (plus `big_ledger` for anything
  financial). Don't do multi-row financial writes from Python.
- **`big_ledger` and `audit_logs` are append-only, signed-cents event logs.**
  DB triggers block `DELETE` and allow only `active → invalidated` status flips.
  Model reversals by appending a row with `reverses_entry_id`, never by mutating
  history. The `EntryType` / `AuditAction` enums are frozen — reuse existing
  values rather than widening them.
- **Every tenant table carries `chapter_id` and has RLS enabled.** On the
  direct-Postgres path (ADR-0002) the runtime tenant guard is the RPC layer —
  the RPC body validates every referenced row against the caller's
  `chapter_id`; RLS is defense-in-depth for any non-privileged access, not the
  runtime enforcement layer.
- **Permission checks** go through `api/rbac` only
  (`require_permission(...)` / `permissions.has_permission(...)`). No inline
  `user["role"] == "officer"` string comparisons in new code.
- **No fabricated business logic.** If a behavior isn't implemented (e.g. bylaws
  Q&A has no RAG), return an explicit `not_implemented` status — never fake an
  answer.

See `docs/ARCHITECTURE.md`, `docs/CODEMAP.md` (guided file order),
`docs/TREASURY_ARCHITECTURE.md`, and `docs/services/README.md` for the
authoritative deep dives.

## Frontend architecture

Layered to keep visual redesigns independent of business logic (full spec in
`../FrontendConventions.md`):

- **Pages** (`app/`) are thin — compose modules, no markup/styling/`fetch`.
- **Module components** (`components/modules/<module>/`) own product workflows
  and receive frontend-facing shapes; they must not know whether data came from
  the API or a mock.
- **UI primitives** (`components/ui/`) own generic appearance/variants
  (`Btn`, `Card`, `Badge`, `DataTable`, `StatCard`, `SegmentedControl`,
  `EmptyState`, `LoadingState`, …). They take semantic variants
  (`tone="warning"`), never product-specific names.
- **API clients** (`lib/api-client.ts`) fetch DTOs; **adapters**
  (`lib/adapters/`) convert backend DTOs → stable frontend **contracts**
  (`lib/contracts/`). Do all snake→camel, cents→dollars, status-label, and date
  formatting in adapters/formatters (`lib/formatters/`), never inline in
  components. Avoid `return data as T` at module/UI boundaries.
- **Design tokens** live in `config/theme/tokens.ts`; navigation + role/capability
  gating live in `config/navigation.ts`, not scattered `user.role` checks.

Money in the UI always passes through `formatMoney(cents)`
(`lib/formatters/money.ts`). Views are migrating from monolithic
`views/<name>.tsx` files into the `components/modules` layering — prefer the
module structure for new work.
