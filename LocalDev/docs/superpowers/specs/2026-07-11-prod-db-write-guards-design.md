# Design: guards that keep test data and stray migrations out of prod

**Date:** 2026-07-11
**Status:** implemented (see docs/superpowers/plans/2026-07-11-prod-db-write-guards.md)
**Related:** [ADR-0002](../../../../docs/adr/0002-supabase-is-hosted-postgres-only.md),
`docs/DATABASE.md`

## Problem

Prod and demo are two Supabase Postgres projects reached the same way — one
psycopg2 client over a connection-pooler URL (ADR-0002). The only thing that
decides *which* database any command touches is a URL string resolved from the
environment or `LocalDev/.env`. Nothing today notices when that string points at
prod:

- `npm run migrate` and the auto-migrate inside `npm run dev` run
  `scripts/migrate_db.py` against whatever `DATABASE_URL` resolves to.
- pytest resolves `TEST_DATABASE_URL → SUPABASE_DB_URL → DATABASE_URL` in
  `tests/treasury/conftest.py` and connects a **superuser** that bypasses RLS.
- `scripts/seed.py` writes fake rows against `DATABASE_URL`.

`big_ledger` and `audit_logs` are append-only (DELETE blocked by trigger), so a
single mispointed `.env` — a test run or a seed against prod — writes permanent
garbage that cannot be cleaned up. `docs/DATABASE.md` names this risk and says
the guard "is part of the ADR-0002 cleanup; until it exists, nothing but your
attention prevents" it. This spec is that guard.

## Goals

1. **No test or seed writes ever reach prod** — pytest and the seeder refuse to
   run against anything but the known demo (or a local Docker) database.
2. **No accidental migration reaches prod** — the demo/auto-migrate paths refuse
   a non-demo URL; prod migration is a deliberate, separate, confirmed ritual.
3. **The guard survives the failure it guards against.** The discriminator is a
   checked-in constant, not a value read from the same `.env` that is the likely
   point of failure.

## Non-goals

- Database-side canaries, per-role least privilege, or Supabase project
  changes. We chose URL matching for its simplicity and zero schema footprint.
- Guarding read-only console access (`psql`, `check_prod_status.py`). This is
  about *writes*.

## Approach (decided)

**URL pattern matching against checked-in project refs.** A Supabase connection
URL carries the project ref in its username (`postgres.<project-ref>`). The ref
is an identifier, not a credential (the password is separate), so it is safe to
check into the repo — and checking it in is what lets the guard work even when a
mispointed `.env` is the bug.

Two postures, deliberately different:

- **Tests and seed — allowlist the demo (fail-closed).** Run only if the URL is
  the known demo ref (or an obvious local/Docker host). Anything unrecognized —
  a mistyped ref, a brand-new prod, a teammate's database — aborts *before
  connecting*. Unknown is treated as unsafe.
- **Migrations — fail-closed demo for the ordinary path, explicit opt-in for
  prod.** The demo/auto-migrate path uses the same allowlist-demo check as
  tests. Prod migration is the one path allowed to see a prod ref, and only
  through a separate command that names prod explicitly and confirms.

## Components

### 1. `scripts/db_guard.py` — single source of truth (new; pure, no I/O)

Everything else imports from here so the ref lists live in exactly one place.

- **Constants (checked in):**
  - `DEMO_PROJECT_REF: str` — the demo project's ref. Read from the current
    `.env` `DATABASE_URL` at implementation time and hard-coded here.
  - `PROD_PROJECT_REFS: frozenset[str]` — prod refs. **Left as a marked
    placeholder for a human to fill** — the prod URL is never stored in
    `LocalDev/.env`, so it cannot be discovered automatically.
- **`classify_url(url) -> "local" | "demo" | "prod" | "unknown"`** — pure string
  match. Loopback/Docker hosts (`localhost`, `127.0.0.1`, `host.docker.internal`)
  → `local`; contains `DEMO_PROJECT_REF` → `demo`; contains any prod ref →
  `prod`; else `unknown`.
- **`redact(url) -> str`** — host + ref only, password stripped, for safe error
  messages. The guard never prints a full connection string.
- **`require_demo(url, *, context) -> None`** — allows `local`/`demo`; raises
  `ProdGuardError` on `prod`/`unknown`. Used by seed, demo-migrate, and pytest.
- **`require_prod(url) -> None`** — requires `prod`; raises otherwise (so
  `migrate:prod` cannot silently target the demo either). Used only by the prod
  migrate path.

`ProdGuardError` carries a redacted message; callers translate it into the right
exit for their context (`SystemExit` for scripts, `pytest.exit` for tests).

### 2. `tests/treasury/conftest.py` — the one test chokepoint

Every domain's conftest does `from tests.treasury.conftest import *`, so the
`db_url` fixture is the single place to guard. Keep the current
skip-when-unset behavior; when a URL *is* set, call `require_demo(...)` and, on
`ProdGuardError`, `pytest.exit(<redacted message>)` so the whole session stops
before any test connects.

### 3. `scripts/migrate_db.py`

- **Default path** → `require_demo(url, context="migrate")` before connecting.
  This covers `npm run migrate` and the `npm run dev` auto-migrate.
- **New `--prod` flag** → resolve **`PROD_DATABASE_URL`** only (never
  `DATABASE_URL`), `require_prod(url)`, print the list of pending migrations,
  then require the operator to type the prod ref to proceed. A `--yes` flag
  skips the prompt for CI. Nothing is applied until confirmation passes. The
  confirmation check is factored into a small pure function so it is testable.

### 4. `scripts/seed.py`

Call `require_demo(DATABASE_URL, context="seed")` before `psycopg2.connect`.

### 5. Wiring & docs

- `package.json`: add `"migrate:prod": "python3 scripts/migrate_db.py --prod"`.
- `.env.example`: add a commented `PROD_DATABASE_URL=` with a note that it is
  read **only** by `migrate:prod`, never by dev/test.
- `docs/DATABASE.md`: drop the "guard doesn't exist yet" caveats; document the
  `migrate:prod` ritual and the fail-closed test guard.
- ADR-0002: note in Consequences that the pytest guard now exists.

## Data flow

| Command | URL source | Guard | Result |
|---|---|---|---|
| `npm run migrate`, `npm run dev` | `DATABASE_URL` (demo) | `require_demo` | passes |
| pytest | `TEST_DATABASE_URL`/… | `require_demo` (fail-closed) | passes on demo, aborts otherwise |
| `npm run seed` | `DATABASE_URL` (demo) | `require_demo` | passes |
| `npm run migrate:prod` | `PROD_DATABASE_URL` | `require_prod` + typed confirm | applies after confirmation |
| **mispointed `.env` → prod** | `DATABASE_URL` (prod) | `require_demo` | **aborts before connecting** |

## Error handling

- All refusals happen in `classify_url`, a pure pre-connection string check — no
  socket is opened against a refused database.
- Messages are redacted (host + ref, never the password).
- Missing `PROD_DATABASE_URL` under `--prod`, or a mismatched confirmation
  input, aborts with nothing applied.

## Testing

Unit tests on the pure guard (no database needed):

- `classify_url` covers demo / prod / local / unknown.
- `require_demo` raises on `prod` **and** `unknown`; passes on `demo`/`local`.
- `require_prod` raises on `demo`/`local`/`unknown`.
- `redact` never emits the password.
- The `migrate:prod` confirmation function accepts the exact ref and rejects
  anything else.

## Open item requiring a human

`PROD_PROJECT_REFS` must be populated with the real prod project ref before the
guard is meaningful. It ships as a clearly-marked placeholder; until it is
filled, the fail-closed test/seed/demo-migrate guards already protect prod
(anything that is not the demo ref is refused), but the `migrate:prod`
`require_prod` check cannot confirm it is truly hitting prod.
