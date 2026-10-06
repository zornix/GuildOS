"""Permission resolver against the live catalog.

Resolution is member_roles plus the implicit member baseline. The legacy
members.role column grants nothing.
"""

from __future__ import annotations

import uuid

from api.rbac.services.permissions import get_member_permissions, has_permission


def _load(sb, member_id):
    return sb.table("members").select("*").eq("id", member_id).single().execute().data


def _grant(cursor, chapter_id, member_id, role_key):
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, %s)",
        (chapter_id, member_id, role_key),
    )


def test_unions_granular_roles_with_the_member_baseline(
    sb_client, chapter_id, member_factory, cursor
):
    target = member_factory()
    _grant(cursor, chapter_id, target, "treasurer")
    perms = get_member_permissions(_load(sb_client, target), sb=sb_client)
    expected = {
        r["permission_key"]
        for r in sb_client.table("role_permissions")
        .select("permission_key")
        .in_("role_key", ["treasurer", "member"])
        .execute()
        .data
    }
    assert perms == expected
    assert "treasury:payment:verify" in perms
    assert "bylaws:query" in perms


def test_legacy_column_alone_does_not_resolve_officer_permissions(
    sb_client, cursor, member_factory
):
    target = member_factory()
    cursor.execute("UPDATE members SET role = 'officer' WHERE id = %s", (target,))
    officer = _load(sb_client, target)
    assert not has_permission(officer, "tasks:assign", sb=sb_client)
    assert not has_permission(officer, "roles:assign", sb=sb_client)


def test_ownership_context_flows_through(sb_client, member_factory):
    target = member_factory()
    member = _load(sb_client, target)
    own = {"owner_member_id": member["id"]}
    foreign = {"owner_member_id": str(uuid.uuid4())}
    assert has_permission(member, "tasks:complete", resource=own, sb=sb_client)
    assert not has_permission(member, "tasks:complete", resource=foreign, sb=sb_client)


def test_officer_grant_does_not_cross_chapters(
    sb_client, cursor, chapter_id, member_factory
):
    home = member_factory()
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s, 'o', 's') RETURNING id",
        (f"rbac-other-{uuid.uuid4()}",),
    )
    other = str(cursor.fetchone()["id"])
    _grant(cursor, chapter_id, home, "officer")
    member = _load(sb_client, home)
    member["chapter_id"] = other
    assert "roles:assign" not in get_member_permissions(member, sb=sb_client)
