# Plan 01 — Foundation: test runner, session permissions, contribution, member balance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first.

**Goal:** Give greekos a unit-test runner, a real session (permissions from RBAC), an honest personal contribution count, and the member's real balance, so Home, Treasury, and Safety plans have data to render.

**Architecture:** Pure functions in `src/lib/` with `node:test` tests. `src/api.ts` gains two GET calls. `src/hooks/useAppData.ts` loads permissions, balance, and per-upcoming-event detail in the existing load path and exposes them. Nothing renders differently yet except the sidebar's officer-only filter.

**Tech Stack:** Vite + React 19 + TypeScript, `tsx` (already a devDependency) running `node:test`.

**Spec:** `LocalDev/docs/greekos-hci-handoff.md` — decisions D3, D5, D8, D11 in `00-README.md`.

## Global Constraints

- No new npm dependencies. No backend or migration changes.
- Money is integer cents outside form inputs.
- Tests take `today` as a parameter; never read the clock inside a pure function.
- Commit per task, no attribution trailers, branch `feat/greekos-hci`.

---

### Task 0: Branch and test runner

**Files:**
- Modify: `LocalDev/greekos/package.json` (scripts)
- Create: `LocalDev/greekos/src/formatters.test.ts`
- Modify: `LocalDev/greekos/README.md` (Checks section)

- [ ] **Step 1: Create the branch**

```bash
cd /home/mshi/GuildOS && git checkout -b feat/greekos-hci main
```

- [ ] **Step 2: Write a failing smoke test**

Create `LocalDev/greekos/src/formatters.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney } from './formatters';

test('formatMoney renders integer cents as dollars', () => {
  assert.equal(formatMoney(150), '$1.50');
  assert.equal(formatMoney(123456), '$1,234.56');
  assert.equal(formatMoney(0), '$0.00');
});
```

- [ ] **Step 3: Run it to confirm there is no runner yet**

Run: `cd LocalDev/greekos && npm test`
Expected: `npm ERR! Missing script: "test"`

- [ ] **Step 4: Add the script**

In `LocalDev/greekos/package.json`, inside `"scripts"`, add after `"lint"`:

```json
    "test": "tsx --test 'src/**/*.test.ts'"
```

- [ ] **Step 5: Run the test and confirm it passes**

Run: `npm test`
Expected: `ℹ pass 1` and `ℹ fail 0`.

- [ ] **Step 6: Document the command**

In `LocalDev/greekos/README.md`, in the `## Checks` code block, add a line before `npm run lint`:

```bash
npm test              # node:test via tsx — src/**/*.test.ts
```

- [ ] **Step 7: Commit**

```bash
git add LocalDev/greekos/package.json LocalDev/greekos/src/formatters.test.ts LocalDev/greekos/README.md
git commit -m "test(greekos): add node:test runner via tsx"
```

---

### Task 1: Session permissions

**Files:**
- Create: `LocalDev/greekos/src/lib/session.ts`
- Create: `LocalDev/greekos/src/lib/session.test.ts`
- Modify: `LocalDev/greekos/src/api.ts` (add `MyPermissionsDto` + `getMyPermissions`)
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (lines 33–35 state, 98–166 load, 241–262 return)

**Interfaces:**
- Produces: `OFFICER_VIEW_KEY`, `isOfficerView(perms)`, `can(perms, key)`; `useAppData()` returns `permissions: Set<string>`, `sessionIsOfficer: boolean`, `sessionName: string` in addition to the existing `isOfficer` / `currentMemberName` (which remain the *view* values the Demo switcher can override).

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/session.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { OFFICER_VIEW_KEY, can, isOfficerView } from './session';

test('officer view requires the chapter-wide standing key', () => {
  assert.equal(OFFICER_VIEW_KEY, 'standing:view_all');
  assert.equal(isOfficerView(['standing:view_all', 'tasks:create']), true);
  assert.equal(isOfficerView(['tasks:complete']), false);
  assert.equal(isOfficerView([]), false);
});

test('can() is an exact key match', () => {
  const perms = new Set(['calendar:event:create']);
  assert.equal(can(perms, 'calendar:event:create'), true);
  assert.equal(can(perms, 'calendar:event'), false);
  assert.equal(can([], 'calendar:event:create'), false);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — `Cannot find module './session'`.

- [ ] **Step 3: Implement**

Create `LocalDev/greekos/src/lib/session.ts`:

```ts
/** Who is signed in, as the backend sees it. Permission keys come from
 *  GET /api/rbac/me/permissions; code never branches on a role's name. */

/** Holding the chapter-wide standing view is what makes a session an
 *  "officer view" in this prototype. Per-module keys are a later slice. */
export const OFFICER_VIEW_KEY = 'standing:view_all';

export function can(permissions: Iterable<string>, key: string): boolean {
  for (const p of permissions) if (p === key) return true;
  return false;
}

export function isOfficerView(permissions: Iterable<string>): boolean {
  return can(permissions, OFFICER_VIEW_KEY);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test`
Expected: `ℹ pass 3`, `ℹ fail 0`.

- [ ] **Step 5: Add the API call**

In `LocalDev/greekos/src/api.ts`, directly after the `MeDto` interface (line 68), add:

```ts
/** GET /api/rbac/me/permissions — the only source of authority in the UI. */
export interface MyPermissionsDto { permissions: string[]; roles: string[]; }
```

In the `api` object, directly after the `getMe` line (line 259), add:

```ts
  getMyPermissions: () => request<MyPermissionsDto>('GET', '/api/rbac/me/permissions'),
```

- [ ] **Step 6: Load permissions and derive the officer view**

In `LocalDev/greekos/src/hooks/useAppData.ts`:

Add to the imports (after line 4):

```ts
import { isOfficerView } from '../lib/session';
```

Replace lines 33–35:

```ts
  // Access level & impersonation state
  const [isOfficer, setIsOfficer] = useState<boolean>(true);
  const [currentMemberName, setCurrentMemberName] = useState<string>('Alexander Mercer');
```

with:

```ts
  // The real session (from /me + /rbac/me/permissions) …
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [sessionName, setSessionName] = useState<string>('');
  const sessionIsOfficer = isOfficerView(permissions);
  // … and the *view*, which the Demo "view as" switcher may override. Starts
  // as officer so the backend-down mock data still shows the full prototype.
  const [isOfficer, setIsOfficer] = useState<boolean>(true);
  const [currentMemberName, setCurrentMemberName] = useState<string>('Alexander Mercer');
```

Replace lines 102–109 (the first `Promise.all` of the load):

```ts
        const [me, memberRows, standingRows, scoreRows] = await Promise.all([
          api.getMe(),
          api.getMembers(),
          // Officer-gated: a member session 403s, which just means an empty
          // standing/score section rather than a failed load.
          optionalOfficerCall(api.getStandings(), []),
          optionalOfficerCall(api.getScores(), [])
        ]);
```

with:

```ts
        const [me, perms, memberRows, standingRows, scoreRows] = await Promise.all([
          api.getMe(),
          api.getMyPermissions(),
          api.getMembers(),
          // Officer-gated: a member session 403s, which just means an empty
          // standing/score section rather than a failed load.
          optionalOfficerCall(api.getStandings(), []),
          optionalOfficerCall(api.getScores(), [])
        ]);
        const permissionSet = new Set(perms.permissions);
```

Replace lines 141–142:

```ts
        setMembers(rosterRows);
        setCurrentMemberName(me.name);
```

with:

```ts
        setMembers(rosterRows);
        setPermissions(permissionSet);
        setSessionName(me.name);
        setCurrentMemberName(me.name);
        setIsOfficer(isOfficerView(permissionSet));
```

In the returned object (lines 241–262), add after `isOfficer,`:

```ts
    permissions,
    sessionIsOfficer,
    sessionName,
```

- [ ] **Step 7: Lint**

Run: `npm run lint`
Expected: no output (clean).

- [ ] **Step 8: Commit**

```bash
git add LocalDev/greekos/src/lib/session.ts LocalDev/greekos/src/lib/session.test.ts LocalDev/greekos/src/api.ts LocalDev/greekos/src/hooks/useAppData.ts
git commit -m "feat(greekos): derive officer view from RBAC permissions"
```

---

### Task 2: Nav gating by permission key

**Files:**
- Modify: `LocalDev/greekos/src/config/navigation.ts`
- Modify: `LocalDev/greekos/src/components/Sidebar.tsx` (props + line 84)
- Modify: `LocalDev/greekos/src/components/layout/AppShell.tsx` (pass `permissions`)
- Modify: `LocalDev/greekos/src/App.tsx` (pass `permissions`)

**Interfaces:**
- `NavItem.officerOnly?: boolean` becomes `NavItem.permission?: string`.
- `Sidebar` gains `permissions: Set<string>`.

- [ ] **Step 1: Change the nav config**

In `LocalDev/greekos/src/config/navigation.ts`, replace:

```ts
  /** Hidden from the nav while the session is in member view. */
  officerOnly?: boolean;
```

with:

```ts
  /** Shown only when the session holds this permission key AND the view is
   *  officer (the Demo "view as" switch hides it too). */
  permission?: string;
```

and replace the two `officerOnly: true` entries:

```ts
  { id: 'recruitment', label: 'Recruitment', icon: UserPlus, permission: 'recruitment:pipeline:view' },
  // Not a demo: every command it runs is a real write (fines, jobs, events, blasts).
  { id: 'command', label: 'Command console', icon: Terminal, permission: 'nl_controller:execute' }
```

- [ ] **Step 2: Filter in the sidebar**

In `LocalDev/greekos/src/components/Sidebar.tsx`:

Add to the props interface after `isOfficer: boolean;`:

```ts
  permissions: Set<string>;
```

Destructure `permissions` in the component signature after `isOfficer,`.

Add the import at the top:

```ts
import { can } from '../lib/session';
```

Replace line 84:

```tsx
        {NAV_ITEMS.filter(item => isOfficer || !item.officerOnly).map(navRow)}
```

with:

```tsx
        {NAV_ITEMS.filter(item => !item.permission || (isOfficer && can(permissions, item.permission))).map(navRow)}
```

- [ ] **Step 3: Thread the prop**

In `AppShell.tsx`: add `permissions: Set<string>;` to `AppShellProps` after `isOfficer`, destructure it, and pass `permissions={permissions}` to `<Sidebar>`.

In `App.tsx`: pass `permissions={app.permissions}` to `<AppShell>` after `isOfficer={isOfficer}`.

- [ ] **Step 4: Lint and test**

Run: `npm run lint && npm test`
Expected: lint clean; `ℹ fail 0`.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/config/navigation.ts LocalDev/greekos/src/components/Sidebar.tsx LocalDev/greekos/src/components/layout/AppShell.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): gate nav items by permission key"
```

---

### Task 3: Upcoming contribution counts

**Files:**
- Create: `LocalDev/greekos/src/lib/contribution.ts`
- Create: `LocalDev/greekos/src/lib/contribution.test.ts`
- Create: `LocalDev/greekos/src/hooks/useContribution.ts`
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (upcoming-event loop lines 124–139; return)

**Interfaces:**
- Produces: `ContributionSummary`, `upcomingContribution(...)`, `useContribution(...)`; `useAppData()` returns `contribution: ContributionSummary`.
- Future hookup: `GET /api/contribution/me` (issue #40) will be adapted into the same `ContributionSummary` with `scope: 'lifetime'`; only `useContribution` changes.

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/contribution.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { upcomingContribution } from './contribution';
import type { ChapterEvent, Initiative } from '../types';

const event = (over: Partial<ChapterEvent>): ChapterEvent => ({
  id: 'e', title: 't', date: '2026-09-10', startTime: '18:00', endTime: '20:00', time: '18:00 - 20:00',
  location: '', type: 'Chapter Meeting', audience: 'All Members', required: false, attendanceTaken: false,
  supervisors: [], organizers: [], jobs: [], ...over
});
const initiative = (over: Partial<Initiative>): Initiative => ({
  id: 'i', title: 't', description: '', leadChairs: [], category: 'Philanthropy',
  startDate: '2026-09-01', targetDate: '2026-09-30', status: 'Active', jobs: [], ...over
});

test('counts only upcoming events the member organizes or supervises', () => {
  const events = [
    event({ id: 'a', date: '2026-09-10', organizers: ['Jake Martinez'] }),
    event({ id: 'b', date: '2026-09-11', supervisors: ['Jake Martinez'], organizers: ['Jake Martinez'] }),
    event({ id: 'c', date: '2026-09-01', organizers: ['Jake Martinez'] }), // past
    event({ id: 'd', date: '2026-09-12', organizers: ['Someone Else'] })
  ];
  const s = upcomingContribution('Jake Martinez', events, [], '2026-09-07');
  assert.deepEqual(s, { scope: 'upcoming', eventsOrganized: 2, eventsSupervised: 1, initiativesChaired: 0 });
});

test('today counts as upcoming', () => {
  const s = upcomingContribution('J', [event({ date: '2026-09-07', supervisors: ['J'] })], [], '2026-09-07');
  assert.equal(s.eventsSupervised, 1);
});

test('counts initiatives chaired that have not ended', () => {
  const inits = [
    initiative({ id: 'x', leadChairs: ['J'], targetDate: '2026-09-30' }),
    initiative({ id: 'y', leadChairs: ['J'], targetDate: '2026-08-01' }), // ended
    initiative({ id: 'z', leadChairs: ['K'] })
  ];
  assert.equal(upcomingContribution('J', [], inits, '2026-09-07').initiativesChaired, 1);
});

test('empty name never matches', () => {
  const s = upcomingContribution('', [event({ organizers: [''] })], [], '2026-09-07');
  assert.equal(s.eventsOrganized, 0);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — `Cannot find module './contribution'`.

- [ ] **Step 3: Implement**

Create `LocalDev/greekos/src/lib/contribution.ts`:

```ts
import type { ChapterEvent, Initiative } from '../types';

/** A member's own contribution numbers. `scope` says how far they reach:
 *  'upcoming' is computed client-side from loaded events; 'lifetime' will come
 *  from GET /api/contribution/me (issue #40). Never rendered as a ranking. */
export interface ContributionSummary {
  scope: 'upcoming' | 'lifetime';
  eventsOrganized: number;
  eventsSupervised: number;
  initiativesChaired: number;
}

/** Upcoming = on or after `today` (YYYY-MM-DD). Names are matched exactly
 *  because the event detail rows carry names, not ids. */
export function upcomingContribution(
  memberName: string,
  events: ChapterEvent[],
  initiatives: Initiative[],
  today: string
): ContributionSummary {
  const me = memberName.trim();
  const has = (names: string[] | undefined) => !!me && (names || []).includes(me);
  const upcoming = events.filter(e => e.date >= today);
  const open = initiatives.filter(i => (i.targetDate || i.startDate) >= today);
  return {
    scope: 'upcoming',
    eventsOrganized: upcoming.filter(e => has(e.organizers)).length,
    eventsSupervised: upcoming.filter(e => has(e.supervisors)).length,
    initiativesChaired: open.filter(i => has(i.leadChairs)).length
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test`
Expected: `ℹ fail 0`.

- [ ] **Step 5: The hook**

Create `LocalDev/greekos/src/hooks/useContribution.ts`:

```ts
import { useMemo } from 'react';
import type { ChapterEvent, Initiative } from '../types';
import { isoDay } from '../formatters';
import { ContributionSummary, upcomingContribution } from '../lib/contribution';

/** Personal contribution counts for the signed-in (or viewed-as) member.
 *  ponytail: upcoming-only, computed from loaded rows. Swap the body for
 *  api.getMyContribution() + an adapter when issue #40 lands; callers keep
 *  the same ContributionSummary. */
export function useContribution(
  memberName: string,
  events: ChapterEvent[],
  initiatives: Initiative[]
): ContributionSummary {
  return useMemo(
    () => upcomingContribution(memberName, events, initiatives, isoDay()),
    [memberName, events, initiatives]
  );
}
```

- [ ] **Step 6: Load organizer/supervisor names and door-link state for upcoming events**

The events list carries no names (see `adaptEvents`, `supervisors: []`). The load path already fetches security per upcoming event; add the detail and door link to the same loop.

In `LocalDev/greekos/src/hooks/useAppData.ts`, add to the adapters import list (lines 5–17): `adaptEventDetail,`.

Replace lines 124–139:

```ts
        // Security rosters are per event, so only upcoming events are worth a
        // request; a failing one just leaves that event's shift list empty.
        const adaptedEvents = adaptEvents(eventRows);
        const membersById = new Map(rosterRows.map(m => [m.id, m]));
        const today = new Date().toISOString().substring(0, 10);
        const securityByEvent = new Map<string, SecurityAssignment[]>();
        await Promise.all(
          adaptedEvents.filter(e => e.date >= today).map(async e => {
            try {
              const rows = await api.listSecurity(e.id);
              securityByEvent.set(e.id, rows.map(row => adaptSecurityAssignment(row, membersById)));
            } catch (err) {
              console.error(`Security load failed for event ${e.id}`, err);
            }
          })
        );
```

with:

```ts
        // Security rosters, organizer/supervisor names and the door link are
        // all per event, so only upcoming events get the extra requests; a
        // failing one just leaves that event's row with the list data.
        const adaptedEvents = adaptEvents(eventRows);
        const membersById = new Map(rosterRows.map(m => [m.id, m]));
        const today = isoDay();
        const securityByEvent = new Map<string, SecurityAssignment[]>();
        const detailByEvent = new Map<string, Partial<ChapterEvent>>();
        await Promise.all(
          adaptedEvents.filter(e => e.date >= today).map(async e => {
            try {
              const [rows, detail, link] = await Promise.all([
                api.listSecurity(e.id),
                api.getEvent(e.id),
                api.getCheckInLink(e.id)
              ]);
              securityByEvent.set(e.id, rows.map(row => adaptSecurityAssignment(row, membersById)));
              detailByEvent.set(e.id, {
                ...adaptEventDetail(detail, rosterRows),
                checkInToken: link.short_code,
                checkInLinkActive: !!link.short_code
              });
            } catch (err) {
              console.error(`Upcoming-event load failed for event ${e.id}`, err);
            }
          })
        );
```

Replace lines 143–146:

```ts
        events.setEvents(adaptedEvents.map(e => ({
          ...e,
          securityAssignments: securityByEvent.get(e.id) || e.securityAssignments
        })));
```

with:

```ts
        events.setEvents(adaptedEvents.map(e => ({
          ...e,
          ...(detailByEvent.get(e.id) || {}),
          securityAssignments: securityByEvent.get(e.id) || e.securityAssignments
        })));
```

Update the imports at the top: add `ChapterEvent` to the `../types` import (line 3) and add `import { isoDay } from '../formatters';`.

Then, after the `const recruitment = useRecruitment(...)` line (68), add:

```ts
  const contribution = useContribution(currentMemberName, events.events, initiatives.initiatives);
```

with `import { useContribution } from './useContribution';` among the hook imports, and add `contribution,` to the returned object.

- [ ] **Step 7: Lint and test**

Run: `npm run lint && npm test`
Expected: lint clean; `ℹ fail 0`.

- [ ] **Step 8: Commit**

```bash
git add LocalDev/greekos/src/lib/contribution.ts LocalDev/greekos/src/lib/contribution.test.ts LocalDev/greekos/src/hooks/useContribution.ts LocalDev/greekos/src/hooks/useAppData.ts
git commit -m "feat(greekos): upcoming contribution counts and per-event detail on load"
```

---

### Task 4: Member balance from the treasury dashboard

**Files:**
- Create: `LocalDev/greekos/src/lib/balance.ts`
- Create: `LocalDev/greekos/src/lib/balance.test.ts`
- Modify: `LocalDev/greekos/src/api.ts` (DTO + call)
- Modify: `LocalDev/greekos/src/hooks/useAppData.ts` (load + return)

**Interfaces:**
- Produces: `MemberBalance`, `adaptMemberBalance(dto)`, `api.getMemberTreasuryDashboard(memberId)`; `useAppData()` returns `myBalance: MemberBalance | null` (null until loaded or when the call fails).
- Backend: `GET /api/treasury/members/{member_id}/dashboard` — readable by the member themself; returns `{ member_id, balance: { outstanding_balance_cents, current_balance_cents, total_owed_cents, total_paid_cents }, pending_cents, pending_submissions, open_invoices: [{ id, description, amount_cents, remaining_cents, due_at, overdue, source, status }], recent_activity }`.

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/balance.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptMemberBalance } from './balance';

test('adapts outstanding cents and invoice counts', () => {
  const b = adaptMemberBalance({
    member_id: 'm1',
    balance: { outstanding_balance_cents: 12500, current_balance_cents: 12500, total_owed_cents: 30000, total_paid_cents: 17500 },
    pending_cents: 0,
    pending_submissions: [],
    open_invoices: [
      { id: 'i1', description: 'Fall dues', amount_cents: 10000, remaining_cents: 10000, due_at: '2026-09-01T00:00:00Z', overdue: true, source: 'dues', status: 'open' },
      { id: 'i2', description: 'Fine', amount_cents: 2500, remaining_cents: 2500, due_at: null, overdue: false, source: 'fine', status: 'open' }
    ],
    recent_activity: []
  });
  assert.deepEqual(b, { outstandingCents: 12500, openInvoiceCount: 2, overdueInvoiceCount: 1 });
});

test('a clean account is all zeros', () => {
  const b = adaptMemberBalance({
    member_id: 'm1',
    balance: { outstanding_balance_cents: 0, current_balance_cents: 0, total_owed_cents: 0, total_paid_cents: 0 },
    pending_cents: 0, pending_submissions: [], open_invoices: [], recent_activity: []
  });
  assert.deepEqual(b, { outstandingCents: 0, openInvoiceCount: 0, overdueInvoiceCount: 0 });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — `Cannot find module './balance'`.

- [ ] **Step 3: Add the DTO and call**

In `LocalDev/greekos/src/api.ts`, after the `TreasuryDashboardDto` interface, add:

```ts
/** GET /api/treasury/members/{id}/dashboard — readable by the member themself. */
export interface MemberTreasuryDashboardDto {
  member_id: string;
  balance: {
    outstanding_balance_cents: number;
    current_balance_cents: number;
    total_owed_cents: number;
    total_paid_cents: number;
  };
  pending_cents: number;
  pending_submissions: unknown[];
  open_invoices: {
    id: string;
    description: string | null;
    amount_cents: number;
    remaining_cents: number;
    due_at: string | null;
    overdue: boolean;
    source: string | null;
    status: string;
  }[];
  recent_activity: unknown[];
}
```

In the `api` object, after `getTreasuryDashboard`, add:

```ts
  getMemberTreasuryDashboard: (memberId: string) =>
    request<MemberTreasuryDashboardDto>('GET', `/api/treasury/members/${memberId}/dashboard`),
```

- [ ] **Step 4: Implement the adapter**

Create `LocalDev/greekos/src/lib/balance.ts`:

```ts
import type { MemberTreasuryDashboardDto } from '../api';

/** What the member owes right now. This is the number Home and the pay modal
 *  show as "Balance owed". It is NOT the standing-derived unpaid-fines number
 *  on Member.duesBalanceCents. */
export interface MemberBalance {
  outstandingCents: number;
  openInvoiceCount: number;
  overdueInvoiceCount: number;
}

export function adaptMemberBalance(dto: MemberTreasuryDashboardDto): MemberBalance {
  const invoices = dto.open_invoices || [];
  return {
    outstandingCents: dto.balance?.outstanding_balance_cents || 0,
    openInvoiceCount: invoices.length,
    overdueInvoiceCount: invoices.filter(i => i.overdue).length
  };
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `npm test`
Expected: `ℹ fail 0`.

- [ ] **Step 6: Load it**

In `LocalDev/greekos/src/hooks/useAppData.ts`:

Add imports: `import { MemberBalance, adaptMemberBalance } from '../lib/balance';`

Add state next to the session state (after `const [sessionName, ...]`):

```ts
  const [myBalance, setMyBalance] = useState<MemberBalance | null>(null);
```

In the second `Promise.all` of the load (the one starting `const [eventRows, excuseRows, ...`), add a ninth call at the end of the array:

```ts
            api.getMemberTreasuryDashboard(me.id).then(adaptMemberBalance).catch(err => {
              console.error('Member balance load failed', err);
              return null;
            })
```

and a ninth destructured name `myBalanceRow` at the end of the tuple. After `setSessionName(me.name);` add:

```ts
        setMyBalance(myBalanceRow);
```

Add `myBalance,` to the returned object.

- [ ] **Step 7: Lint and test**

Run: `npm run lint && npm test`
Expected: lint clean; `ℹ fail 0`.

- [ ] **Step 8: Smoke in the browser**

Start the backend and greekos (see README). Open the app, open devtools Network: confirm `/api/rbac/me/permissions` and `/api/treasury/members/<id>/dashboard` both return 200, and that upcoming events each trigger `/api/events/<id>` and `/api/events/<id>/checkin-link`. The sidebar still shows Recruitment and Command console for Jake.

- [ ] **Step 9: Commit**

```bash
git add LocalDev/greekos/src/lib/balance.ts LocalDev/greekos/src/lib/balance.test.ts LocalDev/greekos/src/api.ts LocalDev/greekos/src/hooks/useAppData.ts
git commit -m "feat(greekos): load the member's real balance owed"
```

---

## Done when

- `npm test` passes with tests for session, contribution, balance, formatMoney.
- `npm run lint` clean.
- `useAppData()` exposes `permissions`, `sessionIsOfficer`, `sessionName`, `contribution`, `myBalance`.
- Nav hides Recruitment / Command console for a session without those permission keys.
- Four commits on `feat/greekos-hci`.
