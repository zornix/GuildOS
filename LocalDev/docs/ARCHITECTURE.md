# GuildOS Architecture & Conventions

Last updated: 2026-07-03

**Purpose of this document:** everything a coding agent needs to work in this
repo without re-exploring the codebase. Read this plus `LocalDev/CLAUDE.md`
(auto-loaded) before writing code. Deep dives:
[TREASURY_ARCHITECTURE.md](TREASURY_ARCHITECTURE.md) (ledger/money internals),
[services/README.md](services/README.md) (per-service docs),
`../../FrontendConventions.md` (full frontend spec),
[events-v1-spec.md](events-v1-spec.md) + [events-dev-status.md](events-dev-status.md)
(current feature work).

---

## 1. System overview

GuildOS / FraternityOS: operational software for fraternity chapters — events,
attendance, dues/fines treasury, standing, tasks/jobs, announcements, roster,
RBAC, calendar.

| Layer | Technology | Local port | Notes |
|-------|------------|------------|-------|
| Frontend | Next.js 16 App Router, React 19, TS | 3000 | `fratos/` — currently a single-route SPA (see §6) |
| Backend | FastAPI (Python 3) | 8001 | `api/` — Swagger at `/api/docs` |
| Database | PostgreSQL, raw SQL migrations | 5434 (docker) / Supabase pooler | plpgsql RPCs for all multi-row mutations |

Deployment: Vercel — `api/index.py` as a Python serverless function, `fratos/`
as the Next app (see `vercel.json`).

### Repo geography (important)

The git root is `/home/mshi/GuildOS`, one level **above** this directory.

- `LocalDev/` — **the active development sandbox. All new work happens here.**
- `Prod/` — sibling copy; `LocalDev/fratos` and `Prod/fratos` are duplicated
  frontends that **drift** (consolidation is a known open task — don't assume
  they match).
- `GreekV1/`, `greekos-landing/` — older copy / marketing site.
- `local-dev-scripts/` — tooling; `LocalDev/package.json` scripts shell out to
  `local-dev-scripts/scripts/local-dev.sh`.

### LocalDev layout

```
LocalDev/
  api/                  # FastAPI backend (domain packages, see §2)
  migrations/           # NNNN_name.sql, applied in lexical order (see §4)
  tests/                # pytest, per-domain dirs (see §5)
  fratos/               # Next.js frontend (see §6)
  scripts/              # migrate_db.py, seed scripts
  docs/                 # this file, specs, imp-*.md plan docs (see §8)
  pytest.ini            # asyncio_mode=auto
  package.json          # npm run dev / dev:docker / dev:seed / migrate / seed
  .env                  # DATABASE_URL etc. (not committed)
```

Commands, ports, and test invocations are in `LocalDev/CLAUDE.md` — not
repeated here.

---

## 2. Backend: domain-package pattern

`api/index.py` is the app factory: it mounts **only** each domain's aggregate
router (`api/<domain>/api/router.py`) and applies CORS. Domain routers are
**append-only** — sub-routers `include_router` into them; existing includes are
never removed.

Domains: `auth`, `events`, `attendance`, `treasury`, `tasks`, `announcements`,
`memberadmin` (standing), `recruitment`, `bylaws`, `nl_controller`, `rbac`,
`calendar`, `standing`, `cron`, `instrumentation`, `members`.

**Treasury (`api/treasury/`) is the reference implementation.** `events/` and
`tasks/` are also modern examples. Every domain follows this shape; small
domains omit files but never invent a different layout:

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

**Legacy flat modules** (`api/routes/`, `api/services/`,
`api/models/schemas.py`) hold pre-refactor code. Some domains are "conform
shells" that delegate to them and carry a `CONFORM_TODO.md`. Put new code in
the domain package, never in the flat modules.

Route-handler error mapping convention: services raise domain exceptions or
return status strings; handlers map to **403** (permission/authority), **404**
(missing or cross-tenant — never leak existence), **409** (state conflicts:
idempotency replay mismatch, cooldown, already-claimed), **422** (Pydantic
validation).

### Database access abstraction

`api/db.py` returns either a Supabase client (prod) or a `PostgresClient`
(`api/postgres_client.py`) that **mimics the supabase-py interface** over raw
psycopg2. The switch is `settings.use_local_db`, which is simply
`bool(DATABASE_URL)` — set `DATABASE_URL` and the whole app talks to local
Postgres with no Supabase.

Auth (`api/dependencies.py::get_current_user`): demo/local JWTs use
`sub = member.id`; Supabase auth uses `auth_id`. HS256, decoded into
`{id, chapter_id, role, ...}`. `chapter_id` always comes from the token —
**never from a client payload**.

### RPC pattern (trust-boundary mutations)

All multi-row / financial / state-machine writes go through plpgsql RPCs called
via the domain's `db/rpc.py::call_rpc(name, params)`. RPC naming is prefixed
per domain: `tr_*` (treasury), `ev_*` (events), `tk_*` (tasks), `rbac_*`,
`in_*` (initiatives, planned). Every RPC body enforces, in this order:

1. **Tenant guard** — every row touched is filtered by `p_chapter_id`; a
   cross-tenant id behaves as "not found".
2. **Authority check** — permission or membership check inside the RPC when the
   rule is per-row (e.g. "is this actor a supervisor of *this* event").
3. **Idempotency** — insert into `idempotency_keys`; on conflict, return the
   stored response (replay) or raise a conflict.
4. **The writes** — atomic within the function.
5. **Audit** — append to `audit_logs`; anything financial also appends to
   `big_ledger`; user-facing notifications enqueue an outbox row.

Never do multi-row financial writes from Python.

### Notifications (transactional outbox)

Domains enqueue via their `notifications.py` helpers into an outbox table
inside the same transaction as the state change (usually from within the RPC).
A dispatcher (`dispatch_send`, keyword-only `send_table=` parameter selects the
per-feature sends table, e.g. `event_notification_sends` from 0143) fans out
later. Never send directly from a route handler.

---

## 3. Hard rules (enforced, non-negotiable)

- **Money is always integer cents (`BIGINT`).** Use the `Money` value object
  (`api/treasury/core/money.py`); it rejects raw floats. The only float→cents
  boundary is `Money.from_numeric`, used solely by the legacy
  `events.fine_amount` → invoices import. Never add another float currency path.
- **`big_ledger` and `audit_logs` are append-only, signed-cents event logs.**
  DB triggers block `DELETE` and allow only `active → invalidated` status
  flips. Model reversals by appending a row with `reverses_entry_id`, never by
  mutating history. The `EntryType` / `AuditAction` enums are frozen — reuse
  existing values rather than widening them (new audit actions go through the
  CHECK-rebuild migration pattern, §4).
- **Every tenant table carries `chapter_id` and has RLS enabled.** Policies key
  on `rbac_request_chapter_id()`. The backend connects with a service role, so
  RLS is defense-in-depth — the *operative* guards are the token-derived
  `chapter_id` filters in routes and RPCs. New tables still must ship RLS
  policies in the same migration (copy the pattern from 0141).
- **Permission checks go only through `api/rbac`** —
  `require_permission("domain:resource:action")` as a route dependency, or
  `permissions.has_permission(...)` in services. **No
  `user["role"] == "officer"` string comparisons in new code.** Per-row
  authority (e.g. event supervisors, initiative chairs) is membership-table
  lookup, not role strings. Chair roles are enumerated once in
  `api/events/auth.py::CHAIR_ROLES`.
- **No fabricated business logic.** If a behavior isn't implemented (e.g.
  bylaws Q&A has no RAG), return an explicit `not_implemented` status — never
  fake an answer.

---

## 4. Migrations

`migrations/NNNN_name.sql`, applied in **lexical order** by
`scripts/migrate_db.py`, tracked in `schema_migrations` (idempotent — only
pending files run). Current frontier: **0143** (`0143_event_notify.sql`); next
free number is **0144**.

**Never edit an already-applied migration; always add a new numbered file.**

Established patterns to copy (don't invent alternatives):

- **New tenant table:** `chapter_id UUID NOT NULL` + FK, `ENABLE ROW LEVEL
  SECURITY`, SELECT policy on `chapter_id = rbac_request_chapter_id()`, writes
  via service-role RPCs only. Model: `event_supervisors` in 0141.
- **Extending a CHECK-constraint catalog** (e.g. `audit_logs.action`,
  outbox/notification types): rebuild the constraint inside a `DO $$` block
  that drops and re-adds it with the widened value list. `audit_logs.action`
  uses the dual-format variant (handles both legacy and current constraint
  names). Models: 0142, 0143.
- **Changing a plpgsql function signature:** `DROP FUNCTION IF EXISTS
  name(old, arg, types);` then `CREATE FUNCTION` with the new signature. **No
  overloads** — new optional params go at the end with `DEFAULT NULL`. Model:
  `tk_create_task` in 0110.
- **Seeding permissions:** `INSERT INTO permissions ... ON CONFLICT DO
  NOTHING` + `role_permissions` rows for each granted role **including explicit
  admin rows** (admin is not implicit). Model: 0130.

---

## 5. Backend testing

Run from `LocalDev/`: `python3 -m pytest` (invocation variants in CLAUDE.md).
`pytest.ini` sets `asyncio_mode=auto` — no per-test `@pytest.mark.asyncio`.

Tests hit a **real Postgres** via `TEST_DATABASE_URL` / `SUPABASE_DB_URL` (read
from env or `LocalDev/.env`) — a running DB is required (`npm run dev:docker`
provides one on 5434).

Test dirs: `tests/{treasury, events, tasks, calendar_view, announcements,
memberadmin, rbac, services_scaffold}`. There is **no root conftest** —
`tests/treasury/conftest.py` is the base fixture set, and other domains
star-import it:

```python
from tests.treasury.conftest import *  # noqa: F401,F403
```

Fixture vocabulary (defined in treasury's conftest or the per-domain ones):

- `db_url`, `cursor`, `chapter_id`, `member_factory`, `sb_client` — base DB
  fixtures. The cursor is a **superuser connection that bypasses RLS** (for
  trigger/RPC assertions); RLS-policy tests use a member JWT instead.
- `harness` — builds a minimal FastAPI app mounting **only** the routers under
  test, overrides `get_current_user`; use as
  `harness.login(user).get("/api/...", params=...)`.
- `user_factory(role=...)`, `assign_role(member_id, role_key)`,
  `grant_treasury_read(member_id)` — identity/permission setup.
- `create_event(actor, **overrides)`, `invoice_factory(member_id=, due_in_days=,
  amount_cents=, status=)`, `task_factory(due_on=, event_id=)` — domain data.

Convention: **don't hardcode absolute date windows** in time-sensitive
assertions — compute them with `date.today() + timedelta(...)` so tests don't
rot (a hardcoded June-2026 window already caused one flake).

---

## 6. Frontend (`fratos/`)

Layered so visual redesigns stay independent of business logic. Full spec:
`../../FrontendConventions.md`. Audit + migration plan:
[imp-fe-remediation.md](imp-fe-remediation.md) (findings F1–F11, phases A–E).

### Layering (target — enforce in all new code)

| Layer | Location | Owns | Must not |
|-------|----------|------|----------|
| Pages | `app/` | compose modules, route params | markup, styling, `fetch` |
| Layout | `components/layout/` | shell, sidebar, topbar, nav rendering | product logic |
| Modules | `components/modules/<module>/` | product workflows, receive frontend contracts | know whether data came from API or mock; generic styling |
| UI primitives | `components/ui/` | `Btn`, `Card`, `Badge`, `Modal`, `DataTable`, `StatCard`, `SegmentedControl`, `EmptyState`, `LoadingState`, … semantic variants (`tone="warning"`) | product-specific names |
| API clients | `lib/api-client.ts` | fetch DTOs, retries, auth headers | shape conversion |
| Adapters | `lib/adapters/<domain>.ts` | DTO → contract: snake→camel, cents→dollars, status labels, date formatting | — |
| Contracts | `lib/contracts/<domain>.ts` | stable frontend-facing types | — |
| Formatters | `lib/formatters/` | `formatMoney(cents)`, dates, status | — |
| Config | `config/theme/tokens.ts`, `config/navigation.ts` | design tokens; nav + role/capability gating | — |

### Current reality (know before editing)

- The app is a **single-route SPA**: `app/page.tsx` renders
  `fraternity-os-frontend.tsx`, which owns nav state and switches between
  `views/*.tsx`. Views are mid-migration into `components/modules/` — prefer
  the module structure for new work; App Router segment split is planned
  (remediation Phase D).
- **Adapters/contracts exist only for treasury** (`lib/adapters/treasury.ts`).
  Everything else still flows raw DTOs via `lib/types.ts` and `as T` casts in
  `api-client.ts` (remediation Phase B fixes this, events first).
- **Two theme systems coexist:** legacy `lib/theme.ts` (`T.*`, colors only) and
  canonical `config/theme/tokens.ts`. Use `tokens.*` in new code; `T.*`
  importers are being burned down.
- `Badge` still takes raw colors (`color="red"`), not tones.
- Role gating: use `config/navigation.ts` + capability helpers; raw
  `user.role === "officer"` checks exist in old code but must not be added.
- `mocks/data/` is dead code pending Phase E.

### Money in the UI

**Always** `formatMoney(cents)` from `lib/formatters/money.ts`. One legacy trap:
`Event.fine_amount` is **float dollars** (the only float money path in the
system) — render it as `formatMoney(Math.round(fine_amount * 100))` until the
events adapter (Phase B) takes over the conversion.

### Frontend testing (run from `fratos/`)

`npm run test:unit` (vitest), `npm run test:e2e` (playwright role flows:
auth, events, fines, excuses, checkin, members), `npm run lint`,
`npm run build`. Known pre-existing lint error: `app/layout.tsx` contains a
committed `<script src="http://localhost:8400/live.js">` injected by the
impeccable dev tool (`@next/next/no-sync-scripts`) — leave it unless told
otherwise.

---

## 7. Auth & RBAC summary

1. `POST /api/auth/login` returns an HS256 JWT (`sub = member.id` locally,
   `auth_id` on Supabase).
2. `get_current_user` (FastAPI dependency) decodes it into the actor dict.
3. Routes gate with `require_permission("domain:resource:action")` (e.g.
   `treasury:payment:verify`, `calendar:event:create`); services use
   `has_permission`.
4. Per-row authority = membership tables (`event_supervisors`,
   `initiative_chairs` planned), checked inside RPCs.
5. Roles are seeded rows (`member_roles`), not enum code paths. Officer-ish
   roles include `officer`, `treasurer`, and the six chair roles in
   `api/events/auth.py::CHAIR_ROLES`.

---

## 8. Working conventions for agents

- **Plan docs:** feature work is planned in `docs/imp-*.md` (decision records
  D1, D2, … carry across phases) and executed by an implementer agent exactly
  as written. Existing: `imp-ev-ph1/2/3.md` (Events V1), `imp-fe-remediation.md`
  (frontend). `events-dev-status.md` tracks phase status. Phase 1 + 2 are
  landed; Phase 3 (initiatives, migration 0144) is planned but not built.
- **Seams:** grep for `PHASE3 SEAM` — deliberate extension points left in 0142
  (`tk_uncommit_task` event-start resolver) and
  `api/tasks/services/approvals.py` (`can_approve_job`) for the initiatives
  work.
- **Issue tracker:** GitHub issues on `zornix/GuildOS` via `gh` (see
  `docs/agents/issue-tracker.md` at the git root).
- **Verification bar before committing backend work:** relevant
  `python3 -m pytest tests/<domain>/` green. Frontend: `npm run test:unit` and
  `npm run build` green; lint may show only the known layout.tsx error.
- There are **no** `npm run verify` / `preflight` scripts (removed with the
  old `deploy/` dir) — don't look for them.
