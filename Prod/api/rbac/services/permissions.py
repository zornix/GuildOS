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
from api.platform.db import get_db

# The one role key that does NOT make someone an officer. Everything else in the
# catalog — officer, president, treasurer, secretary, the chairs — does.
NON_OFFICER_ROLE_KEYS = {"member"}


def _effective_role_keys(member: dict, role_keys) -> set[str]:
    """member_roles ∪ the role mapped from the legacy members.role column."""
    keys = set(role_keys)
    legacy = LEGACY_ROLE_COMPAT.get(member.get("role") or "")
    if legacy:
        keys.add(legacy)
    return keys


def is_officer(member: dict, role_keys) -> bool:
    """THE definition of "who counts as an officer" — one place, not three.

    Same union `get_member_permissions` resolves permissions from, so audience
    membership cannot disagree with authorization. A member promoted through
    `PUT /members/{id}/role` before 0154 has only the legacy column; one promoted
    through `rbac_assign_role` has only a member_roles row. Both are officers.

    `role_keys` is the member's member_roles keys (the caller already has them —
    from a per-member lookup or one chapter-wide fetch — so this stays I/O-free).
    """
    return bool(_effective_role_keys(member, role_keys) - NON_OFFICER_ROLE_KEYS)


def get_member_permissions(member: dict, *, sb=None) -> set[str]:
    client = sb or get_db()
    role_keys = _effective_role_keys(
        member,
        list_member_role_keys(
            client, chapter_id=member["chapter_id"], member_id=member["id"]
        ),
    )
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
