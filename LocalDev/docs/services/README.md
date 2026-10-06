# GuildOS Services

This directory documents the service layer under `LocalDev/api/`. Everything
here describes **one** structure — the treasury domain-package pattern — which
is the canonical shape for every service, existing or new. The conformance pass
that got there is finished: the legacy flat modules (`api/routes/`,
`api/services/`, `api/models/`) no longer exist and nothing delegates to them.

## The canonical package shape

```
api/<domain>/
  __init__.py
  api/
    <resource>.py      # route handlers (thin: parse → service → respond)
    schemas.py         # Pydantic v2 models, domain-local (never shared across domains)
    router.py          # ONLY when several sub-routers need a fixed include order
  services/            # business logic; pure where possible, no FastAPI imports
  core/                # domain rules/value objects (e.g. treasury/core/money.py)
  auth.py              # domain permission constants + capability helpers
  notifications.py     # outbox enqueue helpers
```

Not every domain needs every file — small domains omit what they don't use,
but never invent a different layout.

**There is no per-domain `db/`.** Client acquisition (`get_db`), `call_rpc`,
row unwrapping and delivery mode all come from `api/platform/`, the single
database layer (ADR-0002). Route files import `require_permission` from
`api.rbac.auth` directly; a domain never re-exports it.

**`api/router.py` is the exception, not the rule.** Only `attendance`,
`events`, `tasks` and `treasury` have one, because their include order is
load-bearing (fixed path segments before parameterized ones); every other
domain exposes one resource router that `api/index.py` mounts directly. Those
aggregators are append-only.

## Service inventory

Run `ls api/` for the authoritative list; `api/platform/` sits alongside these
but is plumbing, not a domain.

| Domain | Package | Notes |
|---|---|---|
| RBAC | `api/rbac/` | Keystone; see `permissions-matrix.md` |
| Treasury | `api/treasury/` | Pattern source. Also owns the frozen `/api/fines` surface (`api/fines_legacy.py`) |
| Events | `api/events/` | Events V1: times, co-supervisors, notify gate, security assignments |
| Initiatives | `api/initiatives/` | Chair-led calendar peer of events (0144); jobs reuse the tasks machinery, authority is `initiative_chairs` |
| Calendar | `api/calendar/` | Read-only aggregator over events + initiatives — a view, not an entity |
| Attendance | `api/attendance/` | Check-in, excuses, check-in links, `attendance_sessions` |
| Tasks | `api/tasks/` | Tasks, jobs, commitments, approvals |
| Announcements | `api/announcements/` | SMS outbox, atomic inline claims, dry-run delivery |
| Standing | `api/memberadmin/` | Owns standing (reason codes, derived-standing core module); mounted at `/api/memberadmin` and `/api/standing` |
| Members | `api/members/` | Roster |
| Auth | `api/auth/` | Login, JWT issue, token versioning |
| Recruitment | `api/recruitment/` | Pipeline |
| Bylaws | `api/bylaws/` | Honest Q&A stub — no RAG, never fabricates answers |
| NL Controller | `api/nl_controller/` | Approval-gated; no parser, no execution yet |
| Cron | `api/cron/` | `CRON_SECRET`-gated scheduled endpoints (outbox drain); schedule lives in the root `vercel.json` |
| Instrumentation | `api/instrumentation/` | Usage tracking (`/api/usage`) |

## Hard rules (apply to every service)

- **Money is integer cents** (`BIGINT`). The only float in the system is the
  legacy `events.fine_amount`, converted at the boundary via `FineToInvoice`
  → `Money.from_numeric`. Never add another.
- **Trust-boundary mutations go through plpgsql RPCs** whose bodies enforce
  tenant guards (`chapter_id`), idempotency (`idempotency_keys`), and write
  `audit_logs` (plus `big_ledger` for anything financial).
- **Runtime tenant guards use the authenticated chapter in routes and RPCs.**
  The app connects as the table owner and bypasses RLS; migration 0171 revokes
  public-schema privileges from Supabase API roles.
- **Permission checks use `api/rbac/auth.require_permission(...)` or
  `api/rbac/services/permissions.has_permission(...)` only.** No inline role
  string comparisons.
- **No fake business logic.** Unimplemented behavior returns an explicit
  not-implemented response and carries a `TODO(owner)` marker.

## Related docs

- [`service-map.md`](service-map.md) — who calls whom, and the cross-service seams
- [`mvp-operating-loop.md`](mvp-operating-loop.md) — the weekly chapter loop the services exist to run
- [`permissions-matrix.md`](permissions-matrix.md) — roles × permissions, legacy compat, ownership scoping
- [`future-agents.md`](future-agents.md) — where automation/agents plug in later
