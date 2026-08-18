# GreekOS Prototype ↔ B4FEND Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the six backend surfaces B4FEND just landed (migration 0152, commit `39beb6c`) into `LocalDev/greekos`, replacing the client-local demo behavior for event/initiative jobs, security shifts, announcements, and calendar chips with real API calls.

**Architecture:** greekos already has the layering: `src/api.ts` (fetch client + DTOs), `src/adapters.ts` (DTO → `src/types.ts`), domain hooks in `src/hooks/` that own state + mutations + refetch, modules that only take props. Every task extends those existing files — no new layers, no new dependencies. Mutations keep the existing pattern: optimistic local update → API call → domain refetch, no-op API when `backendDown`.

**Tech Stack:** Vite + React 19 + TS + Tailwind v4. Backend: FastAPI on `localhost:8001`, proxied at `/api`. Auth: `ensureLogin()` dev-login as `jake@tke.org` (officer, passes all gates).

**Spec:** `LocalDev/docs/B4FEND-FIX.md` §3 (endpoint table) + §7. Backend is fully landed; this plan is frontend-only.

## Global Constraints

- No new npm dependencies. `tsx` is already a devDependency — use it for the self-check script.
- Verification gate for every task: `cd LocalDev/greekos && npm run lint` (tsc) and `npm run build` both clean.
- greekos has no test framework by design. The adapter logic (Task 1) gets one assert-based self-check run with `tsx`; UI tasks are verified by lint/build + the smoke script in Task 7.
- All money through `formatMoney(cents)` (`src/formatters.ts`). All new DTO→type conversion in `src/adapters.ts` only.
- Status vocabulary mapping (used by Tasks 1–3, keep identical everywhere):
  backend task `open`→`'To Do'`, `in_progress`→`'In Progress'`, `done_reported`→`'Done Reported'`, `approved`→`'Approved'`; `cancelled` rows are filtered out; `kind==='security'` rows never appear on jobs boards.
- Error copy for 409s (Task 3): map backend detail codes to toasts —
  `job_not_editable`→"Job can no longer be edited", `job_not_cancellable`→"Only unclaimed To-Do jobs can be deleted", `job_capacity_below_claims`→"Can't set spots below current claims", `security_no_edit`/`security_no_cancel`→"Security shifts are managed from the Security panel", `swap_wrong_state`→"That swap request is no longer pending".
- Commits: one per task, messages given in each task. Never add Claude attribution trailers.
- Run the backend while developing: `cd LocalDev && npm run dev` (backend 8001; do NOT start the fratos frontend — greekos runs `npm run dev` from its own folder on port 3000).

---

### Task 1: Job DTOs + adapters (tasks-with-parents → `EventJob`)

**Files:**
- Modify: `LocalDev/greekos/src/api.ts` (extend `TaskDto`, add job endpoint fns)
- Modify: `LocalDev/greekos/src/adapters.ts` (add `adaptTaskToJob`, `groupJobsByParent`)
- Create: `LocalDev/greekos/src/selfcheck.ts` (assert-based, run with `tsx`)

**Interfaces:**
- Consumes: existing `api.get/post/patch/del`, existing `TaskDto`, `Member` type.
- Produces (later tasks rely on these exact names):
  - `TaskDto` gains: `event_id: string | null; initiative_id: string | null; kind: string; people_needed: number; claimants: string[]; claimed_count: number; due_at: string | null; description: string | null; rejection_reason?: string | null`
  - `api.createJob(body: {title: string; description?: string; people_needed: number; event_id?: string; initiative_id?: string}): Promise<TaskDto>` → `POST /api/tasks/`
  - `api.commitTask(id: string): Promise<void>` → `POST /api/tasks/${id}/commit` body `{}`
  - `api.uncommitTask(id: string): Promise<void>` → `POST /api/tasks/${id}/uncommit` body `{}`
  - `api.reportJobDone(id: string): Promise<void>` → `POST /api/tasks/${id}/report-done` body `{}`
  - `api.approveJob(id: string): Promise<void>` → `POST /api/tasks/${id}/approve` body `{}`
  - `api.rejectJob(id: string, reason: string): Promise<void>` → `POST /api/tasks/${id}/reject` body `{reason}`
  - `api.updateJob(id: string, body: {title?: string; description?: string; people_needed?: number}): Promise<void>` → `PATCH /api/tasks/${id}`
  - `api.deleteJob(id: string): Promise<void>` → `DELETE /api/tasks/${id}`
  - `adaptTaskToJob(t: TaskDto, membersById: Map<string, Member>): EventJob`
  - `groupJobsByParent(tasks: TaskDto[], membersById: Map<string, Member>): { byEvent: Map<string, EventJob[]>; byInitiative: Map<string, EventJob[]> }`

- [ ] **Step 1: Write the failing self-check**

```ts
// src/selfcheck.ts — run: npx tsx src/selfcheck.ts   (exits non-zero on failure)
import assert from 'node:assert';
import { adaptTaskToJob, groupJobsByParent } from './adapters';
import type { TaskDto } from './api';
import type { Member } from './types';

const member = { id: 'm1', name: 'Ryan Cole' } as Member;
const membersById = new Map([['m1', member]]);
const base: TaskDto = {
  id: 't1', title: 'Setup chairs', description: 'front lawn', status: 'open',
  kind: 'standard', event_id: 'e1', initiative_id: null, people_needed: 3,
  claimants: [], claimed_count: 0, due_at: null,
} as TaskDto;

// status + claimant mapping
const open = adaptTaskToJob(base, membersById);
assert.equal(open.status, 'To Do');
assert.equal(open.peopleNeeded, 3);
const claimed = adaptTaskToJob({ ...base, status: 'in_progress', claimants: ['m1'], claimed_count: 1 }, membersById);
assert.equal(claimed.status, 'In Progress');
assert.deepEqual(claimed.claimants.map(c => c.memberName), ['Ryan Cole']);
assert.equal(adaptTaskToJob({ ...base, status: 'done_reported' }, membersById).status, 'Done Reported');
assert.equal(adaptTaskToJob({ ...base, status: 'approved' }, membersById).status, 'Approved');

// grouping: cancelled + security rows dropped, parents split
const grouped = groupJobsByParent([
  base,
  { ...base, id: 't2', status: 'cancelled' },
  { ...base, id: 't3', kind: 'security' },
  { ...base, id: 't4', event_id: null, initiative_id: 'i1' },
], membersById);
assert.deepEqual(grouped.byEvent.get('e1')!.map(j => j.id), ['t1']);
assert.deepEqual(grouped.byInitiative.get('i1')!.map(j => j.id), ['t4']);
console.log('selfcheck OK');
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd LocalDev/greekos && npx tsx src/selfcheck.ts`
Expected: FAIL — `adaptTaskToJob` is not exported.

- [ ] **Step 3: Extend `TaskDto` and add the endpoint functions in `src/api.ts`**

Add the fields listed in Interfaces to the existing `TaskDto` interface, and add the eight functions to the existing `api` object literal, e.g.:

```ts
createJob: (body: { title: string; description?: string; people_needed: number; event_id?: string; initiative_id?: string }) =>
  request<TaskDto>('/api/tasks/', { method: 'POST', body }),
commitTask: (id: string) => request<void>(`/api/tasks/${id}/commit`, { method: 'POST', body: {} }),
uncommitTask: (id: string) => request<void>(`/api/tasks/${id}/uncommit`, { method: 'POST', body: {} }),
reportJobDone: (id: string) => request<void>(`/api/tasks/${id}/report-done`, { method: 'POST', body: {} }),
approveJob: (id: string) => request<void>(`/api/tasks/${id}/approve`, { method: 'POST', body: {} }),
rejectJob: (id: string, reason: string) => request<void>(`/api/tasks/${id}/reject`, { method: 'POST', body: { reason } }),
updateJob: (id: string, body: { title?: string; description?: string; people_needed?: number }) =>
  request<void>(`/api/tasks/${id}`, { method: 'PATCH', body }),
deleteJob: (id: string) => request<void>(`/api/tasks/${id}`, { method: 'DELETE' }),
```

(Match the file's actual helper — it may be `api.post(path, body)` style rather than a `request` fn; keep its existing convention. Read `src/api.ts` first.)

- [ ] **Step 4: Implement the adapters in `src/adapters.ts`**

```ts
const JOB_STATUS: Record<string, EventJob['status']> = {
  open: 'To Do', in_progress: 'In Progress', done_reported: 'Done Reported', approved: 'Approved',
};

export function adaptTaskToJob(t: TaskDto, membersById: Map<string, Member>): EventJob {
  return {
    id: t.id,
    title: t.title,
    description: t.description ?? '',
    peopleNeeded: t.people_needed ?? 1,
    claimants: (t.claimants ?? []).map(id => ({
      memberId: id,
      memberName: membersById.get(id)?.name ?? 'Unknown',
      claimedAt: '',
    })),
    status: JOB_STATUS[t.status] ?? 'To Do',
    rejectionReason: t.rejection_reason ?? undefined,
    isSecurity: t.kind === 'security',
  };
}

export function groupJobsByParent(tasks: TaskDto[], membersById: Map<string, Member>) {
  const byEvent = new Map<string, EventJob[]>();
  const byInitiative = new Map<string, EventJob[]>();
  for (const t of tasks) {
    if (t.status === 'cancelled' || t.kind === 'security') continue;
    const job = adaptTaskToJob(t, membersById);
    if (t.event_id) (byEvent.get(t.event_id) ?? byEvent.set(t.event_id, []).get(t.event_id)!).push(job);
    else if (t.initiative_id) (byInitiative.get(t.initiative_id) ?? byInitiative.set(t.initiative_id, []).get(t.initiative_id)!).push(job);
  }
  return { byEvent, byInitiative };
}
```

- [ ] **Step 5: Run the self-check and lint**

Run: `npx tsx src/selfcheck.ts && npm run lint`
Expected: `selfcheck OK`, tsc clean.

- [ ] **Step 6: Commit**

```bash
git add LocalDev/greekos/src/api.ts LocalDev/greekos/src/adapters.ts LocalDev/greekos/src/selfcheck.ts
git commit -m "feat(greekos): job DTOs + adapters for backend tasks"
```

---

### Task 2: Event & initiative jobs boards go live

**Files:**
- Modify: `LocalDev/greekos/src/hooks/useEvents.ts` (job handlers)
- Modify: `LocalDev/greekos/src/hooks/useInitiatives.ts` (same pattern)
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (attach grouped jobs after load)

**Interfaces:**
- Consumes: Task 1's `api.*` fns and `groupJobsByParent`; existing `syncApi` no-op-when-down wrapper; existing `refetchTasks`/task loading in `useTasks`/`useAppData`.
- Produces: the existing handler names keep their signatures (modules don't change): `handleAddJobToEvent`, `handleClaimJob`, `handleUnclaimJob`, `handleReportJobDone`, `handleApproveJob`, `handleRejectJob`, and the initiative twins. A new shared `refetchJobs(): Promise<void>` lives in `useAppData` and is passed into both hooks.

- [ ] **Step 1: Hydrate jobs from the API on load**

In `useAppData.ts`, after the existing parallel load resolves (events + tasks + members are all present), replace the mock `jobs: []` default on adapted events/initiatives:

```ts
const { byEvent, byInitiative } = groupJobsByParent(taskDtos, membersById);
setEvents(evts => evts.map(e => ({ ...e, jobs: byEvent.get(e.id) ?? [] })));
setInitiatives(inits => inits.map(i => ({ ...i, jobs: byInitiative.get(i.id) ?? [] })));
```

Extract that into `refetchJobs()` (re-fetches `GET /api/tasks/`, regroups, re-stamps both states) and pass it to `useEvents` / `useInitiatives` via their existing deps object.

- [ ] **Step 2: Wire the six event-job handlers**

Keep each handler's optimistic local update exactly as-is, then append the API call + refetch, following the file's existing wired-mutation pattern (see `handleAddEvent` in the same file):

```ts
const handleClaimJob = (eventId: string, jobId: string, memberId: string, memberName: string) => {
  /* existing optimistic setEvents(...) block stays */
  syncApi(async () => { await api.commitTask(jobId); await refetchJobs(); });
};
```

Mapping: add-job→`api.createJob({..., event_id: eventId})`, claim→`commitTask`, unclaim→`uncommitTask`, report→`reportJobDone`, approve→`approveJob`, reject→`rejectJob(jobId, reason)` (the outbox enqueue on reject stays — it's the demo notification layer).

- [ ] **Step 3: Same six for initiatives** in `useInitiatives.ts`, with `initiative_id: initId` on create.

- [ ] **Step 4: Verify**

Run: `npm run lint && npm run build` — clean. Then with the backend up: open the app, add a job to an upcoming event, claim it, report done, approve; reload the page and confirm every state survived the reload (it's in Postgres now, not component state).

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/hooks/useEvents.ts LocalDev/greekos/src/hooks/useInitiatives.ts LocalDev/greekos/src/hooks/useAppData.ts
git commit -m "feat(greekos): wire event and initiative job boards to backend tasks"
```

---

### Task 3: Job edit + delete (the new B4FEND PATCH/DELETE)

**Files:**
- Modify: `LocalDev/greekos/src/hooks/useEvents.ts` (two new handlers)
- Modify: `LocalDev/greekos/src/components/EventsModule.tsx` (edit/delete affordances on job cards)
- Modify: `LocalDev/greekos/src/App.tsx` (pass the two new props through)

**Interfaces:**
- Consumes: `api.updateJob`, `api.deleteJob`, `refetchJobs` from Tasks 1–2.
- Produces: `handleEditJob(eventId: string, jobId: string, patch: {title?: string; description?: string; peopleNeeded?: number}): void` and `handleDeleteJob(eventId: string, jobId: string): void`, passed to `EventsModule` as `onEditJob` / `onDeleteJob`.

- [ ] **Step 1: Handlers with the 409 error map**

```ts
const JOB_409: Record<string, string> = {
  job_not_editable: 'Job can no longer be edited',
  job_not_cancellable: 'Only unclaimed To-Do jobs can be deleted',
  job_capacity_below_claims: "Can't set spots below current claims",
  security_no_edit: 'Security shifts are managed from the Security panel',
  security_no_cancel: 'Security shifts are managed from the Security panel',
};

const handleEditJob = (eventId: string, jobId: string, patch: { title?: string; description?: string; peopleNeeded?: number }) => {
  syncApi(async () => {
    try {
      await api.updateJob(jobId, { title: patch.title, description: patch.description, people_needed: patch.peopleNeeded });
      await refetchJobs();
      showToast('Job updated.');
    } catch (e: any) {
      showToast(JOB_409[e?.detail?.error ?? e?.detail] ?? 'Could not update job');
    }
  });
};
```

`handleDeleteJob` is the same shape around `api.deleteJob(jobId)` with success toast `'Job deleted.'`. Inspect how `src/api.ts` surfaces error bodies (it parses JSON error text) and match the actual thrown shape when reading `detail`.

- [ ] **Step 2: UI affordances in `EventsModule.tsx`**

On each job card where the current user can manage (the module already has an `isOfficer` prop — gate on that, matching how existing officer-only buttons in the same file are gated): a small edit button opening the existing job form `Modal` pre-filled (reuse the add-job form state, submit calls `onEditJob`), and a delete button only when `job.status === 'To Do' && job.claimants.length === 0` (mirrors the backend `job_not_cancellable` rule so users rarely see the 409).

- [ ] **Step 3: Verify** — lint + build clean; manual: edit a job title, raise/lower spots, delete an unclaimed job, confirm a claimed job shows no delete button.

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/hooks/useEvents.ts LocalDev/greekos/src/components/EventsModule.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): job edit and delete via new PATCH/DELETE endpoints"
```

---

### Task 4: Security shifts — real assignments and the full swap lifecycle

**Files:**
- Modify: `LocalDev/greekos/src/api.ts` (security DTOs + fns)
- Modify: `LocalDev/greekos/src/adapters.ts` (`adaptSecurityAssignment`)
- Modify: `LocalDev/greekos/src/hooks/useEvents.ts` (replace the local security handlers)
- Modify: `LocalDev/greekos/src/components/EventsModule.tsx` (station column removal, swap-cancel button)

**Interfaces:**
- Consumes: roster `membersById` from Task 1 pattern.
- Produces:
  - `SwapDto { id: string; task_id: string; event_id: string; requester_member_id: string; target_member_id: string; note: string | null; status: string; created_at: string | null }`
  - `SecurityAssignmentDto { task_id: string; event_id: string; member_id: string | null; status: string; rejection_reason: string | null; pending_swap: SwapDto | null }`
  - `api.listSecurity(eventId): Promise<SecurityAssignmentDto[]>` → `GET /api/events/${eventId}/security`
  - `api.assignSecurity(eventId, memberId): Promise<SecurityAssignmentDto>` → `POST /api/events/${eventId}/security` body `{member_id}`
  - `api.removeSecurity(eventId, taskId): Promise<void>` → `DELETE /api/events/${eventId}/security/${taskId}`
  - `api.requestSwap(eventId, taskId, targetMemberId, note?): Promise<SwapDto>` → `POST .../security/${taskId}/swap-request` body `{target_member_id, note}`
  - `api.acceptSwap(eventId, swapId)` / `api.declineSwap(eventId, swapId)` / `api.cancelSwap(eventId, swapId)` → `POST .../security/swaps/${swapId}/(accept|decline|cancel)` body `{}`
  - `adaptSecurityAssignment(dto, membersById): SecurityAssignment` — `id: dto.task_id`, `memberId: dto.member_id ?? ''`, `memberName` via lookup, `status: 'Confirmed'`, and when `pending_swap?.status === 'pending'`: `swapRequestedWithId/Name` from `target_member_id`, `swapStatus: 'Pending'`.

- [ ] **Step 1: DTOs + fns + adapter** as specified above.
- [ ] **Step 2: Replace the four local handlers in `useEvents.ts`.** `handleAssignSecurity(eventId, memberId, memberName, _station)` now calls `api.assignSecurity` then refetches that event's assignments into `event.securityAssignments` (add a `refetchSecurity(eventId)` helper in the hook that calls `listSecurity` + adapter + `setEvents`). `handleRequestSecuritySwap` → `api.requestSwap` (assignmentId is the `task_id`). `handleRespondSecuritySwap(eventId, assignmentId, accept)` → look up `pending_swap.id` from the assignment, call accept/decline. New `handleCancelSecuritySwap(eventId, assignmentId)` → `api.cancelSwap` — this is the B4FEND addition: the requester withdrawing their own pending request.
- [ ] **Step 3: Load assignments with events** — in `useAppData`, after events adapt, fire `listSecurity` for upcoming events only (parallel, best-effort) and stamp `securityAssignments`.
- [ ] **Step 4: UI honesty pass in `EventsModule.tsx`** — the backend has no "station" concept: remove the station text input from the assign flow and the station column from the table (assignments are just member + status + swap state). Add a "Cancel request" button on an assignment whose `swapStatus === 'Pending'` **when the current user is the requester**, calling `onCancelSecuritySwap`.
- [ ] **Step 5: Verify** — lint + build; manual: assign a member, request a swap as them, cancel it, request again, accept as the target. Confirm `GET .../security` reflects each step on reload.
- [ ] **Step 6: Commit**

```bash
git add LocalDev/greekos/src/api.ts LocalDev/greekos/src/adapters.ts LocalDev/greekos/src/hooks/useEvents.ts LocalDev/greekos/src/components/EventsModule.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): wire security assignments and swap lifecycle incl. cancel"
```

---

### Task 5: Announcements — create with calendar slot, send, delete-to-hide

**Files:**
- Modify: `LocalDev/greekos/src/api.ts`, `src/adapters.ts` (calendar fields)
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (announcement create in the NL-command path) and the hook owning announcements state
- Modify: `LocalDev/greekos/src/components/DashboardOverview.tsx` (officer delete button)

**Interfaces:**
- Produces:
  - `api.createAnnouncement(body: {title: string; body: string; calendar_date?: string; calendar_time?: string}): Promise<AnnouncementDto>` → `POST /api/announcements/`
  - `api.sendAnnouncement(id): Promise<void>` → `POST /api/announcements/${id}/send`
  - `api.deleteAnnouncement(id): Promise<void>` → `DELETE /api/announcements/${id}` (draft → gone; sent → hidden from calendar; idempotent)
  - `Announcement` type gains `calendarDate?: string; calendarTime?: string` (adapter maps `calendar_date`/`calendar_time`).

- [ ] **Step 1: API fns + adapter fields** as above. Read the backend `AnnouncementCreate` schema (`LocalDev/api/announcements/api/schemas.py`) first and match its exact field names for title/body/audience; `calendar_time` without `calendar_date` is a 422 — only send `calendar_time` when a date is set.
- [ ] **Step 2: Wire the Command-module ANNOUNCEMENT branch** — where `handleExecuteCommand` currently prepends a local announcement, call `createAnnouncement` (today's date as `calendar_date`) then `sendAnnouncement`, then refetch announcements. Local optimistic prepend stays.
- [ ] **Step 3: Officer delete** — on the dashboard announcements panel, an officer-only ✕ per announcement calling `deleteAnnouncement` + refetch, toast `'Announcement removed from calendar.'`.
- [ ] **Step 4: Calendar placement** — `CalendarModule` currently buckets announcements by their display date; switch it to `calendarDate` when present so backend-dated announcements land on the right day.
- [ ] **Step 5: Verify** — lint + build; manual: command "announce chapter meeting moved to 7pm", see it on today's calendar cell and in the dashboard, delete it, confirm it's gone after reload.
- [ ] **Step 6: Commit**

```bash
git add LocalDev/greekos/src/api.ts LocalDev/greekos/src/adapters.ts LocalDev/greekos/src/hooks LocalDev/greekos/src/components/DashboardOverview.tsx LocalDev/greekos/src/components/CalendarModule.tsx
git commit -m "feat(greekos): announcements create/send/delete with calendar slots"
```

---

### Task 6: Chips + prior shifts (`open_job_count`, `prior_security_shifts`)

**Files:**
- Modify: `LocalDev/greekos/src/api.ts` (`EventDto` + scores fn), `src/adapters.ts`, `src/types.ts`
- Modify: `LocalDev/greekos/src/components/CalendarModule.tsx`, `EventsModule.tsx` (chips), security picker table in `EventsModule.tsx` (prior-shifts column)

**Interfaces:**
- Produces:
  - `EventDto` gains `job_count?: number; open_job_count?: number`; `ChapterEvent` gains `jobCount?: number; openJobCount?: number` (adapter maps them).
  - `api.getScores(): Promise<ScoreDto[]>` → `GET /api/memberadmin/scores`, `ScoreDto` incl. `member_id: string; score: number; prior_security_shifts: number`.
  - `Member` gains `priorSecurityShifts?: number` (merged from scores during roster load, default 0).

- [ ] **Step 1: DTO/adapter/type additions** as above; merge `prior_security_shifts` into members in `useAppData`'s roster load (scores fetch is officer-gated — tolerate 403 by defaulting 0, same best-effort pattern the load already uses).
- [ ] **Step 2: Chips** — on calendar event cells and event list rows: when `openJobCount > 0`, a small gold pill `"{openJobCount} open jobs"` (use the existing pill/badge styling conventions in those files — `bg-gold/20 text-gold-muted`).
- [ ] **Step 3: Prior-shifts column** — the security assign picker table gets a "Prior shifts" column from `member.priorSecurityShifts`, sorted ascending by default (fewest shifts first — that's who to pick), matching B4FEND D17's purpose. Do not show it on the assigned member's card (spec Screen 6).
- [ ] **Step 4: Verify** — lint + build; manual: an event with 2 unclaimed jobs shows the chip on both calendar and list; claim both → chip disappears after refetch.
- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/api.ts LocalDev/greekos/src/adapters.ts LocalDev/greekos/src/types.ts LocalDev/greekos/src/components LocalDev/greekos/src/hooks/useAppData.ts
git commit -m "feat(greekos): open-job chips and prior-security-shifts column"
```

---

### Task 7: End-to-end smoke + docs

**Files:**
- Modify: `LocalDev/greekos/README.md` (replace the AI-Studio boilerplate with the real run instructions)
- Modify: `LocalDev/docs/events-dev-status.md` (Phase 5 row → wired)

- [ ] **Step 1: Full pass** — `npm run lint`, `npm run build`, `npx tsx src/selfcheck.ts` all clean.
- [ ] **Step 2: Manual smoke with seeded backend** (`cd LocalDev && npm run dev`, then `cd LocalDev/greekos && npm run dev`, open :3000): walk Dashboard → Calendar (chips + announcement) → Events (job lifecycle, edit/delete, security swap incl. cancel) → the three demo-gated tabs still gate (Rules/Command/Outbox — Command's announcement branch now hits the API but the tab keeps its demo gate since command *parsing* is still frontend-local).
- [ ] **Step 3: README** — replace with: prerequisites (backend on 8001 with `DEV_AUTH_BYPASS=1`, seeded demo DB), the two `npm run dev` commands, the demo login identity, and the demo-mode tab list.
- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/README.md LocalDev/docs/events-dev-status.md
git commit -m "docs(greekos): run instructions and phase-5 wired status"
```

---

## Explicit non-goals

- The unified `GET /api/calendar/` feed and its `invoice_due` items — the prototype composes its calendar client-side from data it already loads; a second data path for the same pixels is duplication. Revisit only if invoice chips are wanted.
- NL command parsing (backend `nl_controller` still returns no proposed actions), bylaws Q&A, outbox listing — the demo gates stay.
- The 36-hour unclaim lock, notify-gate checklist, record-payment semantics, `station` persistence — not backend surfaces today.
- Removing the dual `duesBalanceCents`/`duesBalance` fields.
