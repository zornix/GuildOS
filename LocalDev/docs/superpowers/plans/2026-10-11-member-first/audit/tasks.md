# Audit: Jobs (storage: `tasks`) + Contribution — backend, schema, frontend

Read-only audit, 2026-10-11. Paths are relative to `LocalDev/` unless noted.
**FACT** means read directly from the code. **INFERENCE** means a conclusion drawn from facts, not run.
Root `CONTEXT.md:63-68` defines a Job: "A claimable unit of work a member commits to, reports done, and a supervisor
or chair approves ... every verified job counts toward contribution. Jobs never affect standing."

---------------------------------------------------------------------------------------------------
## 1. Schema (final state)

### `tasks` (0085 + 0110 + 0142 + 0144 + 0145)
| column | source | notes |
|---|---|---|
| id, chapter_id, title, description | 0085:21-27 | chapter_id NOT NULL FK |
| group_id → task_groups | 0085:24 | **dead**: no API creates task_groups (FACT: grep shows no writer) |
| assigned_member_id | 0085:27 | legacy "assignee"; does NOT create a claim; still grants "ownership" on the status route (tasks.py:93) |
| created_by | 0085:28 | set by tk_create_task (0144:389-392) |
| status | 0085:29, widened 0110:13-15, 0142:25-28 | CHECK IN (`open`,`committed`,`in_progress`,`done`,`cancelled`,`done_reported`,`approved`). The lifecycle never sets `committed`/`done` on jobs; they are legacy "chore" values (0142:11-13) |
| required BOOL | 0085:30 | the only "priority-like" field. **There is no priority column** (FACT) |
| due_at TIMESTAMPTZ | 0085:31 | indexed (0085:41) |
| created_at / updated_at | 0085:32-33 | |
| event_id → events (SET NULL) | 0110:10 | |
| initiative_id → initiatives (SET NULL) | 0144:60-67 | `tasks_single_parent_check`: event_id OR initiative_id, not both (0144:66-67) |
| people_needed INT ≥1 default 1 | 0142:15-16 | capacity |
| reported_by / reported_at | 0142:17-18 | cleared by reject (0142:494-495) |
| approved_by / approved_at | 0142:19-20 | the "verified" stamp |
| rejected_by / rejected_at / rejection_reason | 0142:21-23 | cleared by the next report (0144:563-564) |
| kind (`standard`/`security`) | 0145:31-36 | security ⇒ event_id NOT NULL; security rows are managed only by `ev_*` RPCs |

No `claimed_by` column: claims live in `task_commitments`. No `cancelled_at`/`cancelled_by` column; cancellation is a
status plus an audit row. No soft-delete flag, because cancel is the soft delete.

### Related tables
- `task_commitments` (0110:19-36): claims. One row per (task, member) claim. `status` IN (`active`,`uncommitted`,`completed`),
  `committed_at`, `uncommitted_at`. Partial unique index: one ACTIVE per (task, member) (0110:31-32).
- `task_commitment_log` (0110:47-58): append-only (trigger 0110:66-78) commit/uncommit feed with `late`, `reason`,
  `event_id`, `hours_before_event`. Visible to the whole chapter by design.
- `audit_logs`: every tk_* RPC writes one row. Actions: CREATE_TASK, COMMIT_TASK, UNCOMMIT_TASK, JOB_REPORTED,
  JOB_APPROVED, JOB_REJECTED, UPDATE_TASK, CANCEL_TASK, UPDATE_TASK_STATUS.
- `message_outbox`: JOB_REPORTED goes to the event supervisors / initiative chairs (0144:576-604). JOB_APPROVED and JOB_REJECTED go to the active claimants
  (0142:403-415, 0142:503-515). Standalone jobs notify **no one** on report (0144:574-575 comment). FACT.
- `task_groups` (0085:9-16): dead (see §8).
- RLS SELECT-only, chapter-scoped, on all of these. It is defense-in-depth only (CLAUDE.md hard rules).

---------------------------------------------------------------------------------------------------
## 2. Lifecycle — transitions, who performs them, gates

State map (0142:9-13): open (🔴 To do) → in_progress (🟢) → done_reported (🟡) → approved (✅); cancelled; legacy done.

| transition | RPC (latest def) | HTTP gate (FACT) | RPC guard (FACT) |
|---|---|---|---|
| create → `open` | tk_create_task 0144:343 | `tasks:create` (tasks.py:33). Event parent: plus supervisor/organizer of the event or `tasks:assign` (tasks.py:41, approvals.py:73-79). Initiative parent: plus a chair of the initiative or `tasks:assign` (tasks.py:49, approvals.py:82-86) | chapter checks on member/group/event/initiative; two-parents error (0144:370-388) |
| open → in_progress (first claim) | tk_commit_task 0175:338 | **none beyond being logged in** for a self-claim. Claiming for someone else needs `tasks:assign` (commitments.py:57-59) | row lock; not security; status not in done/cancelled/done_reported/approved; member in chapter AND status active/invited; no duplicate active claim; `job_full` capacity (0175:366-405); first claim flips open→in_progress (0175:415-419) |
| in_progress → open (last unclaim) | tk_uncommit_task 0197:10 | self, or `tasks:review` for others (commitments.py:84-86) | not security; **hard lock inside T-36h of the event/initiative start** (0197:66-68). Standalone jobs never lock. Last active claim leaving reverts to open (0197:85-91) |
| in_progress → done_reported | tk_report_done 0144:522 | `tasks:complete` (jobs.py:86; this is in the member baseline, 0083:80-84) | caller must hold an ACTIVE commitment (0144:548-551); status must be in_progress (0144:553-558) |
| done_reported → approved | tk_approve_task 0142:371 | `can_approve_job` (jobs.py:113, approvals.py:60-70): an event job needs **a supervisor of that event only**, an initiative job needs **a chair of that initiative only**, and a standalone job needs `tasks:review` | status must be done_reported; active commitments → `completed`; stamps approved_by/at (0142:401-424) |
| done_reported → in_progress/open | tk_reject_task 0142:447 | same `can_approve_job` (jobs.py:137) | reason required; goes back to in_progress if claims remain, else open (0142:490-496) |
| edit fields | tk_update_task 0152:81 | `can_manage_job` (tasks.py:139, approvals.py:89-104): whoever may attach a job to that parent. A standalone job needs `tasks:assign` or `tasks:review` | open/in_progress only; capacity cannot drop below the active claims (0152:118-135) |
| open → cancelled ("delete") | tk_cancel_task 0152:170 | `can_manage_job` (tasks.py:164) | **open only** (0152:198-200); not security |
| generic status set | tk_update_task_status 0182:2 | `tasks:complete` AND (assigned_member OR an active claimant OR `tasks:review`) (tasks.py:88-97) | blocks done_reported/approved targets, closed/in-review sources, and `done` on parented jobs (0182:24-49). **Allows** open/committed/in_progress/cancelled on any non-security job, and `done` on standalone jobs |
| event cancelled → job cancelled | ev_delete_or_cancel_event 0216:7 | events domain | cancels every job NOT IN (done, approved, cancelled), **including done_reported**, and releases the claims (0216:41-58) |

### The questions asked
- **Who can create jobs?** (FACT) Holders of `tasks:create`: admin, officer, president, vice_president, social_chair,
  brotherhood_chair, philanthropy_chair (0083:65-163, 0147:57). rush_chair has initiative keys only (0218:22-25).
  **Plain members cannot.** The `tasks:create` gate runs first (tasks.py:33), so a plain member who supervises an event or
  chairs an initiative (an approved proposer becomes creator-chair, CONTEXT.md:42-44) still gets 403 creating a job on
  their own event or initiative. INFERENCE: the UI comment "tasks:assign — attach a job to an initiative you do not chair"
  (InitiativesModule.tsx:18) assumes chairs can create, but the server refuses chairs without `tasks:create`.
- **Who can assign?** Two separate meanings:
  (a) `assigned_member_id` on create. **There is no `tasks:assign` check** (tasks.py:30-71 passes body.assigned_member_id straight
  through). Any `tasks:create` holder can name an assignee, and the assignee then "owns" the job for the status route
  (tasks.py:93). FACT.
  (b) Claiming on someone's behalf (`/commit` with member_id) needs `tasks:assign` (commitments.py:58). FACT.
- **Who can claim?** Any logged-in active/invited member of the chapter, for themselves. The creator is NOT excluded, and neither are the
  supervisors or chairs (no creator check in tk_commit_task, 0175:338-430). Self-claim is allowed. FACT.
- **Who marks complete?** For parented jobs, an active claimant reports (tk_report_done). For standalone jobs it is ALSO the
  status route: any claimant or the assignee can set `done` directly (0182:47 only blocks parented jobs). Active claims then become
  `completed` (0182:55-59) with **no review**. Test `test_standalone_task_can_toggle_open_and_done`
  (tests/tasks/test_jobs_lifecycle.py:306) pins this. FACT.
- **Who approves/verifies?** See can_approve_job above.
  - **Can the claimant approve their own job? YES.** Neither `can_approve_job` nor `tk_approve_task` compares the actor with the
    claimants or with reported_by (approvals.py:60-70, 0142:371-439). An event supervisor can claim → report → approve their own
    job. So can an initiative chair, and so can a `tasks:review` holder on a standalone job. FACT.
  - **Can the creator approve their own job?** Yes, if they are a supervisor/chair (event creators are always supervisors:
    0212:84-89; initiative creators are always chairs: 0211:172-175). FACT.
  - **Officer override for event/initiative jobs: NONE.** `tasks:review` is consulted only for standalone jobs
    (approvals.py:63-70). An officer cannot approve or reject a job on an event they do not supervise. FACT.
- **Who edits/cancels/deletes?** `can_manage_job`. Cancel is only allowed from `open`, and there is no hard delete. **Bypass:** an active claimant or
  the assignee can POST `/status {"status":"cancelled"}` (or `open`) on an event or initiative job. tasks.py:94-97 lets owners through, and
  0182 does not block `cancelled`/`open`. This skips both can_manage_job and the open-only cancel rule, and it leaves the claims
  `active` on a cancelled job. `test_committed_member_can_update_their_job` (test_jobs_api.py:212) shows a claimant
  setting status on an event job. The cancel variant is FACT by code reading and is not exercised by any test.
- **What do 0211/0212 enforce?** Neither touches a tk_* job RPC (FACT: their function lists are ev_accept_security_swap,
  in_create_initiative / ev_create_event, ev_add_supervisor, in_add_chair, in_remove_chair).
  - 0211: a security swap requires the target to be an active/invited member and the job to be `in_progress` + security, with
    an advisory lock (0211:34-59). Initiative creation requires every chair, including the auto-added creator, to be active/invited
    (0211:185-192).
  - 0212: the event creator must be active/invited and always becomes a supervisor (0212:41-47, 84-89). `ev_add_supervisor`
    requires active/invited status plus an eligible role, if one is configured (0212:149-160). in_add/remove_chair lock the initiative `FOR NO KEY
    UPDATE`, so inserting job rows that reference the initiative does not block (0212:1, 202, 274).
  - So the "supervisor-of-event rule" lives in **approvals.py**, not in 0212. 0212 only makes sure that every supervisor is an
    active member.

---------------------------------------------------------------------------------------------------
## 3. Endpoints (mounted at `/api/tasks`, api/index.py:201; `/api/contribution`, index.py:209)

| method path | gate | file |
|---|---|---|
| GET `/api/tasks/` | any logged-in member | tasks.py:24-27 |
| POST `/api/tasks/` | `tasks:create` (+ parent rule) | tasks.py:30-71 |
| POST `/{id}/status` | tasks:complete + own (assigned/claimant) or tasks:review | tasks.py:74-117 |
| PATCH `/{id}` | can_manage_job | tasks.py:130-153 |
| DELETE `/{id}` (= cancel) | can_manage_job | tasks.py:156-174 |
| POST `/{id}/report-done` | tasks:complete + active claim (RPC) | jobs.py:83-100 |
| POST `/{id}/approve` | can_approve_job | jobs.py:103-124 |
| POST `/{id}/reject` {reason} | can_approve_job | jobs.py:127-149 |
| POST `/{id}/commit` {member_id?} | self: anyone; other: tasks:assign | commitments.py:47-71 |
| POST `/{id}/uncommit` {reason?, member_id?} | self: anyone; other: tasks:review | commitments.py:74-99 |
| GET `/uncommit-log?member_id&limit≤200` | any member | commitments.py:102-114 |
| GET `/attribution/me`, `/attribution/{member_id}` | any member (anyone's ledger) | commitments.py:117-129 |
| GET `/{id}/commitments` | any member | commitments.py:132-137 |
| GET `/api/contribution/me` | any member | contribution/api/records.py:22-25 |
| GET `/api/contribution/{member_id}` | `standing:view_all` | records.py:28-42 |

**List filters (FACT, services/tasks.py:149-169):** only `?status=`, which takes one exact value. There is no event, initiative, assignee, mine,
or multi-status filter. **Sort:** `created_at DESC`. **Pagination:** none. The list returns every chapter row, including
cancelled, approved and security rows, and every row is decorated with `committed_member_ids`, `claimants` and
`claimed_count` (the same data three times) plus `kind`. There is no GET `/api/tasks/{id}`.

---------------------------------------------------------------------------------------------------
## 4. Audit rows / history
- FACT: approved and cancelled rows stay in `tasks` forever. `GET /api/tasks/?status=approved` returns the completed-jobs
  history, with approved_by/approved_at/reported_by. There is no hard-delete path. Cancel is the soft delete
  (services/tasks.py:123). An event hard-delete happens only when the event has no tasks (0216:21-36), and the FK is
  `ON DELETE SET NULL` anyway.
- Claim history: `task_commitments` rows are never deleted (status flips), plus the append-only `task_commitment_log`.
  Note: `late` is now always written as FALSE (0197:80-83). The T-36h hard lock replaced "late", so `late_uncommits` in
  `/attribution` is always 0 for new rows (FACT).
- audit_logs covers every transition (test_jobs_lifecycle.py:276).
- Gap: cancelling an event also cancels **done_reported** jobs (0216:41-42). Reported work that was never reviewed is
  lost, and the claimants get no credit. FACT (code); INFERENCE that this is unintended.

---------------------------------------------------------------------------------------------------
## 5. Contribution
- `/api/contribution/me` → services/record.py:159-183. `jobs_done` (record.py:108-143) = tasks with
  **status='approved'** that the member had an active/completed commitment on, newest approved_at first, tagged
  event/initiative/standalone. No storage; derived per request; never feeds standing (tests/contribution/test_standing_firewall.py).
- **Standalone jobs closed through the Jobs-tab toggle (`done`) never count.** The status is `done`, not `approved`. FACT chain:
  useTasks.ts:42 → tk_update_task_status 0182:47 → record.py:126. This contradicts CONTEXT.md:66, "every verified job counts".
- **Second, disagreeing ledger:** `/api/tasks/attribution/*` (services/commitments.py:156-194) counts
  `task_commitments.status='completed'`. That includes the standalone `done` path, so it credits work that was never
  reviewed. It filters events to ones that already started (commitments.py:107-153), while contribution counts every
  organizer/supervisor row, including future and cancelled events (record.py:44-65 has no date/cancelled filter). The frontend
  never calls `/attribution` (FACT: no greekos caller).
- What the member sees: `components/home/MyRecord.tsx:25`, which is a count only ("Jobs completed"). Officers can read any member through
  `standing:view_all`.

---------------------------------------------------------------------------------------------------
## 6. Frontend Jobs tab (greekos/src/components/TasksModule.tsx)
- One grid with **every status mixed together**: To Do, In Progress, Done Reported, Approved, Cancelled (adapters.ts:282 drops only
  security rows; cancelled rows are kept). The order is the server's created_at desc, and the client does not sort.
- The only filter is a **fake priority** (TasksModule.tsx:36, 48-51, 103-113). Priority is not stored. The create form sends
  `required = High|Urgent` (useTasks.ts:29), and the adapter shows `required ? 'High' : 'Medium'` (adapters.ts:296). So "Low" and
  "Urgent" can never appear on a reloaded row, and the Low/Urgent filter buttons always come back empty. FACT.
- Actions: Add job (gated `tasks:create`, :89), Claim (lib/tasks.ts:10-15), status toggle To Do ↔ Completed for
  standalone jobs (:144-157 → useTasks.ts:37-43 → `/status done|open`). This toggle is the review bypass from §2.
  **The tab has no Report-done, Approve, Reject, Unclaim, Edit or Cancel.** Those exist only in the event and initiative detail views
  (useEvents.ts:207-329, useInitiatives.ts:113-149). So a standalone job cannot be reported or approved from any screen. FACT.
- Create form: "Assign to" defaults to the first roster member and has **no Unassigned option** (:42, 229-237), so every new
  job is pre-assigned to someone. The due date defaults to the hard-coded `'2026-07-16'` (:43), which is now in the past. There are no capacity
  (people_needed) or parent fields on this tab.
- "N pending" counts Pending + Done Reported (:81). It is not "open".
- Optimistic fake row with a client id `t_xxxx` (useTasks.ts:16-22) plus optimistic status/claim edits. This conflicts with the
  frontend rule "Nothing on screen that the server did not return" (LocalDev/CLAUDE.md, Frontend rules). FACT.
- Mobile: 1 column below md (:117), `min-h-11` tap targets on phone (:107, 149, 183). Nothing is mobile-specific beyond that.
- `currentMember` is found by **name** (:46). EventsModule.tsx:623 also finds supervisors by name. INFERENCE: this breaks
  when two members share a name.

---------------------------------------------------------------------------------------------------
## 7. Tests
Covered (FACT): capacity/job_full; first claim → in_progress and last unclaim → open; T-36h lock for events, initiatives and the chapter timezone;
report by a non-claimant 403; double report 409; reject reason required, claimants kept, dedup per cycle; approve
completes the commitments and notifies; standalone approve needs tasks:review; initiative approve needs a chair; event-job
create needs supervisor/organizer/assign; edit/cancel matrix; security immutability; idempotency replays; the audit row
for every transition; append-only log; cross-chapter commit and initiative create (RPC level); contribution counts only
approved + committed jobs, officer gate, no off-chapter read; standing firewall.

Gaps:
1. **Self-approval**: no test, and no rule. A supervisor or chair approving a job they claimed succeeds today.
2. **Claimant cancels or reopens via `/status`** (cancelled/open on an event job): no test, and it works.
3. **Standalone `done` without review → not in contribution, but counted in attribution**: the lifecycle test pins the
   toggle (test_jobs_lifecycle.py:306), and no test covers the contribution consequence.
4. **Cross-chapter at the API layer**: no test for approve/reject/report/status/PATCH/DELETE/commitments listing with
   another chapter's task id. INFERENCE: these are safe, because get_task and every RPC filter by chapter_id, but they are unpinned.
5. `assigned_member_id` set by a creator without tasks:assign: untested.
6. A plain-member initiative chair creating a job on their own initiative (403 today): untested at the API layer.
7. Event cancel sweeping done_reported jobs: untested.
8. Uncommit while done_reported (allowed, 0197 has no status check) leaves a reported job with zero claimants: untested.
9. Frontend: tasks-claims/tasks-access only cover the Claim button and Add gating.

---------------------------------------------------------------------------------------------------
## 8. Over-engineering / dead code
- `task_groups` table + `group_id` param + `TaskCreate.group_id`: no writer, no reader. Dead (0085:9-19, schemas.py:17).
- `/api/tasks/attribution/*` + `/uncommit-log` + `services/commitments.py:88-194` (~100 lines): no frontend caller.
  It duplicates and disagrees with `/api/contribution`. `late` is always FALSE. Candidates for deletion.
- Status values `committed` and `done` (legacy chore). `TaskStatusUpdate` still accepts `committed` (schemas.py:49).
  The whole generic `/status` route exists only for the standalone toggle, which is also the hole in §2.
- `list_tasks` emits the same claim list three times (services/tasks.py:162-164). The frontend reads `claimants` and `claimed_count`.
- `create_task` does a follow-up UPDATE for people_needed because tk_create_task lacks the param (services/tasks.py:43-53).
  One RPC param would remove the transaction and the second write.
- Two near-identical `_rpc_http_error` mappers (jobs.py:47-73, commitments.py:25-44).
- Stale docstrings: commitments.py:81 "Always allowed (no hard lock)" and services/commitments.py:3-4 "late when <24h". Both were wrong
  after 0142.
- `assigned_member_id` is a second ownership model next to commitments. lib/tasks.ts:3-7 calls it "only a fallback for demo
  rows", yet the create form always sets it.
- Frontend fake 4-level priority and `Task.category` (types.ts:192, never set by the adapter).

---------------------------------------------------------------------------------------------------
## 9. Proposed member-first workflow — assessment

| step | status today | smallest change |
|---|---|---|
| 1 any authorized member creates | **Supported for `tasks:create` holders** (officers + social/brotherhood/philanthropy chairs). Plain members: 403 (tasks.py:33) | If "authorized" = current holders: nothing. If every member: grant `tasks:create` to role `member` (one-row seed migration), but first gate `assigned_member_id` behind `tasks:assign` (tasks.py:30-71, ~3 lines), or a member could create and pre-assign anyone. Also consider letting supervisors/chairs create on their own parent without `tasks:create` (move the gate into approvals: `get_current_user` + `tasks:create OR can_create_*`). |
| 2 appears unclaimed | Backend supported (`open`, claimed_count 0). Frontend: the form forces an assignee, so the card shows a name | **Frontend only**: default "Assign to" to Unassigned (or drop it), and show claimants rather than the assignee |
| 3 any eligible member (incl. creator) claims | **Supported** (commitments.py:47-71, 0175). Eligibility = active/invited member, capacity, not closed | none |
| 4 claimant completes | Backend **supported** for every job via report-done. The Jobs tab offers only the `done` toggle for standalone jobs (no review) | **Frontend**: replace the toggle with "Report done" (api.reportJobDone already exists), plus Unclaim. **Backend (small)**: make `/status` refuse `done` for all jobs (0182:47, drop the parent condition) and refuse owner-set `cancelled`/`open` (allow only can_manage_job), or delete `/status` once the toggle is gone |
| 5 authorized reviewer approves | Backend supported (supervisor / chair / tasks:review). No self-approval guard. No officer fallback on event/initiative jobs | **Backend**: in `can_approve_job` (approvals.py:60) or `tk_approve_task`, refuse when the actor holds an active commitment on the job. Add a `tasks:review` fallback for event/initiative jobs, so the sole supervisor's own work and absent supervisors have an approver. **Frontend**: Approve/Reject buttons on the Jobs tab for whoever passes the same rule (needs either a `can_approve` flag in the list response or the supervisor/chair ids already loaded) |
| 6 leaves active board into history | Data **supported**: approved rows stay, with approved_by/at | **Frontend only**: filter the client-side list. Active = open/in_progress/done_reported; History = approved (+ cancelled) |

### Challenges
- **Self-assignment (claiming your own job)**: low risk and worth keeping. Capacity, the T-36h unclaim lock and the chapter-visible
  uncommit log already limit hoarding. Standalone jobs have no unclaim lock (0197:66: no start time), so a member can
  claim and abandon standalone jobs freely. No claim cap exists. INFERENCE: acceptable at chapter scale.
- **Self-approval**: the real hole. Today a supervisor or chair (often the creator) can create → claim → report → approve,
  and an officer can do the same on a standalone job. That farms "résumé-grade" contribution (CONTEXT.md:48-55). Standing is unaffected
  (firewall), so the harm is credibility, not money. A one-guard fix (claimant ≠ approver) plus a tasks:review fallback closes it.
  Separate the creator from the approver only if the user wants that. It is NOT needed to stop farming once claimant ≠ approver.
- **Officer oversight**: officers see everything in the list and in audit_logs. They can edit/cancel via tasks:assign (can_manage_job)
  and uncommit anyone via tasks:review. They **cannot** approve or reject event/initiative jobs (approvals.py:63-69).
- **Status-route bypass** (§2): a claimant can cancel an event job or flip it to open. Fix this before giving every member more power.

### Can "active by default, sort by priority, available/claimed/in-progress, history view" use existing fields + filters only?
- **Active by default**: yes, as a client-side filter on `status` in {open, in_progress, done_reported}. `?status=` takes only one value,
  so filter on the client (the list is unpaginated anyway). FACT.
- **Sort by priority**: **only 2 levels** exist (`required` bool), so sort by `required DESC, due_at ASC`. A real 4-level priority needs a
  column + tk_create_task/tk_update_task params + schema (backend). Recommendation: use required + due date and drop the fake 4-level
  picker.
- **Available / claimed / in progress**: partly. `open` = available. `in_progress` = at least one claim, and the first claim sets it
  (0175:415-419), so **"claimed" and "in progress" are the same state in the data**. You can still show "spots left" with
  `claimed_count < people_needed`, and "In review" (done_reported). A separate claimed-but-not-started state would need a new status or column.
  Recommendation: don't add one.
- **History view**: yes, with status=approved (+cancelled). approved_at/approved_by/reported_by are present. FACT.
