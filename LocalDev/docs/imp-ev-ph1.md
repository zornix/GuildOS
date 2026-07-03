# Events V1 — Phase 1 Implementation Plan

**Scope:** schema + jobs core (backend only).
**Spec:** `docs/events-v1-spec.md` §2.1 (times, supervisors, invite link), §2.4 (jobs).
**Status/roadmap:** `docs/events-dev-status.md` (decisions D1–D4 apply; D3 is Phase 2).
**Written:** 2026-07-01. Before implementing, re-verify the migration frontier
(`ls migrations/ | tail`) — this plan assumes the highest applied file is
`0140_usage_events.sql` and numbers new migrations **0141–0142**.

## 1. Scope & assumptions

Phase 1 delivers, end to end (migration → RPC → service → route → tests):

1. `events` gains an end time (`end_date`/`end_time`) and `invite_link`.
2. Co-supervisors via a new `event_supervisors` join table; creator locked in;
   minimum-1 invariant.
3. The tasks domain becomes the spec's "jobs" (decision D1): capacity
   (`people_needed`, fill state), `done_reported` / `approved` states,
   reject-with-required-reason, and the hard T-36h unclaim lock (decision D2).
4. Outbox + audit catalog additions for job report/approve/reject notifications.

Explicit **non-goals** (later phases): notify gate & button, `ORGANIZER_SOFT_MIN`
change (Phase 2); initiatives (Phase 3); security assignments & swaps (Phase 4);
all frontend (Phase 5); SMS of any kind.

Naming: user-facing layer may say "job"; storage, RPCs, and routes stay
`tasks` / `tk_*` / `/api/tasks` — no parallel concept (D1).

### Verified current state this plan builds on

- `tasks` (0085, altered 0110): status CHECK currently
  `('open','committed','in_progress','done','cancelled')`; `event_id` FK added in 0110.
- `task_commitments` (0110): `status IN ('active','uncommitted','completed')`,
  unique-active partial index `uq_task_commitments_active (task_id, member_id)`;
  append-only `task_commitment_log` (`action IN ('commit','uncommit')`,
  `hours_before_event` column — an event-start resolver already exists inside
  `tk_uncommit_task`; today it only *flags* uncommits under 24h as late).
- `events` (0001/0090/0100): `date DATE NOT NULL`, `time TIME NOT NULL`
  (start only), single `supervisor_member_id` (0100), no end/invite columns.
- Events RPCs (0101): `ev_create_event(p_chapter_id, p_title, p_description,
  p_date, p_time, p_location, p_required, p_finable, p_fine_amount,
  p_event_type, p_event_type_id, p_visibility, p_event_group_id,
  p_group_with_event_id, p_audience_member_ids, p_actor_id, p_idempotency_key)`;
  `ev_set_supervisor(p_chapter_id, p_event_id, p_member_id,
  p_required_role_keys, p_actor_id, p_idempotency_key)`.
- `message_outbox` (0070): CHECK-constrained `event_type` catalog, unique
  `dedup_key`. Catalog extensions use the DO-block rebuild pattern (0100/0131).

## 2. Migration `0141_events_v1_times_supervisors.sql`

### 2.1 Events columns

```sql
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS end_date    DATE,
    ADD COLUMN IF NOT EXISTS end_time    TIME,
    ADD COLUMN IF NOT EXISTS invite_link TEXT;
```

Nullable on purpose: legacy rows have no end time. Service-layer validation
(not a DB CHECK) requires `end > start` when provided, with `end_date`
defaulting to `date` (same-day) when only `end_time` is given. The create form
makes the range required in Phase 5; the API accepts it as optional.

### 2.2 `event_supervisors`

```sql
CREATE TABLE IF NOT EXISTS event_supervisors (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id   UUID NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    member_id  UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    is_creator BOOLEAN NOT NULL DEFAULT FALSE,
    added_by   UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_supervisors UNIQUE (event_id, member_id)
);
-- indexes: (chapter_id), (event_id), (member_id)
-- RLS: enable + chapter policy via rbac_request_chapter_id(), same shape as
-- event_organizers in 0100.
```

Backfill (idempotent):

```sql
-- creator is always a supervisor (spec §2.1)
INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
SELECT e.chapter_id, e.id, e.created_by, TRUE
  FROM events e WHERE e.created_by IS NOT NULL
ON CONFLICT (event_id, member_id) DO NOTHING;

-- existing single supervisor becomes a co-supervisor (creator row wins is_creator)
INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
SELECT e.chapter_id, e.id, e.supervisor_member_id, FALSE
  FROM events e WHERE e.supervisor_member_id IS NOT NULL
ON CONFLICT (event_id, member_id) DO NOTHING;
```

`events.supervisor_member_id` is **deprecated in place**: no drop, no further
writes; all reads move to the join table. Note this in `api/events/CONFORM_TODO.md`.

### 2.3 RPC changes (all: tenancy guard, `idempotency_keys`, `audit_logs`)

- **`ev_create_event`** — new params `p_end_date DATE DEFAULT NULL`,
  `p_end_time TIME DEFAULT NULL`, `p_invite_link TEXT DEFAULT NULL`. Body also
  inserts the creator into `event_supervisors` (`is_creator = TRUE`).
  ⚠ Adding parameters changes the function identity in Postgres — `DROP
  FUNCTION IF EXISTS ev_create_event(<old full signature>);` then `CREATE OR
  REPLACE` the new one, in this migration (matches append-only migration rule:
  new file redefines, old file untouched).
- **`ev_add_supervisor(p_chapter_id, p_event_id, p_member_id,
  p_required_role_keys JSONB, p_actor_id, p_idempotency_key)`** — inserts a
  co-supervisor. Guards: event in chapter; target holds one of
  `p_required_role_keys` (reuse the eligibility-check shape from
  `ev_set_supervisor` in 0101; service passes officer-role keys per spec §2.1);
  ON CONFLICT do nothing (idempotent add). Audit: `EVENT_SUPERVISOR_ADDED`
  (match the action naming style already used in 0101 — check before coining).
- **`ev_remove_supervisor(p_chapter_id, p_event_id, p_member_id, p_actor_id,
  p_idempotency_key)`** — guards: cannot remove a row with `is_creator = TRUE`;
  cannot leave the event with zero supervisors (min-1 invariant — with creator
  locked this is belt-and-braces). Audit: `EVENT_SUPERVISOR_REMOVED`.
- **`ev_set_supervisor`** — leave in place (legacy callers), but the route that
  calls it is re-pointed (§4.1).

`audit_logs.action` catalog: add the two new actions via the DO-block rebuild
pattern (template at 0100:117–164).

## 3. Migration `0142_jobs_v1_lifecycle.sql`

### 3.1 Tasks columns + status widening

```sql
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS people_needed    INT  NOT NULL DEFAULT 1
        CHECK (people_needed >= 1),
    ADD COLUMN IF NOT EXISTS reported_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS reported_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check CHECK (status IN
    ('open','committed','in_progress','done','cancelled',
     'done_reported','approved'));
```

Spec-state mapping: 🔴 to-do = `open`, 🟢 in-progress = `in_progress`,
🟡 done-reported = `done_reported`, ✅ = `approved`. `committed`/`done` stay
valid for legacy chore-task rows only; the job lifecycle never sets them.
`tk_update_task_status` gets a guard refusing `done_reported`/`approved`
(those transitions only via the new RPCs below).

### 3.2 `tk_commit_task` — capacity + first-claim transition

Redefine (same signature) with, inside the existing locked transaction:

- Capacity: `SELECT count(*) FROM task_commitments WHERE task_id = p_task_id
  AND status = 'active' FOR UPDATE` (lock the task row first with
  `SELECT ... FROM tasks ... FOR UPDATE` to serialize racing claims);
  if count ≥ `people_needed` → `RAISE EXCEPTION 'job_full'`.
- First active claim on an `open` task → `status = 'in_progress'`.
- Claiming stays open regardless of T-36h and through the event (spec §2.4);
  block claiming only on `done_reported`/`approved`/`cancelled` tasks.

### 3.3 `tk_uncommit_task` — hard T-36h lock (replaces the 24h "late" flag)

The function already resolves the linked event's start (it logs
`hours_before_event`). Change the rule:

```
IF v_event_start IS NOT NULL AND v_event_start - now() < interval '36 hours'
THEN RAISE EXCEPTION 'unclaim_locked';
```

- Tasks with no `event_id` (standalone chores): no lock, unchanged behavior.
- Keep writing `hours_before_event` to the append-only log; the `late` concept
  is superseded (leave existing log rows/columns untouched).
- When the last active claimant uncommits → `status = 'open'` (card reverts 🔴).
- `-- PHASE3 SEAM:` comment where the start is resolved — initiatives will add
  a second parent type here.

### 3.4 New RPCs (each: tenancy, idempotency, audit, outbox enqueue)

- **`tk_report_done(p_chapter_id, p_task_id, p_member_id, p_idempotency_key)`**
  Guards: caller has an `active` commitment on the task; `status = 'in_progress'`
  (this enforces once-per-job — a second report finds `done_reported` and
  raises `already_reported`; idempotent retry of the *same* report replays via
  idempotency key). Sets `status='done_reported'`, `reported_by/at`, and
  **clears `rejected_* / rejection_reason`** (spec: banner clears on next
  report; history stays in `audit_logs`). Outbox: `JOB_REPORTED`, one row per
  approver (event supervisors — resolved from `event_supervisors`).
- **`tk_approve_task(p_chapter_id, p_task_id, p_actor_id, p_idempotency_key)`**
  Guard: `status = 'done_reported'`. Sets `status='approved'`, `approved_by/at`;
  marks active commitments `completed`. Outbox: `JOB_APPROVED`, one row per
  claimant. (Approver *authorization* is checked in the Python service, §4.2;
  the RPC enforces state machine + tenancy.)
- **`tk_reject_task(p_chapter_id, p_task_id, p_actor_id, p_reason TEXT,
  p_idempotency_key)`**
  Guards: `status = 'done_reported'`; `length(btrim(p_reason)) > 0` → else
  `RAISE 'rejection_reason_required'`. Claimants are retained; status returns to
  `in_progress` if any active commitments remain, else `open` (spec: "back to
  🔴/🟢"). Sets `rejected_by/at`, `rejection_reason`; clears `reported_*`.
  Outbox: `JOB_REJECTED` per claimant, reason in `payload`.

Deterministic outbox `dedup_key`s (unique index demands it; keys must be
stable across idempotent retries). Use a rejection-cycle counter,
`v_cycle = (SELECT count(*) FROM audit_logs WHERE target = task AND action =
'JOB_REJECTED')`:
`job_reported:{task_id}:{cycle}:{member_id}`,
`job_rejected:{task_id}:{cycle}:{member_id}`,
`job_approved:{task_id}:{member_id}` (approval is once-per-job).

### 3.5 Catalog additions (DO-block rebuild pattern)

- `message_outbox.event_type` += `JOB_REPORTED`, `JOB_APPROVED`, `JOB_REJECTED`.
- `audit_logs.action` += `JOB_REPORTED`, `JOB_APPROVED`, `JOB_REJECTED`
  (again: match the existing naming style in 0110's audit writes before coining).

### 3.6 Optional (cut first if time-boxed): `tk_update_task`

Small RPC for approver edits (title/description/`people_needed`) with guard
`people_needed >= current active-claim count`. Spec's job-card Edit needs it
eventually, but nothing in Phase 1–4 depends on it.

## 4. Backend code changes

### 4.1 `api/events/`

| File | Change |
|---|---|
| `api/schemas.py` | `EventCreate`/`EventUpdate`/`EventResponse` gain `end_date`, `end_time`, `invite_link`. `EventResponse` gains `supervisors: list[SupervisorOut]` (`member_id`, `is_creator`, `name?`). New `SupervisorAdd {member_id}`. |
| `services/events.py` | Pass new params to `ev_create_event`; validate `end > start` when provided; read supervisors from `event_supervisors` (stop reading `supervisor_member_id`); `add_supervisor` / `remove_supervisor` calling the new RPCs (officer-role keys passed as eligibility, mirroring the existing `CHAIR_ROLES` pattern in `auth.py` — add an `OFFICER_ROLES` tuple there). |
| `api/events.py` | New routes: `POST /{event_id}/supervisors` (actor must be a current supervisor of the event, or hold `calendar:event:update`), `DELETE /{event_id}/supervisors/{member_id}` (same gate; creator/min-1 violations surface as 409 from the RPC). Existing `POST /{event_id}/supervisor` kept, delegating to add-supervisor (deprecation note in `CONFORM_TODO.md`). |

### 4.2 `api/tasks/`

| File | Change |
|---|---|
| `api/schemas.py` | Task shapes gain `people_needed`, `claimed_count`, `claimants: list[ClaimantOut]`, new statuses, `reported_by/at`, `rejection_reason`, `rejected_at`. New `RejectIn {reason: str}` (Pydantic `min_length=1` after strip — reject at the edge *and* in the RPC). |
| `services/` | `report_done` / `approve` / `reject` service functions calling the new RPCs. New `approvals.py`: `can_approve_job(user, task) -> bool` — if `task.event_id`: actor ∈ `event_supervisors` for that event; else fall back to `has_permission(user, "tasks:review", resource=task)`. `-- PHASE3 SEAM`: initiative chairs plug in here. |
| `api/tasks.py` (or sibling route file) | `POST /{task_id}/report-done` (`tasks:complete`, claimant-checked in RPC); `POST /{task_id}/approve` and `POST /{task_id}/reject` (gated by `can_approve_job`, 403 otherwise). Map RPC exceptions → HTTP: `job_full` → 409, `unclaim_locked` → 409, `already_reported` → 409, `rejection_reason_required` → 422. List/detail responses include fill state (`claimed_count`/`people_needed`) and claimants. |
| Job creation on events | When `POST /api/tasks` carries an `event_id`: actor must be a supervisor **or** organizer of that event (spec §5), or hold `tasks:assign`. Reuses `event_supervisors` + `event_organizers` lookups. |

No changes to `api/index.py` (routers already mounted; domain routers are
append-only).

### 4.3 Notifications

Outbox rows are written inside the RPCs (§3.4) — consistent with the
announcements/treasury pattern. No new dispatcher in Phase 1; delivery of
JOB_* messages rides the existing outbox semantics and becomes user-visible in
Phase 2/5. Do **not** add an events-domain `notifications.py` yet (Phase 2, for
EVENT_NOTIFY).

## 5. Tests (pytest, from `LocalDev/`; superuser conn bypasses RLS per existing treasury-test pattern)

`tests/events/test_supervisors.py`
1. Create event → creator auto-present in `event_supervisors` with `is_creator`.
2. Add co-supervisor (officer role) → appears in `EventResponse.supervisors`;
   idempotent re-add is a no-op.
3. Add with non-officer target → rejected.
4. Remove co-supervisor OK; removing creator → error; removing last supervisor → error.
5. Non-supervisor without `calendar:event:update` → 403 on add/remove.
6. Backfill assertions against a pre-seeded legacy row (`supervisor_member_id`).
7. Create with `end_time` before `time` on the same date → 422; valid range persists.

`tests/tasks/test_jobs_lifecycle.py`
1. Capacity: `people_needed=2` → two claims OK, third → `job_full`/409;
   fill state reads 2/2.
2. First claim flips `open → in_progress`; last uncommit (before lock) flips back to `open`.
3. T-36h: task on an event starting <36h from now → uncommit raises
   `unclaim_locked`; claiming still allowed; task with no `event_id` → uncommit fine.
   (Control the window by inserting events with `date`/`time` computed relative
   to `now()` — no clock mocking needed.)
4. Report done: non-claimant → error; claimant → `done_reported` + `reported_by`;
   second report → `already_reported`; idempotency-key replay returns first result.
5. Approve: `done_reported → approved`, commitments `completed`,
   `JOB_APPROVED` outbox rows per claimant with stable dedup keys (re-run RPC
   with same idempotency key → no duplicate rows).
6. Reject: empty/whitespace reason → error; valid reason → back to
   `in_progress` with claimants retained, `rejection_reason` set,
   `JOB_REJECTED` outbox rows; next report clears rejection fields;
   reject when zero active claimants → `open`.
7. `tk_update_task_status` refuses `done_reported`/`approved`.
8. Audit rows written for every transition; `task_commitment_log` append-only
   trigger still blocks mutation.

## 6. Execution checklist

1. `ls migrations/ | tail` — confirm 0141/0142 are free; renumber if not.
2. Write 0141, run `npm run migrate`, then `tests/events/test_supervisors.py`.
3. Write 0142, migrate, then `tests/tasks/test_jobs_lifecycle.py`.
4. Backend code changes (§4), full `python3 -m pytest`.
5. `npm run verify` (CI-equivalent sandbox check).
6. Update `docs/events-dev-status.md`: Phase 1 → done, record actual migration
   numbers, note any decision drift. Update `api/events/CONFORM_TODO.md`
   (supervisor column deprecation, old endpoint deprecation).
7. Commit per repo convention (`feat(events): …`, `feat(tasks): …`).
