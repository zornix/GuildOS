# Plan 09 — Outbox delivery Implementation Plan (wave 2)

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first. You branch from a `main` that already contains wave 1.

**Goal:** the retry cap really caps, a delivered message is never sent twice, and claimed rows don't rot when the time budget runs out.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §12.
**Migrations:** 0215.

**Allowed files:** `migrations/0215_*.sql`, `api/cron/services/outbox_drain.py`, `api/cron/core/` (deletion only), `tests/cron/*`. DB function you own: `outbox_claim_batch` (live: 0200, defined 3×; base on the last).

## Task 1 — RV-12-1 (P2): the 5-attempt cap can never trigger

`migrations/0200_outbox_ops.sql:9-17` (from 0186): claiming does `attempts + 1`, the refund path does `attempts - 1`, so a row that crashes the worker before the provider stamp goes back to pending with attempts at 0 — retried forever, and because claiming is oldest-first it blocks the front of the queue.

- [ ] Failing test first, `tests/cron/test_attempt_cap.py` (own chapter): claim-then-refund the same row 6 times (simulating 6 crashed drains); assert today it is still `pending` with `attempts = 0`; after the fix the row is `failed` (or permanently parked) by the cap.
- [ ] `migrations/0215_outbox_attempt_cap.sql`: `CREATE OR REPLACE FUNCTION outbox_claim_batch` (0200 live body as base): the refund path returns rows to `pending` **without** decrementing `attempts`, and the claim (or refund) marks rows with `attempts >= 5` as `failed` instead of handing them out again. Keep the signature and return shape.
- [ ] Apply, `python3 scripts/migration_checksums.py --update`, test → PASS. Checkpoint: `python3 -m pytest tests/cron/ -q`.

## Task 2 — RV-12-2 (P2): a close-failure after a successful provider call causes a double send

`api/cron/services/outbox_drain.py:303-307`: if marking the row `sent` fails after the provider accepted the message, the row becomes `failed` carrying database error text, and Retry clears the provider stamp → the message goes out twice.

- [ ] Failing test first, `tests/cron/test_no_double_send.py`: monkeypatch the close-as-sent step to raise once after the (fake) provider call succeeded; assert today a retry sends again (provider mock called twice); after the fix the row keeps its provider stamp and the retry path **closes it as sent without calling the provider**.
- [ ] Fix in `outbox_drain.py`: a row that already has a provider stamp is never re-sent — the drain treats it as delivered and only finishes the bookkeeping; the close-failure path stores a fixed message (no raw database text) and never erases the stamp.
- [ ] Checkpoint: `python3 -m pytest tests/cron/ -q`.

## Task 3 — RV-12-3 (P3): budget exhaustion strands claimed rows for 15+ minutes

`outbox_drain.py:343-345`: when the time budget runs out, claimed-but-unsent rows sit in `sending` until the stale-claim sweep.

- [ ] Failing test first: drain with a budget that expires after the claim; assert rows go back to `pending` at loop end (today they stay `sending`). Fix: release unsent claimed rows before returning (the claim refund path from Task 1 — which no longer touches `attempts`).

## Task 4 — RV-12-4 (P3): `test_inline_dispatch_skips_rows_the_cron_already_claimed` would pass with the fix reverted

- [ ] Strengthen the existing test so it fails when the claim-skip behaviour is reverted (assert the inline dispatch actually *skipped* — e.g. the claimed row's state/provider mock untouched — not just that nothing crashed). Verify by mentally (or actually, locally, then restoring) reverting the guard. Report under EXISTING TESTS CHANGED.

## Task 5 — RV-12-5 (P3): `api/cron/core/__init__.py` should be gone

The remediation plan said to remove the directory; the empty `__init__.py` is still tracked.

- [ ] Confirm nothing imports `api.cron.core` (`grep -rn "cron.core" api/ tests/`), then delete the file/directory.

## Task 6 — RV-14-4 (P3): the oldest-pending-age test may read another chapter's row

`tests/cron/test_heartbeats.py:36-45`: on the shared demo DB the assertion can pick up another chapter's pending row.

- [ ] Scope the query/assertion to the test's own `chapter_id` fixture (shared-DB hygiene; behaviour asserted stays the same). Report under EXISTING TESTS CHANGED.
- [ ] Final checkpoint: `python3 -m pytest tests/cron/ -q` — paste the final count line.
