"""Attendance domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

CHECKIN_CREATE = "attendance:checkin:create"
ATTENDANCE_OVERRIDE = "attendance:override"
EXCUSE_REVIEW = "attendance:excuse:review"
