# Implementation plan — make reseed survive a used database

Date: 2026-07-12
Order: independent. Pairs naturally with `imp-docker-db-split-brain.md` (both
are dev-loop reliability), but neither depends on the other.
Scope: one dev-tooling script (`scripts/seed.py`). No product code, no schema
migration, no change to the deployed app.

Decisions are settled here; the implementer executes as written and reports
drift instead of improvising.

## Root cause (verified 2026-07-12, file:line evidence)

Reseeding on top of a database that already has demo data dies partway through
`_clear_demo_seed` and leaves the DB half-wiped.

- `_clear_demo_seed` (`seed.py:167-185`) disables the append-only USER triggers
  on `fines` (`:178`) and `big_ledger` (`:179`) before its deletes, but **not**
  on `audit_logs`.
- `audit_logs` carries an immutable trigger `audit_logs_immutable`
  (`migrations/0005_treasury_foundation_tables.sql:158-159`,
  `BEFORE UPDATE OR DELETE`) that blocks any UPDATE or DELETE.
- `audit_logs` FKs into the seeded rows two ways
  (`0005_…:78-81`): `chapter_id UUID NOT NULL REFERENCES chapters(id)
  ON DELETE CASCADE` and `actor_id UUID REFERENCES members(id)
  ON DELETE SET NULL`. So:
  - `DELETE FROM members …` (`seed.py:182`) fires `actor_id → NULL`, an UPDATE
    on `audit_logs` → blocked by the immutable trigger.
  - `DELETE FROM chapters …` (`seed.py:185`) cascades to a DELETE on
    `audit_logs` → also blocked.
- Because `conn.autocommit = True` (`seed.py:195`), there is no surrounding
  transaction. When a delete raises, the rows already deleted (verified_payments,
  expenses, invoices, excuses, attendance, checkin_links, big_ledger, events)
  are **committed**, and the run aborts with members/chapter still present —
  a corrupt half-seed that the next `seed` run also can't clean.

(On a fresh DB with zero demo `audit_logs` rows the SET NULL/CASCADE touch no
rows, so the trigger never fires — which is why this only bites on *re*seed.)

## Settled decisions

- **D1 — Extend the existing trigger-disable pattern to `audit_logs`.** The
  seed already owns the precedent (fines, big_ledger). Wrap the member/chapter
  deletes with `ALTER TABLE audit_logs DISABLE/ENABLE TRIGGER USER`, matching
  the big_ledger pair. Do not touch the trigger definition or the migration —
  the immutability guarantee for the real app is unchanged; this is a
  seed-only, session-scoped disable.
- **D2 — Make clear-and-reseed atomic.** Run the whole clear+insert under one
  transaction so a failure rolls back instead of committing a half-wipe. Set
  `conn.autocommit = False`, `commit()` once at the end, and `rollback()` on
  exception. Re-enabling triggers must happen even on the failure path.
- **D3 — Triggers re-enabled no matter what.** `DISABLE TRIGGER` is DDL and, on
  rollback, its effect on the session is not something to rely on; explicitly
  re-`ENABLE` in a `finally`/except path before closing so a partial run never
  leaves triggers disabled on a shared demo DB.

## Steps

1. In `_clear_demo_seed` (`seed.py:167-185`), add `audit_logs` to the
   disable/enable bracket that currently wraps only `fines` and `big_ledger`
   (`:178-183`). Concretely, before the member/chapter deletes:

   ```python
   cur.execute('ALTER TABLE fines DISABLE TRIGGER USER')
   cur.execute('ALTER TABLE big_ledger DISABLE TRIGGER USER')
   cur.execute('ALTER TABLE audit_logs DISABLE TRIGGER USER')
   cur.execute('DELETE FROM big_ledger WHERE chapter_id = %s', (CHAPTER_ID,))
   cur.execute('DELETE FROM audit_logs WHERE chapter_id = %s', (CHAPTER_ID,))
   cur.execute('DELETE FROM events   WHERE chapter_id = %s', (CHAPTER_ID,))
   cur.execute('DELETE FROM members  WHERE id IN %s', (demo_member_ids,))
   cur.execute('ALTER TABLE audit_logs ENABLE TRIGGER USER')
   cur.execute('ALTER TABLE big_ledger ENABLE TRIGGER USER')
   cur.execute('ALTER TABLE fines      ENABLE TRIGGER USER')
   cur.execute('DELETE FROM chapters WHERE id = %s', (CHAPTER_ID,))
   ```

   Note the explicit `DELETE FROM audit_logs … chapter_id` added before the
   `events`/`members` deletes: with the trigger disabled we remove the demo
   chapter's audit rows directly, so the later member SET NULL and chapter
   CASCADE touch nothing. (The chapter delete stays last; audit rows are gone
   by then.)

2. In `seed()` (`seed.py:188-198`), stop using autocommit for the mutating
   work. Change `conn.autocommit = True` (`:195`) to `conn.autocommit = False`,
   then wrap `_clear_demo_seed(cur)` **and** all the INSERT logic (through
   `:313`) in `try: … conn.commit()` / `except: conn.rollback(); raise`.

3. Guarantee triggers are re-enabled on the failure path. If step 1's inline
   re-enable can be skipped by an exception between disable and enable, add a
   defensive re-enable in the `except` before `rollback()`:

   ```python
   for t in ("audit_logs", "big_ledger", "fines"):
       try:
           cur.execute(f'ALTER TABLE {t} ENABLE TRIGGER USER')
       except Exception:
           pass
   conn.rollback()
   ```

   (Belt-and-suspenders — the happy path already re-enables in step 1.)

## Verification

- **Reseed twice.** Run `python -m scripts.seed` against a Docker/demo DB, then
  run it again immediately. The second run must complete and print the
  `=== Database seeded ===` summary — today it raises on the member delete.
- **Failure atomicity.** Temporarily inject a raise after the member insert
  loop, run seed, confirm the DB has **no** demo chapter/members afterward
  (rollback worked, not a half-seed). Remove the injected raise.
- **Triggers restored.** After a normal and a failed run, verify
  `audit_logs` / `big_ledger` / `fines` triggers are enabled
  (`SELECT tgenabled FROM pg_trigger WHERE tgname = 'audit_logs_immutable'`
  → `O`), and that a raw `DELETE FROM audit_logs` is once again blocked.
- Runs only against demo (the `require_demo` guard at `seed.py:190` is
  unchanged).
