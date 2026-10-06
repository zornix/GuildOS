"""Announcements permission keys (catalog-seeded; gate with api.rbac.auth.require_permission)."""

from __future__ import annotations

ANNOUNCEMENTS_CREATE = "announcements:create"
ANNOUNCEMENTS_SEND = "announcements:send"
# SMS blasts are President/Secretary only (seeded in 0130; admin too).
ANNOUNCEMENTS_SEND_SMS = "announcements:send:sms"
