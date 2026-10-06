# Plan 06 — Ops & CI tooling Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** a `Prod/` sync can't delete production-owned files, its test survives the sync, and `migrate_db --prod` touches nothing before the operator confirms.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §18, §07 (all but the CLAUDE.md doc note — that's plan 11).
**Migrations:** none. **Never run the actual `Prod/` sync** — tests use temp dirs via `PROD_DIR` only.

**Allowed files:** `LocalDev/scripts/build_prod.sh`, `LocalDev/scripts/migrate_db.py`, `local-dev-scripts/scripts/local-dev.sh`, `tests/test_build_prod.py`, `tests/test_migrate_history.py`.

## Task 1 — RV-18-1 (P1): a sync would delete `Prod/fratos/vercel.json`

`LocalDev/scripts/build_prod.sh:6,75`: the `KEEP` list preserves only **top-level** entries of `$TARGET`, and staging's `fratos/` is built purely from `greekos/` (which has no `vercel.json`). So `rsync --delete` removes the tracked `Prod/fratos/vercel.json` — the file keeping git deploys off for the fraternity-os project — and auto-deploys would silently come back.

- [ ] Failing test first, in `tests/test_build_prod.py`: build into a temp `PROD_DIR` that contains a pre-existing `fratos/vercel.json` with `{"git": {"deploymentEnabled": false}}`; run the sync; assert the file still exists with `deploymentEnabled` false. Must fail untouched.
- [ ] Fix: support nested keep paths. Concretely: after the `greekos/ → staging/fratos/` rsync, if `$TARGET/fratos/vercel.json` exists, copy it into `$STAGING/fratos/` (same retained-byte-for-byte idea as top-level `vercel.json`); also force `deploymentEnabled=false` into it with the same python pattern used for the top-level file, so a hand-edited true can't slip through.
- [ ] Checkpoint: `python3 -m pytest tests/test_build_prod.py -q`.

## Task 2 — RV-18-2 (P2): `test_build_prod` only passes while `Prod/` has drifted

`tests/test_build_prod.py:25` asserts against the real `Prod/` drift, so it will start failing the day the sync runs.

- [ ] Rewrite the test to create its **own** drift inside a temp copy (temp `PROD_DIR` seeded with a stale file + an extra file), run `--check` and the sync against that, and assert on the temp result. No test reads the real `Prod/`.
- [ ] Checkpoint: `python3 -m pytest tests/test_build_prod.py -q`.

## Task 3 — RV-18-3 (P3): `--exclude='.env*'` drops the tracked `.env.example`

`build_prod.sh:37`: the greekos rsync excludes `.env*`, so a sync would delete `Prod/fratos/.env.example`.

- [ ] Failing test first (temp-dir sync: `greekos/.env.example` must land in `fratos/`, a `greekos/.env` must not), then fix with rsync order-sensitive filters: `--include='.env.example' --exclude='.env*'`.
- [ ] Checkpoint: `python3 -m pytest tests/test_build_prod.py -q`.

## Task 4 — RV-07-1 (P2): `migrate_db.py --prod` writes before the operator confirms

`scripts/migrate_db.py:94, 179-185`: it adds the checksum column and backfills it — committing both — before the confirmation prompt at 197-205 and before refusing an unknown history.

- [ ] Failing test first in `tests/test_migrate_history.py`: drive `main()` (monkeypatched DB/connection or the test database with a scratch `schema_migrations` clone — follow the file's existing style) with a refusing answer at the prompt; assert **no** DDL/UPDATE ran before it. Must fail untouched (the ALTER happens first today).
- [ ] Fix: reorder `main()` — read-only history check (including the unknown-history refusal) first, then the prompt, then the ALTER + backfill + migrations. The non-`--prod` path keeps today's behaviour.
- [ ] Checkpoint: `python3 -m pytest tests/test_migrate_history.py -q`.

## Task 5 — RV-07-3 (P3): the `main()` exits are untested

- [ ] Add tests for the two refusal exits: an edited migration (checksum mismatch) and an unknown production history. Same harness style as Task 4; assert exit code/message and that nothing was applied.
- [ ] Checkpoint: `python3 -m pytest tests/test_migrate_history.py -q`.

## Task 6 — RV-07-2 (P2): the dependency stamp misses venv/python changes

`local-dev-scripts/scripts/local-dev.sh:204-210`: the stamp hashes only `requirements.txt`, so a fresh venv or a different `python3` never reinstalls, and bare `pip` may belong to another interpreter.

- [ ] Fix: stamp = hash of `requirements.txt` **plus** `python3 -V` output **plus** the resolved interpreter path (`command -v python3` / `$VIRTUAL_ENV`); install with `python3 -m pip install -r requirements.txt` instead of bare `pip`.
- [ ] Runnable check (no pytest for shell): `bash -n local-dev-scripts/scripts/local-dev.sh` passes, and show in your report the stamp value changing when `VIRTUAL_ENV`/interpreter changes (evaluate just the stamp lines with `bash -c`, do not run the full dev stack).

## Final checkpoint

- [ ] `python3 -m pytest tests/test_build_prod.py tests/test_migrate_history.py -q` — paste the final count line.
