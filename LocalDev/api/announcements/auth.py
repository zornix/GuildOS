"""Announcements domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

ANNOUNCEMENTS_CREATE = "announcements:create"
ANNOUNCEMENTS_SEND = "announcements:send"
