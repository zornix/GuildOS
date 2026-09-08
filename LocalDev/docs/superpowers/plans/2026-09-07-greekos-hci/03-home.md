# Plan 03 — Home: welcome + 2×2, upcoming counts, balance line, inline check-in

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first. Plans 01 and 02 must be on `feat/greekos-hci`.

**Goal:** Home is a welcome banner (name, role, standing, personal upcoming counts, balance owed line, finishing CTAs) over four content tiles: Upcoming events, Announcements, Jobs, Initiatives. Members check in from Home when a door is open. Officers open the create form from Home.

**Architecture:** `DashboardOverview.tsx` is rewritten as a thin 2×2 layout. The banner moves to `components/home/WelcomeBanner.tsx`. The door-code form becomes a shared `components/home/DoorCodeField.tsx` used by Home and Attendance. Balance copy is a tested pure function in `lib/balance.ts`.

**Tech Stack:** React 19, TypeScript, `node:test`.

**Spec:** handoff § "1. Home dashboard"; README decisions D3, D5, D6.

## Global Constraints

- Personal counts only. Never a chapter KPI row, never a ranking. Do not put contribution near standing text beyond the same banner.
- Words: **chaired / chairing**, **Balance owed**, **Door code**.
- Keep Mandatory / organizers-needed / open-jobs badges on event rows, and the pending sign-off alert for officers.

---

### Task 1: Balance status copy

**Files:**
- Modify: `LocalDev/greekos/src/lib/balance.ts`
- Modify: `LocalDev/greekos/src/lib/balance.test.ts`

**Interfaces:**
- Produces: `balanceStatusLine(balance: MemberBalance | null): string`.

- [ ] **Step 1: Add failing tests** to `balance.test.ts`:

```ts
import { balanceStatusLine } from './balance';

test('balance line names the amount and invoice counts', () => {
  assert.equal(
    balanceStatusLine({ outstandingCents: 12500, openInvoiceCount: 2, overdueInvoiceCount: 1 }),
    'Balance owed $125.00 · 2 open invoices (1 overdue)'
  );
  assert.equal(
    balanceStatusLine({ outstandingCents: 2500, openInvoiceCount: 1, overdueInvoiceCount: 0 }),
    'Balance owed $25.00 · 1 open invoice'
  );
});

test('a clean account says so; unknown says nothing', () => {
  assert.equal(balanceStatusLine({ outstandingCents: 0, openInvoiceCount: 0, overdueInvoiceCount: 0 }), 'No balance owed');
  assert.equal(balanceStatusLine(null), '');
});
```

(Merge the import into the existing import line.)

- [ ] **Step 2: Run to verify it fails**

Run: `npm test` — Expected: FAIL, `balanceStatusLine` is not exported.

- [ ] **Step 3: Implement** — append to `lib/balance.ts`:

```ts
import { formatMoney } from '../formatters';

/** The one-line status Home shows. Empty string while the balance is unknown
 *  so the banner can render nothing rather than a fake $0. */
export function balanceStatusLine(balance: MemberBalance | null): string {
  if (!balance) return '';
  if (balance.outstandingCents <= 0 && balance.openInvoiceCount === 0) return 'No balance owed';
  const n = balance.openInvoiceCount;
  const invoices = `${n} open invoice${n === 1 ? '' : 's'}`;
  const overdue = balance.overdueInvoiceCount > 0 ? ` (${balance.overdueInvoiceCount} overdue)` : '';
  return `Balance owed ${formatMoney(balance.outstandingCents)} · ${invoices}${overdue}`;
}
```

Move the `formatMoney` import to the top of the file with the other import.

- [ ] **Step 4: Run to verify it passes** — `npm test` — Expected: `ℹ fail 0`.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/lib/balance.ts LocalDev/greekos/src/lib/balance.test.ts
git commit -m "feat(greekos): balance owed status line"
```

---

### Task 2: Shared door-code field; Attendance member default tab

**Files:**
- Create: `LocalDev/greekos/src/components/home/DoorCodeField.tsx`
- Modify: `LocalDev/greekos/src/components/AttendanceModule.tsx` (props; state 46–49; `handleCodeCheckInSubmit` 99–106; tab 2 form 287–318)
- Modify: `LocalDev/greekos/src/App.tsx` (Attendance props)

**Interfaces:**
- `DoorCodeField` props: `{ onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>; compact?: boolean }`.
- `AttendanceModuleProps` gains `initialTab: 'roster_check' | 'excuses' | 'self_pin'`.

- [ ] **Step 1: Create the field**

Create `LocalDev/greekos/src/components/home/DoorCodeField.tsx`:

```tsx
import React, { useId, useState } from 'react';

interface DoorCodeFieldProps {
  /** The code identifies the event; the backend checks in the signed-in member. */
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
  /** Home renders the small version; Attendance the large centered one. */
  compact?: boolean;
}

/** The 6-character door code entry, shared by Home and Attendance. */
export default function DoorCodeField({ onSelfCheckIn, compact = false }: DoorCodeFieldProps) {
  const id = useId();
  const [code, setCode] = useState('');
  const [feedback, setFeedback] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const result = await onSelfCheckIn(code);
    setBusy(false);
    setFeedback(result);
    if (result.ok) setCode('');
  };

  return (
    <form onSubmit={submit} className={compact ? 'flex flex-wrap items-end gap-2' : 'space-y-4'}>
      <div className={compact ? '' : 'text-center'}>
        <label htmlFor={id} className="text-xs font-bold text-slate-700 block mb-1">
          Door code
        </label>
        <input
          id={id}
          type="text"
          inputMode="text"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={e => setCode(e.target.value)}
          placeholder="A7x9Kp"
          required
          className={compact
            ? 'w-36 text-center text-xl font-mono font-black tracking-widest py-2 border-2 border-slate-300 rounded-lg focus:outline-none focus:border-gold bg-white text-slate-900'
            : 'w-48 mx-auto text-center text-3xl font-mono font-black tracking-widest py-3 border-2 border-slate-300 rounded-xl focus:outline-none focus:border-gold'}
        />
      </div>

      <button
        type="submit"
        disabled={busy || !code.trim()}
        className={`bg-navy text-gold hover:bg-slate-800 font-bold min-h-11 rounded-lg text-xs transition-all cursor-pointer disabled:opacity-50 ${compact ? 'px-4' : 'w-full py-3'}`}
      >
        {busy ? 'Checking in…' : 'Check in'}
      </button>

      {feedback && (
        <div
          role="status"
          className={`p-2.5 rounded-lg text-xs font-semibold ${compact ? 'basis-full' : ''} ${
            feedback.ok ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {feedback.message}
        </div>
      )}
    </form>
  );
}
```

- [ ] **Step 2: Use it in Attendance**

In `AttendanceModule.tsx`:

- Add to props: `initialTab: 'roster_check' | 'excuses' | 'self_pin';` and destructure it.
- Replace `useState<'roster_check' | 'excuses' | 'self_pin'>('roster_check')` with `useState<'roster_check' | 'excuses' | 'self_pin'>(initialTab)`.
- Delete the three door-code state lines (`enteredCode`, `codeFeedback`, `checkingIn`) and the `handleCodeCheckInSubmit` function.
- Replace the whole `<form onSubmit={handleCodeCheckInSubmit} …> … </form>` in the `self_pin` tab with `<DoorCodeField onSelfCheckIn={onSelfCheckIn} />`.
- Add `import DoorCodeField from './home/DoorCodeField';`.
- In the same tab, change the heading text `Live Door Check-In` to `Door code` and the paragraph to: `Enter the door code an officer is showing. The code decides which event you are checked into.`
- Change the tab button label `Live Door Check-In` to `Door code`.

- [ ] **Step 3: App passes the default tab**

In `App.tsx`, add to `<AttendanceModule …>`:

```tsx
          initialTab={isOfficer ? 'roster_check' : 'self_pin'}
```

- [ ] **Step 4: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/components/home/DoorCodeField.tsx LocalDev/greekos/src/components/AttendanceModule.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): shared door-code field; members land on it in Attendance"
```

---

### Task 3: Welcome banner

**Files:**
- Create: `LocalDev/greekos/src/components/home/WelcomeBanner.tsx`

**Interfaces:**
- Props: `{ member: Member | undefined; currentMemberName: string; memberCount: number; isOfficer: boolean; contribution: ContributionSummary; myBalance: MemberBalance | null; liveDoorEvent: ChapterEvent | undefined; onScheduleEvent: () => void; onOpenTreasury: () => void; onOpenAttendance: () => void; onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }> }`.

- [ ] **Step 1: Create it**

```tsx
import { Calendar, KeyRound, Wallet } from 'lucide-react';
import type { ChapterEvent, Member } from '../../types';
import type { ContributionSummary } from '../../lib/contribution';
import { MemberBalance, balanceStatusLine } from '../../lib/balance';
import DoorCodeField from './DoorCodeField';

interface WelcomeBannerProps {
  member: Member | undefined;
  currentMemberName: string;
  memberCount: number;
  isOfficer: boolean;
  contribution: ContributionSummary;
  myBalance: MemberBalance | null;
  liveDoorEvent: ChapterEvent | undefined;
  onScheduleEvent: () => void;
  onOpenTreasury: () => void;
  onOpenAttendance: () => void;
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
}

/** Name, role, standing, the member's own upcoming counts, balance owed, and
 *  the two actions that finish on this screen: schedule (officer) and
 *  check in (member, when a door is open). */
export default function WelcomeBanner({
  member, currentMemberName, memberCount, isOfficer, contribution, myBalance, liveDoorEvent,
  onScheduleEvent, onOpenTreasury, onOpenAttendance, onSelfCheckIn
}: WelcomeBannerProps) {
  const counts = [
    `Organizing ${contribution.eventsOrganized}`,
    ...(isOfficer ? [`Supervising ${contribution.eventsSupervised}`] : []),
    `Chairing ${contribution.initiativesChaired}`
  ];
  const balanceLine = balanceStatusLine(myBalance);

  return (
    <div className="bg-navy text-white rounded-2xl p-6 shadow-md border border-[#1e2d42] space-y-4">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold bg-gold text-navy px-2.5 py-0.5 rounded">
              {member?.role || 'Brother'}
            </span>
            <span className="text-xs text-slate-300">{member?.standing || 'Good Standing'}</span>
          </div>
          <h1 className="text-2xl font-display font-extrabold text-white tracking-tight">
            Welcome back, {currentMemberName}
          </h1>
          <p className="text-xs text-slate-300">
            Alpha Chapter &bull; {memberCount} members
          </p>
          {/* Personal, upcoming-only. Facts of assignment shown to the member
              themself — never a ranking, never a standing input (ADR-0004). */}
          <p className="text-xs text-slate-200 pt-1">
            <span className="text-slate-400">Upcoming:</span> {counts.join(' · ')}
          </p>
        </div>

        <div className="flex flex-col items-start md:items-end gap-2">
          {balanceLine && (
            <button
              type="button"
              onClick={onOpenTreasury}
              className="text-xs font-semibold text-slate-100 hover:text-gold flex items-center gap-1.5 cursor-pointer"
            >
              <Wallet className="w-3.5 h-3.5 text-gold" />
              {balanceLine} &rarr;
            </button>
          )}

          {isOfficer && (
            <button
              type="button"
              onClick={onScheduleEvent}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <Calendar className="w-4 h-4" />
              Schedule event
            </button>
          )}
        </div>
      </div>

      {!isOfficer && (
        <div className="border-t border-[#1e2d42] pt-4">
          {liveDoorEvent ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-gold" />
                Door open for <span className="text-white">{liveDoorEvent.title}</span>
              </p>
              <DoorCodeField onSelfCheckIn={onSelfCheckIn} compact />
            </div>
          ) : (
            <button
              type="button"
              onClick={onOpenAttendance}
              className="text-xs text-slate-300 hover:text-gold cursor-pointer"
            >
              No door open right now &middot; Attendance &rarr;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add LocalDev/greekos/src/components/home/WelcomeBanner.tsx
git commit -m "feat(greekos): welcome banner with upcoming counts, balance line, inline check-in"
```

---

### Task 4: DashboardOverview as 2×2; App wiring

**Files:**
- Rewrite: `LocalDev/greekos/src/components/DashboardOverview.tsx`
- Modify: `LocalDev/greekos/src/App.tsx` (Dashboard props)

**Interfaces:**
- `DashboardOverviewProps` becomes:

```ts
interface DashboardOverviewProps {
  members: Member[];
  events: ChapterEvent[];
  tasks: Task[];
  initiatives: Initiative[];
  announcements: Announcement[];
  isOfficer: boolean;
  currentMemberName: string;
  contribution: ContributionSummary;
  myBalance: MemberBalance | null;
  onNavigateTab: (tab: string) => void;
  onOpenEvent: (eventId: string) => void;
  onScheduleEvent: () => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
  onDeleteAnnouncement: (announcementId: string) => void;
}
```

(`fines`, `ledger`, `onPayDuesQuick` are gone.)

- [ ] **Step 1: Replace the file**

Overwrite `DashboardOverview.tsx` with:

```tsx
import React from 'react';
import { AlertTriangle, Calendar, CheckSquare, Clock, Megaphone, Sparkles, X } from 'lucide-react';
import { ChapterEvent, Member, Task, Initiative, Announcement } from '../types';
import Card from './ui/Card';
import { isoDay } from '../formatters';
import type { ContributionSummary } from '../lib/contribution';
import type { MemberBalance } from '../lib/balance';
import { liveDoorEvent } from '../lib/events';
import WelcomeBanner from './home/WelcomeBanner';

interface DashboardOverviewProps {
  members: Member[];
  events: ChapterEvent[];
  tasks: Task[];
  initiatives: Initiative[];
  announcements: Announcement[];
  isOfficer: boolean;
  currentMemberName: string;
  contribution: ContributionSummary;
  myBalance: MemberBalance | null;
  onNavigateTab: (tab: string) => void;
  onOpenEvent: (eventId: string) => void;
  onScheduleEvent: () => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
  onDeleteAnnouncement: (announcementId: string) => void;
}

const TILE_LIMIT = 3;

function TileHeader({ icon, title, onAll, allLabel }: { icon: React.ReactNode; title: string; onAll: () => void; allLabel: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
      <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
        {icon}
        {title}
      </h3>
      <button type="button" onClick={onAll} className="text-xs font-semibold text-navy hover:text-gold-muted cursor-pointer">
        {allLabel} &rarr;
      </button>
    </div>
  );
}

/** Home: welcome banner over four content tiles. No chapter KPIs, no ranking. */
export default function DashboardOverview({
  members, events, tasks, initiatives, announcements, isOfficer, currentMemberName,
  contribution, myBalance, onNavigateTab, onOpenEvent, onScheduleEvent,
  onVolunteerOrganizer, onSelfCheckIn, onDeleteAnnouncement
}: DashboardOverviewProps) {
  const safeMembers = members || [];
  const safeEvents = events || [];
  const safeTasks = tasks || [];
  const safeInitiatives = initiatives || [];
  const safeAnnouncements = announcements || [];

  const currentMember = safeMembers.find(m => m.name === currentMemberName);
  const today = isoDay();
  const upcomingEvents = safeEvents.filter(e => e.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, TILE_LIMIT);
  const pendingJobSignOffs = safeEvents.flatMap(e => (e.jobs || []).filter(j => j.status === 'Done Reported'));

  return (
    <div className="space-y-6">
      <WelcomeBanner
        member={currentMember}
        currentMemberName={currentMemberName}
        memberCount={safeMembers.length}
        isOfficer={isOfficer}
        contribution={contribution}
        myBalance={myBalance}
        liveDoorEvent={liveDoorEvent(safeEvents, today)}
        onScheduleEvent={onScheduleEvent}
        onOpenTreasury={() => onNavigateTab('finance')}
        onOpenAttendance={() => onNavigateTab('attendance')}
        onSelfCheckIn={onSelfCheckIn}
      />

      {isOfficer && pendingJobSignOffs.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <Clock className="w-5 h-5 text-amber-900 shrink-0" />
            <p className="text-xs text-amber-950">
              <strong>{pendingJobSignOffs.length} job{pendingJobSignOffs.length > 1 ? 's' : ''} reported done</strong> and waiting for your sign-off.
            </p>
          </div>
          <button type="button" onClick={() => onNavigateTab('events')} className="text-xs bg-navy hover:bg-slate-800 text-gold font-bold px-3.5 py-2 rounded-lg cursor-pointer shrink-0">
            Review in Events
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upcoming events */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Calendar className="w-4 h-4 text-gold" />} title="Upcoming events" onAll={() => onNavigateTab('events')} allLabel="All events" />
          {upcomingEvents.length === 0 && <p className="text-xs text-slate-500">No upcoming events.</p>}
          {upcomingEvents.map(event => {
            const orgCount = event.organizerCount ?? (event.organizers || []).length;
            const openJobs = event.openJobCount || 0;
            return (
              <div key={event.id} className="p-3 rounded-xl border border-slate-200/90 bg-slate-50/50 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <button type="button" onClick={() => onOpenEvent(event.id)} className="text-left font-bold text-sm text-slate-900 hover:text-navy cursor-pointer">
                    {event.title}
                  </button>
                  <span className="text-xs text-slate-500 text-right shrink-0">{event.date}<br />{event.time}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-bold text-amber-900 bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">{event.type}</span>
                  {event.required && <span className="text-xs font-extrabold bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">Mandatory</span>}
                  {orgCount === 0 ? (
                    <span className="text-xs font-semibold bg-red-100 text-red-800 px-2 py-0.5 rounded flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 text-red-600" /> Organizers needed
                    </span>
                  ) : (
                    <span className="text-xs text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                      {orgCount} organizer{orgCount > 1 ? 's' : ''}
                    </span>
                  )}
                  {openJobs > 0 && <span className="text-xs text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">{openJobs} open job{openJobs > 1 ? 's' : ''}</span>}
                  {orgCount === 0 && (
                    <button type="button" onClick={() => onVolunteerOrganizer(event.id, currentMemberName)} className="ml-auto text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md cursor-pointer">
                      Volunteer as organizer
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </Card>

        {/* Announcements */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Megaphone className="w-4 h-4 text-blue-600" />} title="Announcements" onAll={() => onNavigateTab('events')} allLabel="Calendar" />
          {safeAnnouncements.length === 0 && <p className="text-xs text-slate-500">No announcements yet.</p>}
          {safeAnnouncements.slice(0, TILE_LIMIT).map(a => (
            <div key={a.id} className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 space-y-1">
              <div className="flex justify-between items-center gap-2">
                <span className="font-bold text-xs text-blue-950">{a.title}</span>
                {isOfficer && (
                  <button
                    type="button"
                    onClick={() => onDeleteAnnouncement(a.id)}
                    aria-label={`Remove announcement "${a.title}" from calendar`}
                    className="text-blue-400 hover:text-red-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <p className="text-xs text-blue-900 leading-relaxed">{a.content}</p>
              <div className="text-xs text-blue-600">{a.date} &bull; {a.author}</div>
            </div>
          ))}
        </Card>

        {/* Jobs */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<CheckSquare className="w-4 h-4 text-gold" />} title="Jobs" onAll={() => onNavigateTab('tasks')} allLabel="All jobs" />
          {safeTasks.length === 0 && <p className="text-xs text-slate-500">No jobs yet.</p>}
          {safeTasks.filter(t => t.status !== 'Completed').slice(0, TILE_LIMIT).map(task => (
            <div key={task.id} className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 flex items-center justify-between text-xs gap-2">
              <div>
                <div className="font-bold text-slate-800">{task.title}</div>
                <div className="text-xs text-slate-500">{task.assignedTo}</div>
              </div>
              <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 shrink-0">{task.status}</span>
            </div>
          ))}
        </Card>

        {/* Initiatives */}
        <Card className="p-5 space-y-3">
          <TileHeader icon={<Sparkles className="w-4 h-4 text-purple-600" />} title="Initiatives" onAll={() => onNavigateTab('initiatives')} allLabel="All initiatives" />
          {safeInitiatives.length === 0 && <p className="text-xs text-slate-500">No initiatives yet.</p>}
          {safeInitiatives.slice(0, TILE_LIMIT).map(init => (
            <div key={init.id} className="p-3 bg-purple-50/40 rounded-xl border border-purple-100 space-y-1">
              <div className="flex justify-between items-start gap-2">
                <h4 className="font-bold text-xs text-slate-900">{init.title}</h4>
                <span className="text-xs text-slate-500 shrink-0">Target {(init.targetDate || '').substring(5)}</span>
              </div>
              <p className="text-xs text-slate-500 line-clamp-1">{init.description}</p>
              <span className="text-xs text-purple-700 block font-semibold">Chairs: {(init.leadChairs || []).join(', ')}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire App.tsx**

Replace the `<DashboardOverview …/>` element with:

```tsx
        <DashboardOverview
          members={roster.members}
          events={events.events}
          tasks={tasks.tasks}
          initiatives={initiatives.initiatives}
          announcements={app.announcements}
          isOfficer={isOfficer}
          currentMemberName={currentMemberName}
          contribution={app.contribution}
          myBalance={app.myBalance}
          onNavigateTab={setActiveTab}
          onOpenEvent={id => { chrome.openEvent(id); setActiveTab('events'); }}
          onScheduleEvent={() => { chrome.openCreate(); setActiveTab('events'); }}
          onVolunteerOrganizer={events.handleVolunteerOrganizer}
          onSelfCheckIn={attendance.handleSelfCheckIn}
          onDeleteAnnouncement={app.handleDeleteAnnouncement}
        />
```

- [ ] **Step 3: Lint and test** — `npm run lint && npm test` — Expected: clean; `ℹ fail 0`.

- [ ] **Step 4: Browser check (officer, then member)**

As Jake (officer): banner shows role, standing, "Upcoming: Organizing N · Supervising N · Chairing N", a balance line (or "No balance owed"), and "Schedule event". Click it: Events opens on the list with the create form open. Four tiles in a 2×2 on desktop, stacked on a 390px-wide viewport. Click an event title: Events list opens with that event selected.

Flip the sidebar switch to Member: no Supervising count, no Schedule button. Open an Events door link as officer first (Events → detail → "Enable door link"), flip back to Member: the banner shows "Door open for <title>" with the code field; entering the code checks in and shows the success message inline.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/components/DashboardOverview.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): home as welcome + 2x2 content tiles"
```

---

## Done when

- Officer and member Home match the ASCII layout in the handoff (welcome, then 2×2).
- Welcome counts are personal and upcoming-only, with "Chairing", never "led".
- Balance line reads from the real balance and links to Treasury; there is no Pay button on Home.
- Member check-in completes on Home when a door is open; Schedule event opens the create form.
- Attendance opens on Door code for members.
- Four commits; `npm test` and lint clean.
