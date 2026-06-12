"""rbac_assign_role / rbac_revoke_role — tenant guards, multi-role, audit.

DB-backed (skips without TEST_DATABASE_URL, like the treasury suite).
"""

from __future__ import annotations

import json

import pytest


def _assign(cursor, chapter_id, member_id, role_key, actor_id, key=None):
    cursor.execute(
        "SELECT rbac_assign_role(%s, %s, %s, %s, %s) AS r",
        (chapter_id, member_id, role_key, actor_id, key),
    )
    return cursor.fetchone()["r"]


def test_member_can_hold_multiple_roles(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()

    _assign(cursor, chapter_id, target, "treasurer", actor)
    _assign(cursor, chapter_id, target, "social_chair", actor)

    cursor.execute(
        "SELECT role_key FROM member_roles WHERE member_id = %s ORDER BY role_key",
        (target,),
    )
    assert [r["role_key"] for r in cursor.fetchall()] == ["social_chair", "treasurer"]


def test_assign_is_idempotent_on_duplicate(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()

    first = _assign(cursor, chapter_id, target, "secretary", actor)
    second = _assign(cursor, chapter_id, target, "secretary", actor)
    assert first["id"] == second["id"]


def test_assign_rejects_member_outside_chapter(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    outsider = member_factory(chapter=other_chapter)

    with pytest.raises(Exception, match="is not in chapter"):
        _assign(cursor, chapter_id, outsider, "treasurer", actor)


def test_assign_writes_audit_log(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()

    row = _assign(cursor, chapter_id, target, "risk_chair", actor)

    cursor.execute(
        """
        SELECT metadata FROM audit_logs
        WHERE chapter_id = %s AND action = 'ASSIGN_ROLE' AND target_id = %s
        """,
        (chapter_id, row["id"]),
    )
    meta = cursor.fetchone()["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta["role_key"] == "risk_chair"


def test_revoke_removes_assignment_and_audits(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()
    _assign(cursor, chapter_id, target, "treasurer", actor)

    cursor.execute(
        "SELECT rbac_revoke_role(%s, %s, 'treasurer', %s) AS r",
        (chapter_id, target, actor),
    )
    result = cursor.fetchone()["r"]
    assert result["revoked"] is True

    cursor.execute("SELECT 1 FROM member_roles WHERE member_id = %s AND role_key = 'treasurer'", (target,))
    assert cursor.fetchone() is None

    cursor.execute(
        "SELECT 1 FROM audit_logs WHERE chapter_id = %s AND action = 'REVOKE_ROLE'",
        (chapter_id,),
    )
    assert cursor.fetchone() is not None


def test_revoke_missing_role_reports_not_revoked(cursor, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()

    cursor.execute(
        "SELECT rbac_revoke_role(%s, %s, 'treasurer', %s) AS r",
        (chapter_id, target, actor),
    )
    assert cursor.fetchone()["r"]["revoked"] is False
