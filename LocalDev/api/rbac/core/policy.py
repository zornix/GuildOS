"""Pure permission policy — no I/O.

Ownership-context convention (documented in docs/services/permissions-matrix.md):
some permissions are *ownership-scoped*. Holding one lets a member act on their
OWN resource; acting on someone else's requires the escalation permission from
OWNERSHIP_ESCALATIONS. Routes opt in by passing a `resource` dict with an
`owner_member_id` key; routes that pass no resource get plain set-membership.
"""

from __future__ import annotations

# The legal values of the display-only members.role column. Not an input to permissions.
LEGACY_ROLE_COMPAT: dict[str, str] = {
    "officer": "officer",
    "member": "member",
}

# permission → escalation permission that unlocks acting on others' resources.
OWNERSHIP_ESCALATIONS: dict[str, str] = {
    "tasks:complete": "tasks:review",
}


def permission_allows(
    granted: set[str],
    permission: str,
    *,
    member: dict,
    resource: dict | None = None,
) -> bool:
    """Decide whether `granted` permits `permission`, honoring ownership scope."""
    if permission not in granted:
        return False

    escalation = OWNERSHIP_ESCALATIONS.get(permission)
    if escalation is None or resource is None:
        return True

    owner = resource.get("owner_member_id")
    if owner is None or owner == member.get("id"):
        return True
    return escalation in granted
