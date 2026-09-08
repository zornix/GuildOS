# Plan 06 — Language and the a11y floor: jobs are jobs, Door code, quiet copy, Modal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first. Plans 01–05 must be on `feat/greekos-hci`.

**Goal:** A new member can tell which job belongs to which event or initiative without reading code, sees one phrase for the door code everywhere, and reads plain copy. Every modal has a role, closes on Escape and overlay click, and has a labeled close. Every ✕ and search field has a name.

**Architecture:** `adaptTasks` gains parent titles (tested). `Modal` gains `title` + `onClose` and owns the header, Escape, overlay dismiss, and initial focus; call sites drop their hand-rolled ✕ headers. Copy edits are string swaps.

**Tech Stack:** React 19, TypeScript, `node:test`.

**Spec:** handoff § "5. Conceptual model" and § "6. Operate floor" (as trimmed by README decision D10); D4.

## Global Constraints

- No focus-trap library. No sidebar regroup. No Events canvas restructuring.
- Words: **Door code**; **Jobs** (never house jobs); **Chapter ledger**; **Announcements**.

---

### Task 1: Jobs carry their parent; members can claim

**Files:**
- Modify: `LocalDev/greekos/src/types.ts` (`Task`)
- Modify: `LocalDev/greekos/src/adapters.ts` (`adaptTasks`)
- Create: `LocalDev/greekos/src/adapters.test.ts`
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (both `adaptTasks` call sites), `src/hooks/useTasks.ts` (`refetchTasks`, copy)
- Modify: `LocalDev/greekos/src/components/TasksModule.tsx`, `src/components/DashboardOverview.tsx` (Jobs tile)

**Interfaces:**
- `Task.parent?: { kind: 'event' | 'initiative'; title: string }`
- `adaptTasks(rows: TaskDto[], members: Member[], titles?: { events?: Map<string, string>; initiatives?: Map<string, string> }): Task[]` — security rows are dropped.

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/adapters.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptTasks } from './adapters';
import type { TaskDto } from './api';
import type { Member } from './types';

const row = (over: Partial<TaskDto>): TaskDto => ({
  id: 't1', title: 'Setup chairs', description: null, assigned_member_id: null, status: 'open', required: false,
  due_at: null, created_at: '2026-09-01T00:00:00Z', event_id: null, initiative_id: null, kind: 'standard',
  people_needed: 1, claimants: [], claimed_count: 0
} as TaskDto);
const members = [{ id: 'm1', name: 'Ryan Cole' } as Member];

test('standalone jobs have no parent; attached jobs name theirs', () => {
  const titles = { events: new Map([['e1', 'Chapter Meeting']]), initiatives: new Map([['i1', 'Coat Drive']]) };
  const tasks = adaptTasks([
    row({ id: 'a' }),
    row({ id: 'b', event_id: 'e1' }),
    row({ id: 'c', initiative_id: 'i1' })
  ], members, titles);
  assert.equal(tasks[0].parent, undefined);
  assert.deepEqual(tasks[1].parent, { kind: 'event', title: 'Chapter Meeting' });
  assert.deepEqual(tasks[2].parent, { kind: 'initiative', title: 'Coat Drive' });
});

test('an attached job whose parent is unknown still says which kind', () => {
  const [t] = adaptTasks([row({ event_id: 'missing' })], members);
  assert.deepEqual(t.parent, { kind: 'event', title: 'Event' });
});

test('security shifts are not jobs on the board', () => {
  assert.equal(adaptTasks([row({ kind: 'security' }), row({ id: 'x' })], members).length, 1);
});
```

- [ ] **Step 2: Run to verify it fails** — `npm test` — Expected: FAIL on `parent` / length assertions.

- [ ] **Step 3: Implement**

In `types.ts`, add to `Task` after `status`:

```ts
  /** Which event or initiative the job belongs to; absent for a standalone job. */
  parent?: { kind: 'event' | 'initiative'; title: string };
```

In `adapters.ts`, replace `adaptTasks` with:

```ts
export function adaptTasks(
  rows: TaskDto[],
  members: Member[],
  titles: { events?: Map<string, string>; initiatives?: Map<string, string> } = {}
): Task[] {
  // Security shifts live on the event's Security panel, never on the jobs board.
  return rows.filter(row => row.kind !== 'security').map(row => ({
    id: row.id,
    title: row.title,
    description: row.description || '',
    assignedTo: row.assigned_member_id ? nameOf(members, row.assigned_member_id) : 'Unassigned',
    assignedToId: row.assigned_member_id || undefined,
    dueDate: day(row.due_at),
    priority: row.required ? 'High' : 'Medium',
    status: TASK_STATUS[row.status] || 'To Do',
    parent: row.event_id
      ? { kind: 'event', title: titles.events?.get(row.event_id) || 'Event' }
      : row.initiative_id
        ? { kind: 'initiative', title: titles.initiatives?.get(row.initiative_id) || 'Initiative' }
        : undefined
  }));
}
```

- [ ] **Step 4: Run to verify it passes** — `npm test` — Expected: `ℹ fail 0`.

- [ ] **Step 5: Pass titles from the load path**

In `useAppData.ts`, where the load calls `tasks.setTasks(adaptTasks(taskRows, rosterRows));`, change to:

```ts
        tasks.setTasks(adaptTasks(taskRows, rosterRows, {
          events: new Map(adaptedEvents.map(e => [e.id, e.title])),
          initiatives: new Map(adaptInitiatives(initRows, rosterRows).map(i => [i.id, i.title]))
        }));
```

In `useTasks.ts`, `Deps` gains `titles: () => { events: Map<string, string>; initiatives: Map<string, string> }` and `refetchTasks` becomes `setTasks(adaptTasks(await api.getTasks(), members, titles()))`. In `useAppData.ts`, construct `useTasks({ members, syncApi, showToast, titles: () => ({ events: new Map(events.events.map(e => [e.id, e.title])), initiatives: new Map(initiatives.initiatives.map(i => [i.id, i.title])) }) })`.

Copy in `useTasks.ts`: `Assigned chore "${t.title}" to ${t.assignedTo}` → `Added job "${t.title}"`; `Claimed house task.` → `Claimed job.`; the hook comment `House chores and officer to-dos.` → `Jobs: standalone or attached to an event or initiative.`

- [ ] **Step 6: TasksModule shows the tag and lets members claim**

Subtitle `House and officer jobs, who owns each one, and when it is due.` → `Every job — standalone or for an event or initiative — who owns it, and when it is due.`

In the card, under the title `<h4>`, add:

```tsx
                {task.parent && (
                  <span className="inline-block mt-1 text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    {task.parent.kind === 'event' ? 'Event' : 'Initiative'}: {task.parent.title}
                  </span>
                )}
```

In the footer row, after the assignee `<span>`, add the claim action that was passed in but never rendered:

```tsx
                {!isDone && task.assignedTo === 'Unassigned' && currentMember && (
                  <button type="button" onClick={() => onClaimTask(task.id, currentMember.name, currentMember.id)}
                    className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md cursor-pointer">
                    Claim
                  </button>
                )}
```

Home Jobs tile (`DashboardOverview.tsx`): under `{task.assignedTo}` add `{task.parent && <> · {task.parent.title}</>}` inside the same `text-slate-500` div.

- [ ] **Step 7: Lint and test** — `npm run lint && npm test` — Expected: clean; `ℹ fail 0`.

- [ ] **Step 8: Commit**

```bash
git add LocalDev/greekos/src/types.ts LocalDev/greekos/src/adapters.ts LocalDev/greekos/src/adapters.test.ts LocalDev/greekos/src/hooks/useAppData.ts LocalDev/greekos/src/hooks/useTasks.ts LocalDev/greekos/src/components/TasksModule.tsx LocalDev/greekos/src/components/DashboardOverview.tsx
git commit -m "feat(greekos): jobs carry their parent; members can claim from the board"
```

---

### Task 2: One phrase: Door code

**Files:**
- Modify: `LocalDev/greekos/src/components/EventsModule.tsx`

- [ ] **Step 1: String swaps** (use grep to find each; the plan lists them all):

| Old | New |
|---|---|
| button `Live Door Mode` (detail banner) | `Show door code` |
| `{selectedEvent.checkInLinkActive ? 'Check-in open' : 'Enable door link'}` | `{selectedEvent.checkInLinkActive ? 'Close door code' : 'Open door code'}` |
| modal `<span …>Live Door Mode</span>` | `Door code` |
| `Live Door Code` | `Door code` |
| `Brothers enter it under Attendance &rarr; Door Check-In. Expires shortly.` | `Members enter it on Home or under Attendance → Door code. Expires shortly.` |
| `No door link is open. Use <strong>Enable Door Link</strong> on the event to open one.` | `No door code is open. Use <strong>Open door code</strong> on the event.` |
| `Close Door View` | `Close` |
| `Schedule Chapter Operation Event` | `Create event` |
| `Create Chapter Event` (if any remains) | `Create event` |

- [ ] **Step 2: Verify**

Run: `grep -rn "Live Door\|door link\|Door Link\|Door Check-In" LocalDev/greekos/src`
Expected: no matches.

- [ ] **Step 3: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/components/EventsModule.tsx
git commit -m "copy(greekos): one phrase for the door code"
```

---

### Task 3: Quieter copy elsewhere

**Files:**
- Modify: `CalendarModule.tsx`, `Sidebar.tsx`, `OutboxModule.tsx`, `InitiativesModule.tsx`, `RosterModule.tsx`, `RecruitmentModule.tsx`, `AttendanceModule.tsx`

- [ ] **Step 1: Swaps**

| File | Old | New |
|---|---|---|
| CalendarModule | `Broadcast Announcements (N)` | `Announcements (N)` |
| CalendarModule | `No executive broadcasts on this day.` | `No announcements on this day.` |
| CalendarModule | `Chapter Events (N)` | `Events (N)` |
| CalendarModule | legend `Chapter Events` | `Events` |
| Sidebar | `Alpha Chapter Operations` | `Alpha Chapter` |
| OutboxModule | any `SMS / Push Outbox` heading | `Message outbox` |
| InitiativesModule | `Leads:` / `Lead chairs` labels | `Chairs:` / `Chairs` |
| InitiativesModule | `Active Committee Initiatives` (if present) | `Initiatives` |
| RosterModule | balance column header containing `Dues` or `Balance` | `Unpaid fines` |
| RecruitmentModule | `Extend Official Chapter Bid` (if still present) | `Extend bid` |
| AttendanceModule | `Submit Excuse Request` / `Submit Absence Excuse Request` / `Submit for Executive Review` | `Request excuse` / `Request an excuse` / `Submit request` |
| AttendanceModule | `Executive board review for academic, medical, and family obligations.` | `Officers review these.` |
| AttendanceModule | `Roll Call Sheet` | `Roll call` |
| AttendanceModule | `Excuse Approvals (N Pending)` | `Excuses (N pending)` |

Use `grep -rn "<old>" LocalDev/greekos/src/components` for each row; some may already be gone.

- [ ] **Step 2: Verify**

Run: `grep -rn "Executive\|Broadcast\|house job\|House job\|chore\|Leads:" LocalDev/greekos/src --include=*.tsx --include=*.ts | grep -v mockData`
Expected: no matches (mock data may keep old words).

- [ ] **Step 3: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/components
git commit -m "copy(greekos): plainer labels across calendar, attendance, initiatives, roster"
```

---

### Task 4: Modal a11y floor

**Files:**
- Modify: `LocalDev/greekos/src/components/ui/Modal.tsx`
- Modify: every `<Modal` call site — enumerate with `grep -n "<Modal" LocalDev/greekos/src/components/*.tsx LocalDev/greekos/src/components/*/*.tsx`

**Interfaces:**
- `ModalProps` gains `title?: string; onClose?: () => void;`. When `onClose` is given: Escape closes, overlay click closes, and a header with `title` + a close button `aria-label="Close"` renders. The panel has `role="dialog" aria-modal="true"` and, when `title` is given, `aria-labelledby`.

- [ ] **Step 1: Rewrite Modal**

```tsx
import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  children: React.ReactNode;
  /** Tailwind max-width for the panel. */
  maxWidth?: string;
  /** Extra panel classes (e.g. text-center space-y-4). */
  className?: string;
  /** Overlay tint override. */
  overlayClassName?: string;
  /** Heading text. Renders a header row with the close button. */
  title?: string;
  /** Escape, overlay click and the close button all call this. */
  onClose?: () => void;
}

/** Fixed overlay + centered white panel. Shared shell for every modal in the app.
 *  ponytail: no focus trap — initial focus lands on the panel, Escape and overlay
 *  close it. Add a trap only if keyboard users report tabbing out. */
export default function Modal({
  children,
  maxWidth = 'max-w-md',
  className = '',
  overlayClassName = 'bg-slate-900/60',
  title,
  onClose
}: ModalProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panel.current?.focus();
    if (!onClose) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      className={`fixed inset-0 ${overlayClassName} backdrop-blur-xs flex items-center justify-center p-4 z-50`}
    >
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        onClick={e => e.stopPropagation()}
        className={`bg-white rounded-2xl border border-slate-200 shadow-2xl ${maxWidth} w-full p-6 animate-in fade-in zoom-in duration-150 outline-none ${className}`}
      >
        {(title || onClose) && (
          <div className="flex justify-between items-center mb-4">
            {title ? <h3 id={titleId} className="font-display font-bold text-base text-slate-900">{title}</h3> : <span />}
            {onClose && (
              <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 -mr-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update every call site**

For each `<Modal …>` found by the grep: pass `title="<the heading text already shown inside>"` and `onClose={<the setter the existing ✕ calls>}`, then delete the hand-rolled header `<div className="flex justify-between items-center mb-4"> <h3>…</h3> <button …>✕</button> </div>` (or the `mb-3` variant). Where the heading had an icon, drop the icon; the title text is enough. `ConfirmDialog` and `AddTransactionModal` (plans 04–05): `ConfirmDialog` passes `title={title} onClose={onCancel}` (so Escape cancels, never confirms) and deletes its own `<h3>`. `AddTransactionModal` passes `title="Add transaction" onClose={onClose}` and deletes its own header.

Known call sites at the time of writing (verify with grep; line numbers drift):

- `AttendanceModule.tsx` — excuse modal
- `EventsModule.tsx` — create event, add/edit job, reject job, assign security, swap, door code
- `FinanceModule.tsx` — pay, adjustment (correction)
- `InitiativesModule.tsx` — create, add job
- `TasksModule.tsx` — add job
- `RosterModule.tsx` — add member (if it uses Modal)
- `RecruitmentModule.tsx` — add prospect (if it uses Modal)
- `components/finance/AddTransactionModal.tsx`
- `components/ui/ConfirmDialog.tsx`

- [ ] **Step 3: Verify no bare ✕ remains**

Run: `grep -rn "✕" LocalDev/greekos/src`
Expected: no matches.

- [ ] **Step 4: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 5: Browser check**

Open any modal: Escape closes it; clicking the dark overlay closes it; clicking inside does not; the close button reads "Close" to a screen reader (inspect `aria-label`). Tab once from a freshly opened modal lands inside it.

- [ ] **Step 6: Commit**

```bash
git add LocalDev/greekos/src/components
git commit -m "a11y(greekos): modals get role, Escape, overlay dismiss, labeled close"
```

---

### Task 5: Named search fields and icon buttons

**Files:**
- Modify: `RosterModule.tsx`, `RecruitmentModule.tsx`, `FinanceModule.tsx`, `OutboxModule.tsx`, `CommandModule.tsx`, `Sidebar.tsx`, `AppShell.tsx`

- [ ] **Step 1: Search inputs** — add `aria-label` to each search `<input>`:

| File | aria-label |
|---|---|
| RosterModule | `Search roster` |
| RecruitmentModule | `Search prospects` |
| FinanceModule | `Search members` |
| OutboxModule | `Search messages` |
| CommandModule (the command input) | `Command` |

- [ ] **Step 2: Icon-only buttons** — run `grep -n "<button" -A6 LocalDev/greekos/src/components/*.tsx LocalDev/greekos/src/components/*/*.tsx | grep -B6 "lucide\|<X \|<Trash2\|<Pencil" | grep "<button"` and for each button whose only content is an icon, add an `aria-label` that names the action and the target (`aria-label={\`Delete job "${job.title}"\`}`, `aria-label="Previous month"`, `aria-label="Next month"`, …). CalendarModule's month arrows and EventsModule's job edit/delete pencils are the known ones.

- [ ] **Step 3: Verify**

Run: `grep -rn "placeholder=\"Search" -B2 -A4 LocalDev/greekos/src/components | grep -c aria-label`
Expected: 4 (one per search field with a Search placeholder). Also `npm run lint` clean.

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/components
git commit -m "a11y(greekos): name search fields and icon-only buttons"
```

---

## Done when

- Jobs board shows "Event: …" / "Initiative: …" tags and a Claim button for unassigned jobs; `onClaimTask` is used.
- `grep -rn "Live Door\|big_ledger\|✕\|house job" LocalDev/greekos/src` returns nothing.
- Every modal: `role="dialog"`, Escape, overlay dismiss, labeled close.
- Five commits; `npm test` (now including `adapters.test.ts`) and lint clean.
