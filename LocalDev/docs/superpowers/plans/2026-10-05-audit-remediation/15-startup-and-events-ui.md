# 15 · App startup: one request for upcoming events, not three per event

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `15-startup-and-events-ui` · **Wave:** 3 (needs 06, 10 and 11 merged) · **Agent:** Claude Fable 5.1 (worktree agent) · **Branch:** `fix/audit-15-startup`
**Findings:** F-044, plus three small UI follow-ups from earlier waves (event delete result, waived fines, role panel)
**Goal:** opening the app costs a fixed number of requests no matter how many events are upcoming.
**Architecture:** today startup makes 15 requests plus 3 per upcoming event (security roster, event detail, check-in link). One new read-only route returns those three things for every upcoming event in a handful of queries; the SPA calls it once. No bootstrap mega-endpoint: the other 15 requests stay, each owned by its domain hook.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` card F-044; decisions D4, D6 in `00-README.md`.

## Global constraints

- Allowed files: `api/events/api/events.py`, `api/events/services/events.py`, `api/events/api/schemas.py`, `tests/events/test_upcoming_details.py` (new), everything under `greekos/src/`.
- No migration, no new npm dependency. Existing routes keep their paths and shapes.
- `api/events/api/router.py` is append-only and order matters: a fixed path segment must be registered before `/{event_id}` routes. Register the new route accordingly and prove it with a test.
- Frontend rules as in plan 06 (pure logic in `src/lib` with tests; `npm test && npm run lint` before each commit; `npm run build` before the last).
- Backend tests: `python3 -m pytest tests/events -q`.

## Review focus

1. The new route applies exactly the same visibility rule as the event list (a member must not receive an event the list would hide; cancelled events never appear).
2. A member without `attendance:checkin_link:manage` gets `{active, expires_at}` for a live code, never the code (same rule as stream 10's single-event route).
3. Query count is constant in the number of events (no per-event query inside a loop). Assert it in a test.
4. If the bulk call fails, the app still renders the event list from `GET /api/events` and says details are unavailable; it does not fall back to 3N calls.
5. Zero upcoming events → one request, empty result.

---

### Task 1: `GET /api/events/upcoming-details`

**Files:** `api/events/api/events.py`, `api/events/services/events.py`, `tests/events/test_upcoming_details.py`

**Interfaces (produced):**

```
GET /api/events/upcoming-details          any authenticated member
200: { "events": [ {
        "event_id": str,
        "detail":   <the same object GET /api/events/{id} returns for this caller>,
        "security": <the same list GET /api/events/{id}/security returns>,
        "checkin_link": {} | {"event_id", "active": true, "expires_at"} | <full link object for managers>
     } ] }
"upcoming" = visible to the caller, not cancelled, and date >= today in the chapter's timezone.
```

- [ ] **Step 1: failing tests.** With two upcoming events and one past event in a chapter (use `tests/events/conftest.py` helpers): the route returns exactly the two; each `detail` equals what `GET /api/events/{id}` returns for the same caller; each `security` equals the single-event security route; a plain member's `checkin_link` has no `short_code`. `test_route_is_not_swallowed_by_event_id`: the path does not 404/422 as an event id. `test_query_count_is_constant`: wrap `sb_client.table` and `.rpc` with a counter (as plan 02's `_Counting` helper does), call the service with 2 events and with 6 events, assert the same count.
- [ ] **Step 2: run, expect FAIL (404).**
- [ ] **Step 3: implement.** In the service, reuse the existing bulk decoration the list already uses (report §9: "events list uses bulk decoration", `api/events/services/events.py:224-377`) to load organizers, supervisors and audience for all upcoming ids in one query each (`.in_("event_id", ids)`); load security assignments and active check-in links the same way; assemble per event with the same presenter functions the single-event routes use so shapes cannot drift. Use `chapter_timezone` / `has_started` from `api/events/core/timing.py` for "today". Apply the check-in code gate with one `has_permission` call for the request.
- [ ] **Step 4: run `tests/events -q`, expect PASS; commit** — `feat(events): one bulk read for upcoming event details`

### Task 2: the SPA calls it once

**Files:** `greekos/src/api.ts`, `greekos/src/hooks/useAppData.ts:126-193`, `greekos/src/adapters.ts` + test

- [ ] **Step 1: failing adapter test:** a pure `adaptUpcomingDetails(dto, rosterRows, membersById)` returns the same `securityByEvent` and `detailByEvent` maps the current per-event loop builds (build the expectation from the existing `adaptSecurityAssignment` / `adaptEventDetail` on a fixture), including an event whose `checkin_link` is `{}` and one whose link has no code.
- [ ] **Step 2:** `api.getUpcomingEventDetails()`; in `useAppData`, replace the `Promise.all(adaptedEvents.filter(...).map(async e => { listSecurity, getEvent, getCheckInLink }))` block with one call and the adapter. On failure: log, leave both maps empty, and surface a non-blocking notice through the existing toast (`Event details could not be loaded.`).
- [ ] **Step 3:** `refetchJobsRef` (`useAppData.ts:104-109`) refetches tasks and events on every job change: refetch only tasks, plus the one affected event's detail when the job belongs to an event.
- [ ] **Step 4:** `npm test && npm run lint`; commit — `perf(greekos): load upcoming event details in one request`

### Task 3: small follow-ups from earlier waves

- [ ] **Event delete result (decision D4).** `DELETE /api/events/{id}` now returns `{deleted, cancelled}`. In `useEvents.ts`, remove the event from the list in both cases and toast `Event deleted.` or `Event cancelled. Its attendance and fines were kept.` The confirm dialog text becomes: `Events with attendance, jobs or fines are cancelled, not deleted.`
- [ ] **Waived fines (F-024).** `adaptFines` (`adapters.ts:218-230`) maps `cancelled` to `Paid`. Map it to a distinct `Waived` status (extend the `Fine['status']` union and the badge that renders it), and show remaining cents for `partially_paid` if the DTO carries them. Adapter tests for both.
- [ ] `npm test && npm run lint && npm run build`; commit — `fix(greekos): cancelled events and waived fines read correctly`

### Task 4: browser check

- [ ] Follow README "Browser check". With the network panel open, load the app as an officer in a chapter with at least five upcoming events: count requests during startup and put the number in the report (expected: 16). Delete an empty event and an event with attendance and confirm the two different toasts.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
