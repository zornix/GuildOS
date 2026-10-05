# 10 · Check-in: login required, one live code per event, closed means closed

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `10-check-in` · **Wave:** 2 (needs 01 merged) · **Agent:** GPT-6 Luna medium (Codex CLI) · **Branch:** `fix/audit-10-check-in`
**Findings:** F-036, F-003, F-011 (check-in link and session paths)
**Migration:** `0178_checkin_guards.sql` (0179, 0180 spare)
**Goal:** nobody checks in without being signed in; members can no longer read the door code from the API; a self check-in is one audited database call; creating a code or a session cannot half-apply; a closed session really closes its link.
**Architecture:** the public phone form goes away (decision D6): `/c/CODE` redirects into the app, which already has a signed-in "enter the door code" call. Link validation stays in Python; the write becomes one small RPC that upserts attendance and writes the audit row. Link and session creation run inside `db.transaction()` (built by stream 01).
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-036, F-003, F-011; decision D6 in `00-README.md`.

## Facts you can rely on

- `get_db().transaction()` exists (stream 01): `with sb.transaction() as tx:` yields a client bound to one connection; commit on exit, rollback on any exception. Inside the block every query must go through `tx`. A failed statement aborts the whole transaction (Postgres), so "retry on duplicate code" must retry the whole block, not one statement.
- `attendance_sessions.checkin_link_id → checkin_links.id`; a link row has no session column.
- The app's signed-in code check-in is `POST /api/attendance/checkin/{short_code}` (`api/attendance/api/attendance.py:26-72`); the SPA calls it from Home. Stream 06 already taught the SPA to read `/?checkin=CODE`.
- `audit_logs.action` values are frozen. Use `'ATTENDANCE_OVERRIDDEN'` (the value `at_set_attendance` uses) and say what happened in `metadata`.

## Global constraints

- Allowed files: `migrations/0178_checkin_guards.sql`, `api/attendance/api/attendance.py` (only the two check-in routes, lines 26-128), `api/attendance/api/checkin_page.py`, `api/attendance/api/checkin_links.py`, `api/attendance/api/schemas.py` (remove `PhoneCheckIn` only), `api/attendance/api/sessions.py`, `api/attendance/services/checkin_links.py`, `api/attendance/services/sessions.py`, `tests/attendance/**`.
- Shared file, one function only: `api/events/api/events.py` → `get_checkin_link` (the `GET /{event_id}/checkin-link` handler, ~lines 224-240). Stream 11 edits other parts of that file in parallel; touch nothing else in it.
- Do not touch `at_set_attendance` or `at_review_excuse` (stream 09 owns them later), `api/attendance/api/excuses.py`, or `api/attendance/services/signals.py` (stream 08).
- Route paths stay as they are, except `POST /api/attendance/checkin/{code}/phone`, which is removed on purpose.
- Run `python3 -m pytest tests/attendance tests/events -q`. Not the full suite.

## Review focus

1. A member of chapter B with a valid code from chapter A gets 403 and no attendance row, no audit row.
2. Checking in twice returns 409 the second time and writes one audit row, not two.
3. A link whose session has closed is rejected even when two sessions are bound to it (fail closed), and the normal "open a link session while a manual session is open" flow no longer produces two bound sessions.
4. If the insert of a new link fails for any reason, the previous active link is still active afterwards.
5. A plain member calling `GET /api/events/{id}/checkin-link` learns that a code is live and when it expires, never the code.

---

### Task 1: F-036 — remove phone check-in; `/c/CODE` sends people into the app

**Files:** `api/attendance/api/attendance.py:74-128`, `api/attendance/api/schemas.py`, `api/attendance/api/checkin_page.py`, `tests/attendance/test_checkin_flow.py`, `tests/attendance/test_checkin_page_escaping.py`, `tests/attendance/test_phone.py`

- [ ] **Step 1: failing tests.** In `test_checkin_flow.py` (read its fixtures first and reuse them):
  - `test_phone_checkin_route_is_gone`: `POST /api/attendance/checkin/{code}/phone` with a member's phone returns 404 or 405 and creates no attendance row.
  - `test_checkin_page_redirects_into_the_app`: `GET /c/ABC123` (no auth, `follow_redirects=False`) returns 302 with `Location` equal to `settings.FRONTEND_URL.rstrip("/") + "/?checkin=ABC123"`.
  - `test_checkin_page_rejects_a_malformed_code`: `GET /c/<script>` (and a 40-character code) returns 404.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**
  - Delete `checkin_via_phone` and the `PhoneCheckIn` schema and their imports. `tests/attendance/test_phone.py` tests the E.164 normalizer in `api/phone.py`; keep every test there that does not use `PhoneCheckIn` and delete the ones that do.
  - Replace the body of `checkin_page.py` with one handler:

```python
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from api.config import settings

router = APIRouter()
_CODE = re.compile(r"[A-Za-z0-9]{4,8}")


@router.get("/{short_code}")
async def checkin_page(short_code: str):
    """Door-code links open the app, which checks the signed-in member in (decision D6)."""
    if not _CODE.fullmatch(short_code):
        raise HTTPException(404, "Not found")
    return RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}/?checkin={short_code.upper()}", status_code=302)
```

  Check the alphabet in `generate_short_code` (`services/checkin_links.py:46`, `ALPHABET`, `CODE_LENGTH`): if codes are case-sensitive or contain other characters, match that exactly and drop `.upper()`.
  - `test_checkin_page_escaping.py` tested HTML escaping of a page that no longer exists: delete the file.
- [ ] **Step 4: run `tests/attendance -q`, expect PASS. Checkpoint** — suggested message `fix(attendance): remove public phone check-in; /c/CODE opens the app`.

---

### Task 2: F-036 — members cannot read the door code

**Files:** `api/events/api/events.py` (`get_checkin_link` only), `api/attendance/api/checkin_links.py`, `tests/attendance/test_checkin_flow.py`

- [ ] **Step 1: failing tests.** `test_member_sees_that_a_code_is_live_but_not_the_code`: an officer creates a link; a plain member GETs `/api/events/{id}/checkin-link` and receives exactly `{"event_id": …, "active": true, "expires_at": …}` with no `short_code` and no `url` key. `test_manager_still_gets_the_code`: a holder of `attendance:checkin_link:manage` gets `short_code`. `test_no_live_code_returns_empty_object` (unchanged behaviour: `{}`).
- [ ] **Step 2: run, expect the first to FAIL.**
- [ ] **Step 3: implement** in `get_checkin_link`: after loading `link`, if it is truthy and `not has_permission(user, CHECKIN_LINK_MANAGE, sb=sb)`, return `{"event_id": link["event_id"], "active": True, "expires_at": link["expires_at"]}`. Import `has_permission` from `api.rbac.services.permissions` and `CHECKIN_LINK_MANAGE` from `api.attendance.auth` (check what the file already imports). `GET /api/checkin-links/active` is already manager-only; leave it.
- [ ] **Step 4: run, expect PASS. Checkpoint** — `fix(attendance): only check-in managers can read the door code`.

---

### Task 3: self check-in is one audited database call

**Files:** `migrations/0178_checkin_guards.sql`, `api/attendance/api/attendance.py:26-72`, `tests/attendance/test_checkin_flow.py`, `tests/attendance/test_tenant_guards.py`

**Interfaces (produced):**

```sql
at_checkin_self(p_chapter_id UUID, p_event_id UUID, p_member_id UUID) RETURNS JSONB
-- {"attendance_id": uuid, "checked_in_at": timestamptz}; raises 'already checked in' when it is
```

- [ ] **Step 1: failing tests.** `test_link_checkin_writes_an_audit_row`: after a successful `POST /api/attendance/checkin/{code}`, exactly one `audit_logs` row exists with `action='ATTENDANCE_OVERRIDDEN'`, `actor_id` = the member, `target_table='attendance'`, and `metadata->>'method' = 'link'`. `test_second_checkin_is_409_and_adds_no_audit_row`. `test_checkin_self_rpc_rejects_cross_chapter` (call the RPC with a member from another chapter; expect an error and no row).
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration.** Read the "present" path of the live `at_set_attendance` (`migrations/0146_attendance_tenant_guards.sql:139-225`) and write `at_checkin_self` the same way: verify the event and the member both belong to `p_chapter_id` (raise otherwise); if an attendance row for (event, member) already has `checked_in = true`, `RAISE EXCEPTION 'already checked in'`; otherwise upsert the row (`checked_in = true`, `checked_in_at = now()`, `method = 'link'`, `chapter_id = p_chapter_id`) on `(event_id, member_id)`; insert the audit row:

```sql
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'ATTENDANCE_OVERRIDDEN', p_member_id, 'attendance', v_attendance_id,
            jsonb_build_object('status', 'present', 'method', 'link', 'self_checkin', true,
                               'event_id', p_event_id, 'member_id', p_member_id));
```

  Apply: `python3 scripts/migrate_db.py`.
- [ ] **Step 4: route.** In `checkin_via_link`, keep the link validation and the wrong-chapter 403, delete the `existing` read and the `.upsert(...)`, and call `call_rpc("at_checkin_self", {"p_chapter_id": event["chapter_id"], "p_event_id": event["id"], "p_member_id": user["id"]})`. Map an error whose text contains `already checked in` to `HTTPException(409, "Already checked in")`; let anything else raise. The response shape stays `{"status", "event_title", "checked_in_at"}`.
- [ ] **Step 5: run `tests/attendance -q`, expect PASS. Checkpoint** — `fix(attendance): self check-in goes through one audited RPC`.

---

### Task 4: F-003 — the link's own session governs it; ambiguity fails closed

**Files:** `api/attendance/services/checkin_links.py:88-164, 220-255`, `tests/attendance/test_checkin_links_unit.py:220-260`

- [ ] **Step 1: flip and add tests.** The existing ambiguity tests around lines 220-260 assert that an ambiguous link stays valid; rewrite them to assert `validate_checkin_link` returns `None`. Add `test_two_sessions_bound_to_one_link_is_invalid_even_before_close` and `test_link_with_no_session_at_all_is_valid_until_ttl`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**

```python
class AmbiguousSession(Exception):
    """More than one attendance session could govern this link."""
```

  In `_session_for_link`: where it returns `None` because more than one session is bound to the link, or because no session is bound and more than one open unbound session exists, `raise AmbiguousSession` instead. Keep returning `None` when there is simply no session. In `validate_checkin_link`, wrap the call: `except AmbiguousSession: return None`. Update the docstrings: rule 3 becomes "ambiguous → the link is invalid".
  In `_bind_open_sessions`: bind only when exactly one open unbound session exists; with zero or several, bind nothing.
- [ ] **Step 4: run, expect PASS. Checkpoint** — `fix(attendance): an ambiguous session binding invalidates the link`.

---

### Task 5: F-011 — link and session creation are atomic; one live code per event

**Files:** `migrations/0178_checkin_guards.sql` (append only if not yet applied; otherwise `0179_one_active_link.sql`), `api/attendance/services/checkin_links.py:167-217`, `api/attendance/services/sessions.py:16-72`, `api/attendance/api/sessions.py`, `tests/attendance/test_checkin_links_unit.py`

- [ ] **Step 1: failing tests.**
  - `test_failed_link_insert_keeps_the_old_link_active`: create a link; monkeypatch `generate_short_code` to return a string longer than the column allows (or otherwise make the insert raise a non-duplicate error); call `create_checkin_link` again and expect an exception; the first link is still `active`.
  - `test_link_session_does_not_double_bind`: open a manual session, then `create_session(mode="short_link")`; exactly one session is bound to the new link, and `validate_checkin_link` accepts the code.
  - `test_failed_session_insert_leaves_no_link`: make the `attendance_sessions` insert fail (pass an invalid `mode` that violates the table's CHECK); no new `checkin_links` row exists and `events.linked_attendance_session_id` is unchanged.
  - `test_one_active_link_per_event_is_enforced_by_the_database`: with `cursor`, insert a second `active = true` link for an event that has one; expect `psycopg2.errors.UniqueViolation`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration.**

```sql
-- Keep only the newest active link per event, then make that a rule.
UPDATE checkin_links c SET active = false
 WHERE c.active
   AND EXISTS (SELECT 1 FROM checkin_links n
                WHERE n.event_id = c.event_id AND n.active
                  AND (n.created_at, n.id) > (c.created_at, c.id));
CREATE UNIQUE INDEX IF NOT EXISTS uq_checkin_links_one_active_per_event
    ON checkin_links(event_id) WHERE active;
```

  Check `checkin_links` has `created_at` (`migrations/0001_initial_schema.sql:143-154`); if not, order by `expires_at`.
- [ ] **Step 4: implement.**
  - `create_checkin_link(event_id, created_by, *, sb=None, bind_sessions=True)`: when `sb` is None, open `with get_db().transaction() as tx:` and do deactivate → insert → (if `bind_sessions`) `_bind_open_sessions` inside it, retrying the whole block up to 5 times when `_is_duplicate_code(exc)` is true AND the error names the short-code constraint. Tell the two unique violations apart by `getattr(exc.diag, "constraint_name", "")`: `uq_checkin_links_one_active_per_event` means a concurrent create won the race → `HTTPException(409, "A check-in code was just created for this event. Refresh to see it.")`; anything else unique is a code collision → retry. When `sb` is given (the caller's transaction), do the three steps once on it and let errors propagate. Return the link's `id` in the result dict as well.
  - `create_session`: wrap everything after the event lookup in `with sb.transaction() as tx:`; for link modes call `create_checkin_link(event_id, actor_id, sb=tx, bind_sessions=False)` and use the returned `id` (drop the read-back by short code); insert the session and update `events.linked_attendance_session_id` through `tx`. Check the caller in `api/attendance/api/sessions.py` still passes a client that has `.transaction()` (it passes `get_db()`).
- [ ] **Step 5: apply, run `tests/attendance tests/events -q`, expect PASS. Checkpoint** — `fix(attendance): atomic link and session creation; one live code per event`.

## Report

Finish with the report block from `00-README.md` ("What to hand back"). Under "Human follow-up" add: "Set `FRONTEND_URL` in the Vercel environment; `/c/CODE` redirects there."
