# Events — remaining conformance work

Status: package boundary + delegation in place; handlers not yet relocated.

Done
- `api/events/api/router.py` is the mount point (`/api/events` in `api/index.py`);
  it delegates to `api/routes/events.py` unchanged.
- `events` table extended (migration 0090): `event_type`, `visibility`,
  `linked_task_group_id`, `linked_attendance_session_id`, `linked_announcement_id`,
  `linked_budget_id` — all nullable/defaulted.
- `EventCreate`/`EventUpdate` accept optional `event_type`/`visibility` and the
  handlers pass them through.
- `api/events/auth.py` defines the calendar permissions.

TODO (behavior-preserving, move one route at a time, keep e2e green)
- Move handlers from `api/routes/events.py` into `api/events/api/events.py`;
  move `EventCreate`/`EventUpdate`/`EventResponse` out of `api/models/schemas.py`
  into `api/events/api/schemas.py`.
- Swap `require_officer` for `require_permission(EVENT_CREATE)` etc. — only after
  verifying e2e specs still pass (legacy officers resolve these permissions via
  the compatibility mapping, so this is safe but must be verified).
- Add a service layer (`api/events/services/events.py`); handlers become thin.
- Enforce `visibility` in list/get queries (`calendar:officer:view` for
  visibility='officer'); currently visibility is stored but not yet filtered.
- Wire `linked_*` columns when creating sessions/task groups from an event
  (the attendance sessions service already backfills
  `linked_attendance_session_id`).
