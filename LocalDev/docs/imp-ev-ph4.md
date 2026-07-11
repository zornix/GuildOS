# Events V1 — Phase 4 Implementation Plan (Security + Swaps)

Backend-only. Implements `docs/events-v1-spec.md` §2.5 (Security), §2.7
(swap notifications), Screen 6 (Security Picker — backend surface only),
Screen 7 (Swap Request), and the §5 permissions-matrix rows for security.
Global decisions D1–D11 in `docs/events-dev-status.md` apply. This plan adds
D12–D14.

**Written:** 2026-07-10. Before implementing, re-verify the migration frontier
(`ls migrations/ | tail`) — this plan assumes the highest file is
`0144_initiatives_v1.sql` and numbers the new migration **0145**.

## 1. Scope & assumptions

In scope, end to end (migration → RPC → service → route → tests):

1. **Persisted security assignments** as a special job type on the tasks
   domain (D12): `tasks.kind = 'security'`, pre-assigned by a supervisor,
   one job card per assigned member, reusing the report/approve/reject
   lifecycle unchanged.
2. **Swap requests** (D13): `security_swap_requests` table, one pending per
   assignment, target accepts/declines, atomic swap in a single RPC,
   notifications to both parties + supervisors.
3. **Replace the memberadmin stub**: delete the non-persisting
   `POST /api/memberadmin/assign-security` (verified: zero frontend callers).
4. Outbox/audit catalog additions for `SECURITY_*` events.

Out of scope (spec §6 + deferred): no-show handling, swaps on non-security
jobs, the Security Picker UI and stats-table columns (Phase 5 composes
`GET /api/memberadmin/scores` + event detail), initiative security (events
only, spec §2.5).

### Verified current state this plan builds on (2026-07-10)

- Migration frontier is `0144_initiatives_v1.sql`; **0145 is free**.
- **Latest tk_* function versions are split across two files.** Any
  `CREATE OR REPLACE` in 0145 must copy the *latest* body, not 0142's:
  - `tk_commit_task`, `tk_approve_task`, `tk_reject_task`,
    `tk_update_task_status` — latest in **0142**.
  - `tk_create_task`, `tk_uncommit_task`, `tk_report_done` — latest in
    **0144** (initiative-parent branches added).
- `task_commitments` (0110): `status IN ('active','uncommitted','completed')`,
  unique-active partial index `uq_task_commitments_active(task_id, member_id)
  WHERE status = 'active'`; append-only `task_commitment_log`
  (`action IN ('commit','uncommit')`, `reason`, `event_id`,
  `hours_before_event` columns).
- `tasks` (0085/0110/0142/0144): `people_needed`, `reported_*`, `approved_*`,
  `rejected_*`/`rejection_reason`, `event_id`, `initiative_id`,
  `tasks_single_parent_check`. Status CHECK includes
  `done_reported`/`approved`. **No `kind` column yet.**
- `tk_report_done` (0144) already fans `JOB_REPORTED` outbox rows to
  `event_supervisors` for event-linked jobs — security jobs get approver
  notifications for free. `can_approve_job`
  (`api/tasks/services/approvals.py`) already authorizes event supervisors —
  security approval works with no change.
- Manage-supervisors gate: `_require_supervisor_manage(sb, actor=…,
  event_id=…)` in `api/events/services/events.py:575` — supervisor of the
  event OR `calendar:event:update`. This is exactly the spec's
  "manage security = supervisors" gate; reuse it, don't duplicate.
- `_actor_is_supervisor` (`services/events.py:563`) is already imported by
  `services/notifications.py` — precedent for cross-file reuse inside the
  domain.
- Completeness gate is enforced **twice**: `api/events/core/rules.py::
  completeness()` (Python, fed by count queries in the events service) and
  defense-in-depth inside `ev_notify_event` (0143). Both count
  "non-cancelled jobs" — Phase 4 must exclude `kind = 'security'` in both
  places (see D12).
- `GET /api/memberadmin/scores` (`api/memberadmin/api/scores.py`) returns
  delinquency-ranked `{member_id, name, email, score, attended, excused,
  missed, total_required, unpaid_fines, unpaid_amount}` — the Screen 6 data
  source; unchanged this phase. `POST /assign-security` in the same file is
  the non-persisting stub to delete (it and `/scores` use legacy
  `require_officer`; deleting the stub satisfies the dev-status note about
  migrating it off `require_officer` — `/scores` auth is untouched this
  phase).
- Outbox/audit catalog patterns: `message_outbox.event_type` DO-block at
  0142 §8; `audit_logs.action` dual-format DO-block at 0142 §9. Copy
  verbatim, swap the arrays.
- No new array/JSONB-typed RPC params are introduced (all scalars) — no
  `_ARRAY_TYPED_RPC_PARAMS` registration in `api/postgres_client.py` needed.
- Events domain router (`api/events/api/router.py`) includes
  `_events_router` then `_notifications_router`; includes are append-only.

### Decisions baked into this plan

- **D12 — A security assignment IS a `tasks` row (`kind='security'`,
  `people_needed=1`) plus a pre-created active commitment.** No fourth
  checklist concept (D1). The task id is the assignment id; one job card per
  assigned member falls out of the data model. The single **active
  commitment is the source of truth for who holds the assignment** —
  `tasks.assigned_member_id` stays NULL (avoids keeping two columns in sync
  through swaps). Assignment starts at `status='in_progress'` (pre-assigned
  = claimed); report/approve/reject reuse `tk_report_done` /
  `tk_approve_task` / `tk_reject_task` **unchanged**. Claiming and
  unclaiming are blocked on security tasks (guards in `tk_commit_task` /
  `tk_uncommit_task`); the swap flow is the only way the holder changes.
  Security tasks are **excluded from the notify-gate job count and from the
  `job_count`/`open_job_count` decorations** — they are not claimable and
  must not let a security-only event pass the ≥3-jobs gate.
- **D13 — Swaps are a `security_swap_requests` table + one atomic accept
  RPC.** One pending request per assignment via a unique partial index on
  `(task_id) WHERE status = 'pending'` (the dev-status §4.6 pointer).
  `ev_accept_security_swap` flips the commitment atomically (uncommit
  requester + commit target + append log rows) with **direct row operations
  inside the RPC** — no nested `tk_*` calls (the guards added in D12 would
  reject them). Swaps have **no T-36h lock** (the lock exists to prevent
  abandonment; a swap requires another member to accept, which is the
  accountability). Row lifecycle `pending → accepted | declined |
  cancelled`, protected by an update-guard trigger (only status resolution
  may change; deletes blocked) in the `event_notification_sends` (0143)
  style.
- **D14 — Security lives in the events domain; no new permission key.**
  Routes under `/api/events`, RPCs `ev_*`, service/route files in
  `api/events/`. The manage gate reuses `_require_supervisor_manage`
  (supervisor OR `calendar:event:update`) — same rule as co-supervisor
  management, matching spec §5 "Manage security ✅ (supervisors)". Swap
  request/accept/decline are gated by **identity** (assignment holder /
  swap target), checked in the RPCs — not permission keys, the same
  membership-not-permission pattern as D5/D9. No RBAC seed migration.

## 2. Migration `0145_security_swaps_v1.sql`

All new RPCs: tenancy guard (`chapter_id` checked on every row touched),
idempotency via `idempotency_keys` (0142's exact open/close blocks,
`operation` = function name), `audit_logs` write. Nothing financial — no
`big_ledger`.

### 2.1 `tasks.kind`

```sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'standard'
    CHECK (kind IN ('standard', 'security'));

-- security is events-only (spec §2.5); belt for the RPC guard below
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_security_event_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_security_event_check
    CHECK (kind <> 'security' OR event_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS ix_tasks_event_security
    ON tasks(event_id) WHERE kind = 'security';
```

### 2.2 `security_swap_requests`

```sql
CREATE TABLE IF NOT EXISTS security_swap_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id          UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id            UUID NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    task_id             UUID NOT NULL REFERENCES tasks(id)    ON DELETE CASCADE,
    requester_member_id UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    target_member_id    UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    note                TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID REFERENCES members(id) ON DELETE SET NULL
);

-- One pending swap per assignment (spec Screen 7, "prevents shotgunning").
CREATE UNIQUE INDEX IF NOT EXISTS uq_security_swaps_pending
    ON security_swap_requests(task_id) WHERE status = 'pending';
-- indexes: (chapter_id), (event_id), (target_member_id), (requester_member_id)
```

RLS: enable + chapter SELECT policy via `rbac_request_chapter_id()` (0143
pattern). Guard triggers in the `ev_enforce_notify_send_update` (0143) style:
BEFORE UPDATE allows only `status`/`resolved_at`/`resolved_by` to change and
only from `status = 'pending'`; BEFORE DELETE raises.

### 2.3 New RPCs (`ev_*`, events domain)

**`ev_assign_security(p_chapter_id UUID, p_event_id UUID, p_member_id UUID,
p_actor_id UUID, p_title TEXT DEFAULT NULL, p_idempotency_key TEXT DEFAULT
NULL) RETURNS JSONB`**
- Guards: event in chapter; member in chapter; member does not already hold
  an active security assignment on this event (query `tasks kind='security'
  AND event_id = p_event_id` joined to active commitments) →
  `target_already_assigned`.
- Inserts the task (`kind='security'`, `status='in_progress'`,
  `people_needed=1`, `title = COALESCE(p_title, 'Security')`,
  `created_by = p_actor_id`, `required = FALSE`), the active
  `task_commitments` row, and a `task_commitment_log` `'commit'` row
  (matching what `tk_commit_task` writes).
- Audit `SECURITY_ASSIGNED`. Outbox `SECURITY_ASSIGNED` to the member,
  dedup `security_assigned:{task_id}:{member_id}`. **Payload is neutral**
  (task_id, event_id, event title/date) — never the delinquency score
  (Screen 6 design note).
- Returns task + commitment as JSONB.

**`ev_remove_security(p_chapter_id UUID, p_task_id UUID, p_actor_id UUID,
p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`**
- Guards: task in chapter and `kind='security'`; `status <> 'approved'` →
  `security_already_approved` (approved work stays credited).
- Cancels any pending swap for the task (`status='cancelled'`,
  `resolved_at=now()`, `resolved_by=p_actor_id`; swap id recorded in the
  audit metadata). Uncommits the active commitment
  (`status='uncommitted'`, `uncommitted_at=now()`) + log `'uncommit'` row
  with `reason='security_removed'`. Sets the task `status='cancelled'`.
- Audit `SECURITY_REMOVED`. No outbox row (spec doesn't ask; V1 non-goal —
  note it).

**`ev_request_security_swap(p_chapter_id UUID, p_task_id UUID,
p_target_member_id UUID, p_actor_id UUID, p_note TEXT DEFAULT NULL,
p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`**
- Guards: task in chapter, `kind='security'`, `status='in_progress'` →
  `swap_wrong_state`; actor holds the active commitment → `not_assigned`;
  target in chapter; target ≠ actor → `swap_self`; target not already
  actively assigned to security on the same event →
  `target_already_assigned`.
- INSERT the request; a `unique_violation` on `uq_security_swaps_pending`
  is caught and re-raised as `swap_already_pending` (the index is the race
  guard — don't pre-check with a SELECT only).
- Audit `SECURITY_SWAP_REQUESTED`. Outbox `SECURITY_SWAP_REQUESTED` to the
  target, dedup `security_swap_requested:{swap_id}:{target_member_id}`,
  payload: swap_id, task_id, event_id, requester_member_id, note.

**`ev_accept_security_swap(p_chapter_id UUID, p_swap_id UUID, p_actor_id
UUID, p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`** — the atomic swap
- Guards: swap in chapter and `status='pending'`; actor =
  `target_member_id` → `not_swap_target`; task still `kind='security'` and
  `status='in_progress'` → `swap_wrong_state`; requester's commitment still
  active → `swap_stale`; target still not otherwise assigned on the event →
  `target_already_assigned`. Lock the task row (`FOR UPDATE`) before the
  commitment flips, same serialization discipline as `tk_commit_task`.
- Atomically: uncommit requester (+ log row, `reason='security_swap'`),
  insert active commitment for target (+ `'commit'` log row), update the
  swap row (`accepted`, `resolved_at`, `resolved_by`). Task status stays
  `in_progress`.
- Audit `SECURITY_SWAP_ACCEPTED`. Outbox `SECURITY_SWAP_ACCEPTED` to the
  requester, the target, and each `event_supervisors.member_id` (spec §2.7:
  both parties + supervisor), dedup
  `security_swap_accepted:{swap_id}:{member_id}`.

**`ev_decline_security_swap(p_chapter_id UUID, p_swap_id UUID, p_actor_id
UUID, p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`**
- Guards: pending; actor = target → `not_swap_target`.
- Updates the row (`declined`, `resolved_at`, `resolved_by`). Audit
  `SECURITY_SWAP_DECLINED`. Outbox `SECURITY_SWAP_DECLINED` to the
  requester, dedup `security_swap_declined:{swap_id}:{requester_member_id}`.

**Optional (cut first if time-boxed): `ev_cancel_security_swap`** — same
shape as decline but actor = requester, status → `cancelled`, audit
`SECURITY_SWAP_CANCELLED`, no outbox. Without it a pending request the
target ignores blocks the assignment's swap slot forever; with
`ev_remove_security` as the supervisor-side escape hatch this is a
quality-of-life addition, not a spec requirement.

### 2.4 Redefined RPCs (copy the LATEST body, add one guard each)

- **`tk_commit_task`** — copy the **0142** body verbatim; after the task
  `FOR UPDATE` lookup add:
  `IF v_task.kind = 'security' THEN RAISE EXCEPTION 'security_preassigned'; END IF;`
- **`tk_uncommit_task`** — copy the **0144** body verbatim (it has the
  initiative parent branch — do NOT copy 0142's); after the commitment
  lookup add:
  `IF v_task.kind = 'security' THEN RAISE EXCEPTION 'security_no_unclaim'; END IF;`
  (spec Screen 5: security cards show Request Swap instead of Unclaim).
- **`tk_update_task_status`** — copy the **0142** body; add a guard
  refusing `kind='security'` tasks (roster changes only via the security
  RPCs; prevents a generic status flip bypassing swap/remove semantics).
- **`ev_notify_event`** — copy the **0143** body; every job-count query in
  it (the ≥3-jobs completeness re-check, and the open-jobs count in the
  notify payload if present) gains `AND kind <> 'security'` (D12).
- `tk_create_task`, `tk_report_done`, `tk_approve_task`, `tk_reject_task`
  are **untouched** — `tk_create_task` has no `kind` param (only
  `ev_assign_security` creates security rows; the column default covers
  everything else), and the report/approve/reject lifecycle plus its
  `JOB_REPORTED`/`JOB_APPROVED`/`JOB_REJECTED` fan-out works for security
  tasks as-is.

### 2.5 Catalog additions (DO-block rebuild patterns from 0142 §8/§9)

- `message_outbox.event_type` += `SECURITY_ASSIGNED`,
  `SECURITY_SWAP_REQUESTED`, `SECURITY_SWAP_ACCEPTED`,
  `SECURITY_SWAP_DECLINED`.
- `audit_logs.action` += the same four, plus `SECURITY_REMOVED` and
  `SECURITY_SWAP_CANCELLED` (audit-only; the latter seeded now even if the
  optional cancel RPC is cut, to avoid a second catalog migration later).
- Shared-name convention follows the `JOB_*` precedent (Phase 1 notes):
  actions that notify use the same string for `audit_logs.action` and
  `message_outbox.event_type`.

## 3. Backend code changes

### 3.1 `api/events/` — security service + routes

| File | Change |
|---|---|
| `services/security.py` (new) | `list_security(sb, *, chapter_id, event_id)` — tasks `kind='security'` for the event, each decorated with the active commitment's `member_id`, task status/`rejection_reason`, and the pending swap (if any). `assign_security` / `remove_security` — call `_require_supervisor_manage` (imported from `services/events.py`, the same cross-file reuse as `notifications.py`), then the RPC. `request_swap` / `accept_swap` / `decline_swap` — thin RPC calls (identity guards live in the RPCs; no permission check — any authenticated member may be a target). `list_my_swaps(sb, *, chapter_id, member_id)` — pending rows where member is target (incoming) or requester (outgoing), for the Phase 5 inbox. |
| `api/security.py` (new) | Routes below; RPC-exception → HTTP mapping in the `_rpc_http_error` style of `api/tasks/api/jobs.py`. |
| `api/router.py` | `router.include_router(_security_router)` (append-only). |
| `api/schemas.py` | `SecurityAssignIn {member_id}`, `SecurityAssignmentOut {task_id, event_id, member_id, status, rejection_reason, pending_swap}`, `SwapRequestIn {target_member_id, note}`, `SwapOut {id, task_id, event_id, requester_member_id, target_member_id, note, status, created_at}`. |
| `services/events.py` | The `job_count`/`open_job_count` decoration queries gain `.neq("kind", "security")` (D12). |
| `services/notifications.py` | The completeness job-count query gains `.neq("kind", "security")` so the Python gate matches the redefined `ev_notify_event`. |

Routes (all thin: parse → service → respond; 404 on cross-tenant/missing id):

| Route | Auth | Behavior |
|---|---|---|
| `GET /api/events/{event_id}/security` | any member | roster (read view, spec Screen 3) |
| `POST /api/events/{event_id}/security` | supervisor or `calendar:event:update` (service gate) | → `ev_assign_security`; 201 |
| `DELETE /api/events/{event_id}/security/{task_id}` | same gate | → `ev_remove_security` |
| `POST /api/events/{event_id}/security/{task_id}/swap-request` | authenticated; RPC enforces assignment holder | → `ev_request_security_swap` |
| `POST /api/events/{event_id}/security/swaps/{swap_id}/accept` | authenticated; RPC enforces target | → `ev_accept_security_swap` |
| `POST /api/events/{event_id}/security/swaps/{swap_id}/decline` | authenticated; RPC enforces target | → `ev_decline_security_swap` |
| `GET /api/events/security-swaps/mine` | any member | pending swaps involving me (incoming + outgoing) |

⚠ Route-matching caution: `/security-swaps/mine` is a literal path on a
router that also carries `/{event_id}/...` dynamic routes registered
earlier (FastAPI matches in registration order across included routers).
Verify no two-segment dynamic GET in `api/events.py` swallows it; if one
does, register the security router **before** `_events_router` in
`router.py` (the append-only rule forbids removing includes, not ordering a
new one first).

Exception → HTTP mapping: `not found` → 404; `not_assigned` /
`not_swap_target` → 403; `swap_self` → 422; `security_preassigned` /
`security_no_unclaim` / `swap_already_pending` / `swap_wrong_state` /
`swap_stale` / `target_already_assigned` / `security_already_approved` →
409.

### 3.2 `api/memberadmin/`

Delete the `assign_security` route from `api/memberadmin/api/scores.py`
(lines 23–34). Verified 2026-07-10: no fratos code references
`assign-security`/`assign_security`. `/scores` and `/member/{id}` are
untouched (they remain the Screen 6 stats source; their `require_officer`
migration is separate debt, not this phase).

### 3.3 `api/tasks/`

- `api/schemas.py` / task response shapes: surface `kind` so Phase 5 can
  render the shield variant and filter security out of the Jobs section.
- No service/route logic changes — the guards live in the redefined RPCs
  and error strings already flow through `_rpc_http_error` (add the two new
  strings to its 409 branch if the mapping there is string-matched:
  `security_preassigned`, `security_no_unclaim`).

## 4. What Phase 4 does NOT change

- No initiative security (spec §2.5: events only) — the
  `tasks_security_event_check` constraint enforces it.
- No swap requests for regular jobs (spec §6 non-goal) — `kind='security'`
  guard in `ev_request_security_swap`.
- No notification on roster removal, no swap-request expiry, no picker read
  endpoint (Phase 5 composes `/scores` + event detail), no prior-security-
  shifts stat column.
- No changes to `tk_create_task`, `tk_report_done`, `tk_approve_task`,
  `tk_reject_task`, any `in_*` RPC, announcements, or the calendar
  aggregator (security rides inside event detail, not the calendar).
- No new permission keys, no RBAC seeds, no `EntryType`/`big_ledger`
  touches (nothing financial).

## 5. Tests

pytest from `LocalDev/`; superuser connection bypasses RLS for RPC tests,
member-JWT HTTP harness for routes — same split as Phases 1–3. Reuse
`tests/events/conftest.py` factories (`event_factory` with
`hours_from_now`, `user_factory`, `assign_role`).

### 5.1 `tests/events/test_security.py` (RPC-level)

1. Assign: creates task (`kind='security'`, `status='in_progress'`,
   `people_needed=1`) + active commitment + `'commit'` log row + audit
   `SECURITY_ASSIGNED` + outbox row whose payload has **no score field**;
   idempotency-key replay returns the first result, no duplicate rows.
2. Assign the same member twice on one event → `target_already_assigned`;
   assigning them on a *different* event is fine.
3. Guards on the shared machinery: `tk_commit_task` on a security task →
   `security_preassigned`; `tk_uncommit_task` → `security_no_unclaim`;
   `tk_update_task_status` refuses security tasks.
4. Lifecycle reuse: assigned member `tk_report_done` → `done_reported` with
   `JOB_REPORTED` outbox to supervisors; supervisor `tk_approve_task` →
   `approved`, commitment `completed`; `tk_reject_task` returns it to
   `in_progress` with the reason set (claimant retained).
5. Remove: pending swap flips to `cancelled`, commitment `uncommitted`
   (log row `reason='security_removed'`), task `cancelled`, audit
   `SECURITY_REMOVED`; removing an `approved` assignment →
   `security_already_approved`.
6. Swap request guards: non-holder → `not_assigned`; target = requester →
   `swap_self`; target already assigned on the event →
   `target_already_assigned`; second request while one is pending →
   `swap_already_pending`; task `done_reported` → `swap_wrong_state`.
   Happy path: row + audit + outbox to target (note in payload).
7. Accept: non-target actor → `not_swap_target`. Happy path: requester
   commitment `uncommitted` + log row, target commitment `active` + log
   row, swap `accepted`, task still `in_progress`, outbox
   `SECURITY_SWAP_ACCEPTED` to requester + target + every supervisor with
   stable dedup keys (idempotent replay adds nothing). Accept after the
   task moved to `done_reported` → `swap_wrong_state`. After a swap
   resolves, a new request on the same assignment is allowed (partial
   index only covers `pending`).
8. Decline: swap `declined`, outbox to requester only.
9. No T-36h lock on swaps: event starting 12h out — request + accept both
   succeed (while `tk_uncommit_task` on a sibling standard job still raises
   `unclaim_locked`).
10. Notify-gate exclusion: event with 3 security assignments and 0 standard
    jobs → `ev_notify_event` still raises the completeness error; with 3
    standard jobs it passes regardless of security rows.
11. Append-only/guard triggers: direct `UPDATE` of a resolved swap row and
    any `DELETE` raise.

### 5.2 `tests/events/test_security_api.py` (HTTP)

12. `GET /{event_id}/security` as a plain member → 200 with roster;
    cross-chapter event id → 404.
13. `POST /{event_id}/security` as non-supervisor member → 403; as
    supervisor → 201; as `calendar:event:update` holder → 201.
14. `DELETE` by supervisor → 200; by plain member → 403.
15. Swap round-trip over HTTP: holder requests (200), non-target accept →
    403, target accept → 200; duplicate pending → 409; `swap_self` → 422.
16. `GET /security-swaps/mine` as target shows the incoming pending row; as
    requester shows it outgoing; uninvolved member sees neither. (This test
    also proves the route isn't shadowed by `/{event_id}` matching — see
    §3.1 caution.)
17. `job_count`/`open_job_count` on event detail exclude security tasks.

## 6. Execution checklist

1. `ls migrations/ | tail` — confirm 0145 is free; renumber if not.
2. Write `0145_security_swaps_v1.sql` (§2); `npm run migrate`; re-run to
   prove idempotence. Remember: copy `tk_uncommit_task` from **0144**, the
   others from their latest files (§2.4 list).
3. RPC tests red → green (§5.1).
4. Backend code (§3): `services/security.py` + `api/security.py` + router
   include; count-query filters; memberadmin stub deletion; tasks `kind`
   in schemas.
5. HTTP tests green (§5.2). Full `python3 -m pytest` — green.
6. Update `docs/events-dev-status.md`: Phase 4 → done with migration
   number, record D12–D14 under §2, note any drift.
7. Commit: `feat(events): security assignments + swap requests (phase 4)`.
