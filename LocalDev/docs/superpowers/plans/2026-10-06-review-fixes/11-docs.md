# Plan 11 — Docs Implementation Plan (wave 3)

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. You branch from a `main` that already contains waves 1–2 — **verify every statement you write against that code**, not against the review text. Reproduce-first here means: confirm the doc claim is wrong against the current code before changing it, and confirm your replacement is right the same way.

**Goal:** every claim the review flagged is made true against the merged code.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §17, plus §07's CLAUDE.md note and §18's runbook note.
**Migrations:** none. **Allowed files:** `*.md` only (root `CLAUDE.md`, `LocalDev/CLAUDE.md`, `LocalDev/CONTEXT.md`, `LocalDev/CODEMAP.md`?, everything under `LocalDev/docs/` incl. `adr/`). No code changes of any kind.

Decision D-R2 (user): the "prod `DATABASE_URL` points at demo" note in `LocalDev/CLAUDE.md` is **correct and stays** — do not change it, and do not "fix" docs to say prod has real data.

## Task 1 — RV-17-1 (P2, F-041 completion): CI drift check and wrong script path

- [ ] Root `CLAUDE.md:4-5` and `LocalDev/docs/ARCHITECTURE.md:37`: the drift check does **not** run in CI yet (verify: `grep -rn build_prod .github/ 2>/dev/null`), and the path is `LocalDev/scripts/build_prod.sh`, not `scripts/build_prod.sh`. Say what is true today ("planned CI drift check" phrasing is fine if it is actually planned).

## Task 2 — RV-17-2/3 (P2): the frontend spec points at the archived app

- [ ] `ARCHITECTURE.md:10`: `FrontendConventions.md` describes the archived Next.js app. Either repoint to the real greekos conventions (the Frontend sections of `LocalDev/CLAUDE.md` / an existing greekos doc) or mark `FrontendConventions.md` itself as historical in one line at its top.
- [ ] `docs/services/service-map.md:8, 19`: remove/replace `fratos/lib/api-client.ts` and the `FineToInvoice` float-to-cents claim with the current path (fines → invoices via the `tr_*` RPCs; verify in code).
- [ ] `ARCHITECTURE.md` §3: `Money.from_numeric` claim — verify its one real caller (`grep -rn from_numeric api/`) and describe that.

## Task 3 — RV-17-4..7 (P3): CONTEXT, CODEMAP, Conventions table

- [ ] `CONTEXT.md:118-120`: fix the "Heartbeat" definition (verify against `api/cron` code) and add the missing "top role" entry.
- [ ] `CODEMAP.md`: delete the Sidebar "chapter switcher" mention; add `api/platform/errors.py` and `api/platform/outbox.py` (verify both exist and describe their real role).
- [ ] `LocalDev/CLAUDE.md` Conventions table lines 213, 216-217, 219-220: for each, read the code it describes; make the row true or delete it. List each changed row in your report.

## Task 4 — RV-17-8..10 (P3): ARCHITECTURE and TREASURY_ARCHITECTURE staleness

- [ ] `ARCHITECTURE.md`: JWT `sub` is `member_id` (verify in `api/platform/postgres.py` `_LocalAuth`); writes go through owner-connection RPCs/`transaction()`, not "service-role RPCs"; "RPCs for all multi-row writes" must mention `transaction()` (the split is: trust-boundary writes → RPC, other multi-statement writes → `transaction()`).
- [ ] `TREASURY_ARCHITECTURE.md` §3, §10, §11: add the treasury RPCs, routes and migrations introduced since (0165–0215 range; list from `fn-index.txt` in this folder + `git log --oneline -- migrations/` if helpful).
- [ ] "RLS on 43 tables": count the real number (`grep -c "ENABLE ROW LEVEL SECURITY" migrations/*.sql` minus disables — or trust the review's 45 only after verifying) and fix everywhere it appears (`grep -rn "43 tables" CLAUDE.md LocalDev/`).

## Task 5 — RV-17-11 (P3): historical claims

- [ ] `docs/adr/0002-…`: the historical path should read `api/db.py`.
- [ ] The prod-`DATABASE_URL` note: **no change** (D-R2). Mark the review item closed in your report as `FIXED — closed by decision D-R2, no edit`.

## Task 6 — RV-07-4 and RV-18-4: the two notes other streams left to docs

- [ ] `LocalDev/CLAUDE.md` (Migrations section): add one line — after adding a migration, run `python3 scripts/migration_checksums.py --update`.
- [ ] `LocalDev/docs/ops-runbook.md`: in the purge runbook section, add that each purge batch takes write locks on every triggered table — run it only when no tests/agents are using the demo DB.

## Final checkpoint

- [ ] Every edited claim was verified against code; nothing else reworded. List file → claim → evidence (file:line you checked) in your report.
