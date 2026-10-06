# Plan 08 — Balance & standing readers Implementation Plan (wave 2)

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first. You branch from a `main` that already contains wave 1.

**Goal:** every exported or displayed balance/attendance number is live and internally consistent.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §08 (all) — §08-1 is the same root cause as §09's "CSV still reads cached figures", fixed once here.
**Migrations:** none.

**Allowed files:** `api/treasury/services/reports.py`, `api/memberadmin/services/member_detail.py`, `api/tasks/services/commitments.py`, `tests/treasury/*`, `tests/memberadmin/*`, `tests/tasks/*` (new files ok).

## Task 1 — RV-08-1 (P2, also §09): the member-balances CSV mixes live and cached numbers

`api/treasury/services/reports.py:361-376`: only `outstanding` is computed live; `owed`, `paid`, `current` and `recomputed_at` come from the balance cache. Since fine issuance stopped refreshing the cache, rows contradict themselves (`owed - paid != outstanding`), and members with no cache row export blanks.

- [ ] Failing test first, `tests/treasury/test_balances_csv_live.py` (own chapter): member with an invoice + partial payment but **no/stale cache row** (issue a fine after the last recompute, or delete the cache row) → assert today the CSV row is internally inconsistent or blank; after the fix `owed`, `paid`, `current`, `outstanding` are all live and `owed - paid` relates to `outstanding` per the column definitions, with no blank rows for cache-less members.
- [ ] Fix: compute **all** money columns in the same live query that already produces `outstanding` (one set-based query — no per-member N+1; reuse `tr_invoice_remaining_cents`-style sums). Drop or honestly label `recomputed_at` (if the column survives, it must describe the live computation time, not a stale cache stamp).
- [ ] Checkpoint: `python3 -m pytest tests/treasury/test_balances_csv_live.py -q`, then any existing reports tests.

## Task 2 — RV-08-2 (P2): future required events are marked "absent"

`api/memberadmin/services/member_detail.py:28-35, 87-91`: the per-member event breakdown counts required events that haven't happened yet as absences (sibling of F-002).

- [ ] Failing test first, `tests/memberadmin/test_member_detail_future_events.py` (own chapter): required event dated tomorrow; assert the member's breakdown today shows it absent (reproduces), after the fix shows it as upcoming/not counted.
- [ ] Fix: restrict the absent computation to past events (same past-event predicate the rest of the detail uses).
- [ ] Checkpoint: `python3 -m pytest tests/memberadmin/ -q`.

## Task 3 — RV-08-3 (P3): `_past_event_ids` uses the server's date, not the chapter's

`api/tasks/services/commitments.py:115` uses `date.today()` — wrong around midnight for chapters not in the server's zone. Hard rule: event times are local to `chapters.timezone`.

- [ ] Failing test first: freeze/fake "now" such that the server date and the chapter-tz date differ (e.g. chapter in `Pacific/Auckland`, event earlier today chapter-time but "tomorrow" server-time, or vice versa); assert the event lands on the wrong side today, right side after.
- [ ] Fix: derive "today" from the chapter timezone via the codebase's one canonical timing helper (`api/events/core/timing.py`) — don't hand-roll a second conversion.
- [ ] Checkpoint: `python3 -m pytest tests/tasks/ -q` — paste the final count line.
