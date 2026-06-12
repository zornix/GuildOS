"""Events domain permissions — thin layer over the central RBAC helper.

The legacy handlers still gate with require_officer; new/migrated handlers use
these granular permissions instead (see CONFORM_TODO.md).
"""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

EVENT_CREATE = "calendar:event:create"
EVENT_UPDATE = "calendar:event:update"
EVENT_DELETE = "calendar:event:delete"
OFFICER_VIEW = "calendar:officer:view"
