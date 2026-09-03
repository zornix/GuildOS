# Service Map

How the domains relate, which routes they own, and the seams between them.

## Route ownership

Every prefix below is mounted in `api/index.py`, and the mounted paths are
frozen — check `fratos/lib/api-client.ts` before changing one.

| Prefix | Domain package | Notes |
|---|---|---|
| `/api/auth` | `api/auth` | login, JWT issue, token versioning |
| `/api/rbac` | `api/rbac` | roles catalog, `me/permissions`, admin-gated assignment |
| `/api/events` | `api/events` | Events V1: times, co-supervisors, notify gate, security assignments |
| `/api/initiatives` | `api/initiatives` | chair-led initiatives (0144); authority is `initiative_chairs` |
| `/api/calendar` | `api/calendar` | read-only aggregator over events + initiatives |
| `/api/attendance` | `api/attendance` | check-in routes + `/sessions` resource |
| `/api/excuses`, `/api/checkin-links`, `/c/{short_code}` | `api/attendance` | standalone routers re-exported so the paths never changed |
| `/api/fines` | `api/treasury` (`api/fines_legacy.py`) | fines → treasury via `FineToInvoice` (float→cents boundary) |
| `/api/treasury` | `api/treasury` | pattern source |
| `/api/tasks` | `api/tasks` | tasks, jobs, commitments, approvals |
| `/api/operations` | `api/tasks` (`api/operations.py`) | event-prep template engine — see below |
| `/api/announcements` | `api/announcements` | |
| `/api/standing` | `api/memberadmin` | `api.memberadmin.api.standing` mounted at its own prefix |
| `/api/memberadmin` | `api/memberadmin` | scores |
| `/api/members` | `api/members` | roster |
| `/api/recruitment` | `api/recruitment` | |
| `/api/bylaws` | `api/bylaws` | |
| `/api/nl-controller` | `api/nl_controller` | |
| `/api/cron` | `api/cron` | `CRON_SECRET`-gated; schedule lives in the root `vercel.json` |
| `/api/usage` | `api/instrumentation` | usage tracking |

## Cross-service seams

Seams are **read functions or audience selectors**, not direct writes into
another domain's tables. A consumer calls the producer's service function (or
API); it never reimplements the producer's rules.

```
events ──(linked_attendance_session_id)──▶ attendance.sessions
events ──(linked_task_group_id)──────────▶ tasks.task_groups
events ──(linked_announcement_id)────────▶ announcements
events ──(linked_budget_id)──────────────▶ treasury budgets   [column exists, no budgets table yet]

attendance.signals.list_unexcused_absences ──▶ standing (reason code UNEXCUSED_ABSENCES)
attendance ──(unexcused absence)──▶ fines/treasury via FineToInvoice  [existing path, unchanged]

treasury (unpaid invoices) ──▶ standing (UNPAID_FINES / HIGH_UNPAID_BALANCE)
treasury (balance owed)    ──▶ announcements audience "members_with_balance"

tasks.tasks.incomplete_required_tasks ──▶ standing (INCOMPLETE_REQUIRED_TASKS, reason-only)

initiatives ──(jobs reuse tk_* machinery)──▶ tasks   [approval authority is initiative_chairs]
calendar ──(read-only aggregate)──▶ events + initiatives

nl_controller ──(after approval; not yet implemented)──▶ calls service APIs of
  events / attendance / tasks / announcements. It never writes domain tables itself.
```

## Standing as the consumer of record

`api/memberadmin/core/standing_rules.derive_standing()` is the single place
that turns signals into a status. Current thresholds (behavior-preserving from
the legacy implementation):

- **delinquent**: 2+ unpaid fines, or ≥ $50 unpaid, or 3+ unexcused absences
- **warning**: 1 unpaid fine or 1+ unexcused absence
- **good_standing**: otherwise

Reason codes are additive metadata (`reason_codes` key in the standing
response). `INCOMPLETE_REQUIRED_TASKS` is currently reason-only — it never
changes the status until the chapter decides the policy (see TODO in
`standing_rules.py`).

## The operations engine is not the NL controller

`api/tasks/api/operations.py` + `api/tasks/services/templates.py` are an
event-prep **template engine** (event templates → roles → task checklists, from
migration 0003) mounted at `/api/operations`. The NL controller (`api/nl_controller`) is a separate, approval-gated
command queue. When command execution is eventually implemented it may *call*
the operations engine, but they are different services.
