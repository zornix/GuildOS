# Review fixes — results (2026-10-06)

All 11 streams implemented by Codex `gpt-6.1-sol` (medium), each adversarially reviewed by
a Claude Opus agent, gaps fixed (Sol fixups or orchestrator hand edits), merged `--no-ff`
to `main`. Branches and worktrees deleted. Nothing pushed, nothing deployed, no `Prod/` sync.

## Outcome

- **68/68 unique issues closed** (71 review bullets, 3 double-reported). All three P1s fixed.
- **Migrations added:** 0206–0217 (no 0202; 0216 fixes 0210's lock order, 0217 fixes 0209's
  tiebreak — both found by Opus review before merge). All applied to demo; CHECKSUMS current.
- **Gates:** wave 1 full suite 1363 passed; wave 2 full suite **1426 passed, 0 failed**;
  frontend 153 tests + lint (`noUnusedLocals` now on) + build green; ruff clean.
- Review re-runs caught and fixed before merge, beyond the plans: refund same-timestamp
  tiebreak (uuid coin flip), event-cancel lock order (deadlock window), outbox stamp
  semantics (provider failures could fake "sent"), Retry on outcome-unknown rows,
  `provision_chapter` admin grant test depth, three flaky `SET lock_timeout` probes
  converted to `SET LOCAL` on their own connections.

## Decisions applied (user, 2026-10-06)

See 00-README "Decisions": D-R1 localhost CORS refusal restored; D-R2 prod `DATABASE_URL`
stays on demo (docs unchanged, orchestrator memory corrected); D-R3 supervisors covered by
the inactive-member guard; D-R4 fake roster controls removed (no endpoint by design).

## Open follow-ups (none blocking)

1. `local-dev-scripts/scripts/local-dev.sh` runs migrations **before** installing Python
   deps, so a brand-new venv crashes before the install step (pre-existing; reviewer 06).
2. `tr_reallocate_payment` (0205) still locks invoices in JSON-input order and can deadlock
   against refund/verify across two payments of one member (pre-existing; reviewer 03).
3. The demo DB credential appeared in a local gitignored pytest failure log
   (`archive/review-fixes-2026-10/05/`); rotate the demo password at convenience.
4. Roster import inherently reveals that an email is registered somewhere
   (`members.email` is globally unique); message is generic now, documented as a known limit.
5. Tasks routes return 500 (was 400 raw) for non-UUID path ids; optional 400 "Invalid id".
6. No test pins the advisory lock itself in `at_set_attendance`/`at_review_excuse`
   (the re-check is tested); a two-connection probe would cover it.
7. From the previous handoff, still waiting on the user: the `Prod/` sync (now unblocked —
   `build_prod.sh` is fixed), prod migration run (hand refunds before 0199), golden dataset
   brainstorm resume.

## Where things are

- Stream reports and logs: `archive/review-fixes-2026-10/<stream>/` (gitignored).
- Plan set + dispatch script: this folder. Fresh `fn-index.txt` regenerated 2026-10-06.
- The review file `LocalDev/docs/audit/remediation-review.md` carries the FIXED banner.
