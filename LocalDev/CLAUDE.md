# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GuildOS / FraternityOS — operational software for fraternity chapters (events,
attendance, dues/fines treasury, standing, tasks, announcements, roster, RBAC).
This directory (`LocalDev/`) is the active development sandbox. The git root is
one level up at `/home/mshi/GuildOS`, which also contains `Prod/` and other
sibling copies — `LocalDev/fratos` and `Prod/fratos` are duplicated frontends
that can drift (consolidation is a known open task).

Stack: **FastAPI (Python)** backend + **Next.js 16 App Router (TS/React 19)**
frontend + **PostgreSQL** (raw SQL migrations). Deployed on Vercel
(`api/index.py` as a Python function, `fratos/` as the Next app — see
`vercel.json`).

## Commands

Run from this directory (`LocalDev/`). `npm run *` shells out to
`../local-dev/scripts/local-dev.sh`.

```bash
npm run dev          # Supabase demo DB + migrate + FastAPI + Next.js
npm run dev:docker   # offline: Docker postgres + migrate + FastAPI + Next.js
npm run dev:seed     # dev:docker with fake seed data (SEED_LOCAL_DB=1)
npm run migrate      # apply pending migrations/*.sql against demo db
npm run seed         # seed demo db only (usually unnecessary — demo has data)
```

Local ports: **frontend 3000**, **backend 8001** (`/api/docs` for Swagger).
Database: **Supabase demo pooler** by default (`DATABASE_URL` in `.env`).
Offline fallback: **`npm run dev:docker`** (postgres **5434**, `fraternityos`/`localdev`).

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

### Frontend (run from `LocalDev/fratos/`)

```bash
npm run test:unit    # vitest
npm run test:e2e     # playwright (role flows: auth, events, fines, excuses, checkin, members)
npm run lint         # eslint
npm run build        # next build
```

## Backend architecture

### Domain-package pattern (canonical — use for all new services)

Treasury (`api/treasury/`) is the reference implementation. Every domain follows
the same shape; small domains omit files but **never invent a different layout**:

```
api/<domain>/
  api/router.py      # aggregates the domain's APIRouters; index.py mounts ONLY this
  api/<resource>.py  # thin route handlers: parse → service → respond
  api/schemas.py     # Pydantic v2 models, domain-local (never shared across domains)
  services/          # business logic; pure where possible, no FastAPI imports
  core/              # domain value objects / rules with no I/O (e.g. treasury/core/money.py)
  db/session.py      # client acquisition
  db/rpc.py          # call_rpc(name, params) — the ONLY sanctioned multi-write path
  auth.py            # domain permission constants + capability helpers
  notifications.py   # transactional outbox enqueue helpers
```

Domains: `auth`, `events`, `attendance`, `treasury`, `tasks`, `announcements`,
`memberadmin` (standing), `recruitment`, `bylaws`, `nl_controller`, `rbac`,
`calendar`, `standing`. `api/index.py` is the FastAPI app: it mounts each
domain's top router and applies CORS. A domain router is itself append-only —
sub-routers `include_router` into it and existing includes are never removed.

**Legacy flat modules** (`api/routes/`, `api/services/`, `api/models/schemas.py`)
still hold pre-refactor code. Some domains are "conform shells" that delegate to
them and carry a `CONFORM_TODO.md`. Put new code in the domain package, not the
flat modules.

### Database access abstraction

`api/db.py` returns either a Supabase client (prod) or a `PostgresClient`
(`api/postgres_client.py`, local) that **mimics the supabase-py interface** over
raw psycopg2. The switch is `settings.use_local_db`, which is simply
`bool(DATABASE_URL)` — set `DATABASE_URL` and the whole app talks to local
Postgres with no Supabase. Demo/local auth uses `member.id` as the JWT subject;
Supabase auth uses `auth_id` (see `api/dependencies.py`).

### Migrations

`migrations/*.sql`, applied in **lexical order** by `scripts/migrate_db.py`,
tracked in a `schema_migrations` table (idempotent — only pending files run).
**Never edit an already-applied migration; always add a new numbered file.**

## Hard rules (enforced across the backend)

- **Money is always integer cents (`BIGINT`).** Use the `Money` value object
  (`api/treasury/core/money.py`); it rejects raw floats. The only float→cents
  boundary is `Money.from_numeric`, used solely by the legacy
  `events.fine_amount` → invoices import. Never add another float currency path.
- **Trust-boundary mutations go through plpgsql RPCs** (`db/rpc.py` →
  `call_rpc`). RPC bodies enforce tenant guards (`chapter_id`), idempotency
  (`idempotency_keys`), and write `audit_logs` (plus `big_ledger` for anything
  financial). Don't do multi-row financial writes from Python.
- **`big_ledger` and `audit_logs` are append-only, signed-cents event logs.**
  DB triggers block `DELETE` and allow only `active → invalidated` status flips.
  Model reversals by appending a row with `reverses_entry_id`, never by mutating
  history. The `EntryType` / `AuditAction` enums are frozen — reuse existing
  values rather than widening them.
- **Every tenant table carries `chapter_id` and has RLS enabled.**
- **Permission checks** go through `api/rbac` only
  (`require_permission(...)` / `permissions.has_permission(...)`). No inline
  `user["role"] == "officer"` string comparisons in new code.
- **No fabricated business logic.** If a behavior isn't implemented (e.g. bylaws
  Q&A has no RAG), return an explicit `not_implemented` status — never fake an
  answer.

See `docs/ARCHITECTURE.md`, `docs/TREASURY_ARCHITECTURE.md`, and
`docs/services/README.md` for the authoritative deep dives.

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
