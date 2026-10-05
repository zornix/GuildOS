# 09 · Fines pipeline: one fine per absence, never alongside an excuse, issued in one transaction

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `09-fines-pipeline` · **Wave:** 3 (needs 03, 08, 10 and 11 merged) · **Agent:** Grok 4.7 medium (Cursor CLI) · **Branch:** `fix/audit-09-fines-pipeline`
**Findings:** F-004, F-057, F-059, F-060, plus the `fine_summary` half of F-024
**Migrations:** `0195_fine_guards.sql`, `0196_issue_event_fines.sql`, `0197_event_start_timezone.sql` (0198, 0199 spare)
**Goal:** the database refuses a second live fine for the same event and member; marking someone present or excused removes their open fine; a batch of fines is issued in one transaction; the legacy second fine engine is gone; the 24-hour fine rule and the 36-hour unclaim lock use the chapter's timezone.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-004, F-057, F-059, F-060, F-024; decisions D5, D20 in `00-README.md`.

## Facts you can rely on (all merged before this wave)

- `api/events/core/timing.py` (stream 08): `chapter_timezone(sb, chapter_id) -> str`, `event_start_utc(event, tz_name) -> datetime` (aware UTC; a missing time means end of the local day), `has_started(event, tz_name, now)`. `chapters.timezone` exists, default `America/Los_Angeles`.
- `api/treasury/services/remaining.py` (stream 08): `remaining_by_invoice(sb, invoices) -> {invoice_id: cents still owed}`.
- `tr_void_invoice(p_chapter_id, p_invoice_id, p_actor_id, p_reason, p_idempotency_key DEFAULT NULL)` (live at `0122:14`) voids an `unpaid` or `partially_paid` invoice, writes the ledger and audit rows, and refuses `paid`/`cancelled`.
- `tr_create_invoice_v2` (live at `0120:59`) creates one invoice with idempotency key, ledger and audit rows; `issue_fines` calls it once per member with key `fine:{event_id}:{member_id}`.
- Balance readers no longer depend on the `member_finance_accounts` cache (stream 08), and `get_member_balance` recomputes on read.
- The live `at_set_attendance` and `at_review_excuse` are in `migrations/0146_attendance_tenant_guards.sql:139` and `:238`. The only live function that computes an event's start in SQL is `tk_uncommit_task` (`migrations/0145_security_swaps_v1.sql:777`, start computed at lines 823 and 830).

## Global constraints

- Allowed files: the three migrations; `api/treasury/api/fines_legacy.py`; `api/treasury/services/fine_processor.py` (delete); `api/treasury/services/invoices.py` (add one function; change nothing existing); `api/attendance/api/attendance.py` (only `manual_checkin`, the `POST /event/{event_id}/manual/{member_id}` handler); `api/attendance/services/signals.py` (comments that mention `fine_processor` only); `tests/treasury/test_v1_fines.py`, `tests/treasury/test_fine_guards.py` (new), `tests/attendance/test_tenant_guards.py`, `tests/tasks/test_commitments_rpcs.py`, `tests/memberadmin/test_engagement_fines.py` (only if a helper it uses changes).
- DB functions you own this wave: `at_set_attendance`, `at_review_excuse`, `tk_uncommit_task`, new `tr_issue_event_fines`, new `ev_local_start`. Keep existing signatures and return shapes. Do not replace `tr_create_invoice_v2`, `tr_void_invoice` or any other function.
- No table or column is dropped (the frozen `fines` table and the NUMERIC `fine_amount` columns stay).
- `/api/fines/*` paths used by the SPA stay (`GET /api/fines/`, `POST /api/fines/issue`, waive, summary). `POST /api/fines/process-event/{id}` is removed on purpose (Task 4).
- Run `python3 -m pytest tests/treasury tests/attendance tests/tasks tests/memberadmin -q`. Not the full suite.

## Review focus

1. The duplicate cleanup in `0195` must never cancel a `paid` fine and must stop with a clear error if two `paid` fines exist for one event and member.
2. Marking a member present or excused voids an open fine whether it is `unpaid` or `partially_paid`, and does nothing (no error) when the fine is already `paid` or `cancelled`.
3. `tr_issue_event_fines` is all-or-nothing: an invalid member id in the list rolls back every invoice in that call.
4. A second call with the same members returns them as skipped and creates nothing.
5. With the chapter in `America/Los_Angeles`, an event at 20:00 local becomes finable at 20:00 local the next day, not 7 or 8 hours earlier.

---

### Task 1: F-004 — one live fine per event and member

**Files:** `migrations/0195_fine_guards.sql`, `tests/treasury/test_fine_guards.py`

- [ ] **Step 1: look before you leap.** Run this read-only query against the demo DB (through `psql "$DATABASE_URL"` or a three-line Python script using `tests.treasury.conftest` helpers) and put the two numbers in your report:

```sql
SELECT count(*) FILTER (WHERE n_open + n_paid > 1) AS pairs_with_duplicates,
       count(*) FILTER (WHERE n_paid > 1)          AS pairs_with_two_paid
  FROM (SELECT source_event_id, member_id,
               count(*) FILTER (WHERE status IN ('unpaid','partially_paid')) AS n_open,
               count(*) FILTER (WHERE status = 'paid') AS n_paid
          FROM unpaid_invoices
         WHERE kind = 'fine' AND source_event_id IS NOT NULL AND status <> 'cancelled'
         GROUP BY 1, 2) t;
```

- [ ] **Step 2: failing test** `test_second_live_fine_for_same_event_and_member_is_rejected`: with `cursor`, insert a fine invoice (`kind='fine'`, `source_event_id`, `member_id`, `status='unpaid'`), insert a second identical one; expect `psycopg2.errors.UniqueViolation`. `test_a_new_fine_is_allowed_after_the_first_is_cancelled`: set the first to `cancelled`, insert again → succeeds. `test_free_form_fines_without_an_event_are_not_limited` (two fines with `source_event_id NULL` for one member → both succeed).
- [ ] **Step 3: run, expect the first to FAIL.**
- [ ] **Step 4: migration.**

```sql
-- F-004. Remove existing duplicates first: per (event, member) keep one live fine,
-- preferring a paid one, then the oldest; void the other OPEN ones through the normal RPC.
DO $$
DECLARE
    r RECORD;
    v_two_paid INT;
BEGIN
    SELECT count(*) INTO v_two_paid FROM (
        SELECT 1 FROM unpaid_invoices
         WHERE kind = 'fine' AND source_event_id IS NOT NULL AND status = 'paid'
         GROUP BY source_event_id, member_id HAVING count(*) > 1) t;
    IF v_two_paid > 0 THEN
        RAISE EXCEPTION '0195: % event/member pairs have two PAID fines; refund one by hand before migrating', v_two_paid;
    END IF;

    FOR r IN
        SELECT id, chapter_id FROM (
            SELECT id, chapter_id, status,
                   row_number() OVER (PARTITION BY source_event_id, member_id
                                      ORDER BY (status = 'paid') DESC, created_at, id) AS rn
              FROM unpaid_invoices
             WHERE kind = 'fine' AND source_event_id IS NOT NULL AND status <> 'cancelled') x
         WHERE rn > 1 AND status IN ('unpaid', 'partially_paid')
    LOOP
        PERFORM tr_void_invoice(r.chapter_id, r.id, NULL, 'duplicate fine for the same event (migration 0195)', NULL);
    END LOOP;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fine_per_event_member
    ON unpaid_invoices (source_event_id, member_id)
    WHERE kind = 'fine' AND status <> 'cancelled' AND source_event_id IS NOT NULL;
```

  If `tr_void_invoice` rejects a NULL actor, read its body (`0122:14-`) and pass what it accepts; do not write to `unpaid_invoices.status` directly.
- [ ] **Step 5: apply (`python3 scripts/migrate_db.py`), run `tests/treasury -q`, expect PASS. Checkpoint** — suggested message `fix(treasury): the database allows one live fine per event and member`.

---

### Task 2: F-004 — present or excused means no open fine

**Files:** `migrations/0195_fine_guards.sql` (append only if not yet applied; otherwise `0198_attendance_voids_fines.sql`), `api/attendance/api/attendance.py` (`manual_checkin`), `tests/attendance/test_tenant_guards.py`

- [ ] **Step 1: failing tests** (follow the existing `at_set_attendance` and `at_review_excuse` tests in this file for arguments):
  - `test_marking_excused_voids_an_open_fine`: unpaid fine for (event, member); call `at_set_attendance` with status `excused` → the invoice is `cancelled`.
  - `test_marking_present_voids_an_open_fine`.
  - `test_partially_paid_fine_is_voided_too` (insert an allocation of 1 cent so the invoice is `partially_paid`, then mark excused → `cancelled`).
  - `test_paid_fine_is_left_alone` (status `paid` → still `paid`, and the RPC does not raise).
  - `test_excuse_approval_voids_partially_paid_fine` (through `at_review_excuse`; today it only looks at `unpaid`).
  - `test_marking_absent_voids_nothing`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** Add one helper to the migration and call it from both functions:

```sql
CREATE OR REPLACE FUNCTION at_void_open_fines(
    p_chapter_id UUID, p_event_id UUID, p_member_id UUID, p_actor_id UUID, p_reason TEXT
) RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    r RECORD;
    v_n INT := 0;
BEGIN
    FOR r IN
        SELECT id FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id AND kind = 'fine'
           AND source_event_id = p_event_id AND member_id = p_member_id
           AND status IN ('unpaid', 'partially_paid')
    LOOP
        PERFORM tr_void_invoice(p_chapter_id, r.id, p_actor_id, p_reason, NULL);
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END;
$$;
```

  - `at_set_attendance`: copy the live body; in the `excused` branch and in the `present` branch, after the attendance/excuse writes, `PERFORM at_void_open_fines(p_chapter_id, p_event_id, p_member_id, p_actor_id, 'marked ' || p_status);`.
  - `at_review_excuse`: copy the live body; replace the `SELECT id … AND status = 'unpaid' LIMIT 1` + single `tr_void_invoice` (lines ~278-288) with `PERFORM at_void_open_fines(p_chapter_id, v_excuse.event_id, v_excuse.member_id, p_actor_id, 'excuse approved');` in the approve path only.
  - Add `at_void_open_fines` to the functions you own in your report.
- [ ] **Step 4: route.** In `manual_checkin`, after the RPC succeeds, refresh the member's balance cache the way `review_excuse` does since stream 08 (`BalanceEngine(sb).recompute_member(member_id)` inside a `try/except Exception` that logs and continues).
- [ ] **Step 5: apply, run `tests/attendance tests/treasury -q`, expect PASS. Checkpoint** — `fix(attendance): marking present or excused voids the member's open fine for that event`.

---

### Task 3: F-057 — issue a batch of fines in one transaction

**Files:** `migrations/0196_issue_event_fines.sql`, `api/treasury/services/invoices.py`, `api/treasury/api/fines_legacy.py:173-224`, `tests/treasury/test_v1_fines.py`

**Interfaces (produced):**

```sql
tr_issue_event_fines(p_chapter_id UUID, p_event_id UUID, p_member_ids JSONB,   -- ["uuid", …]
                     p_amount_cents BIGINT, p_description TEXT, p_actor_id UUID) RETURNS JSONB
-- {"issued": [<invoice json>, …], "skipped_member_ids": ["uuid", …]}
```

- [ ] **Step 1: failing tests** in `test_v1_fines.py` (route level, reuse `api`, `make_user`, `assign_role`):
  - `test_issue_is_all_or_nothing`: call the RPC directly with two valid members and one random UUID that is not in the chapter → error, and zero fine invoices exist for the event.
  - `test_reissue_skips_everyone_and_creates_nothing`: issue for three members twice through the route; the second response has all three in `skipped_member_ids` and the invoice count is still three.
  - `test_issue_queues_one_notice_per_fined_member` (the same notification rows as today, `message_outbox`).
  - The existing response-shape assertions must keep passing unchanged.
- [ ] **Step 2: run, expect the first to FAIL** (function missing).
- [ ] **Step 3: migration.** `tr_issue_event_fines`: verify the event belongs to the chapter; loop over `jsonb_array_elements_text(p_member_ids)`; for each member: verify membership in the chapter (raise if not); if a fine for (event, member) with `status <> 'cancelled'` exists, append to skipped; otherwise call `tr_create_invoice_v2` with the same arguments `create_invoice_v2` passes today for a fine (read `api/treasury/services/invoices.py:62-104` and the SQL signature at `0120:59`), including idempotency key `'fine:' || p_event_id || ':' || member` and the source event, and append its result to issued. Return the object above. One function body, so it is one transaction.
- [ ] **Step 4: Python.** Add `issue_event_fines(sb, *, chapter_id, event_id, member_ids, amount_cents, description, actor_id) -> dict` to `services/invoices.py`: one `call_rpc`, then one `enqueue_many(...)` for the issued invoices using the same event type, target and dedup-key shape `notify_invoice_issued` uses for a single invoice (read `api/treasury/notifications.py:35-46`; if each notice needs its own `target_id`, loop `notify_invoice_issued` instead and say so). No per-member balance recompute.
  In `issue_fines` (`fines_legacy.py`): keep the event load, the 24-hour gate, `list_unexcused_absences` and the eligibility filter; delete `_already_fined_ids` use and the per-member `create_invoice_v2` loop; pass the eligible members to `issue_event_fines`; members filtered out in Python plus the RPC's skipped list form `skipped_member_ids`. The response keys stay exactly as they are.
- [ ] **Step 5: apply, run `tests/treasury tests/memberadmin -q`, expect PASS. Checkpoint** — `perf(treasury): fines for an event are issued in one transaction`.

---

### Task 4: F-059 — remove the legacy fine engine

**Files:** `api/treasury/api/fines_legacy.py:24, 251-272`, `api/treasury/services/fine_processor.py`, `api/attendance/services/signals.py` (comments), tests that exercise the route

- [ ] **Step 1:** confirm nothing else uses it: `grep -rn "process-event\|process_event_fines\|fine_processor" api greekos/src tests scripts`. Expected: `fines_legacy.py`, `fine_processor.py`, two comments in `signals.py`, the disabled `process-fines` cron no-op in `api/cron/api/cron.py` (stream 14's file this wave: if it imports `fine_processor`, stop and report; if it only mentions it in a comment, leave it), and tests.
- [ ] **Step 2:** delete the `process_fines_for_event` route and its import; `git rm api/treasury/services/fine_processor.py`; fix the two comments in `signals.py` to say fines are issued through `POST /api/fines/issue`. Delete the tests that covered the removed route and add `test_process_event_route_is_gone` (404 or 405).
- [ ] **Step 3: run `tests/treasury tests/attendance -q` and `python3 -c "import api.index"`. Checkpoint** — `chore(treasury): remove the legacy process-event fine path`.

---

### Task 5: F-060 — fine timing and the unclaim lock use the chapter's timezone

**Files:** `api/treasury/api/fines_legacy.py:38-46, 150-190`, `migrations/0197_event_start_timezone.sql`, `tests/treasury/test_v1_fines.py`, `tests/tasks/test_commitments_rpcs.py`

- [ ] **Step 1: failing tests.**
  - `test_fine_gate_uses_chapter_timezone`: chapter timezone `America/Los_Angeles` (the default). Insert a required event whose LOCAL start was 20 hours ago (compute the local date and time with `zoneinfo`). `POST /api/fines/issue` → 422 (not yet 24 hours). Insert another whose local start was 25 hours ago → 200. Today the first case passes or fails by the UTC offset.
  - `test_unclaim_lock_uses_chapter_timezone`: commit a member to a job on an event whose LOCAL start is 40 hours from now; `tk_uncommit_task` → not late/locked. An event whose LOCAL start is 30 hours from now → the 36-hour rule applies. Follow the existing lock tests in `test_commitments_rpcs.py` for the exact call and the expected result shape; `tests/tasks/conftest.py::event_factory` builds events from the server clock, so add a local-time variant in the test file rather than editing the shared fixture.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: Python.** Delete `_event_start_utc` from `fines_legacy.py`; at both call sites (the "finable" read near line 158 and the gate near line 182) use `event_start_utc(event, chapter_timezone(sb, user["chapter_id"]))` from `api.events.core.timing`. Make sure the event select includes `date` and `time`.
- [ ] **Step 4: SQL.**

```sql
-- Event and initiative date/time are entered in the chapter's local time (decision D5).
CREATE OR REPLACE FUNCTION ev_local_start(p_chapter_id UUID, p_date DATE, p_time TIME)
RETURNS TIMESTAMPTZ
LANGUAGE sql STABLE AS $$
    SELECT (p_date + COALESCE(p_time, TIME '00:00'))
           AT TIME ZONE (SELECT timezone FROM chapters WHERE id = p_chapter_id);
$$;
```

  Copy the live `tk_uncommit_task` (`migrations/0145_security_swaps_v1.sql:777-`) and replace the two start expressions (`(e.date + COALESCE(e.time, TIME '00:00'))::timestamptz` at line ~823 and the initiative one at ~830) with `ev_local_start(p_chapter_id, e.date, e.time)` and `ev_local_start(p_chapter_id, i.date, i.time)`. Nothing else changes; the missing-time default stays `00:00` there.
- [ ] **Step 5:** fix the half of F-024 left for this stream: in `fine_summary` (`fines_legacy.py:275-298`) select `id, amount_cents, status`, compute `remaining_by_invoice` for the `unpaid`/`partially_paid` rows, and add the remaining cents (not the face amount) to `total_unpaid_cents`; count only invoices with remaining > 0 in `count_unpaid`. Test: a 2500 fine with 1 cent allocated contributes 2499.
- [ ] **Step 6: apply, run the four test folders, expect PASS. Checkpoint** — `fix(fines,tasks): event start uses the chapter's timezone`.

## Report

Finish with the report block from `00-README.md` ("What to hand back"). Include the two numbers from Task 1 Step 1.
