# Events — conformance status

Status: **conformed** (V1 events build, June 2026). The package now follows the
canonical domain shape end to end.

Done
- `api/events/api/router.py` is the mount point (`/api/events` in `api/index.py`).
- Handlers live in `api/events/api/events.py` and are thin; business logic and
  authorization live in `api/events/services/events.py`.
- Domain-local schemas in `api/events/api/schemas.py` (nothing event-shaped is
  left in `api/models/schemas.py`).
- `require_officer` swapped for `require_permission(EVENT_CREATE/UPDATE/DELETE)`
  on create/update/delete (legacy officers resolve via the compatibility
  mapping). The check-in-link handlers intentionally keep `require_officer`
  (legacy surface, unchanged).
- `visibility` IS enforced in list/get (`calendar:officer:view` for
  visibility='officer'; 'custom' audiences via `event_audience_members`;
  supervisors/organizers/creators always see their events).
- V1 model (migrations 0100/0101): `event_types` (case-insensitive unique,
  seeded defaults), `event_groups`, `event_organizers`, `event_audience_members`,
  `finable`, `supervisor_member_id` (chair-gated via CHAIR_ROLES in auth.py),
  ev_* RPCs with tenant guards + idempotency + audit_logs.

Phase 1 (V1, migrations 0141/0142 — July 2026)
- Co-supervisors: `event_supervisors` join table is now the source of truth
  (creator locked in as `is_creator`, min-1 invariant). `ev_add_supervisor` /
  `ev_remove_supervisor` RPCs; `ev_create_event` seeds the creator row.
- **DEPRECATED — `events.supervisor_member_id`**: no longer written; all reads
  moved to `event_supervisors`. Column kept in place for the legacy backfill;
  drop in a later phase once no consumer references it.
- **DEPRECATED — `POST /{event_id}/supervisor`**: kept for back-compat but now
  delegates to add-supervisor (a co-supervisor add, not a single-slot replace).
  New callers should use `POST /{event_id}/supervisors` and
  `DELETE /{event_id}/supervisors/{member_id}`.
- Events gained `end_date` / `end_time` / `invite_link` (nullable; end>start
  validated in the service, not a DB CHECK).

Phase 2 (V1, migration 0143 — July 2026)
- Notify gate: `api/events/services/notifications.py` (new) gates a "Notify
  members" SMS blast on completeness (≥1 supervisor, ≥1 organizer, ≥3
  non-cancelled jobs, computed by `api/events/core/rules.py::completeness()`)
  and a 1/hour per-event cooldown, both re-checked inside the `ev_notify_event`
  RPC as defense in depth.
- New HTTP surface `api/events/api/notifications.py`: `GET
  /{event_id}/notify-preview` (checklist + recipient counts, no side effects)
  and `POST /{event_id}/notify` (two-phase confirm, `Idempotency-Key` header).
  Mounted alongside `events.py`'s router in `api/events/api/router.py`.
- `api/announcements/services/sms.py`'s `dispatch_send` gained a keyword-only
  `send_table` param (default `"announcement_sms_sends"`) so events' notify
  send reuses the same dry_run/twilio dispatch path via
  `send_table="event_notification_sends"` instead of a second Twilio
  integration; the existing announcements call site is unaffected.
- New append-only table `event_notification_sends` (0143), same
  update/delete-guard shape as `announcement_sms_sends` (0131); RLS scoped to
  `chapter_id`. New `message_outbox` event type `EVENT_NOTIFY` and
  `audit_logs` action `EVENT_NOTIFY` (catalog CHECKs extended via the DO-block
  rebuild pattern).
- `EventResponse` (schemas.py) gained optional `job_count`, `open_job_count`,
  `completeness`, `last_notified_at` fields per the plan, though `EventResponse`
  itself is not currently wired as a FastAPI `response_model` anywhere in
  `events.py` — it appears to be documentation-only/orphaned already, unrelated
  to this phase.

Remaining
- Wire `linked_*` columns when creating sessions/task groups from an event
  (the attendance sessions service already backfills
  `linked_attendance_session_id`).
- TODO(events): event delete is still a plain delete with no audit entry;
  consider an ev_delete_event RPC if delete becomes consequential.
