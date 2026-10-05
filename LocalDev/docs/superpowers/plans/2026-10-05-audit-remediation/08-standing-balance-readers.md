# 08 · Standing and balance readers: read what is really owed

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `08-standing-balance-readers` · **Wave:** 2 (needs 01 and 03 merged) · **Agent:** GPT-6 Luna medium (Codex CLI) · **Branch:** `fix/audit-08-standing-readers`
**Findings:** F-024, F-015, F-002, F-028, F-056
**Migration:** `0176_chapter_timezone.sql` (0177 spare)
**Goal:** standing counts the cents still owed on a fine, only counts events that have started, and counts fines even with no past event; dashboards, exports and SMS audiences compute balances live instead of trusting a cache.
**Architecture:** three small shared helpers, each with one job, then every reader is pointed at them. (1) `remaining_by_invoice` = cents still owed per invoice, in bulk. (2) `has_started` = has this event begun, in the chapter's timezone. (3) `BalanceEngine.outstanding_by_member` = the existing balance formula for a whole chapter in four queries. No formula changes, no cache writes added to SQL.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-024, F-015, F-002, F-028, F-056. Decisions D5 (chapter timezone) and D14 in `00-README.md`.

## Facts you can rely on

- After stream 03, an invoice's coverage lives only in `payment_allocations`. Net allocated = sum of `amount_cents` where `reverses_allocation_id IS NULL` minus sum where it is not null (see `_net_allocated_cents` in `api/treasury/services/member_dashboard.py`). `verified_payments.invoice_id` is always NULL now; `_direct_paid_cents` returns 0 and can go.
- `events.date` is a `date`, `events.time` is a `time` (may be NULL), both entered in the chapter's local time, with no timezone.
- `derive_standing` (`api/memberadmin/core/standing_rules.py`) and its signature must not change (ADR-0004). Only its inputs get fixed.
- The balance formula in `BalanceEngine._member_figures` (`api/treasury/core/balance.py:75-116`) is correct and frozen: `current = owed − paid + adjustments + refunds`, `outstanding = max(0, current)`.

## Global constraints

- Allowed files:
  - new: `migrations/0176_chapter_timezone.sql`, `api/events/core/timing.py` (create `api/events/core/__init__.py` if missing), `api/treasury/services/remaining.py`, `tests/events/test_timing.py`, `tests/treasury/test_remaining.py`, `tests/treasury/test_outstanding_by_member.py`, `tests/memberadmin/test_standing_inputs.py`
  - modify: `api/memberadmin/core/engagement.py`, `api/memberadmin/api/scores.py`, `api/attendance/services/signals.py`, `api/attendance/api/excuses.py` (only `review_excuse`), `api/treasury/core/balance.py` (add one method; change nothing existing), `api/treasury/services/reports.py`, `api/treasury/services/member_dashboard.py`, `tests/memberadmin/**`, `tests/events/test_attendance_summary.py`
  - shared files, one branch each and nothing else: `api/announcements/services/sms.py` (the `elif audience == "members_with_balance":` branch in `resolve_recipients`, ~lines 127-139) and `api/announcements/services/announcements.py` (the balance audience in `audiences_for_viewer`, ~lines 132-141). Stream 12 edits other parts of `sms.py` in parallel.
- Do not touch `api/treasury/api/fines_legacy.py` (stream 09 fixes `fine_summary` with your helper later).
- Run `python3 -m pytest tests/memberadmin tests/treasury tests/events tests/announcements tests/attendance -q`. Not the full suite.

## Review focus

1. A fine that is `partially_paid` with 1 cent paid still counts as one unpaid fine with `amount − 1` cents.
2. A fully paid or cancelled fine counts as zero, and a `partially_paid` invoice whose remaining is 0 (data drift) counts as zero.
3. An event today at 20:00 local is not "missed" at 09:00 local, and is at 20:01. An event with no time counts from the end of its local day.
4. A chapter with zero required past events still reports its members' unpaid fines.
5. `outstanding_by_member` must equal `BalanceEngine.member_outstanding` for every member, including members with a credit (negative current → outstanding 0) and members with refunds and adjustments.

---

### Task 1: `remaining_by_invoice` (bulk) and F-056

**Files:** `api/treasury/services/remaining.py`, `tests/treasury/test_remaining.py`, `api/treasury/services/member_dashboard.py:27-98`, `api/memberadmin/api/scores.py:65-85`

**Interfaces (produced):**

```python
def remaining_by_invoice(sb, invoices: list[dict]) -> dict[str, int]:
    """invoices: rows with at least id and amount_cents. Returns {invoice_id: cents still owed, never below 0}."""
```

- [ ] **Step 1: failing tests** (`cursor`, `chapter_id`, `member_factory`, `sb_client`): insert three fine invoices of 2500 for one member directly (see `_insert_invoice` in `tests/memberadmin/test_engagement_fines.py`); insert a `verified_payments` row and `payment_allocations` rows so that invoice A has 1 cent allocated, B has 2500 allocated then a 2500 reversal row (`reverses_allocation_id` pointing at the first), C has nothing. Assert `remaining_by_invoice(sb_client, rows) == {A: 2499, B: 2500, C: 2500}`. Second test: empty list → `{}` and no query errors.
- [ ] **Step 2: run, expect FAIL** (module missing).
- [ ] **Step 3: implement**

```python
"""Cents still owed per invoice. The one place this is computed in Python."""
from __future__ import annotations


def remaining_by_invoice(sb, invoices: list[dict]) -> dict[str, int]:
    if not invoices:
        return {}
    ids = [inv["id"] for inv in invoices]
    rows = (
        sb.table("payment_allocations")
        .select("invoice_id, amount_cents, reverses_allocation_id")
        .in_("invoice_id", ids)
        .execute()
    ).data or []
    allocated: dict[str, int] = {}
    for r in rows:
        sign = 1 if r["reverses_allocation_id"] is None else -1
        allocated[r["invoice_id"]] = allocated.get(r["invoice_id"], 0) + sign * int(r["amount_cents"])
    return {
        inv["id"]: max(int(inv["amount_cents"]) - allocated.get(inv["id"], 0), 0)
        for inv in invoices
    }
```

- [ ] **Step 4: use it.** In `member_dashboard.py` replace the per-invoice loop (lines ~82-98) with one `remaining_by_invoice(sb, open_invoices)` call and delete `_net_allocated_cents` and `_direct_paid_cents` if nothing else imports them (`grep -rn "_net_allocated_cents\|_direct_paid_cents" api tests`). `scores.py:send_reminder` imports those two helpers: switch it to `remaining_by_invoice` too, keeping its behaviour (`owed = [c for c in remaining.values() if c > 0]`).
- [ ] **Step 5: run `tests/treasury tests/memberadmin -q`, expect PASS. Checkpoint** — suggested message `refactor(treasury): one bulk remaining-cents helper for invoices`.

---

### Task 2: F-024 and F-015 — standing counts remaining cents, with or without past events

**Files:** `api/memberadmin/core/engagement.py:42-128`, `tests/memberadmin/test_standing_inputs.py`

- [ ] **Step 1: failing tests** (reuse `_make_required_event`, `_insert_invoice`, `_row_for` by importing them from `tests.memberadmin.test_engagement_fines`):

```python
async def test_partially_paid_fine_still_counts(sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    _make_required_event(cursor, chapter_id)
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s, %s, 'fine', 2500, 'partially_paid') RETURNING id""", (chapter_id, member))
    invoice_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """INSERT INTO verified_payments (chapter_id, member_id, amount_cents)
           VALUES (%s, %s, 1) RETURNING id""", (chapter_id, member))
    payment_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """INSERT INTO payment_allocations (chapter_id, verified_payment_id, invoice_id, amount_cents)
           VALUES (%s, %s, %s, 1)""", (chapter_id, payment_id, invoice_id))

    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents) == (1, 2499)


async def test_fines_count_with_no_past_required_event(sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    _insert_invoice(cursor, chapter_id, member, "fine", 2500)
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents, row.total_required) == (1, 2500, 0)


async def test_paid_and_cancelled_fines_do_not_count(sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    for status in ("paid", "cancelled"):
        cursor.execute(
            """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
               VALUES (%s, %s, 'fine', 2500, %s)""", (chapter_id, member, status))
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents) == (0, 0)
```

If the `verified_payments` insert needs more NOT NULL columns, read `migrations/0010_treasury_receivables_tables.sql:57-76` and supply them. These tests monkeypatch nothing; if `load_member_engagement` cannot reach the test DB, follow how the existing tests in `test_engagement_fines.py` make `get_db()` return `sb_client` (the `api` fixture does it) and do the same.

- [ ] **Step 2: run, expect the first two to FAIL.** If the first passes on the untouched branch, report F-024 `NOT_REPRODUCED`.
- [ ] **Step 3: implement.** In `load_member_engagement`:
  - Delete the `if not required_events: return [...]` early return. When there are no required events, skip the attendance and excuses queries (`attendance = excuses = []`, `total_required = 0`) and carry on.
  - Fines query: `.select("id, member_id, amount_cents")`, replace `.eq("status", "unpaid")` with `.in_("status", ["unpaid", "partially_paid"])`, then `remaining = remaining_by_invoice(sb, fines)` and keep only fines with `remaining[f["id"]] > 0`. `unpaid_fines` = how many are left; `unpaid_amount_cents` = sum of their remaining cents.
- [ ] **Step 4: run `tests/memberadmin -q`, expect PASS. Checkpoint** — `fix(standing): count remaining cents on fines, with or without past events`.

---

### Task 3: F-002 — an event counts only after it starts (decision D5)

**Files:** `migrations/0176_chapter_timezone.sql`, `api/events/core/timing.py`, `tests/events/test_timing.py`, `api/memberadmin/core/engagement.py`, `api/attendance/services/signals.py:14-68`, `tests/events/test_attendance_summary.py`, `tests/memberadmin/test_standing_inputs.py`

**Interfaces (produced, reused by stream 09):**

```python
DEFAULT_TZ = "America/Los_Angeles"

def chapter_timezone(sb, chapter_id: str) -> str            # chapters.timezone, DEFAULT_TZ if unset
def event_start_utc(event: dict, tz_name: str) -> datetime   # aware UTC; uses event["date"], event["time"]
def has_started(event: dict, tz_name: str, now: datetime) -> bool
```

- [ ] **Step 1: migration**

```sql
-- D5: event date/time are entered in the chapter's local time. One timezone per chapter.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'America/Los_Angeles';
```

Apply it: `python3 scripts/migrate_db.py`.

- [ ] **Step 2: failing unit tests** `tests/events/test_timing.py` (pure, no DB):

```python
from datetime import date, datetime, time, timezone
from api.events.core.timing import event_start_utc, has_started

LA = "America/Los_Angeles"


def test_start_is_local_time_converted_to_utc():
    ev = {"date": date(2026, 10, 5), "time": time(20, 0)}          # 20:00 PDT = 03:00 UTC next day
    assert event_start_utc(ev, LA) == datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)


def test_strings_are_accepted():
    ev = {"date": "2026-10-05", "time": "20:00:00"}
    assert event_start_utc(ev, LA) == datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)


def test_missing_time_means_end_of_local_day():
    ev = {"date": date(2026, 10, 5), "time": None}
    assert event_start_utc(ev, LA) == datetime(2026, 10, 6, 6, 59, 59, tzinfo=timezone.utc)


def test_has_started():
    ev = {"date": date(2026, 10, 5), "time": time(20, 0)}
    assert not has_started(ev, LA, datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc))   # 09:00 local
    assert has_started(ev, LA, datetime(2026, 10, 6, 3, 1, tzinfo=timezone.utc))        # 20:01 local
```

- [ ] **Step 3: implement** `api/events/core/timing.py` with `zoneinfo.ZoneInfo` from the standard library: parse `date`/`time` when they are strings (`date.fromisoformat`, `time.fromisoformat`), default a missing time to `time(23, 59, 59)`, build the naive local datetime, attach `ZoneInfo(tz_name)`, convert to UTC. `chapter_timezone` reads `chapters.timezone` by id and falls back to `DEFAULT_TZ` on a missing row or an unknown zone name. `has_started` is `event_start_utc(...) <= now`.
- [ ] **Step 4: failing integration test** in `test_standing_inputs.py`: insert a required event whose local start is 3 hours from now in Pacific time (compute with `ZoneInfo`), plus one member with no attendance; assert `total_required == 0` and `missed == 0`. Insert a second required event that started 2 hours ago local; assert `total_required == 1`, `missed == 1`. Add the same pair of assertions for `attendance_summary` in `tests/events/test_attendance_summary.py`, following how `test_summary_math` builds events there.
- [ ] **Step 5: implement in both loaders.** In `load_member_engagement` and in `attendance_summary`: select `"id, date, time"` for required events with `.lte("date", <tomorrow in UTC, isoformat>)` (a superset), then keep only `has_started(e, tz, now)` where `tz = chapter_timezone(sb, chapter_id)` and `now = datetime.now(timezone.utc)`. `attendance_summary` already takes a `today` argument for tests: replace it with `now: datetime | None = None` and update its callers (`grep -rn "attendance_summary(" api tests`).
- [ ] **Step 6: run `tests/events tests/memberadmin tests/attendance -q`, expect PASS. Checkpoint** — `fix(standing): an event counts as missed only after it starts in the chapter's timezone`.

---

### Task 4: F-028 — balance readers compute live

**Files:** `api/treasury/core/balance.py`, `tests/treasury/test_outstanding_by_member.py`, `api/treasury/services/reports.py:136-148, 354-366`, `api/announcements/services/sms.py` (one branch), `api/announcements/services/announcements.py` (one branch), `api/attendance/api/excuses.py` (`review_excuse`)

**Interfaces (produced):**

```python
class BalanceEngine:
    def outstanding_by_member(self, chapter_id: str) -> dict[str, int]:
        """{member_id: outstanding cents (>= 0)} for every member with any money row. Four queries."""
```

- [ ] **Step 1: failing test.** Build a chapter with four members: (a) one unpaid 10000 invoice; (b) a 10000 invoice plus a 4000 verified payment; (c) a 5000 invoice, a 9000 payment (credit); (d) a 5000 invoice, a 5000 payment and an active 5000 refund of it, plus an active −1000 adjustment. Use the same direct inserts the treasury tests use (`tests/treasury/test_chunkB_balance.py` shows the shapes). Assert `engine.outstanding_by_member(chapter_id)[m] == engine.member_outstanding(m).cents` for all four, and that the values are `10000, 6000, 0, 4000`.
- [ ] **Step 2: run, expect FAIL** (method missing).
- [ ] **Step 3: implement** next to `recompute_all`, using the same tables, filters and signs as `_member_figures`, `_member_adjustments_cents` and `_member_refunds_cents` (read those three and copy their filters exactly), but with `.eq("chapter_id", chapter_id)` and grouping by `member_id` in Python. Do not modify any existing method.
- [ ] **Step 4: point the readers at it.**
  - `reports.dashboard_summary`: `outstanding = engine.outstanding_by_member(chapter_id)`; `total_outstanding_cents = sum(outstanding.values())`; `members_with_balance_count = sum(1 for v in outstanding.values() if v > 0)`. Remove the `member_finance_accounts` read.
  - `reports.period_report_csv`, dataset `member_balances`: read the function, keep its columns, and fill the outstanding column from `outstanding_by_member`. If it exports other cached columns (owed, paid), report that and leave those columns as they are.
  - `sms.resolve_recipients`, branch `members_with_balance`: `owing = {m for m, v in BalanceEngine(sb).outstanding_by_member(chapter_id).items() if v > 0}`.
  - `announcements.audiences_for_viewer`: the viewer is in the balance audience when `BalanceEngine(sb).member_outstanding(viewer["id"]).cents > 0`.
- [ ] **Step 5: excuse approval refreshes the cache.** In `review_excuse` (`api/attendance/api/excuses.py:108-`), after `call_rpc("at_review_excuse", …)` returns successfully, call `BalanceEngine(sb).recompute_member(<the excuse's member id>)` (the RPC result carries the excuse row; read it for the member id). Wrap only that call in `try/except Exception` that logs with `logger.exception` and continues: the approval already committed and readers no longer depend on the cache.
- [ ] **Step 6: tests for the readers.** `test_dashboard_counts_a_fine_the_cache_never_saw`: insert an unpaid invoice directly (no recompute), call `dashboard_summary`, assert it is included. `test_excuse_approval_updates_cache`: issue a fine through `/api/fines/issue`, approve the member's excuse through the route, assert `member_finance_accounts.outstanding_balance_cents` equals `BalanceEngine.member_outstanding`. `test_balance_audience_uses_live_figures` for `resolve_recipients`.
- [ ] **Step 7: run the five test folders from "Global constraints", expect PASS. Checkpoint** — `fix(treasury): dashboards, exports and SMS audiences compute balances live`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
