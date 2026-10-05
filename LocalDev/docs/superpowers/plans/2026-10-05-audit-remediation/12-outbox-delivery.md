# 12 · Outbox delivery: one owner per message, no automatic double sends

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `12-outbox-delivery` · **Wave:** 2 (needs 01 merged) · **Agent:** Grok 4.7 medium (Cursor CLI) · **Branch:** `fix/audit-12-outbox-delivery`
**Findings:** F-063, F-017, F-019, F-018, F-013, F-034 · **Not in scope:** F-021 (done by stream 01), F-037, F-050, F-051 (stream 14, next wave), F-068 and R-05 (decisions D16, D17: no change)
**Migrations:** `0186_outbox_delivery_state.sql`, `0187_notify_and_announcement.sql` (0188–0190 spare)
**Goal:** a message is sent by whoever claimed it and nobody else; a crash after the provider accepted a message never causes an automatic resend; a killed run does not burn retry attempts; two officers cannot double-send an event notification; an in-app announcement no longer creates a row that is guaranteed to fail.
**Architecture:** the claim protocol in `outbox_claim_batch` stays as it is (report §14). Three things are added around it: the inline SMS dispatcher claims its rows with one atomic `UPDATE … WHERE status='pending'` before sending; every real provider call is preceded by a durable "provider attempted" stamp, and the reaper parks stamped rows instead of requeueing them; the drain works in small batches inside a time budget.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-063, F-017, F-019, F-018, F-013, F-034; decisions D15–D17 in `00-README.md`.

## Facts you can rely on

- Statuses on `message_outbox`: `pending`, `sending`, `sent`, `simulated`, `failed` (CHECK built in `migrations/0155_outbox_claim.sql`).
- `outbox_claim_batch(p_limit, p_chapter_id)` (live at `0155:84`): requeues `sending` rows older than 15 minutes, fails `pending` rows with `attempts >= 5`, then claims with `FOR UPDATE SKIP LOCKED`, sets `status='sending'`, `claimed_at=now()`, `attempts = attempts + 1`.
- Two senders exist today: the cron drain (`api/cron/services/outbox_drain.py`) and the inline `dispatch_send` (`api/announcements/services/sms.py:214-317`), called from `sms.py:208` and `api/events/services/notifications.py:178`.
- Dry-run mode (`MESSAGE_DELIVERY_MODE=dry_run`) marks rows `simulated` without any network call. Tests run in dry-run; a test that needs a "real" send monkeypatches the mode and `twilio_client.send_sms` / `send_email` (see `tests/cron/test_drain_outbox.py` for the pattern).
- Twilio is not live for this pilot, but the code path must be correct.

## Global constraints

- Allowed files: the two migrations; `api/platform/message_templates.py` (new, moved); `api/cron/core/templates.py` (delete); `api/cron/services/outbox_drain.py`; `api/announcements/services/sms.py` (NOT the `elif audience == "members_with_balance":` branch in `resolve_recipients`, stream 08 edits it); `api/announcements/services/outbox.py` (import line only); `api/announcements/services/twilio_client.py`; `api/events/services/notifications.py`; `tests/cron/**`; `tests/announcements/**`; `tests/events/test_notify.py`, `tests/events/test_notify_api.py`.
- DB functions you own this wave: `outbox_claim_batch`, `ev_notify_event` (live at `0145:954`), `an_send_announcement` (live at `0086:47`). Keep signatures and return shapes. In `outbox_claim_batch` change only the requeue statement (Task 3); the claim CTE is frozen.
- Do not change `api/platform/outbox.py` (stream 01 already fixed `enqueue`), `api/auth/**`, `api/cron/api/cron.py`, `api/health_checks.py`, `api/observability.py` (stream 14 next wave).
- Run `python3 -m pytest tests/cron tests/announcements tests/events -q`. Not the full suite.

## Review focus

1. A row the cron has already claimed (`sending`) must never be sent by the inline dispatcher, and the reverse.
2. A row whose provider call happened but whose result was not recorded ends `failed` with a clear "outcome unknown" error after the reaper runs. It is never set back to `pending` automatically.
3. A row claimed but never attempted (worker killed first) goes back to `pending` and gets its attempt refunded.
4. Dry-run rows never get a provider stamp and never call the provider.
5. The drain stops starting new deliveries when the time budget is spent and leaves unclaimed rows `pending`.

---

### Task 1: F-063 — templates leave `cron/core`

**Files:** `api/platform/message_templates.py`, `api/cron/core/templates.py`, the five importers

- [ ] **Step 1:** `git mv api/cron/core/templates.py api/platform/message_templates.py`. Update every importer (`grep -rn "cron.core" api tests`): `api/cron/services/outbox_drain.py:47`, `api/announcements/services/sms.py:40`, `api/announcements/services/outbox.py:15`, `tests/cron/test_templates.py:13-15`, and the docstring mention in `api/platform/outbox.py:72` is stream 14's file: leave that comment. Use `from api.platform import message_templates as templates` so call sites stay unchanged. If `api/cron/core/` is now empty apart from `__init__.py`, remove the directory.
- [ ] **Step 2: verify the cycle is gone:** `grep -rn "^from api.cron\|^import api.cron" api/announcements` prints nothing, and `python3 -c "import api.index"` succeeds.
- [ ] **Step 3: run `tests/cron tests/announcements -q`, expect PASS. Checkpoint** — suggested message `refactor(platform): message templates live in platform, breaking the announcements↔cron cycle`.

---

### Task 2: F-017 — the inline dispatcher claims before it sends (decision D15)

**Files:** `api/announcements/services/sms.py:214-317`, `tests/announcements/test_sms_send.py`

- [ ] **Step 1: failing test** `test_inline_dispatch_skips_rows_the_cron_already_claimed`: create an SMS send through the same service call the neighbouring tests use, but stop before dispatch (call the RPC part directly, or monkeypatch `dispatch_send` during creation and call it afterwards). With `cursor`, set one of the send's outbox rows to `status='sending', claimed_at=now()` (as the cron would). Switch mode to `twilio` with `twilio_client.send_sms` monkeypatched to record calls. Call `dispatch_send`. Assert the recorder was NOT called for the already-claimed row and was called once for each other row. Second test `test_inline_dispatch_marks_rows_sending_before_the_provider_call`: the recorder, when called, reads the row's status from the DB and asserts it is `sending`.
- [ ] **Step 2: run, expect FAIL.** If the first test passes on the untouched branch, report F-017 `NOT_REPRODUCED`.
- [ ] **Step 3: implement.** In `dispatch_send`, replace the `pending = (… .eq("status", "pending") …)` select with an atomic claim:

```python
    candidates = (
        sb.table("message_outbox")
        .select("id")
        .eq("target_table", send_table)
        .eq("target_id", send_row["id"])
        .eq("status", "pending")
        .execute()
    ).data or []
    pending = []
    if candidates:
        # One statement: only rows still 'pending' flip to 'sending' and come back.
        # A row the cron drain claimed in the meantime is not returned, so it is not sent twice (F-017).
        pending = (
            sb.table("message_outbox")
            .update({"status": "sending", "claimed_at": _now_iso()})
            .in_("id", [c["id"] for c in candidates])
            .eq("status", "pending")
            .execute()
        ).data or []
```

  The dry-run and twilio branches then work on `pending` exactly as before; both already write a terminal status per row. Do not increment `attempts` here.
- [ ] **Step 4:** the parent status line: `final_status = "failed" if "failed" in statuses else "sent"` stays. When `pending` is empty because the cron took every row, leave the parent's status unchanged (skip the parent update) and return the refreshed row.
- [ ] **Step 5: run `tests/announcements tests/events -q`, expect PASS. Checkpoint** — `fix(outbox): inline SMS dispatch claims its rows before sending`.

---

### Task 3: F-019 and F-018 — stamp before the provider call; park unknown outcomes; refund unused attempts

**Files:** `migrations/0186_outbox_delivery_state.sql`, `api/cron/services/outbox_drain.py`, `api/announcements/services/sms.py` (`_dispatch_twilio_row`), `api/announcements/services/twilio_client.py:38-66`, `tests/cron/test_drain_outbox.py`

- [ ] **Step 1: failing tests** (in `tests/cron/test_drain_outbox.py`, reuse its row factory and its mode/provider monkeypatches):
  - `test_provider_call_is_stamped_first`: in real mode, the patched `send_sms` reads the row and asserts `provider_attempted_at IS NOT NULL` at call time.
  - `test_unknown_outcome_is_parked_not_resent`: patched provider succeeds; `_close_row` is monkeypatched to raise every time (both the `sent` and the `failed` write). After the drain, the row is `sending`. With `cursor`, age it: `UPDATE message_outbox SET claimed_at = now() - interval '20 minutes' WHERE id = …`. Restore `_close_row`, drain again. Assert: provider called exactly once in total; row is `failed`; `last_error` starts with `delivery outcome unknown`.
  - `test_claimed_but_never_attempted_is_requeued_with_its_attempt_back`: with `cursor`, put a row in `sending` with `claimed_at` 20 minutes ago, `attempts = 1`, `provider_attempted_at NULL`. Call `outbox_claim_batch` with `p_limit = 0` (or drain in dry-run with a limit that excludes it; pick what works). Assert `status='pending'`, `attempts = 0`.
  - `test_twilio_sid_is_recorded`: patched `send_sms` returns `"SM123"`; after the drain the row has `provider_message_id = 'SM123'`.
  - `test_dry_run_never_stamps`: dry-run drain leaves `provider_attempted_at` NULL and the row `simulated`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: migration `0186_outbox_delivery_state.sql`.**

```sql
ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS provider_attempted_at TIMESTAMPTZ;
ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
```

  Then re-create `outbox_claim_batch`: copy the live body from `migrations/0155_outbox_claim.sql:84-128` unchanged except the first `UPDATE` (the requeue), which becomes two statements:

```sql
    -- Abandoned claim, provider never called: safe to retry, and the attempt did not happen.
    UPDATE message_outbox
       SET status = 'pending',
           claimed_at = NULL,
           attempts = GREATEST(attempts - 1, 0)
     WHERE status = 'sending'
       AND claimed_at < now() - interval '15 minutes'
       AND provider_attempted_at IS NULL
       AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id);

    -- Abandoned claim, provider WAS called and the result was never recorded: the message may
    -- have gone out. Never resend automatically (F-019); park it for a human.
    UPDATE message_outbox
       SET status = 'failed',
           last_error = 'delivery outcome unknown: the provider was called but the result was not recorded. Check with the recipient before retrying.'
     WHERE status = 'sending'
       AND claimed_at < now() - interval '15 minutes'
       AND provider_attempted_at IS NOT NULL
       AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id);
```

  Keep the `COMMENT ON FUNCTION` that follows the live definition. Apply: `python3 scripts/migrate_db.py`.
- [ ] **Step 4: Python.**
  - `twilio_client.send_sms` returns the message SID from Twilio's JSON response (`sid`) instead of discarding it (line ~65 says callers ignore it). Keep raising on non-2xx as today.
  - In `outbox_drain.py` add:

```python
def _stamp_provider_attempt(sb, row: dict) -> None:
    """Durable mark that the provider is about to be called for this row. If we die after
    this, the reaper parks the row instead of resending it (F-019)."""
    sb.table("message_outbox").update({"provider_attempted_at": _now_iso()}).eq("id", row["id"]).execute()
```

    Call it in `_deliver_sms` immediately before `twilio_client.send_sms(...)` and in `_deliver_email` immediately before `send_email(...)` (after the dry-run, no-phone, no-consent and no-email early returns). `_close_row` gains an optional `provider_message_id: str | None = None` and writes it when given; `_deliver_sms` passes the SID.
  - In `_deliver_row`'s `except`: if the exception came from the provider call itself, the row is closed `failed` with the provider's error as today. That is correct: the provider refused. Leave it.
  - In `sms._dispatch_twilio_row`: stamp before `twilio_client.send_sms` the same way (inline a two-line update; do not import from `api.cron`), and store the SID in the `sent` patch.
- [ ] **Step 5: time budget (F-018).** In `drain_outbox`: replace the single claim of `limit` rows with a loop: claim `min(25, remaining)` rows, deliver them, repeat until `limit` rows were processed, a claim returns nothing, or `time.monotonic() - started > DRAIN_BUDGET_SECONDS`. Module constant `DRAIN_BUDGET_SECONDS = 45`, with the comment `# ponytail: fixed budget well under the function timeout; make it a setting if the timeout ever changes.` Check the budget before each claim and before each row. Add test `test_drain_stops_when_the_budget_is_spent`: monkeypatch the constant to 0 and assert `processed == 0` and every row is still `pending` with `attempts == 0`.
- [ ] **Step 6: run `tests/cron tests/announcements -q`, expect PASS. Checkpoint** — `fix(outbox): never auto-resend after an unrecorded provider call; refund unused attempts; drain within a time budget`.

---

### Task 4: F-013 — one event notification at a time per event

**Files:** `migrations/0187_notify_and_announcement.sql`, `tests/events/test_notify.py:84-175`

- [ ] **Step 1: failing test** `test_notify_takes_the_event_lock`: second connection (`psycopg2.connect(db_url)`, `autocommit=False`) runs `SELECT pg_advisory_xact_lock(hashtext('ev_notify:' || %s))` with the event id; on `cursor`, `SET lock_timeout = '500ms'` and call `ev_notify_event` with the arguments the existing notify tests use; expect `psycopg2.errors.LockNotAvailable`. Roll back, close, `RESET lock_timeout`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** Copy the live `ev_notify_event` (`migrations/0145_security_swaps_v1.sql:954-1078`) into `0187` and add as the first statement after `BEGIN`:

```sql
    -- Serialize sends per event so the one-hour cooldown check cannot be raced (F-013).
    PERFORM pg_advisory_xact_lock(hashtext('ev_notify:' || p_event_id::text));
```

- [ ] **Step 4: apply, run `tests/events/test_notify.py tests/events/test_notify_api.py -q`, expect PASS. Checkpoint** — `fix(events): serialize event notifications so the cooldown holds`.

---

### Task 5: F-034 — announcements stop queueing an undeliverable row

**Files:** `migrations/0187_notify_and_announcement.sql` (append if not yet applied, else `0188_announcement_no_outbox.sql`), `api/cron/services/outbox_drain.py:252-270`, `tests/announcements/test_outbox.py`

- [ ] **Step 1: failing test** `test_in_app_announcement_queues_no_outbox_row`: post an announcement through the route the existing tests use; assert no `message_outbox` row with `event_type = 'ANNOUNCEMENT_PUBLISHED'` exists for that chapter.
- [ ] **Step 2: run, expect FAIL** (one row, `member_id NULL`).
- [ ] **Step 3: implement.** Copy the live `an_send_announcement` (`migrations/0086_announcements_tables_rpcs.sql:47-`) and delete the `INSERT INTO message_outbox … 'ANNOUNCEMENT_PUBLISHED' …` statement and its TODO (lines ~76-89). The announcements table is the feed. Leave the recipient-less guard in `_deliver_row` as a safety net but change its error text to `no recipient` and keep it `failed`.
- [ ] **Step 4:** grep for anything that reads `ANNOUNCEMENT_PUBLISHED` (`grep -rn "ANNOUNCEMENT_PUBLISHED" api tests greekos/src`): templates may define it; leave template definitions, fix tests that expected the row.
- [ ] **Step 5: apply, run `tests/announcements tests/cron -q`, expect PASS. Checkpoint** — `fix(announcements): an in-app announcement no longer queues a row that always fails`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
