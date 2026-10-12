# M4 — Jobs: lifecycle guards and the board

> Read `00-README.md` first. Test first. Stay in your lane. Starts after M3 is merged (the shared `JobCard` replaces the job UI inside `EventDetail`).

**Goal:** the member-first job workflow (D3) with the holes closed: supervisors/chairs create on their own parent; nobody approves a job they claimed; officers can approve as a fallback; the generic status route is gone; one `JobCard`; a board that shows active jobs by default and keeps history.
**Spec:** `../01-phase-b-design.md` §6; `../audit/tasks.md` §2, §9.
**Migrations:** 0221.
**Allowed files:** backend `migrations/0221_job_approval_guards.sql`, `api/tasks/**`, tests under `tests/tasks/`, `tests/contribution/` (only if a test pins removed behaviour); frontend `components/jobs/**`, `components/ui/JobCard.tsx`, `components/TasksModule.tsx` (delete when replaced), `components/events/EventDetail.tsx` (`JobsSection` only), `components/initiatives/**` (job section + add-job form only), `components/InitiativesModule.tsx` (job section only), `lib/tasks.ts`, `hooks/useTasks.ts`, `hooks/useJobs.ts`, `api.ts`/`types.ts` (M4 block), `routes.tsx` (`/jobs` line).

## T1 — Backend guards

- [ ] Failing tests `tests/tasks/test_approval_guards.py`:
  - an event supervisor who holds an active commitment on a job calls `/approve` → 403 `job_self_approval`; same via RPC `tk_approve_task` → raises;
  - a `tasks:review` holder who is not a supervisor approves an event job → 200 (fallback);
  - a `tasks:review` holder who is also a claimant → 403;
  - reject follows the same rule.
- [ ] Failing tests `tests/tasks/test_create_on_own_parent.py`: a member with no `tasks:create` who is a supervisor of event E creates a job on E → 201; a chair with only `calendar:initiative:create` creates a job on their initiative → 201; the same member creating a standalone job → 403; `assigned_member_id` on create by someone without `tasks:assign` → 403.
- [ ] Failing test `tests/tasks/test_status_route_removed.py`: `POST /api/tasks/{id}/status` → 404/405 (route gone); `tests/tasks/test_jobs_lifecycle.py::test_standalone_task_can_toggle_open_and_done` is deleted with a one-line reason in the report (behaviour removed on purpose: standalone jobs now go report → approve like every other job).
- [ ] `migrations/0221_job_approval_guards.sql`: `CREATE OR REPLACE FUNCTION tk_approve_task` and `tk_reject_task` (live bodies per `fn-index.txt`, 0142) adding: `IF EXISTS (SELECT 1 FROM task_commitments WHERE task_id = p_task_id AND member_id = p_actor_id AND status = 'active') THEN RAISE EXCEPTION 'job_self_approval'; END IF;`. Keep signatures. Drop `tk_update_task_status` only if nothing else calls it (grep migrations and api); otherwise leave it and just remove the route.
- [ ] `api/tasks/services/approvals.py:can_approve_job`: event/initiative branch becomes `is_supervisor_or_chair OR has_permission(tasks:review)`, then `AND NOT holds_active_commitment(actor)`. `api/tasks/api/tasks.py:create_task`: replace `Depends(require_permission(TASKS_CREATE))` with `get_current_user` + `tasks:create OR can_create_event_job/can_create_initiative_job`; gate `assigned_member_id` behind `tasks:assign`. Delete the `/status` route and `TaskStatusUpdate`.
- [ ] Also fix (audit §4): `ev_delete_or_cancel_event` cancelling `done_reported` jobs is **out of your lane** (events) — note it under OUTSIDE MY LANE, do not change.
- [ ] Checkpoint: `python3 -m pytest tests/tasks tests/contribution -q`.

## T2 — `JobCard` and the three consumers

- [ ] `components/ui/JobCard.tsx`: props `{ job, me, canApprove, canManage, onClaim, onUnclaim, onReport, onApprove, onReject, onEdit, onCancel }`. Shows title, parent chip (event/initiative/standalone), `claimed/needed`, status pill (Open · In progress · In review · Approved · Cancelled), due in chapter tz, rejection reason, 36 h lock note. `lib/tasks.ts`: `canClaim`, `canUnclaim(now, start, tz)`, `visibleActions(job, me, perms, isSupervisorOrChair)` — pure, tested, including "claimant never sees Approve".
- [ ] `EventDetail`'s `JobsSection`, the initiative detail's job list and the board all render `JobCard`. Delete the two hand-rolled copies (`EventsModule.tsx:617-777` equivalent in `EventDetail`, `InitiativesModule.tsx:273-372`). One `AddJobForm` (title, instructions, spots, due, needed flag; **no assignee**, no priority) used by all three.
- [ ] Hooks: one `useJobs(scope)` with the mutation set (claim/unclaim/report/approve/reject/edit/cancel) that refetches after the server answers; no optimistic rows. `useEvents`/`useInitiatives` drop their job reducers.
- [ ] Tests: `components/job-card.test.ts` — Approve hidden for a claimant even with `tasks:review`; Report shown only to a claimant in progress; `lib/tasks.test.ts` table.
- [ ] Checkpoint: `npm test && npm run lint`.

## T3 — Job board (`/jobs`)

- [ ] `components/jobs/JobBoard.tsx`: tabs **Active** (default: open, in_progress, done_reported) and **History** (approved, cancelled). Sort `required desc, due_at asc, created desc` (client, in `lib/tasks.ts`, tested). Filter chips: Mine · Available (spots left) · In review · parent type. Add job button for anyone `tasks:create` (standalone) — supervisors/chairs add from their parent screens.
- [ ] Mobile: single column, chips scroll; Available first when "Mine" is empty.
- [ ] Remove the fake 4-level priority everywhere (`adapters.ts:296`, `TasksModule`, `types.ts` `Task.priority` → `required: boolean`), the `2026-07-16` default, and `Task.category`.
- [ ] Empty states: "No open jobs right now" / "No completed jobs yet". Loading skeleton. Error with retry.
- [ ] Tests: board default hides approved/cancelled; History shows them; sort order fixture.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Definition of done

M4 acceptance row; `grep -rn "priority" greekos/src/components/jobs greekos/src/adapters.ts` returns nothing job-related; exactly one file renders job cards (`JobCard.tsx`).

## Risks

- Removing `/status` breaks any external caller; `api.ts` is the only one (audit §3). The frozen-paths rule is about not *changing* paths; deleting a dead one is allowed, but say so in the report.
- Contribution counts only `approved`; with the toggle gone, standalone jobs now count once approved. Verify `tests/contribution` still green.
