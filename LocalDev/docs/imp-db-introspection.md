# Implementation plan — introspecting db client (kill the hand registries)

Date: 2026-07-11
Order: step 5 of 7. Depends on: `imp-platform-module.md` (the client now
lives at `api/platform/postgres.py`). Independent of `imp-one-gate.md`.
Scope: `api/platform/postgres.py` + tests. No call-site changes required.

Contract: decisions settled here; implementer executes as written, reports
drift. Context shift since the review: per ADR-0002 this client serves
*production*, so a silently dropped join is a production bug (the `$NaN`
fines feature was exactly this class), not a local-dev quirk.

## Settled decisions

- **D1 — Metadata comes from the database, not from hand lists** (decided
  2026-07-11). At connect time the client introspects `pg_catalog` once and
  deletes all three registries: `FK_MAP` (6 tables), `JOIN_STAR_COLUMNS`
  (3 tables), `_ARRAY_TYPED_RPC_PARAMS` (1 entry + apology comment).
- **D2 — Anything the client can't honour raises loudly at the call site,
  naming the gap.** The silent `continue` for unknown join targets is the
  bug; it dies. No query shape may silently return less than it asked for.
- **D3 — The embed-string interface stays.** Call sites keep writing
  `select("*, members(name)")`; only the resolution mechanism changes. The
  fines Python-stitch from candidate 2 also stays (tests pin it) — reverting
  it to an embed is an optional follow-up, not part of this plan.
- **D4 — Ambiguity is an error, not a guess.** If two tables are linked by
  more than one FK and an embed doesn't disambiguate, raise naming the
  candidate constraints. (Audit the current embed call sites first; if any
  would newly hit this, list them in the drift report.)

## Steps

1. In `PostgresClient.__init__` (after the `ThreadedConnectionPool` is
   built), borrow one connection (the `ping()` pattern) and load, in a single
   round-trip if convenient:
   - **FK graph**: `pg_constraint` (`contype = 'f'`) joined to `pg_class` /
     `pg_attribute` → for each constraint: source table, source column(s),
     target table, constraint name. Build the relationship map in both
     directions (many-to-one embed and its reverse), replacing `FK_MAP`.
   - **Column lists** per public table (`pg_attribute`, `attnum > 0`, not
     dropped) → replaces `JOIN_STAR_COLUMNS` for expanding `related(*)` on
     any table.
   - **Array-typed function params**: `pg_proc` (public schema) with
     `proargnames`/`proargtypes` joined to `pg_type` where
     `typcategory = 'A'` → set of `(function_name, arg_name)` needing real
     array binding, replacing `_ARRAY_TYPED_RPC_PARAMS`. Non-array list/dict
     params keep the existing JSON encoding (JSONB behavior unchanged).
2. Rewrite embed resolution (`postgres.py` ~lines 189-206): unknown
   relationship → raise (D2, message: the two tables, plus "no foreign key
   found — add one or stitch in Python"); multiple candidate FKs → raise (D4);
   registered star-expansion limit disappears (introspected columns cover
   every table).
3. Cache the metadata on the client instance (one process-lifetime load,
   matching the pooled singleton from `platform.db`). Schema changes require
   a process restart — same as today; note it in the module docstring.
4. Delete the three registries and the `_ARRAY_TYPED_RPC_PARAMS` comment
   block; update the `CLAUDE.md` paragraph that instructs adding entries to
   `_ARRAY_TYPED_RPC_PARAMS` (that chore no longer exists).
5. Tests (real DB via `TEST_DATABASE_URL`, like the rest of the suite):
   - An embed that the old `FK_MAP` did **not** cover resolves correctly
     (e.g. `unpaid_invoices` → `members(name)` — the exact join whose silent
     drop caused the `$NaN` bug).
   - An embed against a table pair with no FK raises with the D2 message.
   - `related(*)` works on a table absent from the old `JOIN_STAR_COLUMNS`.
   - The `in_create_initiative.p_chair_member_ids UUID[]` RPC still works
     with the registry gone (existing initiatives tests may already cover
     this — confirm, don't duplicate).
   - A JSONB-param RPC still receives JSON (pin that introspection didn't
     over-reach).

## Verification

`python3 -m pytest` full suite green — this is the strongest check, since
every domain's queries run through the rewritten resolution. `npm run dev`
boots; exercise the events and fines pages (embed-heavy paths).

One commit: `feat(platform): introspect FK/array metadata from pg_catalog; unhonourable queries raise instead of silently dropping`
