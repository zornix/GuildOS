"""Attendance permission keys (catalog-seeded; gate with api.rbac.auth.require_permission)."""

from __future__ import annotations

CHECKIN_CREATE = "attendance:checkin:create"
CHECKIN_LINK_MANAGE = "attendance:checkin_link:manage"
ATTENDANCE_OVERRIDE = "attendance:override"
EXCUSE_REVIEW = "attendance:excuse:review"

# Calendar-domain permission consumed by the attendance-summary read
# (officer-or-self semantics; defined centrally in the RBAC catalog).
CALENDAR_OFFICER_VIEW = "calendar:officer:view"
