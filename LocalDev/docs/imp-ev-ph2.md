# Events V1 — Phase 2 Implementation Plan

**Scope:** notify gate (backend only) — completeness computation, `POST
/{event_id}/notify` → send log + outbox → SMS via the announcements dispatch
path, `ORGANIZER_SOFT_MIN` 2 → 1 (decision D3), "last notified" as an
append-only record.
**Spec:** `docs/events-v1-spec.md` §2.1 (Notify), §2.7 (Event notify), UX Note 1,
§5 (permissions matrix row "Notify"), §7 open item 2 (cooldown).
**Status/roadmap:** `docs/events-dev-status.md` (D1–D4 apply; D3 lands here).
**Written:** 2026-07-02. Before implementing, re-verify the migration frontier
(`ls migrations/ | tail`) — this plan assumes the highest file is
`0142_jobs_v1_lifecycle.sql` and numbers the new migration **0143**.

## 1. Scope & assumptions

Phase 2 delivers, end to end (migration → RPC → service → route → tests):

1. **Completeness** (spec §2.1): an event is *complete* iff supervisors ≥ 1 AND
   organizers ≥ 1 AND jobs ≥ 3. Computed as a pure function, surfaced as a
   checklist object on event detail and list responses (UX Note 1 needs the
   per-item breakdown, not just a boolean).
2. **`POST /api/events/{event_id}/notify`**: two-phase confirmed SMS blast to
   all active members with phones, gated on completeness, reusing the
   announcements delivery path (`dispatch_send` + `MESSAGE_DELIVERY_MODE`).
   No new Twilio integration.
3. **`event_notification_sends`** append-only send log — "Last notified:" is
   `max(created_at)` of these rows, exposed as `last_notified_at`. No mutable
   column on `events`.
4. **`ORGANIZER_SOFT_MIN` 2 → 1** (D3): "Organizers Needed" badge fires only at
   0 organizers.
5. Soft **1/hour cooldown** on notify (spec open item 2) — cut first if
   time-boxed, see §3.4.
6. **Phase 1 follow-ups** (from the 2026-07-02 review): HTTP-layer tests for
   the jobs routes (see §6.3).

Explicit **non-goals** (later phases): initiatives (Phase 3); security & swaps
(Phase 4); all frontend incl. the checklist UI (Phase 5); announcement
scheduled time / calendar presence (Phase 5); a background outbox
worker/drainer (none exists today — delivery stays inline, same as
announcements); notify for initiatives (explicit spec non-goal §6);
JOB_* outbox row delivery (rows keep accruing `pending`; user-visible delivery
is a Phase 5 concern).

### Verified current state this plan builds on (2026-07-02)

- Migration frontier: `0142_jobs_v1_lifecycle.sql`. Phase 1 landed 0141/0142;
  all 92 tests in `tests/events/` + `tests/tasks/` pass.
- `api/events/core/rules.py`: `ORGANIZER_SOFT_MIN = 2` (line 7),
  `organizers_needed(count) = max(0, ORGANIZER_SOFT_MIN - count)`. No
  completeness/boolean-understaffed concept exists.
- `api/events/services/events.py`: `get_event` assembles `attendance_count`,
  `organizers` (list), `organizer_count`/`organizers_needed` via
  `_decorate_counts`, `supervisors` (list via `_decorate_supervisors`),
  `group_events`. `list_events` batch-counts organizers only. **Nothing in the
  events domain queries `tasks`** — the jobs count is new here.
- Jobs = `tasks` rows with `event_id` (D1; FK + `ix_tasks_event_id` from 0110).
- `api/events/api/router.py` is the mount point; a new route file is added via
  `router.include_router(...)` (append-only).
- Supervisor-management authorization pattern (Phase 1):
  `_require_supervisor_manage` = actor is a current `event_supervisors` row OR
  `has_permission(actor, EVENT_UPDATE)`. Notify extends this shape (§3.3).
- Announcements SMS path (`api/announcements/services/sms.py`):
  - `resolve_recipients(sb, *, chapter_id, audience)` — `audience="chapter"` =
    all `members` with `status='active'`; "reachable" = non-blank `phone`.
    Returns `{recipient_member_ids, recipient_count, no_phone_count}`.
  - `_delivery_mode()` reads `MESSAGE_DELIVERY_MODE` env (`dry_run` default /
    `twilio` / unknown → leave `pending` for an external worker).
  - `dispatch_send(sb, send_row)` delivers a send's pending `message_outbox`
    rows and flips the send row's `status`. ⚠ It **hardcodes
    `announcement_sms_sends`** in two places (the `target_table` filter at
    sms.py:207 and the send-row update at sms.py:225-229) — §3.5 generalizes it
    with a default-preserving parameter.
  - `RecipientCountMismatch(recipient_count, no_phone_count)` → routes map to
    409 with fresh counts in `detail`.
- `message_outbox` (0070): recipient column is `member_id`, timestamp is
  `delivered_at`, `dedup_key` globally UNIQUE, `status IN
  (pending|sent|failed)`. `event_type` CHECK is extended via the DO-block
  rebuild from the live constraint (`pg_get_constraintdef`) — copy 0131:80-111.
  `audit_logs.action` CHECK uses the dual-format DO-block — copy 0142:569-610.
- `announcement_sms_sends` (0131) is the send-log template: columns
  `chapter_id, announcement_id→(here: event_id), sender_id, recipient_count,
  recipient_member_ids JSONB, body_snapshot, delivery_mode, status
  queued|sent|failed, created_at`; append-only via an UPDATE-guard trigger
  (only `status` may change, 0131:34-57) + `tr_block_delete` (0005); RLS SELECT
  policy on `chapter_id = rbac_request_chapter_id()`.
- Naming precedent (Phase 1): lifecycle names are **shared** by
  `audit_logs.action` and `message_outbox.event_type` (`JOB_REPORTED` etc.).
  Phase 2 uses **`EVENT_NOTIFY`** for both.

### Decisions baked into this plan

- **D5 — Notify authorization is event-membership, not a new permission key.**
  Spec §5 grants Notify to supervisors and organizers of the event. Gate:
  actor ∈ `event_supervisors` OR actor ∈ `event_organizers` for this event, OR
  `has_permission(actor, EVENT_UPDATE)` (admin/exec fallback, same as
  supervisor management). No `events:notify` key is seeded — membership is not
  representable as a static role grant, and the fallback already covers
  admins. Revisit only if product wants members excluded from the fallback.
- **D6 — Re-notify is allowed; exactly-once is per press.** Announcements
  dedup on `{announcement_id}:{member}` (one blast ever); events must support
  legitimate repeat notifies (spec §2.7). Dedup key therefore includes the
  send row id: `EVENT_NOTIFY:{event_id}:{send_id}:{member_id}`. Idempotent
  *retries* of the same press are handled by `p_idempotency_key` returning the
  stored result before any new send row is created — so the fresh `send_id` in
  the key never double-fans-out.
- **D7 — The completeness gate is enforced in the RPC** (counts re-checked in
  SQL) *and* computed in Python for the checklist read — same belt-and-braces
  split as Phase 1's supervisor eligibility (service raises a domain error for
  a friendly 409; the RPC guard is the trust boundary).

## 2. Migration `0143_event_notify.sql`

### 2.1 `event_notification_sends` (copy the 0131 shape)

```sql
CREATE TABLE IF NOT EXISTS event_notification_sends (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id            UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id              UUID NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    sender_id             UUID REFERENCES members(id) ON DELETE SET NULL,
    recipient_count       INT  NOT NULL,
    recipient_member_ids  JSONB NOT NULL,
    body_snapshot         TEXT NOT NULL,
    delivery_mode         TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','sent','failed')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- indexes: (chapter_id), (event_id, created_at DESC)  -- last_notified_at read
-- append-only: UPDATE-guard trigger allowing only status to change
--   (copy an_enforce_sms_send_update, 0131:34-57) + tr_block_delete (0005).
-- RLS: ENABLE + SELECT policy chapter_id = rbac_request_chapter_id()
--   (writes only via the RPC on the service-role connection, as everywhere).
```

### 2.2 RPC `ev_notify_event`

```sql
ev_notify_event(
  p_chapter_id UUID, p_event_id UUID, p_actor_id UUID,
  p_recipient_member_ids JSONB, p_body_snapshot TEXT, p_delivery_mode TEXT,
  p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB
```

Body, in order (single transaction; template: `an_send_announcement_sms`, 0132):

1. Idempotency replay: `idempotency_keys` lookup, operation
   `'ev_notify_event'` → return stored result.
2. Tenant guards: event ∈ chapter; every recipient ∈ chapter (loop, as 0132
   does); recipients array non-empty (`RAISE 'no_recipients'`).
3. **Completeness gate (D7):**
   `v_supervisors := count(event_supervisors WHERE event_id)`,
   `v_organizers := count(event_organizers WHERE event_id)`,
   `v_jobs := count(tasks WHERE event_id = p_event_id AND chapter_id = p_chapter_id
   AND status <> 'cancelled')`. If `v_supervisors < 1 OR v_organizers < 1 OR
   v_jobs < 3` → `RAISE EXCEPTION 'event_incomplete'`.
4. **Cooldown (§3.4, cut-first):** if a `event_notification_sends` row for
   this event has `created_at > now() - interval '1 hour'` →
   `RAISE EXCEPTION 'notify_cooldown'`.
5. INSERT the `event_notification_sends` row (`status='queued'`).
6. Fan out `message_outbox` rows, one per recipient:
   `event_type='EVENT_NOTIFY'`, `member_id=recipient`,
   `target_table='event_notification_sends'`, `target_id=send_id`,
   `delivery_mode='sms'`, `status='pending'`,
   `dedup_key = 'EVENT_NOTIFY:' || p_event_id || ':' || v_send_id || ':' || member`
   (D6), `payload = jsonb_build_object('event_id', ..., 'send_id', ...,
   'title', ..., 'body', p_body_snapshot)`, `ON CONFLICT (dedup_key) DO NOTHING`.
7. `audit_logs`: action `'EVENT_NOTIFY'`, `target_table
   'event_notification_sends'`, `target_id` send id, metadata
   `{event_id, recipient_count, delivery_mode}`.
8. Store idempotency result; RETURN `to_jsonb(send_row)`.

### 2.3 Catalog additions (DO-block rebuild pattern)

- `message_outbox.event_type` += `EVENT_NOTIFY` (copy 0131:80-111).
- `audit_logs.action` += `EVENT_NOTIFY` (copy the dual-format block,
  0142:569-610).

## 3. Backend code changes

### 3.1 `api/events/core/rules.py` — pure, no I/O

- `ORGANIZER_SOFT_MIN = 2` → `1` (D3). `organizers_needed` unchanged in shape;
  the badge now fires only at 0.
- New `JOBS_COMPLETE_MIN = 3`, `SUPERVISORS_COMPLETE_MIN = 1`,
  `ORGANIZERS_COMPLETE_MIN = 1`.
- New pure function:

```python
def completeness(*, supervisor_count: int, organizer_count: int, job_count: int) -> dict:
    """UX Note 1 checklist: per-item met/current/required + overall flag."""
    items = [
        {"key": "supervisors", "required": SUPERVISORS_COMPLETE_MIN, "current": supervisor_count},
        {"key": "organizers",  "required": ORGANIZERS_COMPLETE_MIN,  "current": organizer_count},
        {"key": "jobs",        "required": JOBS_COMPLETE_MIN,        "current": job_count},
    ]
    for item in items:
        item["met"] = item["current"] >= item["required"]
    return {"is_complete": all(i["met"] for i in items), "items": items}
```

### 3.2 `api/events/services/events.py` — decoration additions (additive fields)

- `get_event`: add `job_count` (count `tasks` where `event_id`, `chapter_id`,
  `status <> 'cancelled'`), `open_job_count` (`status IN
  ('open','in_progress')` — the spec's "{n} open jobs" chip/message),
  `completeness` (rules fn over `len(supervisors)/len(organizers)/job_count`),
  and `last_notified_at` (max `created_at` from `event_notification_sends` for
  the event, `None` if never notified).
- `list_events`: two extra batched grouped queries over the visible event ids
  (`event_supervisors` and `tasks`, mirroring the existing organizer-count
  batch) → decorate each event with `job_count` and `completeness`. Needed by
  Phase 5's calendar `Incomplete` badge; keep it additive, no shape changes.

### 3.3 New `api/events/services/notifications.py` (service, no FastAPI imports)

Domain errors: `EventIncomplete(completeness_dict)`, `NotifyCooldown`,
`NoRecipients` (reuse `EventNotFound`/`NotPermitted` from `services/events.py`
or a shared module — do not redefine).

- `_require_notify(sb, *, actor, event_id)` — supervisor OR organizer OR
  `has_permission(actor, EVENT_UPDATE)` (D5); else `NotPermitted`.
- `_notify_body(event, open_job_count) -> str` — spec Screen 3:
  `"{title} — {date} {time}. {n} open jobs."` (times as stored; prettification
  is a Phase 5 formatter concern).
- `preview_notify(sb, *, actor, event_id)` → `{event_id, completeness,
  recipient_count, no_phone_count, body_preview, last_notified_at}`. Uses
  `resolve_recipients(sb, chapter_id=..., audience="chapter")` imported from
  `api.announcements.services.sms` (sanctioned reuse per
  `docs/events-dev-status.md` §4; leave a comment that SMS plumbing lives in
  the announcements domain until a shared notifications module exists).
- `notify_event(sb, *, actor, event_id, confirmed_recipient_count,
  idempotency_key=None)`:
  1. load event (tenant-scoped) → `EventNotFound`.
  2. `_require_notify`.
  3. compute completeness (Python side, D7) → `EventIncomplete(c)` if unmet
     (carries the checklist for the 409 body).
  4. `resolve_recipients(audience="chapter")`; mismatch →
     `RecipientCountMismatch` (import from announcements sms module).
  5. `call_rpc("ev_notify_event", {...body from _notify_body...,
     "p_delivery_mode": _delivery_mode()})`; map `notify_cooldown` /
     `event_incomplete` SQL errors to the domain errors.
  6. `return dispatch_send(sb, send_row, send_table="event_notification_sends")`
     (§3.5).

### 3.4 Cooldown (cut first if time-boxed)

RPC step 4 + `NotifyCooldown` → HTTP 429. One query on an indexed column; keep
unless the schedule slips. If cut: drop the RPC guard, the error class, the
429 mapping, and test §6.2-7 together (no dangling halves).

### 3.5 `api/announcements/services/sms.py` — minimal generalization

`dispatch_send(sb, send_row)` → `dispatch_send(sb, send_row, *,
send_table: str = "announcement_sms_sends")`; use `send_table` for the
`target_table` outbox filter (sms.py:207) and the send-row status update /
re-read (sms.py:225-233). Default preserves announcements behavior — existing
callers and tests unchanged. `_dispatch_twilio_row`, `_send_via_twilio`,
`_delivery_mode`, `resolve_recipients` need no changes.

### 3.6 New `api/events/api/notifications.py` (routes) + wiring

- `GET /{event_id}/notify-preview` — `Depends(get_current_user)`; service does
  the membership gate (returns the §3.3 preview payload; supervisors/organizers
  and EVENT_UPDATE holders only, 403 otherwise).
- `POST /{event_id}/notify` — `Depends(get_current_user)`, body
  `NotifyConfirm {confirmed_recipient_count: int = Field(ge=0)}` (copy
  `SmsSendConfirm`, 0131-era schema), header `Idempotency-Key`.
- Error mapping (extend the `_map_domain_errors` pattern — keep it in one
  place; either import the contextmanager or add a local one):
  `EventNotFound`→404, `NotPermitted`→403,
  `EventIncomplete`→409 with `detail={"message", "completeness"}`,
  `RecipientCountMismatch`→409 with fresh counts (copy the announcements
  route's detail shape), `NotifyCooldown`→429, `NoRecipients`→409.
- `api/events/api/router.py`: `router.include_router(notifications_router)`
  (append-only, existing includes untouched).
- `api/events/api/schemas.py`: `NotifyConfirm`, `CompletenessItem`,
  `Completeness`, `NotifyPreviewOut`; `EventResponse` gains `job_count`,
  `open_job_count`, `completeness`, `last_notified_at` (all optional/additive).

### 3.7 Docs

- `api/events/CONFORM_TODO.md`: note the notifications route/service files and
  the announcements-sms reuse (candidate for a shared module later).
- `docs/events-dev-status.md`: flip Phase 2 status when landed; record the
  migration number actually used.

## 4. What Phase 2 does NOT change

- `tk_*` RPCs, the jobs lifecycle, and Phase 1 tests — untouched.
- `an_send_announcement_sms`, announcements routes/tests — untouched (only the
  optional `send_table` parameter with a preserving default).
- No outbox drainer; unknown `MESSAGE_DELIVERY_MODE` still parks rows
  `pending` (documented worker seam).
- No `events` table columns (last-notified is derived, D-status §4).

## 5. Tests (pytest from `LocalDev/`, real Postgres; dry_run mode)

### 5.1 `tests/events/test_rules_completeness.py` (pure, no DB)

1. `completeness()` truth table: 1/1/3 → complete; 0 organizers, or 2 jobs, or
   0 supervisors → incomplete with the right `met` flags and
   `current`/`required` values.
2. `organizers_needed`: 0→1, 1→0, 2→0 (D3 — replaces the old 2-threshold
   expectations; **update `tests/events/test_organizers.py`'s progression test
   in the same commit**).

### 5.2 `tests/events/test_notify.py`

Service/RPC behavioral tests (superuser cursor + `sb_client`, treasury harness
via existing events conftest) + HTTP tests (copy the
`tests/announcements/conftest.py` `app_on_test_db`/`as_member` pattern —
`MESSAGE_DELIVERY_MODE=dry_run`, monkeypatched domain DB getters, real
`api.index.app`).

1. **Gate:** event with 1 supervisor / 0 organizers / 3 jobs → notify 409, body
   carries `completeness` with `organizers.met == False`. Same for 2 jobs.
   (Cancelled tasks don't count toward the 3.)
2. **Happy path (dry_run):** complete event → 200; one
   `event_notification_sends` row `status='sent'`; N `message_outbox` rows
   `event_type='EVENT_NOTIFY'`, `status='sent'`, `delivery_mode='sms'`, one per
   phone-holding active member; one `audit_logs` row action `'EVENT_NOTIFY'`;
   `get_event` now returns `last_notified_at`; body_snapshot contains title and
   open-jobs count.
3. **Count mismatch:** stale `confirmed_recipient_count` → 409 with fresh
   `recipient_count`/`no_phone_count`.
4. **Idempotency:** same `Idempotency-Key` re-POST → no second send row, no new
   outbox rows.
5. **Re-notify (D6):** second press (fresh key, cooldown window elapsed — back-
   date the first send row's `created_at` via cursor) → new send row, new
   outbox rows, distinct dedup keys; `last_notified_at` advances.
6. **Permissions (D5):** organizer (chair) → 200; supervisor → 200; plain
   member → 403; member with `calendar:event:update` role → 200.
7. **Cooldown:** immediate second press → 429 (skip if §3.4 cut).
8. **No-phone exclusion** and `no_phone_count` in preview; blank-string phones
   excluded (mirror `test_sms_send.py`).
9. **Append-only:** UPDATE of a non-status column on `event_notification_sends`
   → `DatabaseError` matching "append-only"; DELETE → "forbidden" (copy the
   0131 test assertions).
10. **Preview:** `GET /notify-preview` returns checklist + counts for an
    incomplete event (button-disabled UX data) without side effects.

### 5.3 Phase 1 follow-up: `tests/tasks/test_jobs_api.py` (HTTP layer)

The Phase 1 review found the jobs routes have no HTTP tests (the harness in
`test_commitments_api.py` never patches `jobs_api`). Add coverage:
patch `api.tasks.api.jobs.get_tasks_db` alongside the existing patches; then:
`report-done` non-claimant → 403; second report → 409; blank reason → 422
(schema) and whitespace-only → 422; `approve`/`reject` by non-supervisor
non-`tasks:review` → 403; `job_full` and `unclaim_locked` through
`commitments.py` → 409; job-create on event by non-supervisor/organizer
without `tasks:assign` → 403.

## 6. Execution checklist

1. `ls migrations/ | tail` — confirm 0143 is free; renumber if not.
2. Write `0143_event_notify.sql`; `npm run migrate`.
3. `rules.py` changes + §5.1 pure tests (fast, no DB) — red/green first.
4. RPC-level happy-path + gate tests (§5.2 items 1, 2, 5) against the migrated
   DB, then the service (`notifications.py`) to green.
5. `dispatch_send` `send_table` param + announcements suite still green
   (`python3 -m pytest tests/announcements/`).
6. Routes + schemas + router include; HTTP tests (§5.2 items 3, 4, 6–10).
7. §5.3 jobs HTTP tests.
8. Full `python3 -m pytest`; `npm run verify`.
9. Update `docs/events-dev-status.md` (Phase 2 → done, migration number, any
   decision drift vs D5–D7) and `api/events/CONFORM_TODO.md`.
10. Commit per convention (`feat(events): notify gate + SMS blast (phase 2)`).
