"""Permission resolver — unions member_roles with the legacy members.role.

The supabase client is the system boundary; a minimal fake stands in for it.
"""

from __future__ import annotations

from api.rbac.services.permissions import get_member_permissions, has_permission


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._rows)


class FakeSb:
    """Returns canned rows per table; chapter/member filtering is the query's job."""

    def __init__(self, member_roles, role_permissions):
        self._tables = {
            "member_roles": member_roles,
            "role_permissions": role_permissions,
        }

    def table(self, name):
        return _Query(self._tables[name])


OFFICER = {"id": "m-1", "chapter_id": "c-1", "role": "officer"}
MEMBER = {"id": "m-2", "chapter_id": "c-1", "role": "member"}


def test_unions_granular_roles_with_legacy_role():
    sb = FakeSb(
        member_roles=[{"role_key": "treasurer"}],
        role_permissions=[
            {"role_key": "treasurer", "permission_key": "treasury:payment:verify"},
            {"role_key": "member", "permission_key": "bylaws:query"},
        ],
    )
    perms = get_member_permissions(MEMBER, sb=sb)
    assert perms == {"treasury:payment:verify", "bylaws:query"}


def test_legacy_only_member_still_resolves_permissions():
    sb = FakeSb(
        member_roles=[],
        role_permissions=[{"role_key": "officer", "permission_key": "tasks:assign"}],
    )
    assert has_permission(OFFICER, "tasks:assign", sb=sb)
    assert not has_permission(OFFICER, "roles:assign", sb=sb)


def test_ownership_context_flows_through():
    sb = FakeSb(
        member_roles=[],
        role_permissions=[{"role_key": "member", "permission_key": "tasks:complete"}],
    )
    own = {"owner_member_id": "m-2"}
    foreign = {"owner_member_id": "m-9"}
    assert has_permission(MEMBER, "tasks:complete", resource=own, sb=sb)
    assert not has_permission(MEMBER, "tasks:complete", resource=foreign, sb=sb)
