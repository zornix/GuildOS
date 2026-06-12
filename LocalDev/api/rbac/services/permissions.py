"""Permission resolution — THE single source of truth for authorization.

Resolution = union of:
  1. permissions of every role in member_roles for this member/chapter, and
  2. permissions of the role mapped from the legacy members.role column
     (core.policy.LEGACY_ROLE_COMPAT), so pre-RBAC accounts keep working.
"""

from __future__ import annotations

from api.rbac.core.policy import LEGACY_ROLE_COMPAT, permission_allows
from api.rbac.db.repositories.member_roles import (
    list_member_role_keys,
    list_permissions_for_roles,
)
from api.rbac.db.session import get_rbac_db


def get_member_permissions(member: dict, *, sb=None) -> set[str]:
    client = sb or get_rbac_db()
    role_keys = set(
        list_member_role_keys(
            client, chapter_id=member["chapter_id"], member_id=member["id"]
        )
    )
    legacy = LEGACY_ROLE_COMPAT.get(member.get("role", ""))
    if legacy:
        role_keys.add(legacy)
    return list_permissions_for_roles(client, sorted(role_keys))


def has_permission(
    member: dict,
    permission: str,
    resource: dict | None = None,
    *,
    sb=None,
) -> bool:
    granted = get_member_permissions(member, sb=sb)
    return permission_allows(granted, permission, member=member, resource=resource)
