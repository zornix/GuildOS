# Plan 04 — Events & platform Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** `update_event` survives the event-type race, `transaction()` never masks the real error, and cancelling an event cleans up swaps/claims and stops new check-in links.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §01, §11 (P2, the race dup, and the `events.py` half of the cancelled-event P3).
**Migrations:** 0210 only.

**Allowed files:** `api/platform/postgres.py`, `api/events/services/events.py`, `migrations/0210_*.sql`, `tests/platform/*`, `tests/events/*` (new files ok). DB function you own: the event-cancel function from `migrations/0181_event_cancel.sql` (confirm live name in `fn-index.txt`).

## Task 1 — RV-01-1 (P2, also reported by §11): event-type race inside `update_event` → 500

`api/events/services/events.py:57-62, 85-98, 715-719`: `resolve_event_type_id(tx)` runs inside a transaction; its helpers do try/except on a unique violation of the expression index `(chapter_id, lower(name))` on `event_types`. Catching inside the block leaves the transaction aborted (hard rule 2), so a concurrent insert of the same type name turns into a 500. `insert(..., ignore_conflict=...)` can't help today because it can't target an expression index.

- [ ] Failing test first, `tests/events/test_event_type_race.py` (own chapter): create event type `"Social"`; then inside `get_db().transaction()` call the resolve helper with `"social"` (forcing the insert-then-conflict path — if the helper checks before inserting, monkeypatch/arrange so the pre-check misses, e.g. insert the conflicting row from a second connection between check and insert, or call the internal insert step directly). Assert today it raises/aborts; after the fix the helper returns the existing type's id and the transaction commits.
- [ ] Fix in `api/platform/postgres.py`: let `insert()` accept `ignore_conflict=True` meaning a bare `ON CONFLICT DO NOTHING` (no target), alongside the existing column-target form. Keep the returning-rows semantics: a skipped insert returns no row — callers must then re-select.
- [ ] Fix the resolve helpers in `events.py`: inside a transaction, use `insert(..., ignore_conflict=True)` then re-select by `(chapter_id, lower(name))` — **no try/except on database errors inside the block**.
- [ ] Checkpoint: `python3 -m pytest tests/events/ -q`.

## Task 2 — RV-01-2 (P3): `transaction()`'s `finally` can mask the real error and leak a pool slot

`api/platform/postgres.py:654-674`: if `conn.autocommit = False` raises, `finally` touches `tx` before assignment → `UnboundLocalError` hides the original error and the connection never goes back to the pool.

- [ ] Failing test first, `tests/platform/test_transaction_cleanup.py`: monkeypatch the acquired connection so setting `autocommit` raises `RuntimeError("boom")`; assert the caller sees `boom` (not `UnboundLocalError`) and the pool slot is returned (pool count restored / putconn called — assert via monkeypatched pool).
- [ ] Fix: initialise `tx = None` before the `try` and guard the `finally` (`if tx is not None: …; always return the connection`).
- [ ] Checkpoint: `python3 -m pytest tests/platform/ -q`.

## Task 3 — RV-11-1 (P2): cancelling an event leaves pending swaps and active job claims

`migrations/0181_event_cancel.sql:37-38`: cancel doesn't resolve the event's pending security swaps or release its job claims. The security-cancel path in `migrations/0145` already does both — reuse its statements.

- [ ] Failing test first, `tests/events/test_event_cancel_cleanup.py` (own chapter): event with one **pending** security swap and one **claimed** job; cancel the event via the normal route/RPC; assert the swap is no longer pending (cancelled/declined per 0145's convention) and the claim is released. Must fail untouched.
- [ ] `migrations/0210_event_cancel_cleanup.sql`: `CREATE OR REPLACE` the live cancel function (0181 body as base), adding the swap-resolution and claim-release statements modelled on 0145's security-cancel path. Idempotent; apply; `python3 scripts/migration_checksums.py --update`.
- [ ] Checkpoint: test → PASS; `python3 -m pytest tests/events/ -q`.

## Task 4 — RV-11-4a (P3): a cancelled event still accepts new check-in links

`api/events/services/events.py:261-268` (link creation). The sessions/excuses halves belong to plan 07 (wave 2) — do not touch attendance files.

- [ ] Failing test first: cancel an event, then create a check-in link for it → expect a 409/422 domain error (match the file's existing named-exception pattern), not success.
- [ ] Fix: refuse when the event is cancelled, using the file's existing error-mapping style.
- [ ] Checkpoint: `python3 -m pytest tests/events/ -q` — paste the final count line.
