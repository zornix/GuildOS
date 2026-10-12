# M3 — Calendar-first events, event detail, attendance shortcut

> Read `00-README.md` first. Test first. Stay in your lane.

**Goal:** `/calendar` is a month/week calendar on desktop and an agenda feed on phones, both from `GET /api/calendar/`; `/calendar/:eventId` is a detail sheet/panel with all existing event data and officer actions; "Take attendance" deep-links into a roll call prefilled from the existing roster endpoint. No RSVP (D6).
**Spec:** `../01-phase-b-design.md` §4; `../audit/events-attendance.md` §3, §5, "Gaps"; `../audit/frontend-modules.md` §1–§2.
**Migrations:** none.
**Allowed files:** backend `api/calendar/**`, `api/events/api/events.py` + `api/events/services/events.py` (response fields only), `api/attendance/api/attendance.py` (roster visibility), `api/tasks/services/tasks.py` + `api/tasks/api/tasks.py` (**list filter param only**), tests under `tests/calendar_view/`, `tests/events/`, `tests/attendance/`, `tests/tasks/test_list_filter.py`; frontend `components/calendar/**`, `components/events/**`, `components/attendance/**`, `components/CalendarModule.tsx`, `components/EventsModule.tsx`, `components/EventsBar.tsx`, `components/AttendanceModule.tsx` (all three may be deleted once replaced), `lib/calendar.ts`, `lib/events.ts`, `lib/rollCall.ts`, `hooks/useEvents.ts`, `hooks/useEventsChrome.ts`, `hooks/useAttendance.ts`, `hooks/useCalendar.ts`, `api.ts`/`types.ts` (M3 block), `routes.tsx` (`/calendar`, `/calendar/:eventId`, `/cabin/attendance/:eventId?`, `/me/attendance` lines).

## T1 — Backend: calendar range correctness and detail fields

- [ ] Failing tests `tests/calendar_view/test_range_spanning.py`: an event with `date` before `start` and `end_date` inside the window is returned; default range is computed in the chapter timezone (freeze a clock near midnight UTC); items carry `location` and `event_type_id`; cancelled and security `task_due` items are excluded.
- [ ] `api/calendar/services/calendar.py`: include rows where `end_date >= start` (events and initiatives); default range from `chapters.timezone`; add `location`, `event_type_id`, `visibility` to event items; filter `task_due` to `kind='standard'` and status not cancelled. Response keys stay additive.
- [ ] Failing test `tests/events/test_detail_names.py`: `GET /api/events/{id}` organizers carry `name`.
- [ ] `services/events.py:get_event`: join organizer names (one query). Additive.
- [ ] Failing test `tests/tasks/test_list_filter.py`: `GET /api/tasks/?event_id=` returns only that event's jobs; `?initiative_id=` likewise; an `event_id` the caller cannot see → `[]` (reuse `_can_view` from events via the public service function, not a private import).
- [ ] Failing test `tests/attendance/test_roster_visibility.py`: `GET /api/attendance/event/{id}` → 404 for an officer-only event when the caller cannot see it; 409 for a cancelled event; roster lists audience members only for a `custom` event.
- [ ] Implement in `api/attendance/api/attendance.py:49-103` using the events service's visibility helper and `event_audience_members`.
- [ ] Checkpoint: `python3 -m pytest tests/calendar_view tests/events tests/attendance tests/tasks/test_list_filter.py -q`.

## T2 — Calendar page

- [ ] `hooks/useCalendar.ts`: fetches `/api/calendar/?start&end` for the visible range (month ± 1 week on desktop; rolling 8 weeks on mobile, extended on scroll), plus `/api/events/types` once. `lib/calendar.ts`: `monthGrid(anchor, tz)`, `weekGrid`, `groupByDay(items)`, `typeColor(typeId, types)` (deterministic from catalog order), `badges(item)` → `['Needed', 'Incomplete', 'N open jobs']`. Tests with fixed dates in two timezones.
- [ ] `components/calendar/CalendarPage.tsx`: ≥ `lg`: toolbar (prev/today/next, Month|Week toggle, type chips from the catalog), grid left, agenda rail right (selected day or next 14 d). < `lg`: compact week strip + agenda feed grouped by day; type chips scroll horizontally. Clicking/tapping an item navigates to `/calendar/:eventId` (initiatives → `/initiatives/:id`; announcements → agenda-only detail, no route).
- [ ] Empty/loading/error states: skeleton rows while loading; "Nothing on the calendar this month" per range; error banner with retry.
- [ ] Delete `CalendarModule.tsx`, `EventsBar.tsx` and the list half of `EventsModule.tsx` once `CalendarPage` + `EventDetail` cover them; `useEventsChrome` state moves into the URL (`?view=week&type=…`).
- [ ] Tests: `components/calendar-page.test.ts` renders chips from a types fixture, renders an item in the right day cell, shows "Needed" for `organizers_needed`.
- [ ] Checkpoint: `npm test && npm run lint`.

## T3 — Event detail (`/calendar/:eventId`)

- [ ] `components/events/EventDetail.tsx` rendered inside `ui/Sheet` (bottom < `lg`, right ≥ `lg`) over the calendar. Loads `GET /api/events/{id}`, `/{id}/security`, `/{id}/checkin-link`, `GET /api/tasks/?event_id=`. Sections: header (type, title, required badge, audience), when/where in chapter tz (`lib/time.ts`), description, supervisors + organizers (names), **`<JobsSection />` slot** rendering today's job cards (M4 replaces with `JobCard`), security shifts (existing UI moved), door code (existing modal).
- [ ] Member actions: Volunteer as organizer (existing), Request excuse (required events only; existing excuse modal moved here), claim/report (existing).
- [ ] Officer actions by `can()`: **Edit** (new `EventForm` reused for create and edit, wired to the existing `PUT`), Cancel/Delete (existing, using `ui/ConfirmDialog`), Notify (existing two-phase), Door code (existing), **Take attendance** → `navigate('/cabin/attendance/' + id)` shown with `attendance:override`. Add supervisor (wire the existing `POST /{id}/supervisors`; eligible list = roster filtered by the roles the backend accepts — show the backend error if refused).
- [ ] "Me" checks use `useMe().memberId` (supervisor approve, organizer membership); delete every `name ===` comparison in this lane.
- [ ] Remove prototype residue in this lane: `'Alexander Mercer'`, default fake job on create, QR "demo art" (render the short code large instead; a QR library is not worth it), `notifiedAt.substring(5,16)`.
- [ ] Tests: `components/event-detail.test.ts` — Take attendance present iff `attendance:override`; Edit iff `calendar:event:update`; times formatted with the passed timezone.
- [ ] Checkpoint: `npm test && npm run lint`.

## T4 — Attendance: roll call prefilled, member view

- [ ] `components/attendance/RollCall.tsx` at `/cabin/attendance/:eventId?`: event picker (upcoming first, from the calendar range; preselected from the route), loads `GET /api/attendance/event/{id}` and prefills marks (`checked_in` → Present, `excuse_status='approved'` → Excused); saving posts only **changed** rows (`lib/rollCall.ts` diff, tested); "Late" removed (the API has no late state; audit §2). Door code tab and Excuses review tab move here from `AttendanceModule`.
- [ ] `components/attendance/MyAttendance.tsx` at `/me/attendance`: `GET /api/attendance/summary?member_id=me`, my excuses list with status, "Request excuse" for required events I missed or will miss. Members see no roster.
- [ ] Delete `AttendanceModule.tsx` when both replace it.
- [ ] Tests: `lib/rollCall.test.ts` diff cases; `roll-call.test.ts` prefill from a roster fixture.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Responsive behaviour

- Phone: agenda feed, bottom-sheet detail, roll call as a full-height list with 44px radios.
- Desktop: month grid 7 columns, rail 320px; week view shows hours only as labels (no drag/drop).

## Definition of done

M3 acceptance row; `grep -rn "currentMemberName" greekos/src/components/events greekos/src/components/attendance greekos/src/components/calendar` returns nothing; no event time passes through `new Date(\`${date}T${time}\`)` without a timezone.

## Risks

- `/api/calendar/` items identify themselves with different keys (`id` vs `initiative_id`); normalise in `lib/calendar.ts`, do not change the backend shape.
- Week view is optional polish; if time is short, ship Month + agenda and report `PARTIAL` on week.
