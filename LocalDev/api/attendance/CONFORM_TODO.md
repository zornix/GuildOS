# Attendance — conformance status

Status: fully conformed to the domain-package layout. Kept as a historical
record; delete once the next audit confirms nothing references it.

Done
- `api/attendance/api/router.py` is the `/api/attendance` mount; excuses /
  checkin-links / checkin-page routers are re-exported for their unchanged
  prefixes (`/api/excuses`, `/api/checkin-links`, `/c`).
- Legacy handler relocation — `api/routes/`, `api/services/`, `api/models/`
  no longer exist; handlers live in `api/attendance/api/*`, services in
  `api/attendance/services/*`, schemas (`PhoneCheckIn`, `ManualAttendance`, …)
  in `api/attendance/api/schemas.py`.
- Permission gates — every attendance gate is a catalog key
  (`attendance:override`, `attendance:checkin:create`,
  `attendance:excuse:review`, `attendance:checkin_link:manage`);
  `require_officer` no longer exists (0147 / imp-one-gate.md Phase B).
- `closes_at` is enforced: `validate_checkin_link` resolves the session bound
  to the link (`attendance_sessions.checkin_link_id`) and rejects check-ins
  past its close time, in addition to the link TTL.
- `attendance_sessions` table (0084) layered over attendance/excuses; a
  short_link/qr session opens a REAL link via
  `api/attendance/services/checkin_links.py` and backfills
  `events.linked_attendance_session_id`.
- `services/signals.py` exposes the unexcused-absence read seam for standing.

Explicitly not done (decided, not pending)
- Attendance rows carry no `session_id` column — the audit's "stamp
  session_id" item assumed a column that never existed. The session↔check-in
  relation runs through `checkin_links` (`attendance_sessions.checkin_link_id`),
  and `closes_at` enforcement above is the behavior that mattered. Add the
  column only if a real product need appears.
