"""Announcements domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

ANNOUNCEMENTS_CREATE = "announcements:create"
ANNOUNCEMENTS_SEND = "announcements:send"
# SPEC §6: SMS blasts are President/Secretary only (seeded in 0130; admin too).
ANNOUNCEMENTS_SEND_SMS = "announcements:send:sms"
