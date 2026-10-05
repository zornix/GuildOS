# 18 · Production reproducibility and housekeeping (orchestrator runs this one)

> Executed by the orchestrating Fable session itself, not dispatched. It touches `Prod/`, which is the Vercel root of the live site, so every step that changes `Prod/` or needs the production database stops for the user's explicit go-ahead.

**Stream:** `18-prod-and-ops` · **Wave:** 3 (code) and after wave 4 (the sync itself) · **Branch:** `fix/audit-18-prod-ops`
**Findings:** F-010, F-069, R-08, the human half of F-016, F-038 and F-008
**Goal:** `Prod/` becomes something a script produces from `LocalDev/`, and CI fails when the two drift. The demo database can be cleaned of test chapters. Nothing is deployed and the production database is not touched without the user.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-010, F-016, F-069; decision D22 in `00-README.md`; memory notes "Manual deployments" and "Vercel state + prod DB".

## Facts

- `Prod/vercel.json` builds `api/index.py` (`@vercel/python`) and `fratos/package.json` (static build, `distDir: dist`), has the 5-minute cron, and sets `git.deploymentEnabled=false`. `LocalDev/vercel.json` is the same file with `greekos/` in place of `fratos/` and without the `git` block.
- `Prod/api` is a hand copy from 2026-09-08: 19 files differ, 21 are missing. `Prod/fratos` is an older copy of `LocalDev/greekos`. `Prod/migrations` has 2 files; `LocalDev/migrations` is the real history.
- `scripts/db_guard.py:PROD_PROJECT_REFS` is empty, so `migrate_db.py --prod` refuses to run. After stream 07 it also refuses a database whose `schema_migrations` holds names this tree lacks.
- The production database holds real user data. Its migration state is unknown.

## Tasks

### Task 1: `scripts/build_prod.sh` (F-010)

- [ ] Write `LocalDev/scripts/build_prod.sh [--check]`. It produces, in a temp dir, exactly what `Prod/` should contain: `api/` ← `LocalDev/api/` (excluding `__pycache__`); `fratos/` ← `LocalDev/greekos/` (excluding `node_modules`, `dist`, `.env*`); `migrations/` ← `LocalDev/migrations/`; `scripts/` ← the scripts `Prod/` needs (`migrate_db.py`, `db_guard.py`, `migration_checksums.py`, `check_prod_status.py`); `requirements.txt` ← `LocalDev/requirements.txt` without the `pytest*` lines; `vercel.json` ← `LocalDev/vercel.json` with `greekos` → `fratos` and the `git.deploymentEnabled=false` block added. Files that exist only in `Prod/` and are deliberately its own (`README.md`, `package.json`, `secrets/`, `.vercel/`) are left alone; list them in an `KEEP` array at the top of the script.
  - Without a flag: `rsync -a --delete` the temp dir over `Prod/` (respecting `KEEP`).
  - With `--check`: `diff -rq` the temp dir against `Prod/`, print differences, exit 1 if any.
- [ ] Test: `LocalDev/tests/test_build_prod.py` runs the script with `PROD_DIR` pointed at a temp copy, asserts `--check` fails before a build and passes after, and asserts `KEEP` entries survive.
- [ ] CI: add a step "Prod is built from LocalDev" running `bash LocalDev/scripts/build_prod.sh --check`. **Do not add this step until Task 4 has run**, or CI fails on today's drift.
- [ ] Commit — `feat(prod): build Prod/ from LocalDev with a drift check`

### Task 2: demo database cleanup (F-069)

- [ ] `LocalDev/scripts/purge_test_chapters.py`: `require_demo` first (never runs against prod). Selects chapters whose name starts with a test prefix (`tr-test-` from `tests/treasury/conftest.py`; add the prefixes other conftests use after grepping `INSERT INTO chapters` in `tests/`) and are older than `--older-than-days` (default 2). Default is a dry run that prints counts per table. With `--apply`: in one transaction, disable the append-only delete triggers on the tables that block the cascade (`big_ledger`, `audit_logs`, receipts, allocations, evidence, line items, send logs, swap requests), delete the chapters (cascade), re-enable the triggers. Print before/after row counts.
- [ ] Test (pure): the name filter matches test chapters and not `Alpha Beta` or a real demo chapter name.
- [ ] Run the dry run against the demo DB and put the counts in the final summary. `--apply` only on the user's go-ahead.
- [ ] Commit — `chore(scripts): purge old test chapters from the demo database`

### Task 3: local residue (R-08)

- [ ] In the main checkout (not a worktree), list untracked leftovers: `git status --short --ignored | grep -E "__pycache__|LocalDev/fratos|api/standing"`. Move `LocalDev/fratos/{.next,node_modules}` and `api/standing/` leftovers to `archive/residue-2026-10/` (gitignored); delete `__pycache__` directories whose package no longer has source files. Nothing tracked changes; no commit.

### Task 4: sync `Prod/` (needs the user's go-ahead)

Run only after waves 1–4 are merged and the full suite is green on `main`.

- [ ] Show the user `build_prod.sh --check` output (what will change in `Prod/`).
- [ ] On go-ahead: run `build_prod.sh`, run `Prod`'s own smoke (`python3 -c "import api.index"` from `Prod/` with `APP_ENV=test`), commit `chore(prod): rebuild Prod/ from LocalDev`, then add the CI step from Task 1.
- [ ] This commit does not deploy (git deploys are off). Deploying is a separate, manual decision.

### Task 5: human checklist (handed to the user, not executed)

Write these into the final summary and into `LocalDev/docs/ops-runbook.md` under "Before the next production deploy":

1. Read the production migration state: `SELECT name FROM schema_migrations ORDER BY 1` on the prod database. Paste the result into `LocalDev/docs/ops/prod-migration-state.md` with the date.
2. Take a Supabase backup and note the time.
3. Put the prod project ref into `scripts/db_guard.py:PROD_PROJECT_REFS`.
4. If prod's history is only the two old `Prod/migrations` files: do not run `migrate:prod` (it now refuses, by design). Plan the cut-over separately (restore-then-migrate on a copy first).
5. Vercel env: set `BASE_URL`, `FRONTEND_URL` to the public origins; confirm `JWT_SECRET`, `CRON_SECRET`, `DATABASE_URL`; `DEV_AUTH_BYPASS` unset.
6. Supabase dashboard: confirm the Data API is disabled; record backup retention and PITR in the runbook.
7. Local: add `APP_ENV=local` to `LocalDev/.env`; delete the nine unused names listed in the stream 13 report.
