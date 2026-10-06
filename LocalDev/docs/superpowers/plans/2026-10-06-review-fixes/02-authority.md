# Plan 02 — Authority Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** a provisioned chapter always has an admin; the revoke path locks before it checks; no stale role comments.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §02.
**Migrations:** 0206 only.

**Allowed files:** `scripts/provision_chapter.py`, `tests/rbac/test_authority.py`, new `tests/rbac/test_provision_roles.py`, `migrations/0206_*.sql`, and the comment-only edits in Task 4's list.

## Task 1 — RV-02-1 (P1): `provision_chapter.py` creates a chapter nobody can administer

`scripts/provision_chapter.py:282-291` (`_grant_officer_role`) inserts only an `officer` row into `member_roles`. D8: `admin` and `president` are granted/revoked only by an admin — so a chapter provisioned this way can never change its admin tier. This is the path for the first production chapters.

- [ ] Failing test first, `tests/rbac/test_provision_roles.py`: using the test DB connection and a fresh test chapter + member, call the grant helper and assert `member_roles` holds **both** `officer` and `admin` rows for the officer (also assert the `roles` catalog has an `admin` key — migration 0083). It must fail on the untouched branch (no `admin` row).
- [ ] Fix: extend the helper (rename to `_grant_officer_roles` if you touch the name everywhere) to insert `officer` **and** `admin`, each `ON CONFLICT … DO NOTHING`, with the same catalog-existence warnings. Update the script header/docstring that describes what the provisioned officer can do.
- [ ] Checkpoint: `python3 -m pytest tests/rbac/ -q` passes.

## Task 2 — RV-02-2 (P2): flaky `test_admin_revoke_takes_the_chapter_lock`

`tests/rbac/test_authority.py:153-172`: `SET`/`RESET lock_timeout` on an **autocommit** cursor through the transaction pooler (port 6543) can land on a different server connection, and the setting can leak into the shared pool.

- [ ] Rewrite the lock-probe part of the test to use a non-autocommit connection and `SET LOCAL lock_timeout` inside its transaction (so the setting dies with the transaction and stays on one server connection). Behaviour asserted stays identical.
- [ ] Checkpoint: run the test 5× in a row: `for i in 1 2 3 4 5; do python3 -m pytest tests/rbac/test_authority.py -q || break; done` — all green.

## Task 3 — RV-02-3 (P3): revoke checks the caller's admin role before taking the chapter lock

`migrations/0203_rbac_revoke_admin_lock.sql:30-41` (live body of `rbac_revoke_role`, see `fn-index.txt`): the admin check runs before `pg_advisory_xact_lock`, so an admin demoted a moment earlier can still finish a revoke (the last-admin guard still holds, hence P3).

- [ ] Failing test is impractical for the race itself; instead pin the order: a test that the function source (via `pg_get_functiondef`) takes the lock before the first `member_roles` read is brittle — skip it. Reproduce-first exemption: treat as structural; say `PARTIAL — order fixed, race untestable` if you add no test, or keep the existing revoke tests as the net.
- [ ] `migrations/0206_rbac_revoke_lock_order.sql`: `CREATE OR REPLACE FUNCTION rbac_revoke_role` with the **0203 live body**, moving the chapter advisory lock acquisition above the caller-is-admin check. No signature change. Apply with `python3 scripts/migrate_db.py`, then `python3 scripts/migration_checksums.py --update`.
- [ ] Checkpoint: `python3 -m pytest tests/rbac/ -q` passes.

## Task 4 — RV-02-4 (P3): comments still say `members.role` grants permissions

Comment-only edits (no code changes) — say instead that `members.role` is display-only and permissions come from `member_roles` via `api.rbac`:

- [ ] `api/announcements/services/sms.py:112-113`
- [ ] `api/announcements/services/announcements.py:126-127`
- [ ] `api/rbac/__init__.py:10-12`
- [ ] `api/members/api/members.py:94-96`
- [ ] Checkpoint: `python3 -m pytest tests/rbac/ -q` still green (comments can't break it; this catches accidental code edits).
