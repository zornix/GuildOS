# Before-Frontend Fix — Implementation Plan

**Scope:** backend only. Close the seven gaps that block Events V1 Phase 5
(the frontend prototype) from wiring to real endpoints.
**Spec:** `docs/events-v1-spec.md` Screen 1 (calendar chips), Screen 5
(job edit/delete), Screen 6 (prior security shifts), Screen 7 (requester
cancels a pending swap), Screen 8 (announcement date/time + calendar
presence).
**Status/roadmap:** `docs/events-dev-status.md`. Decisions D1–D14 still
apply. This plan adds D15–D17.
**Written:** 2026-08-15. Before implementing, re-verify the migration
frontier (`ls migrations/ | tail`) — this plan assumes the highest file is
`0146_attendance_tenant_guards.sql` and numbers the new migration **0147**.
**Update 2026-08-16:** 0147–0151 have since landed (one-gate RBAC, auth
hardening, E.164 phones, outbox drain, recruitment RPC) — the new migration
is now **0152**. None of them redefined any `tk_*`/`ev_*`/`an_*` RPC, so
every template reference below still holds. One assumption is stale:
`/api/memberadmin/scores` is no longer on legacy `require_officer` — 0147
moved it to `require_permission(STANDING_VIEW_ALL)`, so §1's note and the
"migrate scores auth" non-goal are moot (keep the gate as-is).

Frontend contracts, adapters, MemberPicker, JobCard, and the day/hour
countdown are **Phase 5**, not this plan.

---

## 1. Scope & assumptions

Seven gaps, five workstreams, one migration. In scope, end to end
(migration → RPC → service → route → tests):

| # | Gap | Fix |
|---|---|---|
| 1 | Event chip "N open jobs" lure | `open_job_count` on `list_events` **and** the calendar aggregator (today it is event-detail-only) |
| 2 | Announcement chips have no data source | Calendar aggregator reads sent, dated, visible announcements |
| 3 | Announcements have no date/time | `calendar_date` / `calendar_time` columns (calendar presence, **not** delayed SMS) |
| 4 | Job edit / delete have no endpoint | `PATCH` + `DELETE /api/tasks/{id}` via new `tk_update_task` / `tk_cancel_task` |
| 5 | Security picker "prior shifts" column | `prior_security_shifts` on `GET /api/memberadmin/scores` |
| 6 | Requester cannot cancel a pending swap | Build `ev_cancel_security_swap` (cut as optional in Phase 4; audit action already seeded) |
| 7 | Sent announcement cannot leave the calendar | `DELETE /api/announcements/{id}` hides a sent row from the calendar (SMS log untouched) |

Also in this pass, because Screen 1 chips cannot render without them and
the aggregator already has the data one function call away:

- Calendar event items gain `time`, `end_date`, `end_time`, `job_count`,
  `open_job_count`, and `completeness` (today they drop everything
  `list_events` computed except organizer flags).

### Decisions this plan settles

- **D15 — Announcement date/time is calendar presence, not a scheduled
  SMS.** Spec §2.3 / Screen 8: "Text + time. Added to the calendar and
  sent as SMS to all members on send." `sent_at` stays "when Send was
  pressed." Twilio still fires on `POST /{id}/send-sms`. No delayed-send
  worker.
- **D16 — Job delete is cancel, never a hard `DELETE FROM tasks`.**
  `tk_cancel_task` sets `status='cancelled'`. Allowed only while
  `status='open'` (spec Screen 5: delete lives in the To-do column).
  Edit (`tk_update_task`) is allowed on `open` and `in_progress` only.
  Parent (`event_id` / `initiative_id`) and `kind` are immutable.
  Security jobs are refused (`security_no_edit` / `security_no_cancel`) —
  roster changes stay on the `ev_*` security RPCs (D12).
- **D17 — `prior_security_shifts` is a count of approved security jobs
  the member held.** Decorated onto `GET /api/memberadmin/scores`. Not a
  new endpoint, not a standing input, not shown on the assigned member's
  card (spec Screen 6: "the assigned member's card does not display why
  they were picked").

### Verified current state this plan builds on (2026-08-15)

- Migration frontier is `0146_attendance_tenant_guards.sql`; **0147 is
  free**.
- `list_events` (`api/events/services/events.py`) already walks every
  visible event's tasks for `job_count` / `completeness`, filtering
  `cancelled` and `kind='security'`. It does **not** tally
  `open_job_count`. `_job_counts_for_event` (used only by `get_event`)
  already returns both counts; `_OPEN_JOB_STATUSES = {"open",
  "in_progress"}`.
- Calendar aggregator (`api/calendar/services/calendar.py`) calls
  `list_events` then copies a subset of fields. It reads `initiatives`
  directly. It never reads `announcements`. Event items omit `time` and
  the job/completeness decorations.
- `announcements` (0086): `title`, `body`, `audience`, `status
  IN ('draft','sent')`, `sent_at`. No calendar columns. Create is a
  single-row insert (`create_draft`); send is `an_send_announcement`.
  No DELETE route. `GET /sms-log` is registered before `/{id}/…`.
- Tasks HTTP (`api/tasks/api/tasks.py`): `GET /`, `POST /`,
  `POST /{id}/status`. No PATCH, no DELETE. Latest `tk_update_task_status`
  is in **0145** (security guard). There is no `tk_update_task`.
  `people_needed` is still a follow-up single-row `UPDATE` after
  `tk_create_task` (Phase 1 drift) — do not change create in this plan.
- Job manage authorization already exists as `can_create_event_job` /
  `can_create_initiative_job` in `api/tasks/services/approvals.py`.
  Reuse them; add `can_manage_job` that also covers standalone jobs.
- `SECURITY_SWAP_CANCELLED` is already in `audit_logs.action` (0145 §4,
  seeded even though the RPC was cut). `security_swap_requests.status`
  already allows `'cancelled'`. The update-guard trigger already permits
  `pending → cancelled` (only `status` / `resolved_at` / `resolved_by`
  may change). Copy `ev_decline_security_swap` from **0145** as the
  template; actor = requester instead of target; **no outbox** (Phase 4
  plan §2.3).
- `GET /api/memberadmin/scores` returns delinquency-ranked engagement
  (`score`, attendance counts, `unpaid_amount_cents`). No shift history.
  `/scores` still uses legacy `require_officer` — **do not migrate that
  auth in this plan** (flagged as separate debt in Phase 4 notes).

### Explicit non-goals

- All frontend (Phase 5): contracts/adapters, MemberPicker, JobCard,
  week view, SMS counter UI.
- Delayed / scheduled SMS.
- Edit-after-send for announcements.
- Changing `tk_create_task` to take `people_needed` (leave the
  follow-up UPDATE).
- Un-approving an approved job; nested jobs; swaps on non-security jobs.
- `ev_cancel_security_swap` outbox (Phase 4: audit only).
- Migrating `/api/memberadmin/scores` off `require_officer`.
- Claim-load-for-this-event on the scores payload (per-event; Phase 5
  derives it from `GET /api/tasks/` + `GET /api/events/{id}/security`).

---

## 2. Migration `0147_b4fend_unblocks.sql`

Four independent sections in one file. No existing function body is
copied-and-patched except where a brand-new function is created.

### 2.1 Announcements calendar columns

```sql
ALTER TABLE announcements
    ADD COLUMN IF NOT EXISTS calendar_date          DATE,
    ADD COLUMN IF NOT EXISTS calendar_time          TIME,
    ADD COLUMN IF NOT EXISTS hidden_from_calendar   BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS ix_announcements_calendar
    ON announcements (chapter_id, calendar_date)
    WHERE status = 'sent' AND hidden_from_calendar = FALSE AND calendar_date IS NOT NULL;
```

Nullable on purpose: every existing row is a draft or a sent feed post
with no calendar slot. Service-layer validation (not a DB CHECK) accepts
`calendar_time` only when `calendar_date` is set. The Phase 5 composer
always sends both; the API does not 422 on omit, so existing
`create_draft` callers keep working.

No change to `an_send_announcement`. Send still flips `draft → sent` and
stamps `sent_at`. A sent row without `calendar_date` is a feed post that
does not appear on the calendar.

### 2.2 `tk_update_task` / `tk_cancel_task`

Audit catalog (DO-block rebuild, copy the 0145 §4 pattern) +=
`UPDATE_TASK`, `CANCEL_TASK`.

**`tk_update_task(p_chapter_id UUID, p_task_id UUID, p_title TEXT,
p_description TEXT, p_people_needed INT, p_due_at TIMESTAMPTZ,
p_actor_id UUID, p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`**

- Idempotency on `('tk_update_task', key)` like every other `tk_*`.
- `SELECT … FOR UPDATE` the task;  not-found → existing
  `task % not found in chapter %` raise.
- `kind = 'security'` → `security_no_edit`.
- `status NOT IN ('open','in_progress')` → `job_not_editable`.
- `p_title` must be non-blank; `p_people_needed` must be `>= 1`.
- Capacity: `p_people_needed` may not drop below the count of active
  commitments → `job_capacity_below_claims`.
- Updates only `title`, `description`, `people_needed`, `due_at`,
  `updated_at`. Does **not** touch `event_id`, `initiative_id`, `kind`,
  `status`, `assigned_member_id`.
- Audit `UPDATE_TASK` with metadata of the new values.
- No `message_outbox` row.

**`tk_cancel_task(p_chapter_id UUID, p_task_id UUID, p_actor_id UUID,
p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`**

- `kind = 'security'` → `security_no_cancel`.
- `status <> 'open'` → `job_not_cancellable` (covers in-progress /
  reported / approved / already-cancelled, and therefore any row with
  active claimants — last unclaim already reverts to `open`).
- Sets `status='cancelled'`. Does not touch commitments (there are none
  in `open`).
- Audit `CANCEL_TASK`.
- No outbox. Completeness / `job_count` already ignore `cancelled`.

Do **not** redefine `tk_update_task_status`. The generic status-flip
path stays for legacy chore rows; job cancel goes through
`tk_cancel_task` so the `open`-only rule is one place.

### 2.3 `ev_cancel_security_swap`

Copy `ev_decline_security_swap` (0145, around line 615) verbatim, then
change:

- Function name / idempotency `operation` → `ev_cancel_security_swap`.
- Identity guard: `p_actor_id <> v_swap.requester_member_id` →
  `not_swap_requester` (decline uses `not_swap_target`).
- `status` → `'cancelled'` (already in the CHECK).
- Audit `SECURITY_SWAP_CANCELLED` (already in the catalog — do not
  re-seed).
- **Delete the `message_outbox` insert.** Phase 4: audit only.
- Keep the `pending` / `swap_wrong_state` / not-found / tenancy /
  idempotency / `FOR UPDATE` shape identical to decline.

Once this lands, a pending request the target ignores no longer blocks
the assignment's unique-partial-index slot forever. Supervisor
`ev_remove_security` remains the other escape hatch.

### 2.4 No other RPC redefines

`tk_commit_task`, `tk_uncommit_task`, `tk_update_task_status`,
`tk_create_task`, `tk_report_done`, `tk_approve_task`, `tk_reject_task`,
every `ev_*` other than the new cancel, every `in_*` and `an_*` —
untouched.

---

## 3. Endpoints

| Method | Path | Who | Behavior |
|---|---|---|---|
| GET | `/api/events/` | member | Additive: each row gains `open_job_count` (security excluded, same filter as `job_count`) |
| GET | `/api/events/{id}` | member | Unchanged (`open_job_count` already present) |
| GET | `/api/calendar` | member | Event items gain `time`, `end_date`, `end_time`, `job_count`, `open_job_count`, `completeness`. New item `kind='announcement'` for sent, dated, unhidden, `audience='chapter'` rows in range |
| POST | `/api/announcements/` | `announcements:create` | Body gains optional `calendar_date`, `calendar_time` |
| DELETE | `/api/announcements/{id}` | `announcements:create` | Draft → hard-delete the row. Sent → `hidden_from_calendar=TRUE`. 404 cross-tenant. Idempotent hide |
| PATCH | `/api/tasks/{id}` | manage-gate (below) | `tk_update_task`. 409 `job_not_editable` / `job_capacity_below_claims` / `security_no_edit` |
| DELETE | `/api/tasks/{id}` | manage-gate | `tk_cancel_task`. 409 `job_not_cancellable` / `security_no_cancel` |
| POST | `/api/events/{event_id}/security/swaps/{swap_id}/cancel` | requester (RPC-gated) | `ev_cancel_security_swap`. 403 `not_swap_requester`. 409 `swap_wrong_state` / `swap_already_pending` N/A |
| GET | `/api/memberadmin/scores` | officer (unchanged gate) | Additive: `prior_security_shifts` int per row |

No new permission keys. No RBAC seed migration.

**Manage-gate** for PATCH/DELETE job: `get_current_user` +
`can_manage_job` (403 otherwise), matching how approve uses
`can_approve_job` rather than `require_permission(TASKS_CREATE)`.

```
can_manage_job(task):
  event_id      → can_create_event_job      (supervisor | organizer | tasks:assign)
  initiative_id → can_create_initiative_job (assigned chair | tasks:assign)
  standalone    → tasks:assign OR tasks:review
```

**Announcement calendar item shape** (discriminator next to event /
initiative / invoice_due / task_due):

```
{
  "kind": "announcement",
  "announcement_id": "<uuid>",
  "title": "...",
  "date": "YYYY-MM-DD",          # calendar_date
  "time": "HH:MM:SS" | null,     # calendar_time
  "audience": "chapter"
}
```

Only `audience='chapter'` rows are aggregated (D15 corollary: the
chapter calendar is not the officers-only / balance-targeted feed).
Drafts never appear. Hidden rows never appear. Rows with
`calendar_date IS NULL` never appear.

**Swap cancel HTTP mapping** — add `not_swap_requester` to `_FORBIDDEN`
in `api/events/api/security.py` (403). Register the route next to
accept/decline; it is a three-segment path under `{event_id}` and cannot
shadow `/security-swaps/mine`.

**Tasks route order** — `api/tasks/api/router.py` already mounts
commitments then jobs then tasks. `PATCH`/`DELETE /{task_id}` on the
tasks router cannot shadow `/uncommit-log` or `/attribution/…`. Do not
add `GET /{task_id}` in this plan.

---

## 4. Backend code changes

### 4.1 Open-job count + calendar event chips

`api/events/services/events.py` — `list_events` already loops
`task_rows` and increments `job_counts` when status isn't cancelled and
kind isn't security. In the same loop, also increment an
`open_job_counts` dict when `status in _OPEN_JOB_STATUSES`. Stamp
`e["open_job_count"]` next to `e["job_count"]`. Do **not** duplicate
`_job_counts_for_event`; keep that helper for the single-event path.

`api/calendar/services/calendar.py` — when copying an event into
`items`, pass through:

- `time`, `end_date`, `end_time` (stringify like initiatives already do)
- `job_count`, `open_job_count`
- `completeness` (the dict `list_events` already attached)

`understaffed` / `organizers_needed` stay as they are (Screen 1
Organizers Needed badge). `completeness.is_complete === false` is the
Incomplete badge. `open_job_count` is the claim lure.

### 4.2 Announcements on the calendar

`api/announcements/api/schemas.py` — `AnnouncementCreate` gains optional
`calendar_date: date | None`, `calendar_time: time | None`. Reject
`calendar_time` without `calendar_date` (422).

`api/announcements/services/announcements.py`

- `create_draft` writes the two new columns when provided (still a
  single-row insert; send remains the RPC).
- `hide_from_calendar(sb, *, chapter_id, announcement_id)` — 404 if
  missing/wrong chapter; if `status='draft'` delete the row; if `sent`,
  `UPDATE hidden_from_calendar=TRUE` (idempotent). No RPC: single-row,
  non-financial, same justification as `create_draft`.
- `list_announcements` already `select("*")` — new columns flow through.

`api/announcements/api/announcements.py` — `DELETE /{announcement_id}`
behind `require_permission(ANNOUNCEMENTS_CREATE)`, registered **after**
`/sms-log` and **before** is fine as long as it does not collide with
`/{id}/sms-preview` / `send-sms` / `send` (those are longer paths).

`api/calendar/services/calendar.py` — after the initiatives block, query
`announcements` for the chapter where `status='sent'`,
`hidden_from_calendar=FALSE`, `audience='chapter'`, `calendar_date`
not null and in `[start, end]`. Append items in the shape above. The
existing `items.sort(key=lambda x: x["date"])` already covers them.

### 4.3 Job edit / cancel

`api/tasks/api/schemas.py` — `TaskUpdate` with optional `title`,
`description`, `people_needed` (`ge=1`), `due_at`. At least one field
required (model validator).

`api/tasks/services/approvals.py` — add `can_manage_job` as specified
in §3. Do not change `can_approve_job`.

`api/tasks/services/tasks.py` — `update_task` / `cancel_task` wrapping
`call_rpc`. After a successful update, if the caller passed
`people_needed`, it is already in the RPC — no follow-up UPDATE.

`api/tasks/api/tasks.py` — `PATCH /{task_id}` and `DELETE /{task_id}`:
load task or 404, `can_manage_job` or 403, then RPC. Extend
`_rpc_http_error` (or a local twin — jobs.py already has one; **share
it or copy the 409 branch**) with `security_no_edit`,
`security_no_cancel`, `job_not_editable`, `job_not_cancellable`,
`job_capacity_below_claims`.

### 4.4 Swap cancel

`api/events/services/security.py` — `cancel_swap` mirroring
`decline_swap`, calling `ev_cancel_security_swap`.

`api/events/api/security.py` — the POST route in the table above;
`not_swap_requester` → 403.

### 4.5 Prior security shifts

`api/memberadmin/services/scoring.py` — after building `results`, load
approved security jobs for the chapter (`tasks.kind='security'`,
`status='approved'`), then active-or-completed commitments on those
task ids (`task_commitments.status IN ('active','completed')` —
approved jobs complete their commitment, but count the holder either
way). Tally per `member_id`. Stamp `prior_security_shifts: int` (default
0) on every score row. Use `get_supabase_admin()` when `use_admin=True`
so tests keep working; otherwise `get_supabase()`.

Do not put this count in `load_member_engagement` (that loader is
attendance + unpaid fines). Do not feed it into the 0–100 score.

---

## 5. Tests

pytest from `LocalDev/`. Superuser connection for RPC tests; member-JWT
HTTP harness for routes. Reuse existing conftests
(`tests/events/`, `tests/tasks/`, `tests/announcements/`,
`tests/calendar_view/`, `tests/memberadmin/`).

### 5.1 Calendar decorations — `tests/calendar_view/test_calendar_view.py`

1. Event with 2 open standard jobs + 1 security job + 1 approved
   standard job → calendar item `job_count=3`, `open_job_count=2`
   (security excluded). `time` is present. `completeness` is the same
   dict `GET /api/events/{id}` would return.
2. `GET /api/events/` (list) on that same event also carries
   `open_job_count=2`. Put this in `tests/events/` next to the existing
   detail-count test rather than stretching the calendar suite — one
   assertion, same factory.

### 5.2 Announcements calendar — `tests/calendar_view/` + `tests/announcements/`

3. Sent announcement with `calendar_date` in range, `audience='chapter'`,
   not hidden → `kind='announcement'` item with title/date/time.
4. Draft with a date → absent. Sent but `calendar_date` null → absent.
   `hidden_from_calendar=TRUE` → absent. `audience='officers'` → absent
   even for an officer (chapter calendar is chapter-audience only).
   Date outside the requested range → absent.
5. `POST /api/announcements/` persists `calendar_date`/`calendar_time`.
   `calendar_time` without a date → 422.
6. `DELETE` a draft → 200 and the row is gone. `DELETE` a sent row → 200,
   row remains, `hidden_from_calendar=TRUE`, disappears from
   `GET /api/calendar`, SMS log (if any) untouched. Second DELETE is 200
   (idempotent hide). Cross-chapter id → 404. Plain member → 403.

### 5.3 Job edit / cancel — `tests/tasks/` (new `test_job_update.py`)

7. Supervisor PATCH title + `people_needed` on an `open` event job →
   200, audit `UPDATE_TASK`. Organizer of that event can PATCH.
   Unrelated member → 403. Initiative chair can PATCH an initiative job;
   a non-chair member cannot.
8. Guards: PATCH a `done_reported` or `approved` job → 409
   `job_not_editable`. PATCH `people_needed` below active claimant count
   → 409 `job_capacity_below_claims`. PATCH a security job → 409
   `security_no_edit`. Parent fields in the body are ignored (or 422 if
   you reject unknown fields — either is fine; the RPC never writes
   them).
9. DELETE an `open` job with zero claimants → 200, `status='cancelled'`,
   audit `CANCEL_TASK`, drops out of `job_count`. DELETE `in_progress` →
   409 `job_not_cancellable`. DELETE security → 409 `security_no_cancel`.
   Idempotency-key replay returns the first result.

### 5.4 Swap cancel — `tests/events/test_security.py` + `test_security_api.py`

10. Requester cancels a pending swap → `status='cancelled'`, audit
    `SECURITY_SWAP_CANCELLED`, **no** outbox row, unique-partial slot
    frees (a new `ev_request_security_swap` on the same task succeeds).
    Target cancelling → `not_swap_requester`. Uninvolved member → same.
    Cancel after accept → `swap_wrong_state`. Append-only trigger still
    blocks DELETEs and non-status UPDATEs.
11. HTTP: `POST …/swaps/{id}/cancel` as requester → 200; as target →
    403; `GET /security-swaps/mine` no longer lists it.

### 5.5 Prior shifts — `tests/memberadmin/`

12. Member with two `approved` security jobs (commitments completed) and
    one `in_progress` security job → `prior_security_shifts == 2` on
    their scores row. Member with none → `0`. The 0–100 `score` is
    unchanged by the decoration (assert against the existing formula on
    a fixture that already has a known score).

---

## 6. Execution checklist

1. `ls migrations/ | tail` — confirm 0147 is free; renumber if not.
2. Write `0147_b4fend_unblocks.sql` (§2). `npm run migrate`; re-run to
   prove idempotence.
3. Open-job count + calendar pass-through (§4.1); tests 1–2 green.
4. Announcement columns already in 0147; service/route/aggregator
   (§4.2); tests 3–6 green.
5. `tk_update_task` / `tk_cancel_task` + HTTP (§4.3); tests 7–9 green.
6. `ev_cancel_security_swap` + HTTP (§4.4); tests 10–11 green.
7. Scores decoration (§4.5); test 12 green.
8. Full `python3 -m pytest` from `LocalDev/` — green.
9. Update `docs/events-dev-status.md`: add a B4FEND row (Done,
   migration 0147), record D15–D17 under §2, note any drift, point
   Phase 5 at the now-complete backend surface.
10. Commit: `fix(events): unblock phase-5 frontend (calendar chips, job edit, swap cancel, announcement time)`.

---

## 7. What Phase 5 can assume after this lands

Every Screen 1–8 feature in the prototype inventory maps to a shipped
endpoint, except the items this plan explicitly left as Phase 5 UI
(MemberPicker, JobCard, week view, SMS counter, T-36h day/hour
countdown, contracts/adapters). The previous "blocked on backend" list
is empty.

Cut-first-if-time-boxed, in order: (a) announcement DELETE-to-hide
(calendar still works; stuck sent rows stay visible), (b)
`prior_security_shifts` (picker still sorts by delinquency), (c) swap
cancel (supervisor Remove remains the escape hatch — that is why Phase 4
cut it). Do not cut `open_job_count`, announcement calendar columns, or
job edit/cancel — those are load-bearing for Screens 1, 5, and 8.
