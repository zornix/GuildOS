# Plan 05 — DB guards Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** finish F-042 and F-054, extend the inactive-member guard to supervisors (decision D-R3), and stop over-locking initiatives.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §04.
**Migrations:** 0211–0212.

**Allowed files:** `migrations/0211_*.sql`, `migrations/0212_*.sql`, `tests/events/*` and `tests/initiatives/*` **new files only** (`test_swap_lock.py`, `test_member_status_guards.py` — don't edit plan 04's test files). DB functions you own: `ev_accept_security_swap` (live: 0175), `in_create_initiative` (live: 0144), `ev_create_event` + `ev_add_supervisor` (live: 0141), and the chair-lock functions from 0174 (`fn-index.txt` confirms; last definition wins).

## Task 1 — RV-04-1 (P2, F-042 completion): `ev_accept_security_swap` takes no lock

`migrations/0175_inactive_member_guards.sql:200-272`: acceptance never takes the `ev_security:<event>` advisory lock, so two concurrent accepts can double-assign a member. 0175 already has a taker to copy: `pg_advisory_xact_lock(hashtext('ev_security:' || p_event_id::text))` (see `ev_assign_security`'s current form).

- [ ] Failing test first, `tests/events/test_swap_lock.py`, modelled on the existing `test_assign_security_takes_the_event_lock`: hold the `ev_security:<event>` advisory lock from a second connection with a short `SET LOCAL lock_timeout` on the function's side — assert accepting a swap blocks on/respects that lock after the fix, and does not today. (Non-autocommit connections + `SET LOCAL`, not session-level `SET` — see plan 02 Task 2's flakiness lesson.)
- [ ] `migrations/0211_guard_completions.sql` part 1: `CREATE OR REPLACE FUNCTION ev_accept_security_swap` (0175 live body as base) taking the advisory lock first thing after resolving the event, before reading assignments.
- [ ] Apply, update checksums, test → PASS.

## Task 2 — RV-04-2 (P2, F-054 completion): inactive/alumni members can become initiative co-chairs

`migrations/0144_initiatives_v1.sql:103-123`: `in_create_initiative` checks co-chairs only for chapter membership, not status, so creation bypasses the active-only rule that `in_add_chair` enforces.

- [ ] Failing test first, `tests/initiatives/test_member_status_guards.py` (own chapter): member with status `inactive` (and one `alumni`) passed in `p_chair_member_ids` → today creation succeeds; after the fix it raises the same error `in_add_chair` uses for status.
- [ ] `migrations/0211_guard_completions.sql` part 2: `CREATE OR REPLACE FUNCTION in_create_initiative` (0144 live body; note its `p_chair_member_ids UUID[]` is array-typed and registered in `_ARRAY_TYPED_RPC_PARAMS` — signature must not change) adding the status check, same error text as `in_add_chair`.
- [ ] Apply, test → PASS.

## Task 3 — RV-04-3 (P3, decision D-R3): supervisors get the active-status check

User decision: inactive members lose participation; supervisors are covered like chairs and security. Alumni/inactive product design is TBD — add only the status check, nothing else.

- [ ] Failing tests first in `test_member_status_guards.py`: `ev_create_event` with an inactive supervisor, and `ev_add_supervisor` adding an inactive member → both succeed today, must raise after.
- [ ] `migrations/0212_supervisor_status_guard.sql`: `CREATE OR REPLACE` both functions (0141 live bodies as base) with the same status predicate the other 0175 guards use (reuse its error message style).
- [ ] Apply, update checksums, tests → PASS.

## Task 4 — RV-04-4 (P3): `FOR UPDATE` on `initiatives` blocks unrelated child inserts

`migrations/0174_initiative_chair_locks.sql:20,84`: the chair-lock functions take `FOR UPDATE` on the initiative row; `FOR NO KEY UPDATE` suffices and stops blocking FK child inserts.

- [ ] No practical failing test for the lock strength; reproduce-first exemption — report `PARTIAL — lock weakened, untestable` unless you find a cheap probe. Existing initiative tests are the net.
- [ ] In `migrations/0212_supervisor_status_guard.sql` (same file, keep 0211/0212 to two files total): `CREATE OR REPLACE` the 0174 functions with `FOR NO KEY UPDATE`.
- [ ] Checkpoint: `python3 -m pytest tests/initiatives/ tests/events/ -q` — paste the final count line.

## Task 5 — RV-04-5 (P3): flaky `test_assign_security_takes_the_event_lock`

Failed once under shared-DB load, passes alone. While writing Task 1's sibling test, check whether the existing test uses session-level `SET lock_timeout` on an autocommit/pooler connection; if so, convert it to the `SET LOCAL` + non-autocommit pattern (report under EXISTING TESTS CHANGED). If it already does, change nothing and note it.
