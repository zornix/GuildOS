# Plan 02 — Events chrome: calendar first, one shared filter bar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first. Plan 01 must be merged into `feat/greekos-hci` before starting.

**Goal:** Opening Events shows the calendar. One horizontal bar holds the type filter, the list/calendar toggle, and the officer Create button. The filter applies to both views. Home (plan 03) can open the create form and jump to an event.

**Architecture:** A pure `src/lib/events.ts` owns the filter list and filtering. A `useEventsChrome` hook owns the four pieces of chrome state (view, filter, createOpen, selectedEventId) so `App.tsx` stays thin. A small `EventsBar` component renders the bar. `EventsModule` and `CalendarModule` become controlled for those four values; the old filter card and orphan toggle are deleted.

**Tech Stack:** React 19, TypeScript, `node:test`.

**Spec:** `LocalDev/docs/greekos-hci-handoff.md` § "2. Events chrome"; README decisions D6 (needs `liveDoorEvent`).

## Global Constraints

- No new deps. Keep the notify gate, 36-hour lock, door-code `maxLength={6}`, reject-needs-reason, Mandatory / organizers-needed / open-jobs badges.
- Calendar day click still opens the list/detail for that event.
- Do not touch `EventsModule` detail canvas beyond what a task names.

---

### Task 1: Filter and live-door helpers

**Files:**
- Create: `LocalDev/greekos/src/lib/events.ts`
- Create: `LocalDev/greekos/src/lib/events.test.ts`

**Interfaces:**
- Produces: `EVENT_FILTER_TYPES`, `filterEventsByType(events, type)`, `liveDoorEvent(events, today)`.

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/events.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EVENT_FILTER_TYPES, filterEventsByType, liveDoorEvent } from './events';
import type { ChapterEvent } from '../types';

const ev = (over: Partial<ChapterEvent>): ChapterEvent => ({
  id: 'e', title: 't', date: '2026-09-10', startTime: '18:00', endTime: '20:00', time: '',
  location: '', type: 'Chapter Meeting', audience: 'All Members', required: false,
  attendanceTaken: false, supervisors: [], organizers: [], jobs: [], ...over
});

test('filter list starts with All and matches the chips in the old filter card', () => {
  assert.deepEqual([...EVENT_FILTER_TYPES], ['All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education']);
});

test('All keeps every event; a type keeps only that type', () => {
  const list = [ev({ id: 'a', type: 'Social' }), ev({ id: 'b', type: 'Philanthropy' })];
  assert.deepEqual(filterEventsByType(list, 'All').map(e => e.id), ['a', 'b']);
  assert.deepEqual(filterEventsByType(list, 'Social').map(e => e.id), ['a']);
  assert.deepEqual(filterEventsByType(list, 'Brotherhood'), []);
});

test('liveDoorEvent is the earliest upcoming event with an open door link', () => {
  const list = [
    ev({ id: 'past', date: '2026-09-01', checkInLinkActive: true }),
    ev({ id: 'later', date: '2026-09-12', checkInLinkActive: true }),
    ev({ id: 'soon', date: '2026-09-08', checkInLinkActive: true }),
    ev({ id: 'closed', date: '2026-09-07', checkInLinkActive: false })
  ];
  assert.equal(liveDoorEvent(list, '2026-09-07')?.id, 'soon');
  assert.equal(liveDoorEvent([ev({ checkInLinkActive: false })], '2026-09-07'), undefined);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd LocalDev/greekos && npm test`
Expected: FAIL — `Cannot find module './events'`.

- [ ] **Step 3: Implement**

Create `LocalDev/greekos/src/lib/events.ts`:

```ts
import type { ChapterEvent } from '../types';

/** Chips on the Events bar. 'All' first; the rest are the types officers
 *  actually schedule (Recruitment and Community Service exist but are rare). */
export const EVENT_FILTER_TYPES = [
  'All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education'
] as const;

export function filterEventsByType(events: ChapterEvent[], type: string): ChapterEvent[] {
  return type === 'All' ? events : events.filter(e => e.type === type);
}

/** The event a member can check into right now: earliest upcoming event whose
 *  door link is open. `today` is YYYY-MM-DD. */
export function liveDoorEvent(events: ChapterEvent[], today: string): ChapterEvent | undefined {
  return events
    .filter(e => e.checkInLinkActive && e.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date) || a.startTime.localeCompare(b.startTime))[0];
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test`
Expected: `ℹ fail 0`.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/lib/events.ts LocalDev/greekos/src/lib/events.test.ts
git commit -m "feat(greekos): event filter and live-door helpers"
```

---

### Task 2: Chrome state hook and the bar

**Files:**
- Create: `LocalDev/greekos/src/hooks/useEventsChrome.ts`
- Create: `LocalDev/greekos/src/components/EventsBar.tsx`

**Interfaces:**
- Produces: `useEventsChrome()` returning `{ view, setView, filterType, setFilterType, createOpen, setCreateOpen, selectedEventId, setSelectedEventId, openCreate(), openEvent(id) }`.
- `EventsBar` props: `{ view, onViewChange, filterType, onFilterChange, isOfficer, onCreate }`.

- [ ] **Step 1: The hook**

Create `LocalDev/greekos/src/hooks/useEventsChrome.ts`:

```ts
import { useState } from 'react';

export type EventsView = 'calendar' | 'list';

/** The Events screen's chrome: which view, which type filter, whether the
 *  create form is open, and which event is selected. Lives above the screen
 *  so Home can open the form or jump to an event. */
export function useEventsChrome() {
  const [view, setView] = useState<EventsView>('calendar');
  const [filterType, setFilterType] = useState<string>('All');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  /** The create form lives in the list view. */
  const openCreate = () => {
    setView('list');
    setCreateOpen(true);
  };

  /** Calendar day click and Home tiles land on the event's detail. */
  const openEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    setView('list');
  };

  return {
    view, setView, filterType, setFilterType, createOpen, setCreateOpen,
    selectedEventId, setSelectedEventId, openCreate, openEvent
  };
}
```

- [ ] **Step 2: The bar**

Create `LocalDev/greekos/src/components/EventsBar.tsx`:

```tsx
import { Plus } from 'lucide-react';
import { EVENT_FILTER_TYPES } from '../lib/events';
import type { EventsView } from '../hooks/useEventsChrome';

interface EventsBarProps {
  view: EventsView;
  onViewChange: (view: EventsView) => void;
  filterType: string;
  onFilterChange: (type: string) => void;
  isOfficer: boolean;
  onCreate: () => void;
}

/** One horizontal bar: type chips, list/calendar toggle, officer Create. */
export default function EventsBar({ view, onViewChange, filterType, onFilterChange, isOfficer, onCreate }: EventsBarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
      <div role="group" aria-label="Filter events by type" className="flex flex-wrap gap-1.5 flex-1">
        {EVENT_FILTER_TYPES.map(t => (
          <button
            key={t}
            type="button"
            aria-pressed={filterType === t}
            onClick={() => onFilterChange(t)}
            className={`text-xs px-2.5 py-1.5 min-h-9 rounded-md font-semibold transition-all cursor-pointer ${
              filterType === t ? 'bg-navy text-gold shadow-xs' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div role="group" aria-label="Events view" className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg w-fit">
        {(['calendar', 'list'] as const).map(v => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => onViewChange(v)}
            className={`px-3 py-2 min-h-9 rounded-md text-xs font-medium capitalize transition-all cursor-pointer ${
              view === v ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {isOfficer && (
        <button
          type="button"
          onClick={onCreate}
          className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Create event
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Lint**

Run: `npm run lint`
Expected: clean (both files are unused so far; tsc does not complain about unused modules).

- [ ] **Step 4: Commit**

```bash
git add LocalDev/greekos/src/hooks/useEventsChrome.ts LocalDev/greekos/src/components/EventsBar.tsx
git commit -m "feat(greekos): events chrome state hook and bar"
```

---

### Task 3: Make EventsModule controlled

**Files:**
- Modify: `LocalDev/greekos/src/components/EventsModule.tsx` (props 25–49; state 75–77; header 246–254; filter card 262–283; list `onClick` ~297; create modal close handlers ~913–922; `handleCreateEvent` close call)

**Interfaces:**
- `EventsModuleProps` gains: `filterType: string; createOpen: boolean; onCreateOpenChange: (open: boolean) => void; selectedEventId: string | null; onSelectEventId: (id: string) => void;`
- Removes internal `filterType`, `showAddForm`, `selectedEventId` state and the header Create button.

- [ ] **Step 1: Props**

Add to `EventsModuleProps` after `currentMemberName: string;`:

```ts
  /** Chrome owned by useEventsChrome — the bar above this module sets them. */
  filterType: string;
  createOpen: boolean;
  onCreateOpenChange: (open: boolean) => void;
  selectedEventId: string | null;
  onSelectEventId: (eventId: string) => void;
```

Destructure all five in the component signature.

Add the import: `import { filterEventsByType } from '../lib/events';`

- [ ] **Step 2: Remove the internal state**

Delete lines 75–77:

```ts
  const [selectedEventId, setSelectedEventId] = useState<string>(events[0]?.id || '');
  const [filterType, setFilterType] = useState<string>('All');
  const [showAddForm, setShowAddForm] = useState(false);
```

Then, everywhere in the file:
- `setSelectedEventId(` → `onSelectEventId(`
- `setShowAddForm(true)` → `onCreateOpenChange(true)`
- `setShowAddForm(false)` → `onCreateOpenChange(false)`
- `showAddForm &&` → `createOpen &&`

Use `grep -n "setShowAddForm\|showAddForm\|setSelectedEventId\|setFilterType" src/components/EventsModule.tsx` afterwards; expected: no matches.

- [ ] **Step 3: Use the shared filter**

Replace:

```ts
  const filteredEvents = safeEvents.filter(e => filterType === 'All' || e.type === filterType);
```

with:

```ts
  const filteredEvents = filterEventsByType(safeEvents, filterType);
```

- [ ] **Step 4: Delete the header Create button and the filter card**

Delete the `{isOfficer && ( <button onClick={() => onCreateOpenChange(true)} …> Create Chapter Event </button> )}` block in the header (lines 246–254 before edits). The header keeps the title and subtitle.

Delete the whole `{/* Category Filter */} <div className="bg-white rounded-xl …"> … </div>` block (lines 262–283 before edits).

- [ ] **Step 5: Lint**

Run: `npm run lint`
Expected: errors only in `App.tsx` (missing new props). Fix in the next task.

- [ ] **Step 6: Commit (with App.tsx temporarily broken is not allowed — do Task 4 first, then commit both together)**

Skip the commit; continue to Task 4.

---

### Task 4: Calendar opens an event; App wires the chrome

**Files:**
- Modify: `LocalDev/greekos/src/components/CalendarModule.tsx` (props 15–29; day-panel event card ~238–250)
- Modify: `LocalDev/greekos/src/App.tsx`

**Interfaces:**
- `CalendarModuleProps` gains `onOpenEvent: (eventId: string) => void`.
- `App.tsx` uses `useEventsChrome()`; exposes nothing new to modules beyond the props above.

- [ ] **Step 1: Calendar prop and button**

In `CalendarModule.tsx`, add to the props interface and destructure:

```ts
  /** Jump to the list/detail view for one event. */
  onOpenEvent: (eventId: string) => void;
```

In the day panel, inside `dayEvents.map(e => …)`, the header row is:

```tsx
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-1.5">
                            <h4 className="font-bold text-xs text-slate-900">{e.title}</h4>
```

Add, as the second child of that `flex items-start justify-between` div (after the inner `<div>…</div>` that holds the title and type):

```tsx
                        <button
                          type="button"
                          onClick={() => onOpenEvent(e.id)}
                          className="text-xs font-semibold text-navy hover:text-gold-muted cursor-pointer shrink-0"
                        >
                          Open &rarr;
                        </button>
```

- [ ] **Step 2: Rewrite the Events section of App.tsx**

Replace line 20:

```ts
  const [eventsView, setEventsView] = useState<'list' | 'calendar'>('list');
```

with:

```ts
  const chrome = useEventsChrome();
```

and add imports:

```ts
import { useEventsChrome } from './hooks/useEventsChrome';
import EventsBar from './components/EventsBar';
import { filterEventsByType } from './lib/events';
```

Delete the orphan toggle block (lines 56–70, `{activeTab === 'events' && ( <div className="flex items-center gap-1 …"> … </div> )}`).

Replace the two blocks `{activeTab === 'events' && eventsView === 'calendar' && (…)}` and `{activeTab === 'events' && eventsView === 'list' && (…)}` with:

```tsx
      {activeTab === 'events' && (
        <>
          <EventsBar
            view={chrome.view}
            onViewChange={chrome.setView}
            filterType={chrome.filterType}
            onFilterChange={chrome.setFilterType}
            isOfficer={isOfficer}
            onCreate={chrome.openCreate}
          />

          {chrome.view === 'calendar' && (
            <CalendarModule
              events={filterEventsByType(events.events, chrome.filterType)}
              initiatives={initiatives.initiatives}
              announcements={app.announcements}
              currentMemberName={currentMemberName}
              onVolunteerOrganizer={events.handleVolunteerOrganizer}
              onOpenEvent={chrome.openEvent}
            />
          )}

          {chrome.view === 'list' && (
            <EventsModule
              events={events.events}
              members={roster.members}
              isOfficer={isOfficer}
              currentMemberName={currentMemberName}
              filterType={chrome.filterType}
              createOpen={chrome.createOpen}
              onCreateOpenChange={chrome.setCreateOpen}
              selectedEventId={chrome.selectedEventId}
              onSelectEventId={chrome.setSelectedEventId}
              onSelectEvent={events.handleSelectEvent}
              onAddEvent={events.handleAddEvent}
              onUpdateEvent={events.handleUpdateEvent}
              onVolunteerOrganizer={events.handleVolunteerOrganizer}
              onClaimJob={events.handleClaimJob}
              onUnclaimJob={events.handleUnclaimJob}
              onReportJobDone={events.handleReportJobDone}
              onApproveJob={events.handleApproveJob}
              onRejectJob={events.handleRejectJob}
              onAddJobToEvent={events.handleAddJobToEvent}
              onEditJob={events.handleEditJob}
              onDeleteJob={events.handleDeleteJob}
              onSendEventNotifyBlast={events.handleSendEventNotifyBlast}
              onToggleCheckInLink={events.handleToggleCheckInLink}
              onAssignSecurity={events.handleAssignSecurity}
              onRequestSecuritySwap={events.handleRequestSecuritySwap}
              onRespondSecuritySwap={events.handleRespondSecuritySwap}
              onCancelSecuritySwap={events.handleCancelSecuritySwap}
            />
          )}
        </>
      )}
```

The `useState` import in `App.tsx` is still needed for `activeTab`.

- [ ] **Step 3: Lint and test**

Run: `npm run lint && npm test`
Expected: clean; `ℹ fail 0`.

- [ ] **Step 4: Browser check**

Start backend + greekos. Click Events: the calendar shows first, with the bar above it. Click "Social": both the calendar cells and (after switching to List) the list show only Social events. Click a day with an event, press "Open →": the list view opens with that event selected. As Jake, "Create event" from the calendar view switches to list and opens the form; creating still works.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/components/EventsModule.tsx LocalDev/greekos/src/components/CalendarModule.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): calendar-first events with one shared filter bar"
```

---

## Done when

- Events opens on the calendar; the bar is the only place with type chips, the view toggle, and Create.
- Changing a chip filters both views. Calendar "Open →" lands on the event's detail. Create works from either view.
- `npm test` includes `events.test.ts`; lint clean; three commits.
