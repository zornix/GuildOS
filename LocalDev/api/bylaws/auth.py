"""Bylaws domain permissions — thin layer over the central RBAC helper."""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

BYLAWS_QUERY = "bylaws:query"
BYLAWS_ADMIN = "bylaws:admin"
