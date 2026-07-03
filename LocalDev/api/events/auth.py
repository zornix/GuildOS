"""Events domain permissions — thin layer over the central RBAC helper.

No inline role/permission strings in route handlers: the service layer checks
CHAIR_ROLES (supervisor eligibility, spec §1) and the routes gate with
require_permission on the calendar:* permissions below.
"""

from __future__ import annotations

from api.rbac.auth import require_permission  # noqa: F401  (domain re-export)

EVENT_CREATE = "calendar:event:create"
EVENT_UPDATE = "calendar:event:update"
EVENT_DELETE = "calendar:event:delete"
OFFICER_VIEW = "calendar:officer:view"

# Supervisor eligibility (spec §1: "must hold a chair position").
CHAIR_ROLES: tuple[str, ...] = (
    "risk_chair",
    "social_chair",
    "recruitment_chair",
    "brotherhood_chair",
    "philanthropy_chair",
    "standards_chair",
)

# Co-supervisor eligibility (spec §2.1: co-supervisors must hold an officer role).
# Superset of CHAIR_ROLES plus the executive board.
OFFICER_ROLES: tuple[str, ...] = CHAIR_ROLES + (
    "president",
    "vice_president",
    "treasurer",
    "secretary",
)
