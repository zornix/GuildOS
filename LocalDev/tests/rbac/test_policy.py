"""Core RBAC policy — pure logic, no I/O (api/rbac/core/policy.py)."""

from __future__ import annotations

from api.rbac.core.policy import (
    LEGACY_ROLE_COMPAT,
    OWNERSHIP_ESCALATIONS,
    permission_allows,
)

MEMBER = {"id": "m-1", "chapter_id": "c-1", "role": "member"}


def test_granted_permission_allows():
    assert permission_allows({"tasks:create"}, "tasks:create", member=MEMBER)


def test_missing_permission_denies():
    assert not permission_allows({"tasks:create"}, "roles:assign", member=MEMBER)


def test_ownership_scoped_permission_allows_own_resource():
    granted = {"tasks:complete"}
    own_task = {"owner_member_id": "m-1"}
    assert permission_allows(granted, "tasks:complete", member=MEMBER, resource=own_task)


def test_ownership_scoped_permission_denies_foreign_resource_without_escalation():
    granted = {"tasks:complete"}
    other_task = {"owner_member_id": "m-2"}
    assert not permission_allows(granted, "tasks:complete", member=MEMBER, resource=other_task)


def test_escalation_permission_allows_foreign_resource():
    granted = {"tasks:complete", "tasks:review"}
    other_task = {"owner_member_id": "m-2"}
    assert permission_allows(granted, "tasks:complete", member=MEMBER, resource=other_task)


def test_no_resource_context_means_plain_grant_check():
    # Routes that don't pass a resource get the plain set-membership behavior.
    assert permission_allows({"tasks:complete"}, "tasks:complete", member=MEMBER, resource=None)


def test_legacy_compat_maps_both_known_roles():
    assert LEGACY_ROLE_COMPAT["officer"] == "officer"
    assert LEGACY_ROLE_COMPAT["member"] == "member"


def test_ownership_escalations_cover_tasks_complete():
    assert OWNERSHIP_ESCALATIONS["tasks:complete"] == "tasks:review"
