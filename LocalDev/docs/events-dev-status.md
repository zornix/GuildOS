# Events Service V1 — Development Status & Roadmap

**Last updated:** 2026-08-18
**Spec:** `docs/events-v1-spec.md` (Events Service V1, saved verbatim)
**Current phase:** B4FEND **done** (migration 0152) — the Events V1 backend
surface is complete; **Phase 5 (frontend)** is **wired** in the `greekos`
prototype (`LocalDev/greekos`), which now reads and writes the real API for
events, jobs, security + swaps and announcements

This document is the entry point for anyone (human or agent session) continuing
the Events V1 build. It records what exists, what's missing, the decisions that
were made to reconcile spec vs. code, and the phase-by-phase build order with
instructions for planning each next phase.

---

## 1. Gap analysis (as of 2026-07-01)

### 1.1 Backend — what already exists

- **Events domain** (`api/events/`) is a fully conformed domain package
  (status "conformed, V1 events build, June 2026" per its `CONFORM_TODO.md`).
  CRUD, event types (`GET /types`), event groups (setup→event→cleanup),
  visibility/audience enforcement, check-in link hooks. RPCs (migration 0101):
  `ev_create_event`, `ev_set_audience`, `ev_set_supervisor`, `ev_add_organizer`,
  `ev_remove_organizer`.
- **Organizers**: `event_organizers(event_id, member_id, source volunteer|assigned)`
  with self-volunteer + assign/remove endpoints. Derived "understaffed" flag
  exists but with `ORGANIZER_SOFT_MIN = 2` (`api/events/core/rules.py`) — spec
  wants the badge at 0 organizers and the notify gate at ≥1.
- **Supervisor**: single `events.supervisor_member_id` column (0100), set via
  `ev_set_supervisor` with chair-role eligibility enforcement. Spec wants
  creator locked in + N co-supervisors → needs a join table.
- **Claim machinery** (tasks domain, migration 0110): `task_commitments` with a
  unique-active partial index, append-only `task_commitment_log`, RPCs
  `tk_commit_task` / `tk_uncommit_task`, `tasks.event_id` linkage. Uncommit is
  currently *always allowed*, flagged "late" under 24h — spec mandates a hard
  T-36h lock instead.
- **Announcements** (`api/announcements/`): draft→send, audience resolution,
  two-phase confirmed **Twilio SMS blast** (`an_send_announcement_sms`, 0130–0132)
  with append-only send log and `MESSAGE_DELIVERY_MODE` (dry_run/twilio).
  Missing: scheduled time, calendar presence.
- **Notification plumbing**: transactional `message_outbox` (0070) with unique
  `dedup_key`, CHECK-constrained `event_type` catalog (extended per-migration via
  the DO-block rebuild pattern, see 0100/0131); `idempotency_keys` + `audit_logs`
  RPC discipline (treasury is the reference implementation).
- **Member stats / delinquency**: `GET /api/memberadmin/scores` returns
  delinquency-ranked engagement scores (attendance/excused/fines formula in
  `api/memberadmin/services/scoring.py`). `POST /api/memberadmin/assign-security`
  exists as a **non-persisting stub** (picks 3 lowest scorers, saves nothing).
- **RBAC**: `require_permission(...)` / `has_permission(...)` machinery; roles
  seeded in 0083 include six `*_chair` keys (modeled as `CHAIR_ROLES` in
  `api/events/auth.py`), `officer`, offices (president etc.). Relevant permission
  keys: `calendar:event:create/update/delete`, `tasks:create/assign/complete/review`,
  `announcements:create/send/send:sms`.

### 1.2 Backend — missing

- No `end_time` / end timestamp on `events` (only `date DATE + time TIME` start);
  no invite-link column.
- No co-supervisors table; no min-1-supervisor / creator-locked semantics.
- No job capacity ("people needed" / fill state), no done-reported→approved/rejected
  lifecycle, no rejection reasons, no T-36h hard lock.
- No initiatives — no table, route, or concept anywhere.
- No security assignments or swap requests — zero hits in code or migrations.
- No event "Notify members" action; no outbox event types for event-notify,
  job rejection/approval, or swaps; events domain has no `notifications.py`.
- No "exec" role tier (see decision D4).

### 1.3 Frontend — what already exists

(All under `LocalDev/fratos/`; note this is a client-side-routed SPA — screens
live in `views/*.tsx` + `components/modules/`, switched by `PageId` in
`components/layout/app-shell.tsx`, not App Router routes.)

- Month calendar with list/calendar toggle (`components/modules/events/event-calendar.tsx`,
  `views/events.tsx`) — month only, chips show dot+title, no badges.
- Event detail (`event-detail.tsx`) — attendance/check-in/fines oriented; none
  of the spec's People / Jobs / Security / Notify sections.
- Create-event modal form (`components/forms/create-event-form.tsx`) — 5 basic
  fields; sends `fine_amount` as a dollar float (legacy boundary; do not copy).
- Announcement composer (`views/announcements.tsx`) — draft/send + audience;
  no SMS counter.
- Tasks view (`views/tasks.tsx`) — list rows with status flips only; no claim UI.
- UI primitives: `Badge` (has red/green/yellow), `Card`, `Btn`, `DataTable`,
  `Modal`, `SegmentedControl`, `EmptyState`, `Avatar`, `Toast`, etc.

### 1.4 Frontend — missing / structural debt

- No jobs UI of any kind (JobCard, claim/report/approve/reject flows).
- No initiative, security-picker, or swap screens; no week calendar view; no
  calendar badges; no SMS length counter.
- No multi-select member picker primitive (needed by 3+ screens).
- **Contracts/adapters exist only for treasury** — events/tasks/announcements
  views consume raw snake_case DTOs from `lib/types.ts`, violating the project's
  own adapter convention. Fix this before building the V1 screens on top.
- Role gating is binary `officer|member` with inline `user.role === "officer"`
  checks in several views (violates the RBAC rule in CLAUDE.md).

---

## 2. Decisions (spec ↔ code reconciliation)

These were the four contradictions found; the adopted resolutions below are
baked into the phase plans. Revisit here if product overrules.

- **D1 — Jobs are the tasks domain, extended.** The spec's "jobs" =
  `tasks` + `task_commitments` plus capacity, report/approve/reject states, and
  the T-36h lock. Do **not** introduce a fourth checklist concept (there are
  already `tasks`, legacy `event_tasks` from 0003, and task templates; 0085
  already marks `event_tasks` as "fold into tasks later"). API/UI may say "job";
  the storage and RPC layer stays `tasks` / `tk_*`.
- **D2 — Hard T-36h unclaim lock** replaces the current "always allowed,
  late-if-<24h" rule in `tk_uncommit_task`. Claiming stays open through the
  event. The append-only commitment log is unchanged.
- **D3 — Organizer thresholds follow the spec**: "Organizers Needed" badge when
  count = 0; notify gate needs ≥1 organizer. `ORGANIZER_SOFT_MIN` drops 2 → 1
  (done in Phase 2 together with the completeness gate).
- **D4 — "Exec" is a permission, not a new role.** Spec's "exec" maps to
  existing permission keys (`calendar:event:create`, `announcements:create`, …).
  Chairs remain the `*_chair` role keys. No new role tier is added.
- **D8 — Initiatives are a separate table, not a flavor of events.** A new
  `initiatives` table (own `id`, `title`, `date`, `time`, `created_by`) plus
  `initiative_chairs` (many-to-many, `is_creator` flag). `tasks` gains a
  nullable `initiative_id` alongside `event_id`, mutually exclusive via
  `tasks_single_parent_check`.
- **D9 — Chapter-level chair gating is a seeded permission key; per-initiative
  authorization is `initiative_chairs` membership.** Creating an initiative
  requires the new `calendar:initiative:create`/`:update` permission keys
  (granted to `admin` + the six `*_chair` roles, same set as jobs in D5).
  Updating an initiative, and adding/removing its chairs, is gated on
  `initiative_chairs` membership (checked in the service layer), not a
  permission key.
- **D10 — New domain package `api/initiatives/`**, mounted at
  `/api/initiatives`, following the same shape as `api/events/` (thin routes →
  service layer → `db/rpc.py::call_rpc`). Small enough to omit `core/`.
- **D11 — The job RPC surface is reused, not duplicated.** No `in_*` job
  RPCs. `tk_create_task` gains an optional `p_initiative_id` (mutually
  exclusive with `p_event_id`); `tk_uncommit_task`/`tk_report_done` resolve
  the T-36h lock window and the `JOB_REPORTED` notify fan-out against
  whichever parent (event or initiative) is set. `tk_commit_task`,
  `tk_approve_task`, `tk_reject_task`, and all `ev_*` RPCs are unchanged.
- **D12 — A security assignment IS a `tasks` row (`kind='security'`,
  `people_needed=1`, `status='in_progress'`) plus a pre-created active
  commitment.** No fourth checklist concept (D1). The task id is the
  assignment id; one job card per assigned member falls out of the model. The
  **active commitment is the source of truth for the holder** —
  `tasks.assigned_member_id` stays NULL (no two-column sync through swaps).
  Report/approve/reject reuse `tk_report_done`/`tk_approve_task`/
  `tk_reject_task` unchanged. Claiming/unclaiming are blocked on security
  tasks (`security_preassigned` in `tk_commit_task`, `security_no_unclaim` in
  `tk_uncommit_task`, `security_no_status_change` in `tk_update_task_status`);
  the swap flow is the only way the holder changes. Security tasks are
  **excluded from the notify-gate job count and the `job_count`/
  `open_job_count` decorations** (both the Python count helpers and
  `ev_notify_event`) so a security-only event cannot pass the ≥3-jobs gate.
- **D13 — Swaps are a `security_swap_requests` table + one atomic accept
  RPC.** One pending request per assignment via a unique partial index on
  `(task_id) WHERE status = 'pending'`. `ev_accept_security_swap` flips the
  commitment with **direct row operations inside the RPC** (uncommit requester
  + commit target + append log rows) — no nested `tk_*` calls (the D12 guards
  would reject them). Swaps have **no T-36h lock** (a swap requires another
  member to accept, which is the accountability). Row lifecycle
  `pending → accepted | declined | cancelled`, protected by an update-guard
  trigger (only status resolution may change; deletes blocked) in the
  `event_notification_sends` (0143) style.
- **D14 — Security lives in the events domain; no new permission key.** Routes
  under `/api/events`, RPCs `ev_*`, service/route files in `api/events/`. The
  manage gate (assign/remove) reuses `_require_supervisor_manage` (supervisor
  of the event OR `calendar:event:update`). Swap request/accept/decline are
  gated by **identity** (assignment holder / swap target), checked in the RPCs
  — not permission keys (the membership-not-permission pattern of D5/D9). No
  RBAC seed migration.
- **D15 — An announcement's date/time is calendar presence, not a scheduled
  SMS.** `announcements.calendar_date` / `calendar_time` (0152) put a sent
  announcement on the chapter calendar; `sent_at` still means "when Send was
  pressed" and Twilio still fires on `POST /{id}/send-sms`. There is no
  delayed-send worker. Only `status='sent'`, `audience='chapter'`, dated,
  `hidden_from_calendar=FALSE` rows are aggregated. `DELETE
  /api/announcements/{id}` drops a draft outright and merely sets
  `hidden_from_calendar` on a sent row — the feed post and SMS log survive.
- **D16 — Job delete is cancel, never a hard `DELETE FROM tasks`.**
  `tk_cancel_task` (0152) sets `status='cancelled'` and is allowed only while
  `status='open'` — the last unclaim already reverts a job to `open`, so
  "open" and "no claimants" are one rule stated once. `tk_update_task` edits
  `title`/`description`/`people_needed`/`due_at` on `open`/`in_progress` only;
  parent (`event_id`/`initiative_id`), `kind`, `status` and
  `assigned_member_id` are immutable, and capacity may not drop below the
  active claim count (`job_capacity_below_claims`). Security jobs are refused
  by both (`security_no_edit` / `security_no_cancel`) — roster changes stay on
  the `ev_*` security RPCs (D12). The manage gate is `can_manage_job`
  (`api/tasks/services/approvals.py`): whoever may attach a job to that parent
  may maintain it; standalone jobs fall back to `tasks:assign`/`tasks:review`.
- **D17 — `prior_security_shifts` is a count of approved security jobs the
  member held.** Decorated onto every `GET /api/memberadmin/scores` row
  (commitment `active` or `completed`). It is not a new endpoint, not a
  standing input, and never feeds the 0–100 score.

---

## 3. Build order

| Phase | Scope | Plan doc | Status |
|---|---|---|---|
| 1 | Schema + jobs core: event end time & invite link, `event_supervisors`, job capacity + report/approve/reject + T-36h lock, outbox/audit catalog additions | `docs/imp-ev-ph1.md` | **Done** (migrations 0141/0142) |
| 2 | Notify gate: completeness computation (≥1 supervisor, ≥1 organizer, ≥3 jobs), `POST /{id}/notify` → outbox → SMS, events `notifications.py`, `ORGANIZER_SOFT_MIN` → 1, "last notified" timestamp | `docs/imp-ev-ph2.md` | **Done** (migration 0143) |
| 3 | Initiatives: new entity (chair-created, assigned chairs, required start time), reuses job machinery with chair approval; calendar aggregator includes them | `docs/imp-ev-ph3.md` | **Done** (migration 0144) |
| 4 | Security + swaps: persisted security assignments as a special job type (replace the memberadmin stub), swap requests (one pending per assignment, accept/decline, atomic swap), notifications | `docs/imp-ev-ph4.md` | **Done** (migration 0145) |
| B4FEND | Backend unblocks for Phase 5: `open_job_count` on list/calendar, announcement calendar date + aggregator, job PATCH/DELETE, requester swap cancel, `prior_security_shifts` on scores | `docs/B4FEND-FIX.md` | **Done** (migration 0152) |
| 5 | Frontend: events/tasks contracts+adapters, member-picker primitive, JobCard, event-detail sections (People/Jobs/Security/Notify + checklist + T-36h countdown), calendar badges + week view + mixed chips, initiative/security/swap screens, announcement SMS counter + scheduled time + calendar posting | `docs/imp-ev-ph5.md` | **Wired** in `LocalDev/greekos` (see `greekos/README.md`) — job boards + create/claim/unclaim/report/approve/reject, job edit/delete with 409 copy, security assignments + swap request/accept/decline/cancel, announcements with calendar slots, open-job chips, `prior_security_shifts` ordering. Not in `fratos`; the demo-gated tabs (Rules/Command/Outbox) stay mock-backed |

Phases 1→2→3 are sequential (each builds on the previous schema). Phase 4
depends on Phase 1 only. Phase 5 tracks whatever backend phases have landed —
with Phases 1–4 and B4FEND deployed it is wired end to end in
`LocalDev/greekos` (jobs, security + swaps, announcements, open-job chips).

**Phase 1 landed (migrations 0141/0142) — notes & minor drift from the plan:**
- Audit actions named `ADD_EVENT_SUPERVISOR` / `REMOVE_EVENT_SUPERVISOR` (verb-first,
  matching the existing `ADD_/REMOVE_EVENT_ORGANIZER` style) rather than the plan's
  `EVENT_SUPERVISOR_ADDED`. Job actions `JOB_REPORTED/JOB_APPROVED/JOB_REJECTED`
  are shared by `audit_logs.action` **and** `message_outbox.event_type` (the
  reject-cycle dedup counter in `tk_reject_task`/`tk_report_done` counts
  `JOB_REJECTED` audit rows, so the names must match).
- Co-supervisor eligibility uses a new `OFFICER_ROLES` tuple in
  `api/events/auth.py` (chairs + exec offices), passed to `ev_add_supervisor`.
- `people_needed` is not a `tk_create_task` param (0110 signature left alone); the
  tasks service sets it via a follow-up single-row `UPDATE` after create.
- The T-36h resolver in `tk_uncommit_task` carried a `-- PHASE3 SEAM:` marker
  where the linked-event start is resolved (initiatives add a second parent
  type) — **resolved in Phase 3** (migration 0144 replaces `tk_uncommit_task`/
  `tk_report_done` with versions that branch on `event_id` vs `initiative_id`).
- `events.supervisor_member_id` and `POST /{event_id}/supervisor` are deprecated
  in place (see `api/events/CONFORM_TODO.md`); reads moved to `event_supervisors`.
- `message_outbox` JOB_* rows are written in the RPCs but not yet dispatched
  (delivery becomes user-visible in Phase 2/5); no events-domain `notifications.py`
  was added (that is Phase 2, for `EVENT_NOTIFY`).

**Phase 2 landed (migration 0143) — notes & minor drift from the plan:**
- The soft 1/hour cooldown flagged as "cut-first-if-time-boxed" in the plan
  **was implemented** (not cut): `ev_notify_event` raises `notify_cooldown` if
  an `event_notification_sends` row for the event is younger than 1 hour; the
  HTTP layer maps this to `429`.
- `event_notification_sends` follows the exact append-only shape/guard pattern
  as `announcement_sms_sends` (0131): BEFORE UPDATE trigger allows only
  `status` to advance, BEFORE DELETE trigger blocks hard deletes.
- Notify SMS reuses the announcements dispatch path exactly as planned:
  `api/announcements/services/sms.py`'s `dispatch_send` gained a keyword-only
  `send_table` param (default `"announcement_sms_sends"`); events passes
  `"event_notification_sends"`. No second Twilio integration was added.
- `dedup_key` for `EVENT_NOTIFY` outbox rows includes the send id
  (`EVENT_NOTIFY:{event_id}:{send_id}:{member_id}`), not just event+member, so
  a re-notify after the cooldown elapses fans out fresh rows instead of being
  silently dropped by the first send's dedup key (decision D6).
- Notify permission (D5): supervisor of the event, OR organizer of the event,
  OR holder of `calendar:event:update` — enforced in
  `api/events/services/notifications.py::_require_notify`, reusing
  `events.py`'s existing `_actor_is_supervisor` rather than duplicating it.
- Completeness gate (D7): ≥1 supervisor, ≥1 organizer, ≥3 non-cancelled jobs —
  computed by `api/events/core/rules.py::completeness()` (pure function, unit
  tested independently of the RPC/HTTP layers) and re-checked defense-in-depth
  inside `ev_notify_event` itself.
- Test-file layout deviates slightly from the plan's single
  `tests/events/test_notify.py`: service/RPC-level tests (gate, happy path,
  D6 re-notify) live there; HTTP-layer tests (count mismatch, idempotency,
  permissions, cooldown, no-phone preview, append-only) live in the sibling
  `tests/events/test_notify_api.py`, split for readability. Both are run as
  part of the same `tests/events/` suite.
- The D6 re-notify test cannot back-date an existing send row's `created_at`
  via `UPDATE` (the append-only trigger's column-guard includes `created_at`,
  so any such `UPDATE` raises "append-only" regardless of DB role). Instead,
  the test seeds a synthetic stale send via a direct `INSERT ... created_at =
  now() - interval '2 hours'`, then calls the real service for the fresh send.

**Phase 3 landed (migration 0144) — notes & minor drift from the plan:**
- New `api/initiatives/` domain package (D10): `initiatives`/`initiative_chairs`
  tables, `in_create_initiative`/`in_update_initiative`/`in_add_chair`/
  `in_remove_chair` RPCs (idempotency-key + `chapter_id` guards + `audit_logs`,
  same discipline as every other RPC), `INITIATIVE_CREATED`/`_UPDATED`/
  `_CHAIR_ADDED`/`_CHAIR_REMOVED` audit actions added via the DO-block CHECK
  rebuild. No new `message_outbox` event types — initiative jobs reuse
  `JOB_REPORTED`, fanned out to `initiative_chairs` alongside
  `event_supervisors`.
- `tk_create_task` gained an optional `p_initiative_id UUID DEFAULT NULL`
  (mutually exclusive with `p_event_id`, raising `task_two_parents` if both are
  set); `tk_uncommit_task`/`tk_report_done` were replaced (`CREATE OR REPLACE`,
  same RPC names) to resolve the T-36h window and job-report notification
  fan-out against whichever parent is set — this closes the `PHASE3 SEAM`
  markers left in Phase 1. `tk_commit_task`, `tk_approve_task`,
  `tk_reject_task`, and every `ev_*` RPC are untouched, per the plan's non-goals.
- `api/tasks/services/approvals.py` gained `_is_initiative_chair` /
  `can_create_initiative_job`; `can_approve_job` now has an initiative branch
  alongside its existing event-supervisor branch. No `user["role"] == ...`
  string comparisons were introduced.
- **Deviation (infrastructure fix, outside the plan's file list):**
  `in_create_initiative`'s `p_chair_member_ids UUID[]` is the first RPC
  parameter anywhere in the codebase that is a true SQL array type rather than
  JSONB. The local Postgres shim (`api/postgres_client.py`'s `_RpcBuilder`)
  previously JSON-encoded every list/dict RPC param unconditionally, which is
  correct for existing JSONB-typed params (`ev_notify_event`'s
  `p_recipient_member_ids`, `ev_add_supervisor`'s `p_required_role_keys`) but
  produces a malformed array literal / an untyped-array-vs-`text[]` cast
  failure for a real `UUID[]` param. Fixed with a small explicit allow-list
  (`_RpcBuilder._ARRAY_TYPED_RPC_PARAMS = {("in_create_initiative",
  "p_chair_member_ids")}`) so only that one (function, param) pair renders as
  a raw Postgres array-literal string; every other RPC call keeps the original
  JSON-encoding behavior unchanged. No production code path (Supabase) is
  affected — this only touches the local-dev Postgres client shim.
- Test layout follows the plan's §5 structure exactly: `tests/initiatives/`
  (new: `conftest.py`, `test_initiatives_rpcs.py`, `test_initiatives_api.py`)
  for the domain's own RPC + HTTP tests; `tests/tasks/test_jobs_initiative.py`
  (new) for the extended job lifecycle against an initiative parent; two new
  tests added to `tests/calendar_view/test_calendar_view.py` (with a matching
  `initiative_factory` fixture in that suite's `conftest.py`) for calendar
  aggregation.

**Phase 4 landed (migration 0145) — notes & minor drift from the plan:**
- New `api/events/services/security.py` + `api/events/api/security.py` (included
  in the events domain router after `_events_router`/`_notifications_router`,
  append-only). Six RPCs: `ev_assign_security`, `ev_remove_security`,
  `ev_request_security_swap`, `ev_accept_security_swap`,
  `ev_decline_security_swap` (idempotency-key + `chapter_id` guards +
  `audit_logs`, no `big_ledger` — nothing financial). `tk_commit_task`,
  `tk_uncommit_task`, `tk_update_task_status`, `ev_notify_event` were redefined
  (`CREATE OR REPLACE`, same names) each with one added guard/filter, copying
  the **latest** body of each (`tk_uncommit_task` from 0144, the rest from
  0142/0143). Catalog: `message_outbox.event_type` += the four `SECURITY_*`
  notify events; `audit_logs.action` += those four plus `SECURITY_REMOVED` and
  `SECURITY_SWAP_CANCELLED`, all via the DO-block CHECK rebuild.
- **`ev_cancel_security_swap` was NOT built** (the plan's optional,
  "cut-first-if-time-boxed" RPC). Its audit action `SECURITY_SWAP_CANCELLED`
  was still seeded now (per plan §2.5) to avoid a second catalog migration
  later; `ev_remove_security` (which cancels any pending swap) is the
  supervisor-side escape hatch for a stuck pending request.
- **Count filters are Python-side, not `.neq(...)`.** The plan wrote
  `.neq("kind", "security")`, but the local Postgres shim
  (`api/postgres_client.py`) exposes only `eq`/`in_`/`lte`/`gte`, no `neq`.
  The security exclusion is done in Python in
  `api/events/services/events.py::_job_counts_for_event` and `list_events`
  (mirroring how `_job_counts_for_event` already filters `cancelled`).
  `services/notifications.py` needed **no separate edit** — its completeness
  gate reuses `_job_counts_for_event`, so the one shared helper covers both the
  event-detail decoration and the notify pre-check.
- `list_security` opens with `_get_event_row` so `GET /{event_id}/security`
  returns **404 for a cross-tenant/missing event** (plan's route table:
  "404 on cross-tenant/missing id"); without it the empty-roster query would
  200. `remove_security` likewise verifies the task is a security task **of
  that event** (404 otherwise) so a supervisor of event A can't remove event
  B's security row through a mismatched URL.
- `GET /api/events/security-swaps/mine` returns
  `{"incoming": [...], "outgoing": [...]}` (pending rows where the caller is
  target vs requester). It is registered before the `/{event_id}/...` dynamic
  routes; verified it is not shadowed (no events GET route matches a
  two-segment path whose 2nd segment is `mine`).
- `tasks.kind` is surfaced to the frontend for free: `list_tasks`/`get_task`
  already `select("*")`, so `kind` flows through; a defensive
  `row["kind"] = row.get("kind", "standard")` was added to `list_tasks`
  (mirrors the `people_needed` normalization). No `TaskOut` response model
  exists to extend — the tasks routes return raw dicts. `api/tasks/api/jobs.py`
  `_rpc_http_error` gained `security_preassigned`/`security_no_unclaim` in its
  409 branch.
- The non-persisting `POST /api/memberadmin/assign-security` stub was deleted
  (`api/memberadmin/api/scores.py`); `/scores` and `/member/{id}` (still on
  legacy `require_officer`) are untouched — that auth migration remains
  separate debt.
- Test layout follows plan §5: `tests/events/test_security.py` (11 RPC-level
  behaviors) + `tests/events/test_security_api.py` (items 12-17, HTTP). The
  plan named fixtures `event_factory`/`hours_from_now` that don't exist in
  `tests/events/conftest.py`; the actual fixtures are `create_event`,
  `user_factory`, `assign_role`, and the T-36h test computes a 12h-out start
  inline with a small `_future(hours)` helper. `app_on_test_db` in the events
  conftest gained a `security_api.get_events_db` monkeypatch.

**B4FEND landed (migration 0152) — notes & minor drift from the plan:**
- Migration numbered **0152**, not the plan's original 0147: 0147–0151 were
  taken by the ops/auth/RBAC pass of 2026-08-16.
- `_rpc_http_error` is **shared, not copied**: `api/tasks/api/jobs.py` grew a
  module-level `_CONFLICT` tuple (now also holding `security_no_edit`,
  `security_no_cancel`, `job_not_editable`, `job_not_cancellable`,
  `job_capacity_below_claims`) and `api/tasks/api/tasks.py` imports the mapper
  rather than keeping a twin. `job_title_required` /
  `job_people_needed_invalid` map to 422.
- The plan's §4.5 note about `get_supabase_admin()` / `use_admin` is stale —
  ADR-0002 deleted the supabase-py path, so `_prior_security_shifts` uses the
  single `get_db()` like every other reader.
- `hide_from_calendar` returns `{"id", "deleted", "hidden_from_calendar"}`.
  `DELETE /api/announcements/{id}` is method-distinct from `GET /sms-log`, so
  route order needed no change.
- `tk_update_task` treats a NULL param as "leave that column alone" (PATCH
  semantics), so clearing a description is out of reach — no screen asks for
  it. `TaskUpdate` rejects an empty body (422) and simply has no parent/kind/
  status fields, so those are dropped rather than 422'd.
- Test layout: calendar chips + announcement items went into a new
  `tests/calendar_view/test_calendar_chips.py` (the existing
  `test_calendar_view.py` stays focused on aggregation); the list-endpoint
  `open_job_count` assertion sits next to the existing detail-count test in
  `tests/events/test_security_api.py`; announcement columns/DELETE in
  `tests/announcements/test_calendar_fields.py`; job edit/cancel in
  `tests/tasks/test_job_update.py`; swap cancel appended to
  `tests/events/test_security.py` + `test_security_api.py`; prior shifts in
  `tests/memberadmin/test_prior_security_shifts.py`.
- **Pre-existing red on the shared demo DB (11 tests), none caused by 0152.**
  Verified by running the same set against the `main` checkout (identical
  failures) and by inspecting 0152, which only adds `announcements` columns +
  a partial index, rebuilds the `audit_logs` CHECK additively (all 42 actions
  any migration writes are still allowed), and creates three function names
  that existed nowhere before. Causes found:
  - `tests/events/test_notify_api.py::test_preview_no_phone_exclusion` — sets a
    whitespace-only phone, which 0149's `members_phone_e164` CHECK now rejects.
  - `tests/cron/test_drain_outbox.py` (4) — the drain records `simulated`
    where the tests expect `failed`/`delivered`; a delivery-mode config seam,
    not a schema one.
  - `tests/treasury/test_v1_fines.py` (3) + `test_v1_allocation.py` (1) —
    permission gates return 200 where 403 is expected; RBAC seed state on the
    shared demo DB after 0147's one-gate pass.
  - `tests/auth/test_invite_setup_codes.py` (2) — a redeemed token
    authenticates as the wrong member (auth-domain fixture/session issue).
- **Shared-DB repair (not a code change):** `big_ledger`'s two append-only
  triggers and `fines_frozen` were sitting `DISABLED` on the demo DB — the
  signature of an interrupted `scripts/seed.py`, which disables USER triggers
  on exactly those two tables (lines 187-193) before re-enabling them. Five
  treasury append-only tests were failing on that alone. Re-enabled with
  `ALTER TABLE {big_ledger,fines} ENABLE TRIGGER USER`; those five are green
  again. Worth hardening seed.py to re-enable in a `finally`.

---

## 4. How to continue implementation (instructions for the next session)

1. **Read, in order:** this file → `docs/events-v1-spec.md` → the plan doc for
   the phase you're implementing (or the previous phase's plan if you're
   writing the next one). Also skim `CLAUDE.md` hard rules and
   `docs/ARCHITECTURE.md`.
2. **Re-verify the migration frontier before writing DDL.** Phase 1 assumed the
   highest migration was `0140_usage_events.sql` and numbered from **0141**.
   Run `ls migrations/ | tail` — if newer migrations exist, renumber. Never
   edit an applied migration; always add new files (lexical order applies).
3. **Planning a new phase:** write `docs/imp-ev-phN.md` following the shape of
   `imp-ev-ph1.md` (scope & assumptions → migrations with concrete DDL → RPC
   signatures → endpoint list → backend code changes → tests → non-goals →
   execution checklist). Ground every column/function name by reading the
   actual migrations first — do not trust this doc's snapshot blindly; earlier
   phases will have changed things.
4. **Update this file when a phase lands:** flip its Status, note the migration
   numbers it consumed, and record any decision changes under §2.
5. **Conventions that apply to every phase** (enforced, see CLAUDE.md):
   - Multi-row / trust-boundary mutations go through plpgsql RPCs
     (`db/rpc.py` → `call_rpc`) with `chapter_id` guards, `idempotency_keys`,
     and `audit_logs` writes. Treasury is the reference.
   - New `message_outbox.event_type` and `audit_logs.action` values require the
     additive DO-block CHECK-rebuild pattern (copy from 0100/0131).
   - Every new tenant table: `chapter_id` FK + RLS (via `rbac_request_chapter_id()`).
   - Permission checks via `api/rbac` only — no role-string comparisons.
   - Money is integer cents; never copy the legacy `events.fine_amount` float.
   - Backend tests: pytest from `LocalDev/` against a real Postgres
     (`TEST_DATABASE_URL` / `.env`), `asyncio_mode=auto`. Add per-phase tests
     under `tests/events/` and `tests/tasks/`.
   - Frontend (Phase 5): pages thin, modules own workflows, DTO→contract via
     adapters, `formatMoney(cents)`, capability gating via `usePermissions().can()`.
6. **Phase-specific pointers for the next planner:**
   - *Phase 3:* **done** — see the "Phase 3 landed" notes above.
   - *Phase 4:* **done** — see the "Phase 4 landed" notes above. The Screen 6
     picker composes `GET /api/memberadmin/scores` (delinquency-ordered) with
     `GET /api/events/{id}/security`; the persisted assignment surface is the
     `ev_assign_security`/`ev_remove_security` + swap RPCs. The
     `POST /api/memberadmin/assign-security` stub was deleted (`/scores` +
     `/member/{id}` keep their legacy `require_officer` — separate debt).
   - *B4FEND:* **done** (migration 0152) — `docs/B4FEND-FIX.md`. All seven
     backend gaps are closed: `open_job_count` on `GET /api/events/` **and**
     the calendar aggregator (whose event items now also carry `time`,
     `end_date`, `end_time`, `job_count`, `completeness`), announcement
     `calendar_date`/`calendar_time` + a `kind='announcement'` calendar item +
     `DELETE /api/announcements/{id}`, `PATCH`/`DELETE /api/tasks/{id}`
     (`tk_update_task`/`tk_cancel_task`),
     `POST /api/events/{event_id}/security/swaps/{swap_id}/cancel`
     (`ev_cancel_security_swap`), and `prior_security_shifts` on
     `GET /api/memberadmin/scores`. Decisions D15–D17 above.
   - *Phase 5:* create `lib/contracts/events.ts` + `lib/adapters/events.ts`
     (and tasks/jobs equivalents) *first*; build the member-picker primitive in
     `components/ui/`; the existing `components/countdown.tsx` is mm:ss and
     legacy-themed — build a day/hour variant on design tokens instead. Assume
     B4FEND has landed — do not re-plan those backend gaps in the Phase 5 doc.
