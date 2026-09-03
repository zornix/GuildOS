# GuildOS Services

This directory documents the service layer under `LocalDev/api/` after the
scaffold/conformance pass (June 2026). Everything here describes **one**
structure — the treasury domain-package pattern — which is the canonical shape
for every service, existing or new.

## The canonical package shape

```
api/<domain>/
  __init__.py
  api/
    router.py          # aggregates the domain's APIRouters; index.py mounts only this
    <resource>.py      # route handlers (thin: parse → service → respond)
    schemas.py         # Pydantic v2 models, domain-local (never shared across domains)
  services/            # business logic; pure where possible, no FastAPI imports
  core/                # domain rules/value objects (e.g. treasury/core/money.py)
  db/
    session.py         # client acquisition
    rpc.py             # call_rpc helper for trust-boundary plpgsql RPCs
    repositories/      # read-side query helpers
  auth.py              # domain permission constants + capability helpers
  notifications.py     # outbox enqueue helpers (transactional outbox pattern)
```

Not every domain needs every file — small domains omit what they don't use,
but never invent a different layout.

## Service inventory

| Domain | Package | Status |
|---|---|---|
| RBAC | `api/rbac/` | **New** — keystone; see `permissions-matrix.md` |
| Treasury | `api/treasury/` | Existing, untouched (pattern source) |
| Calendar / Events | `api/events/` | Conform shell delegating to `api/routes/events.py` + new columns |
| Attendance | `api/attendance/` | Conform shell + new `attendance_sessions` resource |
| Tasks | `api/tasks/` | **New** |
| Announcements | `api/announcements/` | **New** (transactional outbox, dry-run delivery) |
| Standing | `api/memberadmin/` | Extended (reason codes, derived-standing core module) |
| Recruitment | `api/recruitment/` | **New** |
| Bylaws | `api/bylaws/` | **New** (honest Q&A stub — no RAG, never fabricates answers) |
| NL Controller | `api/nl_controller/` | **New** (approval-gated; no parser, no execution yet) |

The conform pass is finished: the legacy flat modules (`api/routes/`,
`api/services/`, `api/models/`) no longer exist and no domain carries a
`CONFORM_TODO.md`.

## Hard rules (apply to every service)

- **Money is integer cents** (`BIGINT`). The only float in the system is the
  legacy `events.fine_amount`, converted at the boundary via `FineToInvoice`
  → `Money.from_numeric`. Never add another.
- **Trust-boundary mutations go through plpgsql RPCs** whose bodies enforce
  tenant guards (`chapter_id`), idempotency (`idempotency_keys`), and write
  `audit_logs` (plus `big_ledger` for anything financial).
- **Every tenant table carries `chapter_id` and has RLS enabled.**
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
