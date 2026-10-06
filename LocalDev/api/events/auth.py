"""Events domain permissions and role sets.

No inline role/permission strings in route handlers: the service layer checks
CHAIR_ROLES (supervisor eligibility) and the routes gate with
require_permission on the calendar:* permissions below.
"""

from __future__ import annotations

EVENT_CREATE = "calendar:event:create"
EVENT_UPDATE = "calendar:event:update"
EVENT_DELETE = "calendar:event:delete"
OFFICER_VIEW = "calendar:officer:view"

# Supervisor eligibility: must hold a chair position.
CHAIR_ROLES: tuple[str, ...] = (
    "risk_chair",
    "social_chair",
    "rush_chair",
    "brotherhood_chair",
    "philanthropy_chair",
    "standards_chair",
)

# Co-supervisor eligibility: co-supervisors must hold an officer role.
# Superset of CHAIR_ROLES plus the executive board.
OFFICER_ROLES: tuple[str, ...] = CHAIR_ROLES + (
    "president",
    "vice_president",
    "treasurer",
    "secretary",
)
