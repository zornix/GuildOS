# 14 · Outbox operations: no stored codes, atomic retry, a heartbeat, honest health

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `14-outbox-ops` · **Wave:** 3 (needs 12 and 13 merged) · **Agent:** Grok 4.7 medium (Cursor CLI) · **Branch:** `fix/audit-14-outbox-ops`
**Findings:** F-037, F-050, F-051, F-046, F-067, R-02
**Migration:** `0200_outbox_ops.sql` (0201, 0202 spare)
**Goal:** a setup or reset code never sits in a finished outbox row; pressing Retry cannot half-apply; there is a durable record that the cron ran; the health endpoint returns 503 when the database is down; every log line carries the request id.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-037, F-050, F-051, F-046, F-067 and Appendix C.4 (R-02); decision D21 in `00-README.md`.

## Facts you can rely on (all merged before this wave)

- `get_db().transaction()` (stream 01); `enqueue` uses `ON CONFLICT DO NOTHING` and re-raises inside a transaction.
- Stream 12 added `provider_attempted_at`, `provider_message_id`, the park-instead-of-resend rule in `outbox_claim_batch` (live in `0186`), a time-budgeted `drain_outbox`, and moved templates to `api/platform/message_templates.py`.
- `_SECRET_EVENT_TYPES = (SETUP_CODE, RESET_CODE)` in `api/cron/services/outbox_drain.py`; `_close_row` blanks the payload of those rows on `sent` and `simulated` only.
- The officer can always issue a fresh code: `POST /api/auth/reset-code/{member_id}`.

## Global constraints

- Allowed files: `migrations/0200_outbox_ops.sql`; `api/cron/services/outbox_drain.py`; `api/cron/api/cron.py`; `api/announcements/services/outbox.py`; `api/announcements/api/announcements.py` (retry route error mapping only); `api/health_checks.py`; `api/observability.py`; `scripts/check_prod_status.py`; `tests/cron/**`, `tests/announcements/test_outbox.py`, `tests/config/test_observability.py`, `tests/test_check_prod_status.py`, `tests/test_health.py` (new).
- Shared file, one region only: `api/index.py` → the `@app.get("/api/health")` handler (~lines 214-216).
- DB functions you own this wave: `outbox_claim_batch` (two statements only, Task 1). Do not change the claim CTE.
- Do not touch `api/treasury/**` or `api/attendance/**` (stream 09 this wave) or `greekos/**` (stream 15).
- Run `python3 -m pytest tests/cron tests/announcements tests/config tests/test_check_prod_status.py tests/test_health.py -q`. Not the full suite.

## Review focus

1. No code path leaves a `SETUP_CODE`/`RESET_CODE` row in a terminal status (`sent`, `simulated`, `failed`) with a non-empty payload, including rows failed by the attempt cap and rows parked by the reaper.
2. Retry of a code-bearing row is refused with a message that tells the officer what to do instead.
3. A drain run that claims nothing still records a heartbeat.
4. `/api/health` is 200 with a stale cron (body says `degraded`) and 503 only when the database check fails. An uptime monitor must not flap on a quiet cron.
5. The logging filter must not break log calls made outside a request (request id is `-`).

---

### Task 1: F-037 — finished rows never keep a code

**Files:** `migrations/0200_outbox_ops.sql`, `api/cron/services/outbox_drain.py` (`_close_row`), `api/announcements/services/outbox.py:130-170`, `api/announcements/api/announcements.py`, `tests/cron/test_drain_email.py`, `tests/announcements/test_outbox.py`

- [ ] **Step 1: failing tests.**
  - `test_failed_code_row_has_no_payload`: a `SETUP_CODE` row whose delivery fails (member has no email) ends `failed` with `payload == {}`.
  - `test_attempt_capped_code_row_has_no_payload`: with `cursor`, a `pending` `RESET_CODE` row with `attempts = 5` and a payload; run a drain; row is `failed`, `payload == {}`.
  - `test_parked_code_row_has_no_payload`: a `sending` `SETUP_CODE` row with `provider_attempted_at` set and `claimed_at` 20 minutes ago; run a drain; `failed`, `payload == {}`.
  - `test_retry_of_a_code_row_is_refused`: `retry_outbox_row` on a failed `SETUP_CODE` row raises the new error; through the route it is 409 with `"This message carried a one-time code. Send the member a new code instead."`.
  - `test_non_secret_failed_row_keeps_its_payload_and_can_be_retried` (unchanged behaviour).
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**
  - `_close_row`: blank the payload for `_SECRET_EVENT_TYPES` on every terminal status: change `if status in ("sent", "simulated") and …` to `if row["event_type"] in _SECRET_EVENT_TYPES:` and fix the comment.
  - `outbox.py`: add `class OutboxRowNotRetryable(Exception)`; in `retry_outbox_row`, after the status check, raise it when `row["event_type"]` is `SETUP_CODE` or `RESET_CODE` (import the constants from where `outbox_drain.py` gets them). Map it to the 409 above in the retry route, next to the existing `OutboxRowNotFound` / `OutboxRowNotFailed` mapping.
  - Migration: (a) one-time cleanup `UPDATE message_outbox SET payload = '{}'::jsonb WHERE event_type IN ('SETUP_CODE','RESET_CODE') AND status IN ('sent','simulated','failed') AND payload <> '{}'::jsonb;` (b) re-create `outbox_claim_batch` from the live body in `0186`, adding to BOTH the park statement and the attempt-cap statement: `payload = CASE WHEN event_type IN ('SETUP_CODE','RESET_CODE') THEN '{}'::jsonb ELSE payload END`.
- [ ] **Step 4: apply (`python3 scripts/migrate_db.py`), run, expect PASS. Checkpoint** — suggested message `fix(outbox): one-time codes are wiped from every finished row and cannot be retried`.

---

### Task 2: F-050 — Retry is atomic

**Files:** `api/announcements/services/outbox.py:130-170`, `tests/announcements/test_outbox.py`

- [ ] **Step 1: failing test** `test_retry_rolls_back_when_the_audit_row_fails`: monkeypatch so the `audit_logs` insert raises (for example patch `retry_outbox_row`'s client with a thin wrapper whose `table("audit_logs")` raises `RuntimeError`, delegating everything else, including `transaction()`, to the real client; the wrapper must wrap the transaction client too). Call `retry_outbox_row`; expect the error; the row is still `failed` with its original `attempts`.
- [ ] **Step 2: run, expect FAIL** (row is `pending`).
- [ ] **Step 3: implement.** Wrap the `message_outbox` update and the `audit_logs` insert in `with sb.transaction() as tx:` and run both through `tx`. Also reset `provider_attempted_at` to NULL in the update (a human chose to resend).
- [ ] **Step 4: parent send log.** After a successful retry the parent send (`announcement_sms_sends` / `event_notification_sends`, found through the row's `target_table` / `target_id`) still reads `failed` even when the child later sends. Read the two update-guard triggers (`an_enforce_sms_send_update` at `migrations/0131:34`, `ev_enforce_notify_send_update` at `0143:35`). If they allow `failed → sent`: in `outbox_drain.py`, after a row with one of those `target_table` values closes as `sent` or `simulated`, set the parent to `sent` when it has no remaining `failed` or `pending`/`sending` children (one count query, one update), with a test. If the triggers forbid that transition: change nothing, and report this step as `BLOCKED: parent status is append-only` so the orchestrator can decide.
- [ ] **Step 5: run, expect PASS. Checkpoint** — `fix(outbox): retry requeues and audits in one transaction`.

---

### Task 3: F-051 and R-02 — a heartbeat for the cron

**Files:** `migrations/0200_outbox_ops.sql` (append if not applied, else `0201_cron_heartbeats.sql`), `api/cron/services/outbox_drain.py`, `api/cron/api/cron.py:38-45`, `tests/cron/test_drain_outbox.py`

**Interfaces (produced):**

```sql
CREATE TABLE IF NOT EXISTS cron_heartbeats (
    job TEXT PRIMARY KEY,
    last_started_at TIMESTAMPTZ NOT NULL,
    last_finished_at TIMESTAMPTZ NOT NULL,
    last_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    oldest_pending_seconds INT
);
ALTER TABLE cron_heartbeats ENABLE ROW LEVEL SECURITY;   -- no policies: owner only
```

- [ ] **Step 1: failing tests.** `test_drain_records_a_heartbeat_even_when_idle`: run the route-level drain (not chapter-scoped) with nothing pending; the row `job='drain-outbox'` exists with `last_finished_at` within the last minute and `last_counts.processed == 0`. `test_heartbeat_reports_oldest_pending_age`: leave one `pending` row created 10 minutes ago that the run does not reach (budget 0); `oldest_pending_seconds >= 600`. `test_chapter_scoped_drain_writes_no_heartbeat` (tests and manual single-chapter drains must not fake the scheduled job's heartbeat).
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** In `drain_outbox`, when `chapter_id is None`: record the start time; after the loop, read the oldest `pending` row's `created_at` (one query: `.select("created_at").eq("status", "pending").order("created_at").limit(1)`), and `upsert` the heartbeat row (`on_conflict="job"`). A failure to write the heartbeat is logged with `logger.exception` and never fails the drain. Always log one summary line per scheduled run, including empty ones.
- [ ] **Step 4: R-02.** Split the combined handler into two functions sharing one helper so each has its own OpenAPI operation id: `@router.get("/drain-outbox") async def cron_drain_outbox_scheduled()` and `@router.post("/drain-outbox") async def cron_drain_outbox_manual()`. Keep auth dependencies exactly as they are on the current route. Check `tests/services_scaffold/test_route_registration.py` still passes.
- [ ] **Step 5: apply, run `tests/cron tests/services_scaffold -q`, expect PASS. Checkpoint** — `feat(cron): record a heartbeat for every scheduled outbox drain`.

---

### Task 4: F-046 — health says what is true

**Files:** `api/health_checks.py:30-52`, `api/index.py` (health handler only), `scripts/check_prod_status.py`, `tests/test_health.py`, `tests/test_check_prod_status.py`

Response contract:

| Database | Outbox heartbeat | HTTP | `status` | `checks` |
|---|---|---|---|---|
| ok | finished within 15 min | 200 | `ok` | `{"database": "ok", "outbox_drain": "ok"}` |
| ok | older than 15 min | 200 | `degraded` | `{"database": "ok", "outbox_drain": "stale"}` |
| ok | no row, or the table is missing | 200 | `ok` | `{"database": "ok", "outbox_drain": "unknown"}` |
| error | (not checked) | 503 | `error` | `{"database": "error"}` plus `detail: "database_unreachable"` |

- [ ] **Step 1: failing tests** in `tests/test_health.py`: build the payload with a real client and (a) a fresh heartbeat row, (b) one aged 30 minutes (`cursor` update), (c) a client whose `ping` raises → the handler returns status code 503 with the body above. For (c) call the FastAPI handler through `TestClient` with `get_db` monkeypatched in `api.index`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** `build_health_payload` adds the `outbox_drain` check when the database is up (one select on `cron_heartbeats`; any exception → `"unknown"`). The handler returns `JSONResponse(payload, status_code=503 if payload["status"] == "error" else 200)`. `scripts/check_prod_status.py`: treat `degraded` as a warning (exit code as its existing convention defines for warnings; if it has only pass/fail, print a `WARN` line and pass) and a 503 as a failure; update its tests.
- [ ] **Step 4: run, expect PASS. Checkpoint** — `fix(health): return 503 when the database is down; report a stale outbox cron`.

---

### Task 5: F-067 — the request id is on every log line

**Files:** `api/observability.py:29-52`, `tests/config/test_observability.py`

- [ ] **Step 1: failing test:** set `request_id_ctx` to `"req-123"`, log a warning through an unrelated logger (`logging.getLogger("api.cron.services.outbox_drain")`) with `caplog`, format the record with the module's handler formatter, and assert the output contains `req-123`. Outside a request the same call renders `-`.
- [ ] **Step 2: implement.**

```python
class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True
```

  `_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [rid=%(request_id)s] %(message)s"`. In `_configure_logging`, after `basicConfig`, add the filter to every handler on the root logger (a filter on a handler sees records from all loggers; a filter on the root logger does not). Remove the manual `[request_id=…]` formatting from the unhandled-exception handler if it now duplicates the field.
- [ ] **Step 3: run `tests/config -q`, expect PASS. Checkpoint** — `feat(observability): every log line carries the request id`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
