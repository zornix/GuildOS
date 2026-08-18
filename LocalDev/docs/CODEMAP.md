# Code map

Guided file map for agents. Distilled from the Understand-Anything graph
(2026-08-15) and corrected against the post-`api/platform` tree (2026-08-16).

Read `CLAUDE.md` first (hard rules, commands, domain-package shape). Read
repo-root `CONTEXT.md` and `docs/adr/` for vocabulary — permission, standing,
contribution, shoutout, job, chair. This file only answers **which files to
open, in what order**.

The generated `.ua/` snapshot is local-only and goes stale on every refactor.
Do not treat it as truth.

---

## Layers

| Layer | Where | What belongs |
|-------|--------|----------------|
| Backend API | `api/<domain>/api/` | Thin FastAPI handlers and domain-local Pydantic schemas. Aggregate `router.py` only when include order is load-bearing (attendance, events, tasks, treasury). |
| Domain services & rules | `api/<domain>/services/`, `core/`, `auth.py` | Orchestration; I/O-free value objects (`Money`, event rules); permission-key constants. |
| Platform | `api/platform/`, `api/index.py`, `api/dependencies.py` | The one DB path: `get_db`, `PostgresClient`, `call_rpc`, `unwrap_row`, `delivery_mode`. JWT → member. |
| Schema & RPCs | `migrations/*.sql` | Lexical SQL: tables, RLS, plpgsql RPCs, `big_ledger` / `audit_logs`. |
| Frontend UI | `fratos/app/`, `components/` | Thin App Router page, shell, modules, UI primitives, leftover `views/`. |
| Frontend data | `fratos/lib/`, `hooks/`, `config/` | `api-client` → adapters → contracts → formatters. Nav + tokens. |
| Tests | `tests/`, `fratos/**/*.test.ts`, `fratos/e2e/` | Real Postgres pytest; Vitest; Playwright role flows. |
| Ship | `vercel.json`, `.github/workflows/`, `scripts/` | Vercel dual-runtime, CI, `migrate_db.py`, `db_guard.py`. |

---

## Reading order

### 1. Product and rules

- `PRODUCT.md` — who it serves
- `CLAUDE.md` — stack, commands, hard rules
- `docs/ARCHITECTURE.md` — conventions in full

### 2. FastAPI entry

- `api/index.py` — app + Vercel handler; CORS; mounts every domain router
- `api/config.py` — pydantic `settings` from `.env`
- `api/health_checks.py` — `/api/health`

### 3. Database seam

- `api/platform/db.py` — `get_db()`; the only accessor
- `api/platform/postgres.py` — PostgREST-shaped client over psycopg2; `_ARRAY_TYPED_RPC_PARAMS`
- `api/dependencies.py` — JWT → member; `ver` vs `members.token_version`

There is no supabase-py path and no per-domain `db/session.py` / `db/rpc.py`.

### 4. Domain-package pattern (treasury)

- `api/treasury/api/router.py` — append-only aggregator, mounted at `/api/treasury`
- `api/treasury/api/invoices.py` — thin handlers; mutations go to RPCs
- `api/treasury/services/` — orchestration
- `api/platform/rpc.py` — `call_rpc`; the only multi-write path for every domain

### 5. Money as integer cents

- `api/treasury/core/money.py` — `Money`; floats rejected; `from_numeric` is the sole legacy exception
- `api/treasury/core/ledger.py` — append-only `big_ledger`; reversals are new rows
- `api/treasury/core/idempotency.py` — `Idempotency-Key` contract
- `fratos/lib/formatters/money.ts` — only sanctioned cents → screen path

### 6. Permissions through RBAC only

- `api/rbac/auth.py` — `require_permission`; domains import this directly
- `api/rbac/services/permissions.py` — union of `member_roles`
- `api/rbac/core/policy.py` — I/O-free policy, including ownership escalation
- `api/events/auth.py` — typical domain permission-key constants (`CHAIR_ROLES`)

### 7. Schema foundation

- `migrations/0001_initial_schema.sql` — tenant tables, each with `chapter_id`
- `migrations/0005_treasury_foundation_tables.sql` — `big_ledger`, `audit_logs`
- `migrations/0082_rbac_foundation_tables.sql` — roles / permissions catalogs
- `docs/DATABASE.md` — demo vs prod pooler, how to migrate safely

### 8. RPCs, RLS, tenant guards

- `migrations/0006_treasury_foundation_rls_rpc.sql` — RLS helpers from JWT claims
- `migrations/0080_treasury_tenant_guards.sql` — body ids re-checked against caller chapter
- `migrations/0083_rbac_seed_rpcs.sql` — catalog seed + `rbac_assign_role` / `rbac_revoke_role`
- `docs/TREASURY_ARCHITECTURE.md` — ledger invariants

### 9. Events (same pattern, different subject)

- `api/events/api/router.py`
- `api/events/services/events.py`
- `api/events/core/rules.py` — notify-gate completeness, organizer minimum, visibility

### 10. Attendance (pattern not finished)

- `api/attendance/CONFORM_TODO.md` — remaining legacy handlers
- `api/attendance/api/router.py` — also re-exports excuses / check-in routers

### 11. Frontend shell

- `fratos/app/page.tsx` — thin; no fetch
- `fratos/components/layout/app-shell.tsx` — sidebar, header, active page
- `fratos/config/navigation.ts` — page ids + `requiredPermission`
- `fratos/hooks/use-permissions.ts` — `can(permission)`
- `fratos/config/theme/tokens.ts`

Still a single-route SPA over `views/`; new work goes in `components/modules/`.

### 12. Frontend data path

- `fratos/lib/api-client.ts` — one HTTP client; check here before changing a URL prefix
- `fratos/lib/contracts/` + `fratos/lib/adapters/` — treasury is the model; events still pending Phase 5
- `fratos/hooks/use-api.ts`

### 13. Tests

- `tests/treasury/conftest.py` — real Postgres harness reused across domains
- `tests/treasury/test_chunkH_tenant_guards.py` — cross-chapter ids rejected
- `fratos/` Vitest + `fratos/e2e/` Playwright

### 14. How it ships

- `vercel.json` — `api/index.py` + `fratos/`; `/api/*` and `/c/*` → FastAPI
- `.github/workflows/ci.yml` — Postgres 16 service, LocalDev verification
- `scripts/migrate_db.py` — lexical, idempotent via `schema_migrations`
- `scripts/db_guard.py` — refuses writes to production URLs

---

## What the graph did not capture

- Repo-root `CONTEXT.md` / `docs/adr/` (contribution, shoutout, proposal, the
  standing–contribution firewall).
- FastAPI routes as method+path+permission (handlers are tagged functions only).
- `docs/B4FEND-FIX.md` — next Events backend slice before Phase 5.
