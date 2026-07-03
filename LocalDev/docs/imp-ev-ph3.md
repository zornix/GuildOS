# Events V1 — Phase 3 Implementation Plan (Initiatives)

Backend-only. Implements `docs/events-v1-spec.md` §2.2 (Initiative), §2.4 (jobs
lifecycle shared with initiatives), §2.6 (calendar), §5 (permissions matrix
rows for initiatives), and resolves spec Open Item 1 (initiatives always have a
start time). Global decisions D1–D4 in `docs/events-dev-status.md` apply;
Phase 2's D5–D7 stand. This plan adds D8–D11.

## 1. Scope & assumptions

In scope: the `initiatives` entity (chair-created, assigned chairs, required
start time), jobs on initiatives via the existing tasks machinery with
**chair** approval, the T-36h unclaim lock anchored to initiative start, and
`kind: "initiative"` items in the calendar aggregator.

Out of scope (spec §2.2, §6): supervisors, security, attendance/fines, and the
notify gate — "an initiative is an event with the officer layer deleted."

### Verified current state this plan builds on (2026-07-03)

- Migration frontier is `0143_event_notify.sql`; **0144 is free**. Re-verify
  with `ls migrations/ | tail` before writing anything; renumber if taken.
- `migrations/0142_jobs_v1_lifecycle.sql` contains the T-36h resolver seam
  inside `tk_uncommit_task` (lines ~160–172), marked:
  `-- PHASE3 SEAM: the linked-event start is resolved here; initiatives will
  add a second parent type (resolve its start alongside v_task.event_id).`
- `api/tasks/services/approvals.py:10` carries the second seam:
  `-- PHASE3 SEAM: initiative chairs plug into can_approve_job for initiative
  jobs.` Today `can_approve_job` branches: `task["event_id"]` →
  `_is_event_supervisor`, else `has_permission(user, TASKS_REVIEW)`.
- `tk_report_done` (0142) fans `JOB_REPORTED` outbox rows to
  `event_supervisors`; for parentless jobs the loop is empty by design.
- Current tk_* signatures in force: `tk_create_task` (0110 — ends
  `p_idempotency_key TEXT DEFAULT NULL, p_event_id UUID DEFAULT NULL`),
  `tk_commit_task` / `tk_uncommit_task` / `tk_report_done` / `tk_approve_task`
  / `tk_reject_task` (all 0142).
- `event_supervisors` (0141): `id, chapter_id, event_id, member_id,
  is_creator, added_by, created_at`, `UNIQUE(event_id, member_id)`, RLS via
  `rbac_request_chapter_id()` — the shape `initiative_chairs` mirrors.
- Events carry `date DATE NOT NULL`, `time TIME NOT NULL` (0001) and nullable
  `end_date`/`end_time` (0141) — initiatives mirror this, which is exactly
  what Open Item 1 asks for.
- `api/events/auth.py` defines
  `CHAIR_ROLES = ("risk_chair", "social_chair", "recruitment_chair",
  "brotherhood_chair", "philanthropy_chair", "standards_chair")`.
- No `initiative` code exists anywhere (grep confirms: only the two seam
  comments). No `calendar:initiative:*` permission keys are seeded.
- Calendar aggregator: `api/calendar/services/calendar.py::get_calendar`
  appends `kind: "event" | "invoice_due" | "task_due"` items; the frontend
  switches on `kind`, so a new kind needs no discriminator plumbing.
- `npm run verify` no longer exists (deploy/ was removed); the full-suite gate
  is `python3 -m pytest`.

### Decisions baked into this plan

- **D8 — Initiatives are a separate table, not a flavor of events.** Events
  carry the officer machinery (supervisors, attendance/fines, notify) that the
  spec explicitly deletes for initiatives. A type flag on `events` would leak
  initiatives into every event list, RPC, and attendance path and force
  NULL-guards everywhere. Instead: `initiatives` + `initiative_chairs`
  mirroring `events` + `event_supervisors` shape-for-shape, and jobs attach
  via a sibling `tasks.initiative_id`.
- **D9 — Chapter-level chair gating is a seeded permission key; per-initiative
  authority is membership.** `calendar:initiative:create` / `:update` are
  seeded to the six chair roles (0130 seeding pattern, including the explicit
  admin rows). Everything scoped to one initiative — edit, manage chairs,
  create jobs, approve/reject jobs — is gated on **assigned-chair membership**
  (a row in `initiative_chairs`), the same membership-not-permission pattern
  as D5. No `user["role"]` string comparisons anywhere (hard rule); the
  spec's "Chair ✅ / exec — / member —" matrix is realized by which roles the
  key is seeded to, not by code.
- **D10 — New domain package `api/initiatives/`, mounted at
  `/api/initiatives`.** Initiatives are calendar peers of events, not
  sub-resources of them. The canonical domain-package layout applies; a small
  domain omits what it doesn't need (no `core/`, no `notifications.py`).
  `api/index.py` mounting is append-only.
- **D11 — The job RPC surface is reused, not duplicated.** No `in_*` job
  RPCs. `tk_create_task` gains `p_initiative_id` (using 0110's own
  DROP-then-recreate precedent for signature changes), `tk_uncommit_task`
  resolves initiative start at the PHASE3 SEAM, and `tk_report_done` fans
  `JOB_REPORTED` to `initiative_chairs`. Approval authorization stays
  Python-side in `can_approve_job` (as it is for events today).

## 2. Migration `0144_initiatives_v1.sql`

All RPCs: tenancy guard (`chapter_id` checked against the row), idempotency
via `idempotency_keys` (0143's exact open/close blocks, `operation` = function
name), `audit_logs` write. RLS + policies per the 0143 pattern
(`rbac_request_chapter_id()`).

### 2.1 `initiatives`

```sql
CREATE TABLE IF NOT EXISTS initiatives (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id  UUID NOT NULL REFERENCES chapters(id),
    title       TEXT NOT NULL,
    description TEXT,
    date        DATE NOT NULL,          -- Open Item 1: start is required
    time        TIME NOT NULL,
    end_date    DATE,
    end_time    TIME,
    created_by  UUID NOT NULL REFERENCES members(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Index on `(chapter_id, date)`. RLS enabled + chapter SELECT policy (0143
pattern). No status column in V1 (no cancel flow in the spec).

### 2.2 `initiative_chairs`

Mirror `event_supervisors` (0141) exactly, renamed:

```sql
CREATE TABLE IF NOT EXISTS initiative_chairs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id    UUID NOT NULL REFERENCES chapters(id),
    initiative_id UUID NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE,
    member_id     UUID NOT NULL REFERENCES members(id),
    is_creator    BOOLEAN NOT NULL DEFAULT false,
    added_by      UUID REFERENCES members(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (initiative_id, member_id)
);
```

RLS + chapter SELECT policy.

### 2.3 `tasks.initiative_id` + parent exclusivity

```sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS
    initiative_id UUID REFERENCES initiatives(id) ON DELETE SET NULL;
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_single_parent_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_single_parent_check
    CHECK (event_id IS NULL OR initiative_id IS NULL);
```

Index on `initiative_id` (partial, `WHERE initiative_id IS NOT NULL`).

### 2.4 RPC changes

**New: `in_create_initiative(p_chapter_id UUID, p_title TEXT, p_description
TEXT, p_date DATE, p_time TIME, p_end_date DATE, p_end_time TIME,
p_chair_member_ids UUID[], p_actor_id UUID, p_idempotency_key TEXT DEFAULT
NULL) RETURNS JSONB`**
- Validates every member id in `p_chair_member_ids` belongs to
  `p_chapter_id`; raises `member_not_in_chapter` otherwise.
- Inserts the initiative; inserts one `initiative_chairs` row per id, with the
  actor auto-added if absent and marked `is_creator = true` (spec: creator
  pre-filled; any number of chairs).
- Audit `INITIATIVE_CREATED`. Returns the initiative row + chair ids as JSONB.

**New: `in_update_initiative(p_chapter_id UUID, p_initiative_id UUID,
p_title TEXT, p_description TEXT, p_date DATE, p_time TIME, p_end_date DATE,
p_end_time TIME, p_actor_id UUID, p_idempotency_key TEXT DEFAULT NULL)
RETURNS JSONB`**
- Raises `not_assigned_chair` unless the actor has an `initiative_chairs` row
  (trust-boundary check lives in the RPC, mirroring where 0143 put the
  completeness gate). NULL params mean "unchanged" (COALESCE). `date`/`time`
  may never be set NULL (Open Item 1). Bumps `updated_at`; audit
  `INITIATIVE_UPDATED`.

**New: `in_add_chair` / `in_remove_chair` `(p_chapter_id UUID,
p_initiative_id UUID, p_member_id UUID, p_actor_id UUID, p_idempotency_key
TEXT DEFAULT NULL) RETURNS JSONB`**
- Actor must be an assigned chair. `in_add_chair` is idempotent on the UNIQUE
  constraint (ON CONFLICT DO NOTHING, still returns the row). `in_remove_chair`
  raises `last_chair` when it would leave zero chairs (an initiative must stay
  approvable). Audit `INITIATIVE_CHAIR_ADDED` / `INITIATIVE_CHAIR_REMOVED`.

**Changed: `tk_create_task`** — follow 0110's precedent: `DROP FUNCTION IF
EXISTS tk_create_task(<full current 0110 signature>);` then recreate with
trailing `p_initiative_id UUID DEFAULT NULL` (do NOT leave an overload
behind). New body checks: both `p_event_id` and `p_initiative_id` non-null →
`RAISE EXCEPTION 'task_two_parents'`; a non-null `p_initiative_id` must exist
in `p_chapter_id` → else `initiative_not_found`. Everything else verbatim.

**Changed: `tk_uncommit_task`** — CREATE OR REPLACE (same signature). At the
PHASE3 SEAM, add alongside the event branch:

```sql
    IF v_task.initiative_id IS NOT NULL THEN
        SELECT (i.date + COALESCE(i.time, TIME '00:00'))::timestamptz
          INTO v_event_start
          FROM initiatives i WHERE i.id = v_task.initiative_id;
        v_hours := ROUND((EXTRACT(EPOCH FROM (v_event_start - now())) / 3600.0)::numeric, 2);
    END IF;
```

The existing `< interval '36 hours'` hard-lock check then applies unchanged
(spec §2.4: "36 hours before event/initiative start"; D2).

**Changed: `tk_report_done`** — CREATE OR REPLACE (same signature). Extend the
fan-out: when `v_task.initiative_id IS NOT NULL`, enqueue `JOB_REPORTED`
outbox rows to each `initiative_chairs.member_id` (same dedup-key shape the
supervisor loop uses, task-scoped). Supervisor loop stays as is.

`tk_approve_task` / `tk_reject_task` are untouched — approver authorization is
Python-side (§3.2), consistent with events today.

### 2.5 Catalog additions + permission seed

- `audit_logs.action`: add `INITIATIVE_CREATED`, `INITIATIVE_UPDATED`,
  `INITIATIVE_CHAIR_ADDED`, `INITIATIVE_CHAIR_REMOVED` via the **dual-format
  DO-block rebuild** (copy 0142 lines ~569–610 verbatim, swap the array).
- `message_outbox.event_type`: **no additions** — `JOB_REPORTED` already
  exists.
- Permissions: seed `calendar:initiative:create` and
  `calendar:initiative:update` following `0130_announcements_sms_rbac_seed.sql`
  exactly (INSERT INTO `permissions`, then `role_permissions` rows), granted
  to the six chair roles from `api/events/auth.py::CHAIR_ROLES` **and** the
  explicit admin rows 0130 adds. Do not seed exec/member (spec §5: exec —,
  member —). No `:delete` key — there is no delete flow in V1.

## 3. Backend code changes

### 3.1 New domain package `api/initiatives/`

Canonical layout, small-domain subset:

```
api/initiatives/
  __init__.py
  auth.py            # INITIATIVE_CREATE/UPDATE consts + is_assigned_chair(sb, initiative_id, member_id)
  api/router.py      # aggregates; api/index.py mounts ONLY this at /api/initiatives
  api/initiatives.py # route handlers, thin
  api/schemas.py     # Pydantic v2, domain-local
  services/initiatives.py
  db/session.py      # get_initiatives_db (copy events' shape)
  db/rpc.py          # call_rpc (copy verbatim from api/events/db/rpc.py)
```

Routes (parse → service → respond; all 404 on cross-tenant / missing id):

| Route | Auth | Behavior |
|---|---|---|
| `POST /api/initiatives` | `require_permission(INITIATIVE_CREATE)` | → `in_create_initiative`; 201 |
| `GET /api/initiatives` | any member | chapter list, each item decorated with `chairs` (member ids) and `job_count` / `open_job_count` (batched, copying the Phase 2 decoration approach in `api/events/services/events.py`) |
| `GET /api/initiatives/{id}` | any member | detail: initiative + chairs + jobs (tasks where `initiative_id = id`) |
| `PATCH /api/initiatives/{id}` | assigned chair (403 otherwise) | → `in_update_initiative` |
| `POST /api/initiatives/{id}/chairs` | assigned chair | → `in_add_chair` |
| `DELETE /api/initiatives/{id}/chairs/{member_id}` | assigned chair | → `in_remove_chair`; map `last_chair` → 409 |

Service-layer 403s use `is_assigned_chair`; the RPCs re-check (defense in
depth at the trust boundary). Add the mount in `api/index.py` (append-only).

### 3.2 `api/tasks/` — the approval + creation seams

`api/tasks/services/approvals.py` (the PHASE3 SEAM file):
- `can_approve_job`: add the branch — if `task.get("initiative_id")` →
  `_is_initiative_chair(sb, task["initiative_id"], user_member_id)` (query
  `initiative_chairs`). Event branch and `TASKS_REVIEW` fallback unchanged.
- New `can_create_initiative_job(sb, *, user, initiative_id)`: assigned chair
  OR `has_permission(user, TASKS_ASSIGN)` — the initiative twin of
  `can_create_event_job`.
- Remove/resolve the seam comment.

Job creation surface: the tasks create schema/route accepts optional
`initiative_id` (mutually exclusive with `event_id` — reject both with 422 at
the schema layer before the RPC's own guard), threads `p_initiative_id`
through to `tk_create_task`, and authorizes via `can_create_initiative_job`.

### 3.3 `api/calendar/` — aggregator

In `api/calendar/services/calendar.py::get_calendar`, add an initiatives
block after the events block: fetch chapter initiatives in `[start, end]` and
append

```python
items.append({
    "kind": "initiative",
    "initiative_id": ..., "title": ..., "date": ..., "time": ...,
    "end_date": ..., "end_time": ...,
    "chair_member_ids": [...],   # spec Screen 1: title + time + chair avatars
})
```

Existing `items` date-sort covers ordering. `overdue_invoices` / `groups`
untouched.

## 4. What Phase 3 does NOT change

- No initiative notify button (spec §6 non-goal), no security section, no
  supervisors, no attendance/fines on initiatives.
- No frontend work — Screens 1/4 land with the frontend phase.
- No changes to `tk_commit_task`, `tk_approve_task`, `tk_reject_task`,
  `ev_*` RPCs, or any Phase 1/2 route.
- No new `message_outbox` event types; `EntryType`/`big_ledger` untouched
  (nothing financial here).

## 5. Tests

pytest from `LocalDev/`; superuser connection bypasses RLS for RPC tests, as
in Phases 1–2. Reuse `tests/treasury/conftest.py` via star-import like the
other suites.

### 5.1 `tests/initiatives/` (new)

`conftest.py`: mirror `tests/events/conftest.py` — `user_factory`,
`assign_role`, an `initiative_factory(chairs=[...], hours_from_now=None,
**overrides)` (insert directly or via `in_create_initiative`), and an HTTP
harness mounting the real `api.index.app` with `get_initiatives_db` /
`get_rbac_db` monkeypatched to `sb_client`, plus `as_member(member_id)`.

`test_initiatives_rpcs.py`:
1. create: initiative + chair rows written, actor auto-added as
   `is_creator = true`, audit row `INITIATIVE_CREATED` present.
2. create idempotency: same `p_idempotency_key` twice → one initiative,
   replayed result.
3. create tenant guard: chair id from another chapter →
   `member_not_in_chapter`.
4. update by non-chair → `not_assigned_chair`; by chair → fields change,
   `updated_at` bumps, audit `INITIATIVE_UPDATED`.
5. add/remove chair: audit rows; duplicate add is a no-op; removing the final
   chair → `last_chair`.

`test_initiatives_api.py`:
6. `POST /api/initiatives` as plain member → 403; as chair-role member → 201
   with chairs in body.
7. `GET /api/initiatives/{id}` → chairs + jobs + counts; other chapter's id →
   404.
8. chair-management routes: non-assigned chair → 403; `last_chair` → 409.

### 5.2 `tests/tasks/` additions (`test_jobs_initiative.py`)

9. `tk_create_task` with both `p_event_id` and `p_initiative_id` →
   `task_two_parents`; with a foreign-chapter initiative →
   `initiative_not_found`.
10. T-36h: job on an initiative starting 12h out → `tk_uncommit_task` raises
    `unclaim_locked`; 72h out → succeeds (reuse the `hours_from_now`
    factory approach from `tests/tasks/conftest.py::event_factory`).
11. approval: assigned chair passes `can_approve_job` and
    `tk_approve_task` completes; non-chair member without `tasks:review` is
    rejected at the service layer.
12. `tk_report_done` on an initiative job → one `JOB_REPORTED` outbox row per
    assigned chair, deduped on replay.

### 5.3 `tests/calendar_view/` addition

13. Add an `initiative_factory` to the calendar conftest; an initiative inside
    the window yields a `kind == "initiative"` item carrying
    `chair_member_ids`; outside the window it does not appear.

## 6. Execution checklist

1. `ls migrations/ | tail` — confirm 0144 is free; renumber if not.
2. Write `0144_initiatives_v1.sql` (§2); `npm run migrate`; re-run to prove
   idempotence.
3. RPC tests red → green (§5.1 items 1–5, §5.2 items 9–12).
4. Build `api/initiatives/` package + mount (§3.1); tasks seams (§3.2);
   calendar block (§3.3).
5. HTTP tests green (§5.1 items 6–8, §5.3).
6. Full `python3 -m pytest` — green (no `npm run verify`; it was removed).
7. Update `docs/events-dev-status.md` (Phase 3 → done, decisions D8–D11
   recorded) and resolve both PHASE3 SEAM comments.
8. Commit: `feat(initiatives): chair-led initiatives with jobs + calendar (phase 3)`.
