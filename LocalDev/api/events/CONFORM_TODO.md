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

Remaining
- Wire `linked_*` columns when creating sessions/task groups from an event
  (the attendance sessions service already backfills
  `linked_attendance_session_id`).
- TODO(events): event delete is still a plain delete with no audit entry;
  consider an ev_delete_event RPC if delete becomes consequential.
