# 11 · Events and tasks: safe delete, atomic edits, a real job lifecycle

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `11-events-tasks` · **Wave:** 2 (needs 01 and 04 merged) · **Agent:** GPT-6 Luna medium (Codex CLI) · **Branch:** `fix/audit-11-events-tasks`
**Findings:** F-012, F-011 (`update_event`, `create_task`), F-025, F-043, F-053
**Migrations:** `0181_event_cancel.sql`, `0182_task_status_transitions.sql` (0183–0185 spare)
**Goal:** deleting an event never strands or destroys records; editing an event or creating a task cannot half-apply; a job cannot skip review or be reopened after it is closed; a re-assigned organizer is notified again; the dead "operations" API is unmounted.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-012, F-011, F-025, F-043, F-053; decision D4 in `00-README.md`.

## Facts you can rely on

- `get_db().transaction()` exists (stream 01): `with sb.transaction() as tx:`; every query inside must use `tx`; `call_rpc(name, params, sb=tx)` joins it.
- The query builder has no `IS NULL` filter. Use boolean columns for flags.
- Task statuses (`tasks_status_check`, `migrations/0142_jobs_v1_lifecycle.sql:26`): read the live list there. `done_reported` and `approved` are set only by `tk_report_done` / `tk_approve_task`; `tk_cancel_task` (`0152:170`) cancels.
- A "job" is a task with `event_id` or `initiative_id` set. A "standalone task" has neither; the SPA toggles those between `open` and `done` (`greekos/src/hooks/useTasks.ts:39-45`).
- Live definitions: `tk_update_task_status` → `0145:885` (four definitions; that is the live one). `fn-index.txt` has the rest.

## Global constraints

- Allowed files: `migrations/0181_event_cancel.sql`, `migrations/0182_task_status_transitions.sql`, `api/events/api/events.py` (NOT the `get_checkin_link` handler, stream 10 edits it), `api/events/services/events.py`, `api/events/notifications.py`, `api/tasks/api/tasks.py`, `api/tasks/api/operations.py` (delete), `api/tasks/services/tasks.py`, `api/tasks/services/templates.py` (delete), `tests/events/**`, `tests/tasks/**`, `tests/services_scaffold/test_route_registration.py`.
- Shared file, two regions only: `api/index.py` → the operations router import (~lines 142-143) and its `include_router` (~lines 199-203). Stream 13 edits the boot guard at the top of that file in parallel.
- DB functions you own this wave: new `ev_delete_or_cancel_event`; `tk_update_task_status`. Do not replace any other `ev_*` or `tk_*` function.
- Do not touch `api/events/services/notifications.py` (stream 12), `api/memberadmin/**`, `api/attendance/**`.
- Do not drop any table. The operations tables (`event_templates*`, `event_roles`, `event_tasks`, `post_event_reports`) stay.
- Run `python3 -m pytest tests/events tests/tasks tests/services_scaffold tests/calendar_view -q`. Not the full suite.

## Review focus

1. Deleting an event from another chapter is 404 and changes nothing.
2. An event with only an expired, inactive check-in link and nothing else still counts as "empty" and is really deleted; one with any attendance row, excuse, job, fine invoice, notification send or security swap is cancelled instead.
3. A cancelled event stops counting for standing and fines (it becomes `required = false`) but its attendance rows and issued fines remain.
4. `update_event` with a bad audience leaves title, time and visibility unchanged.
5. Replaying an idempotent `tk_update_task_status` call returns the stored result even if the transition would now be illegal.

---

### Task 1: F-012 — delete if empty, otherwise cancel (decision D4)

**Files:** `migrations/0181_event_cancel.sql`, `api/events/api/events.py:128-147`, `api/events/services/events.py` (visibility function, ~lines 224-377), `tests/events/test_event_delete.py` (new)

**Interfaces (produced):**

```sql
ev_delete_or_cancel_event(p_chapter_id UUID, p_event_id UUID, p_actor_id UUID) RETURNS JSONB
-- {"deleted": true, "cancelled": false}  or  {"deleted": false, "cancelled": true}
```

`DELETE /api/events/{id}` returns that object (it returned `{"deleted": true}` before).

- [ ] **Step 1: failing tests** (follow `tests/events/conftest.py` for event and member helpers; use the tasks `task_factory` shape from `tests/tasks/conftest.py` with direct inserts where needed):
  - `test_empty_event_is_deleted`: fresh event → `{"deleted": True, "cancelled": False}`, row gone.
  - `test_event_with_attendance_is_cancelled_not_deleted`: add an attendance row → `{"deleted": False, "cancelled": True}`; event row still exists with `cancelled = true` and `required = false`; the attendance row still exists.
  - `test_cancel_closes_open_work`: event with an active check-in link, an open job and a fine invoice (`unpaid_invoices.source_event_id`) → after delete: link `active = false`, job `status = 'cancelled'`, invoice unchanged and still pointing at the event.
  - `test_cancelled_event_is_hidden_from_lists`: it no longer appears in `GET /api/events` or the calendar feed for a member or an officer.
  - `test_cancel_writes_audit_row`; `test_delete_other_chapter_is_404`; `test_cancelling_twice_is_a_noop_success`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration.**

```sql
ALTER TABLE events ADD COLUMN IF NOT EXISTS cancelled BOOLEAN NOT NULL DEFAULT false;
```

  Then `ev_delete_or_cancel_event`: lock the event row (`FOR UPDATE`, raise `event % not found in chapter %` if missing); if `cancelled` already, return the cancelled shape. Compute "has history" = any row referencing this event in `attendance`, `excuses`, `tasks` (`event_id`), `unpaid_invoices` (`source_event_id`), `event_notification_sends`, `security_swap_requests`, `attendance_sessions`. Find every table with a foreign key to `events` first (`grep -n "REFERENCES events" migrations/*.sql`) and include each one that holds user-visible history; `checkin_links`, `event_organizers`, `event_supervisors` and `event_audience_members` do not count as history. If no history: `DELETE FROM events WHERE id = p_event_id` and return the deleted shape. Otherwise: `UPDATE events SET cancelled = true, required = false`; `UPDATE checkin_links SET active = false WHERE event_id = … AND active`; `UPDATE tasks SET status = 'cancelled' WHERE event_id = … AND status NOT IN (<the terminal statuses in tasks_status_check: done, approved, cancelled; read the constraint>)` (security tasks included; if a trigger refuses that, use the same statements `tk_cancel_task` uses); insert one `audit_logs` row. For the audit `action`, reuse an existing event action value: `grep -n "INSERT INTO audit_logs" -A2 migrations/0101*.sql migrations/0141*.sql` and pick the event-update action already in use; put `{"cancelled": true}` in `metadata`. Return the cancelled shape.
- [ ] **Step 4: route and reads.** `delete_event` keeps its 404 lookup and then returns `call_rpc("ev_delete_or_cancel_event", {...}).data`. In `api/events/services/events.py`, add `.eq("cancelled", False)` to the one visibility/list query the list, detail and calendar reads share (report §9: "Event visibility is one function reused by list, detail and calendar"). Detail of a cancelled event → 404.
- [ ] **Step 5: apply (`python3 scripts/migrate_db.py`), run `tests/events tests/calendar_view -q`, expect PASS. Checkpoint** — suggested message `fix(events): delete empty events, cancel the rest and keep their history`.

---

### Task 2: F-011 — `update_event` and `create_task` are all-or-nothing

**Files:** `api/events/services/events.py:527-598`, `api/tasks/services/tasks.py` (`create_task`), `tests/events/test_audience.py`, `tests/tasks/test_jobs_api.py`

- [ ] **Step 1: failing tests.**
  - `test_update_event_rolls_back_when_audience_is_rejected`: call `update_event` with a new title and a custom audience containing a member id from another chapter (the `ev_set_audience` RPC rejects it). Expect an error, and the event's title is unchanged afterwards.
  - `test_create_task_is_atomic`: read `create_task` first to see its second statement (the audit card says capacity is set in a second write). Make that second statement fail (for example a `people_needed` value the table's CHECK rejects, if the first statement does not already validate it; otherwise monkeypatch the second call to raise) and assert no task row was left behind.
- [ ] **Step 2: run, expect FAIL** (title changed; task row left behind). If `create_task` turns out to be a single statement already, record that half as `NOT_REPRODUCED`.
- [ ] **Step 3: implement.** In `update_event`, wrap the scalar update and the `ev_set_audience` call (and any other write in that function) in `with sb.transaction() as tx:` and route each through `tx` (`call_rpc(..., sb=tx)`). Reads before the block may stay on `sb`. Same for `create_task`. If either function calls a helper that fetches its own client with `get_db()`, give that helper an `sb` parameter and pass `tx`.
- [ ] **Step 4: run `tests/events tests/tasks -q`, expect PASS. Checkpoint** — `fix(events,tasks): event update and task create commit as one transaction`.

---

### Task 3: F-025 — task status follows a transition table

Rules:

| Current status | Allowed through `POST /api/tasks/{id}/status` |
|---|---|
| `approved`, `cancelled` | nothing (closed) |
| `done_reported` | nothing (use approve / reject) |
| any other, task is a job (`event_id` or `initiative_id` set) | any target except `done`, `done_reported`, `approved` |
| any other, standalone task | any target except `done_reported`, `approved` |

And the route's ownership rule: the caller may change status when they are the task's `assigned_member_id`, or hold an active commitment on it, or hold `tasks:review`. An unowned task therefore needs `tasks:review` (today it is open to everyone with `tasks:complete`).

**Files:** `migrations/0182_task_status_transitions.sql`, `api/tasks/api/tasks.py:74-99`, `tests/tasks/test_jobs_lifecycle.py:264-290`

- [ ] **Step 1: failing tests** next to the existing status-guard tests: `test_job_cannot_be_set_done_directly` (job → `done` raises `use report and approve`); `test_approved_task_cannot_be_reopened`; `test_cancelled_task_cannot_be_reopened`; `test_done_reported_cannot_be_changed_here`; `test_standalone_task_can_toggle_open_and_done` (must keep passing); and at the route level `test_unowned_job_status_needs_review_permission` (plain member, task with no `assigned_member_id` and no commitment by them → 403) and `test_committed_member_can_update_their_job` (→ 200 for `in_progress`).
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration.** Copy the live `tk_update_task_status` (`0145:885-947`). After `v_old_status := v_task.status;` add:

```sql
    IF v_old_status IN ('approved', 'cancelled') THEN
        RAISE EXCEPTION 'task_closed: a % task cannot change status', v_old_status;
    END IF;
    IF v_old_status = 'done_reported' THEN
        RAISE EXCEPTION 'task_in_review: approve or reject the reported job instead';
    END IF;
    IF p_status = 'done' AND (v_task.event_id IS NOT NULL OR v_task.initiative_id IS NOT NULL) THEN
        RAISE EXCEPTION 'job_needs_review: jobs are completed through report and approve';
    END IF;
```

- [ ] **Step 4: route.** In `update_task_status`, replace the `resource = {...}` permission block with: allowed if `task.get("assigned_member_id") == user["id"]`, or the caller has an `active` row in `task_commitments` for this task (one query), or `has_permission(user, "tasks:review", sb=sb)`; and in every case the caller must hold `tasks:complete` (keep that check). Otherwise 403 with the existing message. Map the three new error prefixes to `HTTPException(409, <the text after the colon>)` the same way this file maps other RPC errors.
- [ ] **Step 5: apply, run `tests/tasks -q`, expect PASS. Checkpoint** — `fix(tasks): status changes follow the job lifecycle and need ownership`.

---

### Task 4: F-043 — a new assignment is a new notification

**Files:** `api/events/notifications.py:81-98`, `api/events/services/events.py:625-754`, `tests/events/test_organizers.py`, `tests/events/test_supervisors.py`

- [ ] **Step 1: failing test** `test_reassigned_organizer_is_notified_again`: add member M as organizer, remove M, add M again; two `message_outbox` rows of type `EVENT_ROLE_ASSIGNED` exist for M and this event. Same for supervisor. And `test_retry_of_one_assignment_notifies_once`: calling the add with the same `Idempotency-Key` twice (or the add RPC returning the existing row) produces one row.
- [ ] **Step 2: run, expect FAIL** (one row).
- [ ] **Step 3: implement.** `notify_role_assigned` gains a required keyword `assignment_id: str` and builds `dedup_key=f"{EVENT_ROLE_ASSIGNED}:{event_id}:{member_id}:{role}:{assignment_id}"`. In `add_organizer` / `add_supervisor`, pass the id of the row the RPC just returned (`ev_add_organizer`, `ev_add_supervisor` return the assignment row; read the result shape). If a result has no row id, pass its `created_at` timestamp string instead.
- [ ] **Step 4: run `tests/events -q`, expect PASS. Checkpoint** — `fix(events): notify again when someone is re-assigned to an event role`.

---

### Task 5: F-053 — unmount the operations template engine

Nothing in the UI calls `/api/operations`; it writes rows no screen reads.

**Files:** `api/index.py` (two regions), `api/tasks/api/operations.py`, `api/tasks/services/templates.py`, `tests/services_scaffold/test_route_registration.py:32`

- [ ] **Step 1:** confirm no caller: `grep -rn "operations" greekos/src api --include=*.ts --include=*.tsx --include=*.py | grep -v "^api/tasks/api/operations.py\|^api/tasks/services/templates.py"`. Expected hits: the two regions in `api/index.py`, possibly a docstring in `api/nl_controller`. If anything else imports `templates.py` or `operations.py`, stop and report.
- [ ] **Step 2: failing test:** change the assertion at `test_route_registration.py:32` to assert that no route path starts with `/api/operations`. Run it; expect FAIL.
- [ ] **Step 3:** remove the import and the `include_router` for the operations router from `api/index.py`; `git rm api/tasks/api/operations.py api/tasks/services/templates.py`. If `api/tasks/api/router.py` includes the operations router, remove that include too (the append-only rule does not apply to a deleted sub-router; say so in the report).
- [ ] **Step 4:** `python3 -c "import api.index"` succeeds; run `tests/services_scaffold tests/tasks -q`, expect PASS. **Checkpoint** — `chore(tasks): unmount the orphaned operations template API`.

## Report

Finish with the report block from `00-README.md` ("What to hand back"). List the two deleted files under "Deleted files" so the orchestrator can archive them.
