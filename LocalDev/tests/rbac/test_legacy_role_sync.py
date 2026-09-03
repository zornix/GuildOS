"""Promotion and demotion write BOTH sides of "is an officer" (issue #28).

Permissions resolve from `member_roles` unioned with the legacy `members.role`
column. `PUT /members/{id}/role` used to write only the column, so after 0147
backfilled an `officer` member_roles row for every then-active officer, demoting
someone revoked nothing — they kept roles:assign, treasury:refund:create and
attendance:override while the roster showed them as an ordinary member.

The handler is awaited directly rather than through a TestClient: `get_db` is
the only boundary it has, and the assertions here are about what lands in the
database, not about routing.

DB-backed (skips without TEST_DATABASE_URL, like the rest of the suite).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.members.api.members import update_role
from api.rbac.services.permissions import get_member_permissions

# The keys the officer role carries that a demoted member must lose (0147 §3).
OFFICER_ONLY_KEYS = ["roles:assign", "treasury:refund:create", "attendance:override"]


@pytest.fixture
def set_role(sb_client, monkeypatch, chapter_id):
    """Call the real PUT /members/{id}/role handler against the test database."""
    import api.members.api.members as members_api

    monkeypatch.setattr(members_api, "get_db", lambda: sb_client)

    async def _set(member_id: str, role: str, *, chapter: str | None = None):
        officer = {"id": member_id, "chapter_id": chapter or chapter_id}
        return await update_role(member_id=member_id, role=role, officer=officer)

    return _set


def _role_keys(cursor, member_id: str) -> list[str]:
    cursor.execute(
        "SELECT role_key FROM member_roles WHERE member_id = %s ORDER BY role_key",
        (member_id,),
    )
    return [r["role_key"] for r in cursor.fetchall()]


async def test_promotion_grants_the_member_roles_officer_row(
    set_role, cursor, member_factory, sb_client, chapter_id
):
    target = member_factory()

    result = await set_role(target, "officer")

    assert result["role"] == "officer"
    assert _role_keys(cursor, target) == ["officer"]
    granted = get_member_permissions(
        {"id": target, "chapter_id": chapter_id, "role": "officer"}, sb=sb_client
    )
    assert set(OFFICER_ONLY_KEYS) <= granted


async def test_demotion_revokes_the_officer_permissions(
    set_role, cursor, member_factory, sb_client, chapter_id
):
    """The #28 bug: demotion left the member_roles grant, so nothing was revoked.

    The grant is seeded the way 0147 §4 seeded it — a backfilled officer, not one
    promoted through this endpoint — so the test pins the revoke, not the promote.
    """
    target = member_factory(role="officer")
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'officer')",
        (chapter_id, target),
    )

    result = await set_role(target, "member")

    assert result["role"] == "member"
    assert _role_keys(cursor, target) == []
    granted = get_member_permissions(
        {"id": target, "chapter_id": chapter_id, "role": "member"}, sb=sb_client
    )
    assert not (set(OFFICER_ONLY_KEYS) & granted)


async def test_demotion_leaves_separately_granted_roles_alone(
    set_role, cursor, member_factory, chapter_id
):
    """Stackable roles come from rbac_assign_role; this endpoint must not strip them."""
    target = member_factory(role="officer")
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'officer')",
        (chapter_id, target),
    )
    cursor.execute(
        "SELECT rbac_assign_role(%s, %s, 'treasurer', %s)", (chapter_id, target, target)
    )

    await set_role(target, "member")

    assert _role_keys(cursor, target) == ["treasurer"]


async def test_promotion_is_idempotent(set_role, cursor, member_factory):
    target = member_factory()

    await set_role(target, "officer")
    await set_role(target, "officer")

    assert _role_keys(cursor, target) == ["officer"]


async def test_role_change_is_audited(set_role, cursor, member_factory, chapter_id):
    target = member_factory()
    await set_role(target, "officer")
    await set_role(target, "member")

    cursor.execute(
        """
        SELECT action FROM audit_logs
        WHERE chapter_id = %s AND target_table = 'members' AND target_id = %s
        ORDER BY created_at
        """,
        (chapter_id, target),
    )
    assert [r["action"] for r in cursor.fetchall()] == ["ASSIGN_ROLE", "REVOKE_ROLE"]


# ── error surface ────────────────────────────────────────────────────────────


async def test_catalog_role_the_legacy_column_cannot_hold_is_a_400(
    set_role, member_factory
):
    """A real catalog role, but not one members.role accepts — a 400, no driver text."""
    target = member_factory()

    with pytest.raises(HTTPException) as exc:
        await set_role(target, "treasurer")

    assert exc.value.status_code == 400
    assert "treasurer" in exc.value.detail
    assert "psycopg2" not in exc.value.detail


async def test_unknown_role_is_a_400(set_role, member_factory):
    with pytest.raises(HTTPException) as exc:
        await set_role(member_factory(), "grand_poobah")
    assert exc.value.status_code == 400


async def test_member_outside_the_chapter_is_a_404(set_role, cursor, member_factory):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other', 'o', 's') RETURNING id"
    )
    outsider = member_factory(chapter=str(cursor.fetchone()["id"]))

    with pytest.raises(HTTPException) as exc:
        await set_role(outsider, "officer")

    assert exc.value.status_code == 404
