# Plan 05 — Safety and truth: roll call, confirms, command chips, toast, Demo view-as

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first. Plans 01–04 must be on `feat/greekos-hci`.

**Goal:** Nothing consequential happens silently. A blank roll sheet cannot be saved as "everyone present". Fines, Mark paid, standing changes, announcement deletes, bid blasts, and command runs each show who/what/consequence and ask once. Command chips fill the input. The toast is announced to screen readers and stays until dismissed. Impersonation is visibly Demo.

**Architecture:** Roll-call math is a tested pure function in `src/lib/rollCall.ts`. One `ConfirmDialog` primitive on top of `Modal`. `useToast` drops its timer. Session vs view comparison comes from `useAppData` (plan 01).

**Tech Stack:** React 19, TypeScript, `node:test`.

**Spec:** handoff § "4. Safety / truth"; README decisions D7, D9, D13, D14, D15.

## Global Constraints

- Keep: job reject requires a reason; door-code `maxLength={6}`; notify gate.
- Never send an attendance status a human did not set.
- Copy: **Save roll call**, **Mark remaining present**, **Demo: view as**.

---

### Task 1: Roll call math

**Files:**
- Create: `LocalDev/greekos/src/lib/rollCall.ts`
- Create: `LocalDev/greekos/src/lib/rollCall.test.ts`

**Interfaces:**

```ts
export type RollStatus = 'Present' | 'Absent' | 'Excused' | 'Late';
export interface RollCallSummary {
  present: number; absent: number; excused: number; late: number; unmarked: number;
  marked: { memberId: string; status: RollStatus }[];   // only rows a human set, roster order
  label: string;                                         // "48 present · 3 absent · 9 unmarked"
}
export function rollCallSummary(members: Member[], records: Record<string, RollStatus>): RollCallSummary;
export function markRemainingPresent(members: Member[], records: Record<string, RollStatus>): Record<string, RollStatus>;
```

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/rollCall.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { markRemainingPresent, rollCallSummary } from './rollCall';
import type { Member } from '../types';

const m = (id: string): Member => ({ id, name: id } as Member);
const roster = [m('a'), m('b'), m('c'), m('d')];

test('summary counts each status and the unmarked rest, in roster order', () => {
  const s = rollCallSummary(roster, { b: 'Absent', d: 'Present', zzz: 'Present' });
  assert.equal(s.present, 1);
  assert.equal(s.absent, 1);
  assert.equal(s.unmarked, 2);
  assert.deepEqual(s.marked, [{ memberId: 'b', status: 'Absent' }, { memberId: 'd', status: 'Present' }]);
  assert.equal(s.label, '1 present · 1 absent · 2 unmarked');
});

test('label only names non-zero buckets and says all marked when none left', () => {
  assert.equal(rollCallSummary(roster, {}).label, '4 unmarked');
  const all = rollCallSummary(roster, { a: 'Present', b: 'Late', c: 'Excused', d: 'Present' });
  assert.equal(all.unmarked, 0);
  assert.equal(all.label, '2 present · 1 excused · 1 late');
});

test('markRemainingPresent fills only the gaps', () => {
  const next = markRemainingPresent(roster, { b: 'Absent' });
  assert.deepEqual(next, { a: 'Present', b: 'Absent', c: 'Present', d: 'Present' });
});
```

- [ ] **Step 2: Run to verify it fails** — `npm test` — Expected: FAIL, `Cannot find module './rollCall'`.

- [ ] **Step 3: Implement**

Create `LocalDev/greekos/src/lib/rollCall.ts`:

```ts
import type { Member } from '../types';

export type RollStatus = 'Present' | 'Absent' | 'Excused' | 'Late';

export interface RollCallSummary {
  present: number;
  absent: number;
  excused: number;
  late: number;
  unmarked: number;
  /** Only rows a human set, in roster order. This is what gets saved. */
  marked: { memberId: string; status: RollStatus }[];
  label: string;
}

/** Unmarked stays unmarked. Nothing is defaulted to Present here or anywhere. */
export function rollCallSummary(members: Member[], records: Record<string, RollStatus>): RollCallSummary {
  const counts = { present: 0, absent: 0, excused: 0, late: 0, unmarked: 0 };
  const marked: RollCallSummary['marked'] = [];
  for (const m of members) {
    const status = records[m.id];
    if (!status) { counts.unmarked++; continue; }
    counts[status.toLowerCase() as 'present' | 'absent' | 'excused' | 'late']++;
    marked.push({ memberId: m.id, status });
  }
  const parts = (['present', 'absent', 'excused', 'late', 'unmarked'] as const)
    .filter(k => counts[k] > 0)
    .map(k => `${counts[k]} ${k}`);
  return { ...counts, marked, label: parts.join(' · ') };
}

/** The explicit version of the old silent default: fills gaps, keeps choices. */
export function markRemainingPresent(members: Member[], records: Record<string, RollStatus>): Record<string, RollStatus> {
  const next: Record<string, RollStatus> = {};
  for (const m of members) next[m.id] = records[m.id] || 'Present';
  return next;
}
```

- [ ] **Step 4: Run to verify it passes** — `npm test` — Expected: `ℹ fail 0`.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/lib/rollCall.ts LocalDev/greekos/src/lib/rollCall.test.ts
git commit -m "feat(greekos): roll call summary with explicit unmarked"
```

---

### Task 2: Roll call sheet uses it

**Files:**
- Modify: `LocalDev/greekos/src/components/AttendanceModule.tsx` (`handleSaveAttendance`; the roll-call header button; the row status default)

- [ ] **Step 1: Import and compute**

Add `import { RollStatus, markRemainingPresent, rollCallSummary } from '../lib/rollCall';`.

Change the records state type to `Record<string, RollStatus>` (same union; alias it). After `handleStatusChange`, add:

```ts
  const summary = rollCallSummary(safeMembers, attendanceRecords);
```

Replace `handleSaveAttendance` with:

```ts
  const handleSaveAttendance = () => {
    if (!selectedEvent || summary.marked.length === 0) return;
    onRecordAttendance(selectedEvent.id, summary.marked);
  };
```

- [ ] **Step 2: Header controls**

Replace the officer `Commit Attendance to Roster` button block with:

```tsx
            {isOfficer && (
              <div className="flex flex-col sm:items-end gap-2">
                <div className="flex gap-2">
                  {summary.unmarked > 0 && (
                    <button
                      type="button"
                      onClick={() => setAttendanceRecords(markRemainingPresent(safeMembers, attendanceRecords))}
                      className="bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-xs cursor-pointer"
                    >
                      Mark remaining present ({summary.unmarked})
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleSaveAttendance}
                    disabled={summary.marked.length === 0}
                    className="bg-navy hover:bg-slate-800 text-gold font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all cursor-pointer flex items-center gap-2 shadow-xs disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    Save roll call
                  </button>
                </div>
                <p role="status" className="text-xs text-slate-600">{summary.label || 'Nothing marked yet'}</p>
              </div>
            )}
```

- [ ] **Step 3: Rows show unmarked as unmarked**

Replace `const status = attendanceRecords[mem.id] || 'Present';` with `const status = attendanceRecords[mem.id];` (type `RollStatus | undefined`). The four status buttons already compare `status === st`, so an unmarked row now renders none as selected. Add before the button group, so the state is legible:

```tsx
                        {!status && <span className="text-xs text-slate-400 mr-2">Unmarked</span>}
```

- [ ] **Step 4: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 5: Browser check**

As Jake, Attendance → roll call. Save is disabled and the status line says "N unmarked". Mark two absent: "2 absent · N-2 unmarked", Save enabled. Press "Mark remaining present": all rows are set, the button disappears. Save: toast "Recorded roll call attendance."; Network shows one POST per member.

- [ ] **Step 6: Commit**

```bash
git add LocalDev/greekos/src/components/AttendanceModule.tsx
git commit -m "feat(greekos): roll call saves only marked rows; explicit mark-remaining-present"
```

---

### Task 3: ConfirmDialog primitive

**Files:**
- Create: `LocalDev/greekos/src/components/ui/ConfirmDialog.tsx`

- [ ] **Step 1: Create it**

```tsx
import React from 'react';
import Modal from './Modal';

interface ConfirmDialogProps {
  title: string;
  /** Who, what, consequence. Keep it to two short lines. */
  body: React.ReactNode;
  confirmLabel: string;
  tone?: 'default' | 'danger';
  onConfirm: () => void;
  onCancel: () => void;
}

/** One question, two buttons. Cancel is always on the left and never styled as primary. */
export default function ConfirmDialog({ title, body, confirmLabel, tone = 'default', onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Modal maxWidth="max-w-sm">
      <h3 className="font-display font-bold text-base text-slate-900 mb-2">{title}</h3>
      <div className="text-xs text-slate-700 mb-5 space-y-1">{body}</div>
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} autoFocus
          className="flex-1 min-h-11 border border-slate-200 text-slate-700 font-bold rounded-lg text-xs cursor-pointer hover:bg-slate-50">
          Cancel
        </button>
        <button type="button" onClick={onConfirm}
          className={`flex-1 min-h-11 font-bold rounded-lg text-xs cursor-pointer ${tone === 'danger' ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-navy hover:bg-slate-800 text-gold'}`}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 2: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add LocalDev/greekos/src/components/ui/ConfirmDialog.tsx
git commit -m "feat(greekos): ConfirmDialog primitive"
```

---

### Task 4: Confirms on consequence-bearing actions

**Files:**
- Modify: `FinanceModule.tsx` (Mark paid button, Fines tab "Mark paid")
- Modify: `RosterModule.tsx` (standing `<select>`)
- Modify: `DashboardOverview.tsx` (announcement ✕)
- Modify: `RecruitmentModule.tsx` (Extend bid)
- Modify: `CommandModule.tsx` (Execute + chips)

The pattern is the same in every file: a `pending` state holding the thing about to happen; the action button sets it; a `<ConfirmDialog>` at the bottom of the component performs it on confirm and clears it on cancel. Fines issued through Add transaction are already confirmed by that modal's own confirm step (plan 04).

- [ ] **Step 1: FinanceModule — Mark paid (balances row) and Mark paid (fines tab)**

Add `import ConfirmDialog from './ui/ConfirmDialog';` and state:

```ts
  const [pendingMarkPaid, setPendingMarkPaid] = useState<{ member: Member; balanceCents: number } | null>(null);
  const [pendingFinePaid, setPendingFinePaid] = useState<Fine | null>(null);
```

Balances row button: replace its `onClick={() => { onRecordPayment({…}) }}` with `onClick={() => setPendingMarkPaid({ member: mem, balanceCents })}`.

Fines tab button: `onClick={() => setPendingFinePaid(f)}`.

Before the closing `</div>` of the component's root, add:

```tsx
      {pendingMarkPaid && (
        <ConfirmDialog
          title="Mark paid?"
          body={<p>Record a cash payment of <strong>{formatMoney(pendingMarkPaid.balanceCents)}</strong> from <strong>{pendingMarkPaid.member.name}</strong>. Their balance becomes $0.00.</p>}
          confirmLabel="Mark paid"
          onCancel={() => setPendingMarkPaid(null)}
          onConfirm={() => {
            onRecordPayment({
              memberId: pendingMarkPaid.member.id, memberName: pendingMarkPaid.member.name,
              amount: pendingMarkPaid.balanceCents / 100, amountCents: pendingMarkPaid.balanceCents,
              type: 'Dues', paymentMethod: 'Cash', reference: 'IN_PERSON_CASH'
            });
            setPendingMarkPaid(null);
          }}
        />
      )}
      {pendingFinePaid && (
        <ConfirmDialog
          title="Mark fine paid?"
          body={<p><strong>{pendingFinePaid.memberName}</strong>'s {formatMoney(pendingFinePaid.amountCents)} fine for "{pendingFinePaid.reason}" will show as paid.</p>}
          confirmLabel="Mark paid"
          onCancel={() => setPendingFinePaid(null)}
          onConfirm={() => { onApproveFinePayment(pendingFinePaid.id); setPendingFinePaid(null); }}
        />
      )}
```

- [ ] **Step 2: RosterModule — standing**

Add the import and `const [pendingStanding, setPendingStanding] = useState<{ member: Member; standing: Member['standing'] } | null>(null);`. Change the select's `onChange` to `onChange={e => setPendingStanding({ member: mem, standing: e.target.value as Member['standing'] })}`. Note the `<select value={mem.standing}>` stays controlled, so cancelling leaves it unchanged. Add:

```tsx
      {pendingStanding && (
        <ConfirmDialog
          title="Change standing?"
          tone="danger"
          body={<p><strong>{pendingStanding.member.name}</strong>: {pendingStanding.member.standing} → <strong>{pendingStanding.standing}</strong>. Standing affects what they may do in the chapter.</p>}
          confirmLabel="Change standing"
          onCancel={() => setPendingStanding(null)}
          onConfirm={() => { onUpdateStanding(pendingStanding.member.id, pendingStanding.standing as any); setPendingStanding(null); }}
        />
      )}
```

- [ ] **Step 3: DashboardOverview — announcement delete**

Add the import and `const [pendingDelete, setPendingDelete] = useState<Announcement | null>(null);` (add `useState` to the React import). The ✕ button's `onClick` becomes `() => setPendingDelete(a)`. Add at the end of the root `<div>`:

```tsx
      {pendingDelete && (
        <ConfirmDialog
          title="Remove announcement?"
          tone="danger"
          body={<p>"<strong>{pendingDelete.title}</strong>" comes off the calendar for everyone. Already-sent messages are not recalled.</p>}
          confirmLabel="Remove"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => { onDeleteAnnouncement(pendingDelete.id); setPendingDelete(null); }}
        />
      )}
```

- [ ] **Step 4: RecruitmentModule — bid**

Add the import and `const [pendingBid, setPendingBid] = useState<PNM | null>(null);`. The bid button's `onClick` becomes `() => setPendingBid(pnm)`; its label becomes `Extend bid`. Add:

```tsx
      {pendingBid && (
        <ConfirmDialog
          title="Extend a bid?"
          body={<p><strong>{pendingBid.name}</strong> moves to Bid Extended and gets a text saying the chapter has offered them membership.</p>}
          confirmLabel="Extend bid"
          onCancel={() => setPendingBid(null)}
          onConfirm={() => { onExtendBid(pendingBid.id); setPendingBid(null); }}
        />
      )}
```

- [ ] **Step 5: CommandModule — chips fill, Execute confirms, no fake history**

- Replace the seeded `commandHistory` initial array with `[]`.
- Chip `onClick={() => { setCommandInput(t); handleRunCommand(t); }}` → `onClick={() => setCommandInput(t)}`; the chips heading `Quick Command Templates:` → `Templates (fill the box, then Execute):`.
- Add `const [pendingCommand, setPendingCommand] = useState<string | null>(null);` and change the form's `onSubmit` to `(e) => { e.preventDefault(); if (commandInput.trim()) setPendingCommand(commandInput.trim()); }`.
- Add:

```tsx
      {pendingCommand && (
        <ConfirmDialog
          title="Run this command?"
          tone="danger"
          body={<><p className="font-mono bg-slate-100 rounded p-2 text-slate-900">{pendingCommand}</p><p>This writes to the live chapter record (fines, jobs, events, texts).</p></>}
          confirmLabel="Run"
          onCancel={() => setPendingCommand(null)}
          onConfirm={() => { handleRunCommand(pendingCommand); setPendingCommand(null); }}
        />
      )}
```

- Header: `Natural Language Command Console` → `Command console`; delete the `GreekOS NLP Engine` badge span; subtitle → `Type an instruction in plain English. Every command is a real write to the chapter record.`
- Log heading `Command Execution Log & Audit Trail` → `Command log`; its subtitle → `Commands run in this session.`

- [ ] **Step 6: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 7: Browser check**

Each of: Treasury Mark paid, Roster standing change, Home announcement ✕, Recruitment Extend bid, Command Execute shows a dialog naming who and what; Cancel leaves everything unchanged; Confirm performs it. Clicking a command chip only fills the input; the log starts empty.

- [ ] **Step 8: Commit**

```bash
git add LocalDev/greekos/src/components/FinanceModule.tsx LocalDev/greekos/src/components/RosterModule.tsx LocalDev/greekos/src/components/DashboardOverview.tsx LocalDev/greekos/src/components/RecruitmentModule.tsx LocalDev/greekos/src/components/CommandModule.tsx
git commit -m "feat(greekos): confirm consequence-bearing actions; command chips only fill"
```

---

### Task 5: Persistent, announced toast

**Files:**
- Modify: `LocalDev/greekos/src/hooks/useToast.ts`
- Modify: `LocalDev/greekos/src/components/layout/AppShell.tsx` (toast block, props)
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (return `dismissToast`)
- Modify: `LocalDev/greekos/src/App.tsx` (pass `onDismissToast`)

- [ ] **Step 1: Hook**

Replace `useToast.ts` body with:

```ts
import { useState } from 'react';

/** One toast at a time. It stays until the next toast replaces it or the
 *  user dismisses it — no timer, so nothing disappears before it is read. */
export function useToast() {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => setToastMessage(msg);
  const dismissToast = () => setToastMessage(null);
  return { toastMessage, showToast, dismissToast };
}

export type ShowToast = ReturnType<typeof useToast>['showToast'];
```

In `useAppData.ts`, destructure `dismissToast` from `useToast()` and add `dismissToast,` to the return.

- [ ] **Step 2: Shell**

In `AppShell.tsx`, add prop `onDismissToast: () => void;` and replace the toast block with:

```tsx
      <div role="status" aria-live="polite" className="fixed bottom-6 right-6 z-50">
        {toastMessage && (
          <div className="bg-navy text-white pl-4 pr-2 py-3 rounded-xl border border-gold shadow-2xl flex items-center gap-2.5 animate-in fade-in slide-in-from-bottom-5">
            <Sparkles className="w-4 h-4 text-gold shrink-0" />
            <span className="text-xs font-semibold">{toastMessage}</span>
            <button type="button" onClick={onDismissToast} aria-label="Dismiss notification" className="ml-2 p-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 cursor-pointer">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
```

Add `X` to the `lucide-react` import. The live region must exist even when empty, which is why the wrapper is outside the conditional.

In `App.tsx`, pass `onDismissToast={app.dismissToast}` to `<AppShell>`.

- [ ] **Step 3: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/hooks/useToast.ts LocalDev/greekos/src/hooks/useAppData.ts LocalDev/greekos/src/components/layout/AppShell.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): toast is a live region and stays until dismissed"
```

---

### Task 6: Demo view-as is visibly demo

**Files:**
- Modify: `LocalDev/greekos/src/components/Sidebar.tsx` (switcher block)
- Modify: `LocalDev/greekos/src/components/layout/AppShell.tsx` (header chip; props)
- Modify: `LocalDev/greekos/src/App.tsx`

- [ ] **Step 1: Sidebar**

Wrap the switcher contents (the `{switcherOpen && (<div className="px-3.5 pb-3.5 space-y-2.5"> …` block) so that its first child is:

```tsx
            <p className="text-xs font-bold text-amber-300 bg-amber-900/40 border border-amber-700/60 rounded-lg px-2.5 py-1.5">
              Demo: view as — changes only what this screen shows
            </p>
```

Change the `View as` label text to `Demo: view as member`.

- [ ] **Step 2: Header chip**

`AppShellProps` gains `sessionName: string; sessionIsOfficer: boolean;`. In the header chip, after the name/role block, add:

```tsx
            {(currentMemberName !== sessionName || isOfficer !== sessionIsOfficer) && (
              <span className="text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300 px-1.5 py-0.5 rounded">
                Viewing as
              </span>
            )}
```

In `App.tsx`, pass `sessionName={app.sessionName}` and `sessionIsOfficer={app.sessionIsOfficer}`.

- [ ] **Step 3: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 4: Browser check**

Flip to Member or pick another name: the header chip shows "Viewing as" in amber and the sidebar switcher carries the Demo notice. Flip back: the chip disappears.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/components/Sidebar.tsx LocalDev/greekos/src/components/layout/AppShell.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): label impersonation as Demo view-as"
```

---

## Done when

- A blank roll sheet cannot be saved; unmarked rows are never sent.
- Every action in Task 4 asks once, naming who and what; command chips only fill the input; the command log starts empty.
- Toast has `role="status" aria-live="polite"` and a labeled dismiss button.
- Impersonation shows "Viewing as" and the Demo notice.
- Six commits; `npm test` and lint clean.
