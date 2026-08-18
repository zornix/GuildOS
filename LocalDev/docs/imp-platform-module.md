# Implementation plan — one platform module for db access (+ ADR-0002 execution)

Date: 2026-07-11. Refreshed: 2026-08-16 against the post-one-gate tree.
Depends on: `imp-hygiene.md` (done, archived). `imp-one-gate.md` has since
shipped (migration 0147) — it deleted `api/treasury/auth.py` already, so the
one-gate carve-outs in the original D4 are gone.
Blocks: `imp-db-introspection.md`.
Scope: backend only (`api/`, `requirements.txt`, `CLAUDE.md`). Mechanical
consolidation — zero intended behavior change except the deliberate deletions
listed in Phase B.

Contract: decisions settled here; implementer executes as written, reports
drift. Authority: `/home/mshi/GuildOS/docs/adr/0002-supabase-is-hosted-postgres-only.md`
(supabase-py is deliberately unused — do not "fix" its absence) and the
architecture review, candidate 3. The prod boot guard (commit `03fba7c`)
refuses to start without `DATABASE_URL`, so the supabase-py branch is provably
dead in every environment.

## Settled decisions

- **D1 — `api/platform/` is the one home for db plumbing.** It owns client
  acquisition, `call_rpc`, row unwrapping, and delivery-mode resolution.
  Domains import it. Per-domain `db/` directories are deleted.
- **D2 — One accessor, honest name.** `get_supabase()` / `get_supabase_admin()`
  and the per-domain `get_*_db()` forwards all become a single
  `api.platform.db.get_db()`. The distinction between the two supabase
  accessors never mattered on the psycopg path (both return the same client);
  ADR-0002 sanctions renaming once, here.
- **D3 — supabase-py dies now.** The `create_client` branches in `api/db.py`,
  the `use_local_db` setting, the `auth_id` lookup branch in
  `api/dependencies.py`, and the `supabase` requirement are deleted. ADR-0002
  established these branches have never carried traffic anywhere, and the boot
  guard now enforces it.
- **D4 — A domain file survives only if it holds real domain logic.**
  Kept: `api/rbac/auth.py` (the permission gate), `api/cron/auth.py`
  (`require_cron_secret`, real shared-secret gate — not a re-export shell),
  `api/initiatives/auth.py`'s `is_assigned_chair`, domain permission-key
  *constants*, treasury/events notification logic, and the 4 router
  aggregators with real ordering (attendance, events, tasks, treasury).
  (`api/treasury/auth.py` no longer exists — one-gate deleted it.)
- **D5 — URL paths are frozen.** Folding `api/standing/` into `memberadmin`
  and deleting router wrappers must not change any mounted route path. Grep
  `fratos/lib/api-client.ts` for every prefix before touching mounts.
- **D6 — no local Docker DB.** Per ADR-0002 ("no offline Docker fallback"),
  Docker mode has been removed entirely: `dev:docker`/`dev:seed`,
  `docker-compose.yml`, and the `USE_DOCKER_DB` branch of `local-dev.sh` are
  gone. Both demo and prod are Supabase pooler URLs selected by `DATABASE_URL`;
  `npm run dev` is the only local stack.

## Phase A — create `api/platform/`

1. `git mv api/postgres_client.py api/platform/postgres.py` (class name
   `PostgresClient` unchanged; update the module docstring — it no longer
   "mimics supabase-py locally", it *is* the client, per ADR-0002).
2. `api/platform/db.py`: the lazy singleton (today's `api/db.py:_get_pg`)
   exposed as `get_db()`. `DATABASE_URL` and `JWT_SECRET` missing → fail at
   import/boot with a clear message (ADR-0002 consequence).
3. `api/platform/rpc.py`: the one `call_rpc(name, params, *, sb=None)` —
   keep treasury's docstring (the single-transaction plpgsql explanation, the
   only divergence among the 8 copies).
4. `api/platform/rows.py`: `unwrap_row(result)` — the `_row` idiom
   (`data[0] if isinstance(data, list) else data`).
5. `api/platform/delivery.py`: one `delivery_mode()` — diff the three copies
   (`announcements/services/sms.py:68`, `events/services/notifications.py:64`,
   `treasury/notifications.py:33`) first; if they genuinely differ, report
   drift instead of merging.

## Phase B — delete the supabase-py path (ADR-0002)

6. Repo-wide rename: every `get_supabase()` / `get_supabase_admin()` call →
   `get_db()`; every `from api.db import ...` → `from api.platform.db import
   get_db`. Delete `api/db.py`. (~36 files reference `get_supabase` — tests
   included.)
7. `api/config.py`: delete the `use_local_db` property (line 32) and the
   `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
   settings if nothing else reads them (grep first).
8. `api/dependencies.py`: keep only the `member.id` lookup (the `auth_id`
   branch is the never-used supabase path). **New since the original plan:**
   the session-epoch check (migration 0148, `token_version` vs the JWT `ver`
   claim, currently behind `if settings.use_local_db:` at line 48) becomes
   **unconditional** — on the psycopg path every token carries our `ver`
   claim, so the guard was only ever shielding the dead supabase branch.
9. `api/auth/api/auth.py:230` (dev-login guard): `if not
   settings.DEV_AUTH_BYPASS or not settings.use_local_db` → `if not
   settings.DEV_AUTH_BYPASS`.
10. Remove `supabase` from `requirements.txt` (line 5). Grep `from supabase` /
    `import supabase` → zero hits.

## Phase C — delete the per-domain shells

11. Delete the 9 `api/*/db/session.py` files (announcements, calendar, events,
    initiatives, instrumentation, rbac, recruitment, tasks, treasury) and the
    3 inlined `get_*_db()` helpers (`attendance/services/sessions.py:16`,
    `bylaws/services/documents.py:8`, `nl_controller/services/commands.py:10`);
    callers use `get_db()`. (Recruitment's helper moved into `db/session.py`
    since the original plan — `recruitment/services/pipeline.py:21` re-exports
    it; drop the re-export too.)
12. Delete the 8 `api/*/db/rpc.py` (announcements, attendance, events,
    initiatives, rbac, recruitment, tasks, treasury); callers import
    `api.platform.rpc.call_rpc`. Delete now-empty `db/` directories.
13. The 9 re-export `auth.py` shells (announcements, attendance, bylaws,
    calendar, events, initiatives, nl_controller, recruitment, tasks): remove
    the `from api.rbac.auth import require_permission` re-export lines; route
    files import it from `api.rbac.auth` directly. Files reduced to *only*
    permission-key constants keep those constants (D4); files left empty
    (calendar's 1-liner) are deleted. `initiatives/auth.py` keeps
    `is_assigned_chair`. `cron/auth.py` is not a shell — leave it whole.
14. Replace the 4 named `_row` helpers (`attendance/services/sessions.py:20`,
    `treasury/services/invoices.py:29`, `nl_controller/services/commands.py:14`,
    `recruitment/services/pipeline.py:53`) and 2 inline copies
    (`announcements/services/announcements.py:46`,
    `bylaws/services/documents.py:28`) with `unwrap_row`. Leave
    `tasks/services/templates.py:_coerce_rows` (different shape).
15. Replace the 3 `_delivery_mode()` copies with `platform.delivery`.

## Phase D — fold `standing/`, flatten router wrappers

16. Delete `api/standing/` (pure facade — `api/standing/api/router.py` is a
    single include). In `api/index.py`, mount the underlying memberadmin
    standing router under the exact prefix the deleted package produced
    (D5 — verify against frontend calls first).
17. Delete the 13 include-only `api/*/api/router.py` wrappers (announcements,
    auth, bylaws, calendar, cron, initiatives, instrumentation, memberadmin,
    members, nl_controller, rbac, recruitment, standing — the last covered by
    step 16); `api/index.py` includes each inner router directly at the same
    prefix. Keep the 4 real aggregators (attendance, events, tasks, treasury).

## Phase E — docs

18. `LocalDev/CLAUDE.md`: rewrite the "Domain-package pattern" block (domains
    hold `api/`, `services/`, `core/`, optional `auth.py` constants /
    `notifications.py`; plumbing comes from `api.platform`), and the
    "Database access abstraction" section (one psycopg client per ADR-0002;
    `DATABASE_URL` selects the database; the `_ARRAY_TYPED_RPC_PARAMS` note
    moves/updates — superseded entirely once `imp-db-introspection` lands).

## Verification

`python3 -m pytest` green after every phase. `npm run dev` boots and serves
`/api/docs`; spot-check one route per domain (the mounted-paths list printed
by FastAPI must be identical before/after Phase D — capture it first).
Greps at the end, all zero: `get_supabase`, `use_local_db`, `from supabase`,
`db/session`, `def _row`, `def _delivery_mode`.

Counts above were re-derived 2026-08-16; if the tree has moved again, trust
the greps over the enumerations and report the drift.

Suggested commits: one per phase (`refactor(platform): ...`).
