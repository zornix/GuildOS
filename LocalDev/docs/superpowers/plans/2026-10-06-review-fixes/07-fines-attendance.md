# Plan 07 — Fines & attendance Implementation Plan (wave 2)

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first. You branch from a `main` that already contains wave 1 (plans 01–06).

**Goal:** no fine can land on someone excused/present (D20), self check-in voids open fines, check-in sessions fail loudly and honestly, and cancelled events stop accepting attendance writes.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §09, §10, §11 (the attendance half of the cancelled-event P3).
**Migrations:** 0213–0214. The "event lock" is `pg_advisory_xact_lock(hashtext('ev_attendance:' || event_id::text))` — one key for everything attendance-vs-fines on an event.

**Allowed files:** `migrations/0213_*.sql`, `migrations/0214_*.sql`, `api/attendance/services/checkin_links.py`, `api/attendance/services/sessions.py`, `api/attendance/services/excuses.py`, `api/events/services/events.py` (only the 550-575 bulk-read gate), `api/treasury/api/fines_legacy.py`, `tests/attendance/*`, `tests/treasury/test_v1_fines.py`. DB functions you own: `tr_issue_event_fines` (live: 0201), `at_set_attendance` + `at_review_excuse` (live: 0198), `at_checkin_self` (live: 0178).

## Task 1 — RV-09-1 (P2): a fine can land on someone excused or marked present (D20 race)

`tr_issue_event_fines` (0201) trusts an absence list built in Python (`api/treasury/api/fines_legacy.py:191-205`), and `at_set_attendance` / `at_review_excuse` (0198) take no event lock — so an excuse approved at the same moment as fine issuance still gets fined.

- [ ] Failing test first, `tests/attendance/test_fine_attendance_race.py` (own chapter): simulate the race deterministically — mark the member present (or approve their excuse) **after** the Python absence list would have been built but **before** the RPC runs, by calling the RPC directly with a stale absence list containing that member. Assert today a fine is created; after the fix the RPC skips them.
- [ ] `migrations/0213_fine_attendance_interlock.sql`: `CREATE OR REPLACE` all three (live bodies as base): `tr_issue_event_fines` takes the event lock, then **re-checks attendance and approved excuses inside the RPC** and skips handled members (keep 0201's existing skip semantics); `at_set_attendance` and `at_review_excuse` take the same event lock first.
- [ ] Apply, `python3 scripts/migration_checksums.py --update`, test → PASS. Checkpoint: `python3 -m pytest tests/attendance/ -q`.

## Task 2 — RV-09-2 / RV-10-1 (P2, reported by two reviewers): self check-in doesn't void an open fine

`at_checkin_self` (0178:24-33) never calls `at_void_open_fines` (0198) — a fine issued 24h after start followed by a door-code check-in leaves the member present but still owing.

- [ ] Failing test first, `tests/attendance/test_self_checkin_voids_fine.py`: issue an event fine, then self check-in via the door-code path; assert the fine is voided (status per 0198's convention) — fails untouched.
- [ ] `migrations/0214_self_checkin_voids_fines.sql`: `CREATE OR REPLACE FUNCTION at_checkin_self` (0178 live body) calling `at_void_open_fines` the same way `at_set_attendance` does.
- [ ] Apply, update checksums, test → PASS.

## Task 3 — RV-10-2 (P2): a database fault during link check-in leaves no trace

`api/attendance/services/checkin_links.py:213`: `logger.exception` became `logger.error` — no traceback.

- [ ] One-line fix back to `logger.exception`. Trivial; add a caplog assertion only if the file already has logging tests, otherwise state `FIXED — one-liner, no test` in the report.

## Task 4 — RV-10-3 (P3): two officers opening a check-in session at once → raw 500

`api/attendance/services/sessions.py:40`: the unique violation surfaces as 500.

- [ ] Failing test first: open a session, then open again for the same event → expect 409 with fixed text. Fix by catching the conflict **outside** any transaction block (or pre-checking then relying on the constraint) and mapping to the domain's named-exception pattern.

## Task 5 — RV-10-4 (P3): closed sessions' codes still show as live

The F-003 "same session gate on active-link reads" was left out of scope. Gate all three readers on an **open** session: `get_active_link_for_event`, the bulk read in `api/events/services/events.py:550-575`, `list_active_links_for_chapter`.

- [ ] Failing test first: close a session; assert all three readers stop returning its code. Fix each reader with the same open-session predicate (one shared helper in the attendance service, imported by events.py only if it's already a public cross-domain surface — otherwise duplicate the predicate in SQL and note it).

## Task 6 — RV-10-5 (P3): a rotated link escapes the old session's close time

`checkin_links.py:126-131, 160`: a link rotated while a session bound to the old link is open isn't governed by that session's close time.

- [ ] Failing test first: open a session, rotate the link, assert the new link's validity is still bounded by the open session's close time (today it isn't). Fix in the rotation path.

## Task 7 — RV-11-4b (P3): a cancelled event still accepts sessions and excuses

`api/attendance/services/sessions.py:25-33`, `api/attendance/services/excuses.py:22-28` (the links half was done in plan 04).

- [ ] Failing tests first: cancel an event → opening a session and filing an excuse both refuse (409/422, named-exception pattern, mirroring plan 04's link guard on `events.py:261-268`).

## Task 8 — RV-09-4 (P3): the fines atomicity test proves nothing about the route

`tests/treasury/test_v1_fines.py:296-306` calls the RPC directly.

- [ ] Rework it to go through the HTTP route with a dependency-override client, keeping the same atomicity assertion (report under EXISTING TESTS CHANGED).

## Final checkpoint

- [ ] `python3 -m pytest tests/attendance/ tests/treasury/test_v1_fines.py -q` — paste the final count line.
