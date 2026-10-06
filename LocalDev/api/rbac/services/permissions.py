"""Permission resolution — THE single source of truth for authorization.

Resolution = member_roles ∪ the member baseline. The legacy members.role
column is display-only and never grants anything (F-022).
"""

from __future__ import annotations

from api.rbac.core.policy import permission_allows
from api.rbac.db.repositories.member_roles import (
    list_member_role_keys,
    list_permissions_for_roles,
)
from api.platform.db import get_db

# The one role key that does NOT make someone an officer. Everything else in the
# catalog — officer, president, treasurer, secretary, the chairs — does.
NON_OFFICER_ROLE_KEYS = {"member"}


def _effective_role_keys(member: dict, role_keys) -> set[str]:
    """member_roles plus the baseline every member holds. The legacy
    members.role column is display-only and never grants anything (F-022)."""
    return set(role_keys) | {"member"}


def is_officer(member: dict, role_keys) -> bool:
    """THE definition of "who counts as an officer" — one place, not three.

    Same roles `get_member_permissions` resolves permissions from, so audience
    membership cannot disagree with authorization. Only a member_roles key
    other than `member` counts; the legacy members.role column does not.

    `role_keys` is the member's member_roles keys (the caller already has them —
    from a per-member lookup or one chapter-wide fetch — so this stays I/O-free).
    """
    return bool(_effective_role_keys(member, role_keys) - NON_OFFICER_ROLE_KEYS)


def get_member_permissions(member: dict, *, sb=None) -> set[str]:
    client = sb or get_db()
    cached = member.get("_rbac")
    if cached is None:
        keys = list_member_role_keys(client, chapter_id=member["chapter_id"], member_id=member["id"])
        cached = member["_rbac"] = {
            "roles": sorted(keys),
            "permissions": frozenset(list_permissions_for_roles(client, sorted(_effective_role_keys(member, keys)))),
        }
    return set(cached["permissions"])


def get_member_role_keys(member, *, sb=None) -> list[str]:
    get_member_permissions(member, sb=sb)
    return member["_rbac"]["roles"]


def has_permission(
    member: dict,
    permission: str,
    resource: dict | None = None,
    *,
    sb=None,
) -> bool:
    granted = get_member_permissions(member, sb=sb)
    return permission_allows(granted, permission, member=member, resource=resource)
