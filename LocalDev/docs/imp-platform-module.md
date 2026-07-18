# Implementation plan — one platform module for db access (+ ADR-0002 execution)

Date: 2026-07-11
Order: step 3 of 7. Depends on: `imp-hygiene.md` (flat modules deleted).
Blocks: `imp-one-gate.md`, `imp-db-introspection.md`.
Scope: backend only (`api/`, `requirements.txt`, `CLAUDE.md`). Mechanical
consolidation — zero intended behavior change except the deliberate deletions
listed in Phase B.

Contract: decisions settled here; implementer executes as written, reports
drift. Authority: `/home/mshi/GuildOS/docs/adr/0002-supabase-is-hosted-postgres-only.md`
(supabase-py is deliberately unused — do not "fix" its absence) and the
architecture review, candidate 3.

## Settled decisions

- **D1 — `api/platform/` is the one home for db plumbing.** It owns client
  acquisition, `call_rpc`, row unwrapping, and delivery-mode resolution.
  Domains import it. Per-domain `db/` directories are deleted.
- **D2 — One accessor, honest name.** `get_supabase()` / `get_supabase_admin()`
  and the 12 per-domain `get_*_db()` forwards all become a single
  `api.platform.db.get_db()`. The distinction between the two supabase
  accessors never mattered on the psycopg path (both return the same client);
  ADR-0002 sanctions renaming once, here.
- **D3 — supabase-py dies now.** The `create_client` branches in `api/db.py`,
  the `use_local_db` setting, the `auth_id` lookup branch in
  `api/dependencies.py`, and the `supabase` requirement are deleted. ADR-0002
  established these branches have never carried traffic anywhere.
- **D4 — A domain file survives only if it holds real domain logic.**
  Kept: `api/rbac/auth.py` (the permission gate), `api/treasury/auth.py`
  (until `imp-one-gate` deletes it), `api/initiatives/auth.py`'s
  `is_assigned_chair`, domain permission-key *constants*, treasury/events
  notification logic, and the 4 router aggregators with real ordering
  (attendance, events, tasks, treasury).
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
   only divergence among the 6 copies).
4. `api/platform/rows.py`: `unwrap_row(result)` — the `_row` idiom
   (`data[0] if isinstance(data, list) else data`).
5. `api/platform/delivery.py`: one `delivery_mode()` — diff the three copies
   (`announcements/services/sms.py:60`, `events/services/notifications.py:65`,
   `treasury/notifications.py:30`) first; if they genuinely differ, report
   drift instead of merging.

## Phase B — delete the supabase-py path (ADR-0002)

6. Repo-wide rename: every `get_supabase()` / `get_supabase_admin()` call →
   `get_db()`; every `from api.db import ...` → `from api.platform.db import
   get_db`. Delete `api/db.py`.
7. `api/config.py`: delete the `use_local_db` property and the
   `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
   settings if nothing else reads them (grep first).
8. `api/dependencies.py:20-38`: keep only the `member.id` lookup (the
   `auth_id` branch is the never-used supabase path).
9. `api/auth/api/auth.py:71` (dev-login guard): `if not
   settings.DEV_AUTH_BYPASS or not settings.use_local_db` → `if not
   settings.DEV_AUTH_BYPASS`.
10. Remove `supabase` from `requirements.txt`. Grep `from supabase` /
    `import supabase` → zero hits.

## Phase C — delete the per-domain shells

11. Delete the 8 `api/*/db/session.py` files and the 4 inlined `get_*_db()`
    helpers (`attendance/services/sessions.py:16`,
    `bylaws/services/documents.py:8`, `nl_controller/services/commands.py:10`,
    `recruitment/services/pipeline.py:14`); callers use `get_db()`.
12. Delete the 6 `api/*/db/rpc.py`; callers import `api.platform.rpc.call_rpc`.
    Delete now-empty `db/` directories.
13. The 9 re-export `auth.py` shells: remove the `from api.rbac.auth import
    require_permission` re-export lines; route files import it from
    `api.rbac.auth` directly. Files reduced to *only* permission-key constants
    keep those constants (D4); files left empty (calendar's 1-liner) are
    deleted. `initiatives/auth.py` keeps `is_assigned_chair`.
14. Replace the 4 named `_row` helpers and 2 inline copies
    (`announcements/services/announcements.py:34`,
    `bylaws/services/documents.py:28`) with `unwrap_row`. Leave
    `tasks/services/templates.py:_coerce_rows` (different shape).
15. Replace the 3 `_delivery_mode()` copies with `platform.delivery`.

## Phase D — fold `standing/`, flatten router wrappers

16. Delete `api/standing/` (8 lines, pure facade). In `api/index.py`, mount
    `api.memberadmin.api.standing:router` under the exact prefix the deleted
    package produced (D5 — verify against frontend calls first).
17. Delete the 12 include-only `api/*/api/router.py` wrappers (plus
    memberadmin's if it is also single-include); `api/index.py` includes each
    inner router directly at the same prefix. Keep the 4 real aggregators.

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

Suggested commits: one per phase (`refactor(platform): ...`).
