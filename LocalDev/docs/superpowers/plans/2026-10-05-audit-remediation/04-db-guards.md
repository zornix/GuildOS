# 04 · DB guards: assignment races, inactive members, API roles, usage limits

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `04-db-guards` · **Wave:** 1 · **Agent:** Grok 4.7 medium (Cursor CLI) · **Branch:** `fix/audit-04-db-guards`
**Findings:** F-042, F-047, F-054, F-008, F-009, F-048
**Migrations:** `0171_revoke_api_roles.sql`, `0172_assignment_guards.sql`, `0173_usage_events_limits.sql` (0174, 0175 spare)
**Goal:** close two write-skew races, stop assigning deactivated members, take table access away from Supabase's public API roles, and bound the usage tracker.
**Architecture:** all but the usage tracker are SQL-only: a lock or a predicate added inside an existing function. Concurrency is proven with a deterministic "the function waits on this lock" test, not with threads racing.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-042, F-047, F-054, F-008, F-009, F-048. Decisions D12, D13 in `00-README.md`.

## Global constraints

- Allowed files: the three migrations above, `api/instrumentation/services/usage.py`, `api/instrumentation/api/schemas.py`, `tests/events/test_security.py`, `tests/initiatives/test_initiatives_rpcs.py`, `tests/tasks/test_commitments_rpcs.py`, `tests/config/test_api_role_grants.py` (new), `tests/instrumentation/**` (new or existing).
- DB functions you own this wave: `ev_assign_security`, `ev_request_security_swap`, `ev_accept_security_swap`, `tk_commit_task`, `in_add_chair`, `in_remove_chair`, `ux_block_usage_events_mutation`. `fn-index.txt` gives the live definition of each; `tk_commit_task` has three definitions and the live one is `0145:684`. Copy the live body, keep signature and return shape, change only what the task says.
- Run `python3 -m pytest tests/events tests/initiatives tests/tasks tests/config tests/instrumentation -q`. Not the full suite.

## Review focus

1. Lock order: every function here that takes more than one lock must take them in the same order (advisory or parent-row lock first, then child rows), or two calls can deadlock.
2. `invited` members (imported, not yet logged in) stay assignable; only `inactive` and `alumni` are refused (decision D12).
3. The revoke migration must be a no-op on a database that has no `anon`/`authenticated` roles (the CI Postgres).
4. An over-limit usage event is dropped silently: `POST /api/usage/track` still returns `{"ok": true}`.
5. Deleting a chapter or member must no longer be blocked by `usage_events`.

---

### Task 1: F-042 — serialize security assignment per event

**Files:** `migrations/0172_assignment_guards.sql`, `tests/events/test_security.py`

- [ ] **Step 1: failing test.** Add `test_assign_security_takes_the_event_lock`. Open a second connection with `psycopg2.connect(db_url)` (fixture `db_url`), `autocommit = False`, and run `SELECT pg_advisory_xact_lock(hashtext('ev_security:' || %s))` with the event id. On the normal `cursor`, run `SET lock_timeout = '500ms'` and call `ev_assign_security` with the same arguments the neighbouring test `test_assign_same_member_twice_rejected_but_other_event_ok` (line ~143) uses. Expect `psycopg2.errors.LockNotAvailable`. Then roll back and close the second connection and `RESET lock_timeout`.
- [ ] **Step 2: run, expect FAIL** (the call succeeds because nothing takes the lock). If it passes on the untouched branch, report `NOT_REPRODUCED`.
- [ ] **Step 3: implement.** In `ev_assign_security`, as the first statement after `BEGIN`:

```sql
    -- One assignment at a time per event, so the duplicate pre-check below cannot be raced (F-042).
    PERFORM pg_advisory_xact_lock(hashtext('ev_security:' || p_event_id::text));
```

Use the function's real event-id parameter name.

- [ ] **Step 4: apply (`python3 scripts/migrate_db.py`), run `tests/events/test_security.py -q`, expect PASS.**
- [ ] **Step 5: checkpoint** — suggested message `fix(events): serialize security assignment per event`.

---

### Task 2: F-047 — chair changes lock the initiative

**Files:** same migration, `tests/initiatives/test_initiatives_rpcs.py`

- [ ] **Step 1: failing test.** `test_remove_chair_waits_for_the_initiative_lock`: create an initiative with two chairs using the helpers the chair-removal tests at lines ~195-230 use. On a second connection (`autocommit = False`) run `SELECT 1 FROM initiatives WHERE id = %s FOR UPDATE`. On `cursor`, `SET lock_timeout = '500ms'` and call `in_remove_chair`; expect `psycopg2.errors.LockNotAvailable`. Clean up as in Task 1.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** In `in_remove_chair` and `in_add_chair`, first statement after `BEGIN`:

```sql
    -- Serialize chair changes per initiative so the last-chair count cannot be raced (F-047).
    PERFORM 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id FOR UPDATE;
```

Use the real parameter names. Leave the existing target-row lock and count as they are; they now run under the parent lock.

- [ ] **Step 4: apply, run `tests/initiatives -q`, expect PASS; checkpoint** — `fix(initiatives): lock the initiative while chairs change`.

---

### Task 3: F-054 — deactivated members cannot be assigned (decision D12)

**Files:** same migration, `tests/events/test_security.py`, `tests/tasks/test_commitments_rpcs.py`, `tests/initiatives/test_initiatives_rpcs.py`

- [ ] **Step 1: failing tests**, one per RPC. In each, create a member, set `status = 'inactive'` with `cursor`, then expect `psycopg2.Error` matching `not an active member` from: `ev_assign_security` (as the assignee), `ev_request_security_swap` (as the target), `tk_commit_task` (as the committed member), `in_add_chair` (as the new chair). One more for `ev_accept_security_swap`: request a swap to an active target, then set the target inactive, then accept; expect the same error. And one that must still pass: an `invited` member can be committed to a task.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** In each of the five functions, find the member-in-chapter check for the member being assigned or targeted (shape: `IF NOT EXISTS (SELECT 1 FROM members WHERE id = <member> AND chapter_id = p_chapter_id)`) and add a second check right after it:

```sql
    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = <member> AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', <member>;
    END IF;
```

Do not add it for the actor. In `ev_accept_security_swap` the check is new: apply it to the swap's target member after the swap row is locked.

- [ ] **Step 4: apply, run the three test folders, expect PASS; checkpoint** — `fix(db): refuse to assign inactive members`.

---

### Task 4: F-008 and F-009 — Supabase API roles get no table access

Whether these roles can reach tables today depends on a dashboard toggle outside the repo. This makes the answer "no" from inside the repo and pins it with the suite's first test as a non-owner role.

**Files:** `migrations/0171_revoke_api_roles.sql`, `tests/config/test_api_role_grants.py`

- [ ] **Step 1: failing test**

```python
import psycopg2
import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", ["members", "message_outbox", "unpaid_invoices", "events"])
def test_api_roles_cannot_read_tables(db_url, role, table):
    conn = psycopg2.connect(db_url, connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if not cur.fetchone():
                pytest.skip(f"role {role} does not exist on this database")
            cur.execute(f"SET LOCAL ROLE {role}")
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
    finally:
        conn.rollback()
        conn.close()
```

- [ ] **Step 2: run.** Expected on the demo DB today: FAIL for at least `members` (the select succeeds or returns rows). If every case already raises `InsufficientPrivilege`, record F-008 as `NOT_REPRODUCED`, keep the test, and still add the migration (it is the repo-side guarantee).
- [ ] **Step 3: migration**

```sql
-- F-008: the app connects as the table owner. Supabase's public API roles must hold
-- nothing in this schema, whatever the dashboard's Data API toggle says.
DO $$
DECLARE
    r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
        END IF;
    END LOOP;
END;
$$;
```

- [ ] **Step 4: apply, run the test, expect PASS (or SKIP where the role is missing). Then run `tests/auth tests/chapters -q`** to confirm nothing in the app depended on those grants.
- [ ] **Step 5: checkpoint** — `fix(db): revoke all schema access from the Supabase API roles`. In your report, add under "Human follow-up": "Confirm in the Supabase dashboard that the Data API is disabled for the demo and prod projects."

---

### Task 5: F-048 — bound the usage tracker (decision D13)

**Files:** `migrations/0173_usage_events_limits.sql`, `api/instrumentation/services/usage.py`, `api/instrumentation/api/schemas.py`, `tests/instrumentation/test_usage_limits.py`

- [ ] **Step 1: failing tests** (create `tests/instrumentation/__init__.py` and a `conftest.py` with `from tests.treasury.conftest import *  # noqa: F401,F403` if the folder does not exist):
  - `test_bad_event_name_is_dropped`: `track(sb_client, chapter_id, member_id, "x" * 200)` and `track(..., "DROP TABLE; --")` insert no row.
  - `test_metadata_over_1kb_is_truncated`: metadata of ~2 KB is stored as `{"_truncated": true}`.
  - `test_per_member_hourly_cap`: monkeypatch `usage.MAX_EVENTS_PER_MEMBER_PER_HOUR` to 3, call `track` 5 times, assert exactly 3 rows for that member.
  - `test_usage_rows_can_be_deleted_but_not_updated`: `DELETE FROM usage_events WHERE member_id = …` succeeds; `UPDATE usage_events SET event_name = 'x' …` raises.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**
  - Migration: re-create the trigger as `BEFORE UPDATE` only (`DROP TRIGGER IF EXISTS usage_events_immutable ON usage_events; CREATE TRIGGER usage_events_immutable BEFORE UPDATE ON usage_events FOR EACH ROW EXECUTE FUNCTION ux_block_usage_events_mutation();`) and add `CREATE INDEX IF NOT EXISTS ix_usage_events_member_created ON usage_events(member_id, created_at);`.
  - `usage.py`: module constants `MAX_EVENTS_PER_MEMBER_PER_HOUR = 600`, `_EVENT_NAME = re.compile(r"[a-z0-9_.:\-]{1,64}")`, metadata cap 1000 bytes. In `track`: return without inserting when the name does not fully match; before the insert, count the member's rows in the last hour with `db.table("usage_events").select("id", count="exact").eq("member_id", member_id).gte("created_at", <utc now − 1h, isoformat>).limit(1).execute().count` and return when it is at or over the cap. Keep the function fire-and-forget (never raises to the caller except the existing empty-name `ValueError`).
  - Add above the cap: `# ponytail: one extra indexed COUNT per tracked event; move to a windowed counter if tracking volume ever matters.`
  - Before settling the name pattern, run `grep -rn "usage/track" ../greekos/src ../../Prod 2>/dev/null; grep -rn "event_name\|track(" api --include=*.py | grep -v instrumentation` and make sure every event name the app sends today matches. Widen the pattern if one does not, and say so in the report.
- [ ] **Step 4: apply, run `tests/instrumentation tests/calendar_view -q`, expect PASS; checkpoint** — `fix(usage): cap and validate usage events; allow retention deletes`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
