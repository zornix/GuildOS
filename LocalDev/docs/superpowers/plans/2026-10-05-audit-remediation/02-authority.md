# 02 · Authority: one source of truth for roles, with a ceiling

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `02-authority` · **Wave:** 1 · **Agent:** Grok 4.7 medium (Cursor CLI) · **Branch:** `fix/audit-02-authority`
**Findings:** F-022, F-023, F-006, F-033, F-052
**Migrations:** `0162_rbac_authority.sql`, `0163_roster_import_role.sql`, `0164_rbac_admin_tier.sql`
**Goal:** permissions come only from `member_roles`; revoking a role really revokes it; every chapter has an admin, and only an admin can hand out the top roles; roster import stops minting officers.
**Architecture:** the legacy `members.role` column stops being an input to permissions. One backfill gives every legacy officer a `member_roles` row, the resolver then reads `member_roles` plus an implicit `member` baseline, and the assign/revoke RPCs keep the column in step for display only. The admin tier (only an admin grants `admin` or `president`; the last admin cannot be removed) lives inside the RPCs.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-022, F-023, F-006, F-033, F-052. Decisions D8, D9 in `00-README.md`.

## Facts checked on 2026-10-05 (demo DB)

- Roles: `admin` (38 permissions, all of them), `officer` (32), `president` (24), `treasurer`, `secretary`, `vice_president`, ten chairs/boards, `member` (2).
- The chapter founder gets only `officer` (`ch_create_chapter`, `migrations/0156`). Most roles hold at least one permission `officer` lacks, so a "you can only grant what you hold" rule would stop a founder appointing a treasurer. That is why the ceiling is a tier (decision D8, set by the user), not a subset rule: the chapter creator becomes `admin`; an admin can make anyone else an admin and step down; several admins may exist.
- 4,506 members have `role='officer'` and no `member_roles` officer row. 30,230 members have no `member_roles` row at all, so the `member` baseline must be implicit.
- Live definitions: `rbac_assign_role` and `rbac_revoke_role` in `migrations/0083_rbac_seed_rpcs.sql:203-300`; `mem_set_legacy_role` in `0154:20` (not changed by this stream); `ch_import_roster` in `0157:29`; `ch_create_chapter` in `0156:21`.

## Global constraints

- Allowed files: `migrations/0162_rbac_authority.sql`, `migrations/0163_roster_import_role.sql`, `migrations/0164_rbac_admin_tier.sql`, `api/rbac/**`, `tests/rbac/**`, `tests/chapters/test_roster_import.py`, `tests/chapters/test_create_chapter.py`, `api/chapters/services/onboarding.py` (`parse_roster_csv` only).
- DB functions you own this wave: `rbac_assign_role`, `rbac_revoke_role`, `ch_import_roster`, `ch_create_chapter`. Replace each with `CREATE OR REPLACE FUNCTION` keeping the exact signature and return shape. Copy the live body and change only what the task says.
- Permission keys, the `/api/rbac/me/permissions` response shape, and every route path stay the same.
- Keep the name `LEGACY_ROLE_COMPAT` (`api/members/api/members.py:110` uses its keys as the legacy column's domain). Only its comment changes.
- `is_officer(member, role_keys)` keeps its signature; it is an audience predicate used by `api/announcements/services/{sms,announcements}.py`.
- Run only `python3 -m pytest tests/rbac tests/chapters tests/members tests/announcements -q`. Not the full suite.

## Review focus

1. A member with `members.role='officer'` and no `member_roles` row before the migration must hold exactly the same permissions after it (the backfill).
2. A member with zero `member_roles` rows must still hold the two `member` permissions.
3. Revoking a role the target does not hold stays an idempotent success (`revoked: false`) and must not trip the last-admin guard.
4. An idempotent replay (`p_idempotency_key` already stored) returns the stored result before any ceiling check, as today.
5. Both backfills must be safe to run twice (`ON CONFLICT DO NOTHING`), and the admin backfill must give each chapter exactly one admin (its earliest officer), never one per officer.

---

### Task 1: F-022 — reproduce: RBAC revoke leaves officer permissions

**Files:** `tests/rbac/test_authority.py` (new)

Use the real database (`sb_client`, `cursor`, `chapter_id`, `member_factory` from `tests/treasury/conftest.py`, already imported by `tests/rbac/conftest.py`). No `FakeSb`.

- [ ] **Step 1: write the failing tests**

```python
import psycopg2
import pytest

from api.rbac.services.permissions import get_member_permissions
from api.platform.rpc import call_rpc


def _member(sb, member_id):
    return sb.table("members").select("*").eq("id", member_id).single().execute().data


def _assign(sb, chapter_id, member_id, role_key, actor_id):
    return call_rpc("rbac_assign_role", {
        "p_chapter_id": chapter_id, "p_member_id": member_id,
        "p_role_key": role_key, "p_actor_id": actor_id}, sb=sb)


def _revoke(sb, chapter_id, member_id, role_key, actor_id):
    return call_rpc("rbac_revoke_role", {
        "p_chapter_id": chapter_id, "p_member_id": member_id,
        "p_role_key": role_key, "p_actor_id": actor_id}, sb=sb)


def test_revoking_officer_removes_officer_permissions(sb_client, chapter_id, member_factory):
    boss = member_factory(role="officer")
    target = member_factory(role="officer")          # legacy column says officer
    _assign(sb_client, chapter_id, boss, "officer", boss)
    _assign(sb_client, chapter_id, target, "officer", boss)
    assert "roles:assign" in get_member_permissions(_member(sb_client, target), sb=sb_client)

    _revoke(sb_client, chapter_id, target, "officer", boss)

    m = _member(sb_client, target)
    assert "roles:assign" not in get_member_permissions(m, sb=sb_client)
    assert m["role"] == "member"


def test_legacy_column_alone_grants_nothing(sb_client, chapter_id, member_factory):
    target = member_factory(role="officer")          # column only, no member_roles row
    perms = get_member_permissions(_member(sb_client, target), sb=sb_client)
    assert "roles:assign" not in perms


def test_member_with_no_rows_keeps_member_baseline(sb_client, chapter_id, member_factory):
    target = member_factory()
    perms = get_member_permissions(_member(sb_client, target), sb=sb_client)
    expected = {r["permission_key"] for r in
                sb_client.table("role_permissions").select("permission_key").eq("role_key", "member").execute().data}
    assert perms == expected
```

- [ ] **Step 2: run, expect the first two to FAIL** — `python3 -m pytest tests/rbac/test_authority.py -q`. If the first test passes on the untouched branch, stop and report F-022 `NOT_REPRODUCED`.

### Task 2: F-022 — fix the resolver and the RPCs

**Files:** `migrations/0162_rbac_authority.sql` (new), `api/rbac/services/permissions.py`, `api/rbac/core/policy.py` (comment only)

- [ ] **Step 1: migration, part 1 (backfill).** Start `0162_rbac_authority.sql` with a header comment naming F-022/F-023, then:

```sql
-- Every legacy officer gets the member_roles row the resolver will now require.
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT m.chapter_id, m.id, 'officer'
  FROM members m
 WHERE m.role = 'officer'
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;
```

- [ ] **Step 2: migration, part 2 (`rbac_revoke_role`).** Copy the live body from `0083:257-300`. After the `DELETE … RETURNING * INTO v_row;` add, inside the same function:

```sql
    IF v_row.id IS NOT NULL AND p_role_key = 'officer' THEN
        UPDATE members SET role = 'member'
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND role = 'officer';
    END IF;
```

- [ ] **Step 3: migration, part 3 (`rbac_assign_role` and `mem_set_legacy_role`).** In `rbac_assign_role`, after the `INSERT INTO member_roles … RETURNING * INTO v_row;` add:

```sql
    IF p_role_key = 'officer' THEN
        UPDATE members SET role = 'officer'
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND role <> 'officer';
    END IF;
```

`mem_set_legacy_role` already writes both stores; leave it alone.

- [ ] **Step 4: resolver.** In `api/rbac/services/permissions.py` replace `_effective_role_keys` with:

```python
def _effective_role_keys(member: dict, role_keys) -> set[str]:
    """member_roles plus the baseline every member holds. The legacy
    members.role column is display-only and never grants anything (F-022)."""
    return set(role_keys) | {"member"}
```

Drop the now-unused `LEGACY_ROLE_COMPAT` import there. Rewrite the module docstring to say resolution = `member_roles` ∪ the `member` baseline. In `api/rbac/core/policy.py` change the comment above `LEGACY_ROLE_COMPAT` to: `# The legal values of the display-only members.role column. Not an input to permissions.`

- [ ] **Step 5: apply and run.** `python3 scripts/migrate_db.py` (from `LocalDev/`, see README "Database"), then `python3 -m pytest tests/rbac tests/members tests/announcements -q`. Expected: Task 1 tests pass. Existing tests that built an officer with only `member_factory(role="officer")` and expected officer permissions will now fail: fix those tests by also assigning the role with `rbac_assign_role` (or a direct `member_roles` insert through `cursor`), never by restoring the union. List every test you changed in the report.
- [ ] **Step 6: checkpoint** (README "Commits": external agents do not commit; write the suggested message `fix(rbac): permissions come from member_roles only; revoke clears the legacy column` into your report).

---

### Task 3: F-023 — the admin tier (decision D8)

Rule, set by the user on 2026-10-05:

- The person who creates a chapter becomes its `admin`.
- `admin` and `president` can be granted or revoked only by an admin of that chapter. Every other role keeps today's behaviour (the route already requires `roles:assign`).
- More than one admin is allowed. An admin may revoke their own `admin` role (step down) as long as another admin remains: hand off first, then step down.
- Existing chapters have no admin. One backfill makes each chapter's earliest officer its admin.

**Files:** `migrations/0164_rbac_admin_tier.sql`, `api/rbac/services/assignments.py` (or `api/rbac/api/roles.py`, see Step 5), `tests/rbac/test_authority.py`, `tests/chapters/test_create_chapter.py`

- [ ] **Step 1: failing tests** (append to `test_authority.py`):

```python
def _make_admin(cursor, chapter_id, member_id):
    """Test bootstrap only: a fresh test chapter has no admin to do the granting."""
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'admin')",
        (chapter_id, member_id))


def _roles(sb, member_id):
    return {r["role_key"] for r in sb.table("member_roles").select("role_key").eq("member_id", member_id).execute().data}


def test_officer_cannot_grant_admin_or_president(sb_client, chapter_id, member_factory):
    officer = member_factory(role="officer")
    _assign(sb_client, chapter_id, officer, "officer", officer)
    for role in ("admin", "president"):
        with pytest.raises(psycopg2.Error, match="rbac_ceiling"):
            _assign(sb_client, chapter_id, officer, role, officer)


def test_admin_can_hand_off_and_step_down(sb_client, cursor, chapter_id, member_factory):
    founder, heir = member_factory(role="officer"), member_factory()
    _make_admin(cursor, chapter_id, founder)
    _assign(sb_client, chapter_id, heir, "admin", founder)          # hand off
    assert _revoke(sb_client, chapter_id, founder, "admin", founder).data["revoked"] is True   # step down
    assert "admin" in _roles(sb_client, heir) and "admin" not in _roles(sb_client, founder)


def test_two_admins_may_coexist(sb_client, cursor, chapter_id, member_factory):
    a, b = member_factory(), member_factory()
    _make_admin(cursor, chapter_id, a)
    _assign(sb_client, chapter_id, b, "admin", a)
    assert "admin" in _roles(sb_client, a) and "admin" in _roles(sb_client, b)


def test_non_admin_cannot_revoke_admin(sb_client, cursor, chapter_id, member_factory):
    admin, officer = member_factory(), member_factory(role="officer")
    _make_admin(cursor, chapter_id, admin)
    _assign(sb_client, chapter_id, officer, "officer", admin)
    with pytest.raises(psycopg2.Error, match="rbac_ceiling"):
        _revoke(sb_client, chapter_id, admin, "admin", officer)


def test_officer_can_still_grant_ordinary_roles(sb_client, chapter_id, member_factory):
    officer, target = member_factory(role="officer"), member_factory()
    _assign(sb_client, chapter_id, officer, "officer", officer)
    assert _assign(sb_client, chapter_id, target, "treasurer", officer).data["role_key"] == "treasurer"
```

In `tests/chapters/test_create_chapter.py`, next to the existing happy-path test, add `test_creator_becomes_admin`: after creating a chapter through the same call that test uses, the first officer has `member_roles` rows for both `officer` and `admin`.

- [ ] **Step 2: run, expect FAIL** (no exception raised; creator has no admin row). If `test_officer_cannot_grant_admin_or_president` passes on the untouched branch, report F-023 `NOT_REPRODUCED`.
- [ ] **Step 3: migration `0164_rbac_admin_tier.sql`, part 1 (who is admin).**

```sql
-- D8: every existing chapter gets one admin: its earliest officer who can still log in.
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT DISTINCT ON (m.chapter_id) m.chapter_id, m.id, 'admin'
  FROM members m
  JOIN member_roles mr
    ON mr.member_id = m.id AND mr.chapter_id = m.chapter_id AND mr.role_key = 'officer'
 WHERE m.status IN ('active', 'invited')
   AND NOT EXISTS (SELECT 1 FROM member_roles a
                    WHERE a.chapter_id = m.chapter_id AND a.role_key = 'admin')
 ORDER BY m.chapter_id, m.created_at, m.id
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;
```

  Then `ch_create_chapter`: copy the live body from `migrations/0156_chapter_onboarding.sql:21-` (keep `SECURITY DEFINER`, `SET search_path`, signature and return shape) and, right after the statement that inserts the first officer's `member_roles` row, add:

```sql
    INSERT INTO member_roles (chapter_id, member_id, role_key)
    SELECT v_chapter_id, v_member_id, 'admin'
     WHERE EXISTS (SELECT 1 FROM roles WHERE key = 'admin');
```

  Use the function's real variable names.
- [ ] **Step 4: migration, part 2 (the ceiling).** Re-create `rbac_assign_role` and `rbac_revoke_role` from their bodies in `0162` (your Task 2 versions). In BOTH, directly after the idempotency replay block and the member-in-chapter check, add:

```sql
    IF p_role_key IN ('admin', 'president')
       AND NOT EXISTS (
            SELECT 1 FROM member_roles
             WHERE chapter_id = p_chapter_id AND member_id = p_actor_id AND role_key = 'admin')
    THEN
        RAISE EXCEPTION 'rbac_ceiling: only an admin may grant or revoke %', p_role_key;
    END IF;
```

- [ ] **Step 5: map the errors.** Wrap the two `call_rpc` calls in `api/rbac/services/assignments.py`: catch the database error; when its message contains `rbac_ceiling` raise `HTTPException(403, "Only an admin can grant or revoke that role")`; when it contains `rbac_last_admin` (Task 4) raise `HTTPException(409, "The chapter must keep at least one admin. Make someone else an admin first.")`; re-raise anything else. If the service layer has no FastAPI import today, do the mapping in `api/rbac/api/roles.py` instead. Add a route-level test for the 403.
- [ ] **Step 6:** do not apply `0164` yet; Task 4 adds one more block to it. Suggested message for this task's changes: `fix(rbac): chapter creators are admins; only an admin grants admin or president`.

---

### Task 4: the last admin cannot be removed

**Files:** `migrations/0164_rbac_admin_tier.sql`, `tests/rbac/test_authority.py`

Write Task 3 and Task 4 into `0164` before you apply it, so the file is applied once and complete.

- [ ] **Step 1: failing tests**

```python
def test_last_admin_cannot_step_down(sb_client, cursor, chapter_id, member_factory):
    only = member_factory()
    _make_admin(cursor, chapter_id, only)
    with pytest.raises(psycopg2.Error, match="rbac_last_admin"):
        _revoke(sb_client, chapter_id, only, "admin", only)
    assert "admin" in _roles(sb_client, only)


def test_revoking_a_role_not_held_is_still_a_noop(sb_client, cursor, chapter_id, member_factory):
    only = member_factory()
    _make_admin(cursor, chapter_id, only)
    assert _revoke(sb_client, chapter_id, only, "secretary", only).data["revoked"] is False


def test_an_inactive_admin_does_not_count_as_the_remaining_admin(sb_client, cursor, chapter_id, member_factory):
    a, b = member_factory(), member_factory()
    _make_admin(cursor, chapter_id, a)
    _make_admin(cursor, chapter_id, b)
    cursor.execute("UPDATE members SET status = 'inactive' WHERE id = %s", (b,))
    with pytest.raises(psycopg2.Error, match="rbac_last_admin"):
        _revoke(sb_client, chapter_id, a, "admin", a)
```

- [ ] **Step 2: run, expect the first and third to FAIL.**
- [ ] **Step 3: implement.** In `rbac_revoke_role`, after the `DELETE … RETURNING * INTO v_row;` and before the audit insert:

```sql
    IF v_row.id IS NOT NULL AND p_role_key = 'admin' AND NOT EXISTS (
        SELECT 1
          FROM member_roles mr
          JOIN members m ON m.id = mr.member_id
         WHERE mr.chapter_id = p_chapter_id
           AND mr.role_key = 'admin'
           AND m.status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'rbac_last_admin: chapter % must keep at least one admin', p_chapter_id;
    END IF;
```

  The `RAISE` aborts the function's transaction, so the delete is undone.
- [ ] **Step 4: apply `0164` (`python3 scripts/migrate_db.py`), run `tests/rbac tests/members tests/chapters -q`, expect every Task 3 and Task 4 test to PASS. Checkpoint** — `fix(rbac): a chapter always keeps at least one admin`.

---

### Task 5: F-006 — roster import stops stamping officer

**Files:** `migrations/0163_roster_import_role.sql`, `tests/chapters/test_roster_import.py`

- [ ] **Step 1: failing test.** In `test_roster_import.py`, next to `test_optional_role_column_grants_the_catalog_role` (line ~63), add `test_non_officer_role_keeps_legacy_column_member`: import one row with role `treasury_viewer` and one with `social_chair` using the same helper that test uses; assert each member's `members.role == 'member'`, each has exactly one `member_roles` row with the CSV key, and `get_member_permissions` for the `treasury_viewer` member does not contain `roles:assign`. Add a second test: a row with role `officer` gets `members.role == 'officer'` and an `officer` row.
- [ ] **Step 2: run, expect FAIL** (`role == 'officer'`).
- [ ] **Step 3: implement.** Copy the live `ch_import_roster` from `migrations/0157_sms_consent.sql:29-` into `0163`, and change the `CASE` to:

```sql
            CASE WHEN v_row->>'role_key' = 'officer' THEN 'officer' ELSE 'member' END,
```

- [ ] **Step 3b: the import cannot hand out top roles.** A CSV row with role `admin` or `president` would bypass the admin tier. In the same function, at the top of the per-row loop add `IF v_row->>'role_key' IN ('admin', 'president') THEN RAISE EXCEPTION 'rbac_ceiling: top roles cannot be set by roster import'; END IF;`. In `api/chapters/services/onboarding.py` (`parse_roster_csv`, ~lines 118-141, where unknown role keys are already rejected) reject those two keys the same way unknown keys are rejected, with the message `admin and president cannot be set by import`. Add `test_import_rejects_top_roles` (a row with role `admin` → the import is refused and no member is created).
- [ ] **Step 4: apply, run `tests/chapters -q`, expect PASS.**
- [ ] **Step 5: checkpoint** — `fix(chapters): roster import only marks real officers as officer`.

---

### Task 6: F-033 — resolve permissions once per request

**Files:** `api/rbac/services/permissions.py`, `api/rbac/api/roles.py`, `tests/rbac/test_permission_cache.py`

The `user` dict returned by `get_current_user` lives for one request. Cache on it.

- [ ] **Step 1: failing test**

```python
from api.rbac.services import permissions as svc


class _Counting:
    def __init__(self, sb):
        self._sb, self.calls = sb, 0

    def table(self, name):
        self.calls += 1
        return self._sb.table(name)


def test_second_lookup_uses_the_request_cache(sb_client, chapter_id, member_factory):
    member = sb_client.table("members").select("*").eq("id", member_factory()).single().execute().data
    counting = _Counting(sb_client)
    first = svc.get_member_permissions(member, sb=counting)
    after_first = counting.calls
    assert svc.get_member_permissions(member, sb=counting) == first
    assert svc.has_permission(member, "tasks:complete", sb=counting) in (True, False)
    assert counting.calls == after_first
```

- [ ] **Step 2: run, expect FAIL** (`calls` grows).
- [ ] **Step 3: implement.** In `get_member_permissions`:

```python
    cached = member.get("_rbac")
    if cached is None:
        keys = list_member_role_keys(client, chapter_id=member["chapter_id"], member_id=member["id"])
        cached = member["_rbac"] = {
            "roles": sorted(keys),
            "permissions": frozenset(list_permissions_for_roles(client, sorted(_effective_role_keys(member, keys)))),
        }
    return set(cached["permissions"])
```

Add `def get_member_role_keys(member, *, sb=None) -> list[str]` that calls `get_member_permissions` and returns `member["_rbac"]["roles"]`; use it in `get_my_permissions` (`api/rbac/api/roles.py:28-36`) in place of the second `list_member_role_keys` read.

- [ ] **Step 4: leak check.** Run `grep -rnE "return user$|return \{\*\*user|\"user\": user" api`. If any route returns the raw user dict, strip keys starting with `_` there and add that file to your report. (None did on 2026-10-05.)
- [ ] **Step 5: run `tests/rbac -q`, expect PASS; checkpoint** — `perf(rbac): resolve a member's permissions once per request`.

---

### Task 7: F-052 — delete `FakeSb`

**Files:** `tests/rbac/test_permissions_service.py`, `tests/rbac/test_one_gate.py`

- [ ] **Step 1:** in both files, replace `FakeSb` / `_Query` / `rbac_on_fake` with the real `sb_client`: create the member with `member_factory`, grant the role with `rbac_assign_role` (or a `member_roles` insert through `cursor`), monkeypatch `permissions_service.get_db` to return `sb_client`, and keep every assertion. Add one test the fake could never fail: a member of chapter A with `officer` in chapter A holds no officer permission when the member dict's `chapter_id` is swapped to chapter B.
- [ ] **Step 2: run `tests/rbac -q`, expect PASS.** `grep -rn "FakeSb" tests/` must print nothing.
- [ ] **Step 3: checkpoint** — `test(rbac): exercise the resolver against the real catalog`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
