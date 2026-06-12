# Attendance — remaining conformance work

Status: package boundary + delegation in place; legacy handlers not yet relocated.

Done
- `api/attendance/api/router.py` is the `/api/attendance` mount (legacy handlers
  + new `/sessions` endpoints); excuses / checkin-links / checkin-page routers
  are re-exported for their unchanged prefixes (`/api/excuses`,
  `/api/checkin-links`, `/c`).
- `attendance_sessions` table (0084) layered over attendance/excuses; a
  short_link/qr session opens a REAL link via api/services/checkin_links.py and
  backfills `events.linked_attendance_session_id`.
- `services/signals.py` exposes the unexcused-absence read seam for standing.

TODO (behavior-preserving, one route at a time, keep e2e green)
- Move `api/routes/attendance.py`, `excuses.py`, `checkin_links.py`,
  `checkin_page.py` handlers into `api/attendance/api/*`; move
  `api/services/checkin_links.py` into `api/attendance/services/`.
- Move `PhoneCheckIn`/`ManualAttendance` from `api/models/schemas.py` into
  `api/attendance/api/schemas.py`.
- Swap `require_officer` for `require_permission(ATTENDANCE_OVERRIDE)` /
  `require_permission(CHECKIN_CREATE)` / `require_permission(EXCUSE_REVIEW)`
  after verifying e2e specs (legacy officers resolve these via the compat map).
- Teach the check-in flow to stamp the session id on attendance rows once
  sessions are the primary surface (today the legacy flow works without one).
- Have closes_at actually close a session (today checkin_links TTL is the only
  expiry; a session row is informational).
