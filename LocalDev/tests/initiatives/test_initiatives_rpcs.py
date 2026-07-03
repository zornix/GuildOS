"""Initiatives RPC-level tests (docs/imp-ev-ph3.md §5.1 items 1-5).

Service-layer functions (api.initiatives.services.initiatives) do not enforce
chapter-level permission checks themselves (only the FastAPI route layer does,
via require_permission) -- these tests call the service layer directly and
exercise membership-based (is_assigned_chair) and RPC-level guards only.
"""

from __future__ import annotations

import uuid

import pytest

from api.initiatives.services import initiatives as svc


def _audit_actions(cursor, initiative_id):
    cursor.execute(
        "SELECT action FROM audit_logs WHERE target_table = 'initiatives' AND target_id = %s",
        (initiative_id,),
    )
    return [r["action"] for r in cursor.fetchall()]


# ── 1. create writes initiative + chairs + audit ─────────────────────────────


def test_create_writes_initiative_chairs_and_audit(
    sb_client, cursor, chapter_id, user_factory, member_factory
):
    actor = user_factory()
    co_chair = member_factory()

    result = svc.create_initiative(
        sb_client,
        actor=actor,
        title="Blood Drive",
        date="2026-07-15",
        time="10:00",
        chair_member_ids=[co_chair],
    )

    assert result["title"] == "Blood Drive"
    assert set(result["chair_member_ids"]) == {actor["id"], co_chair}

    cursor.execute(
        "SELECT member_id, is_creator FROM initiative_chairs WHERE initiative_id = %s",
        (result["id"],),
    )
    rows = {str(r["member_id"]): r["is_creator"] for r in cursor.fetchall()}
    assert rows[actor["id"]] is True  # actor auto-added as creator chair
    assert rows[co_chair] is False

    assert "INITIATIVE_CREATED" in _audit_actions(cursor, result["id"])


def test_create_actor_already_in_chair_list_stays_creator(
    sb_client, chapter_id, cursor, user_factory
):
    actor = user_factory()
    result = svc.create_initiative(
        sb_client,
        actor=actor,
        title="Canned Food Drive",
        date="2026-07-16",
        time="09:00",
        chair_member_ids=[actor["id"]],
    )
    cursor.execute(
        "SELECT is_creator FROM initiative_chairs WHERE initiative_id = %s AND member_id = %s",
        (result["id"], actor["id"]),
    )
    assert cursor.fetchone()["is_creator"] is True


# ── 2. create idempotency ────────────────────────────────────────────────────


def test_create_idempotency_replays_same_initiative(
    sb_client, chapter_id, cursor, user_factory
):
    actor = user_factory()
    key = f"k-{uuid.uuid4()}"

    first = svc.create_initiative(
        sb_client, actor=actor, title="Toy Drive", date="2026-07-20", time="12:00",
        idempotency_key=key,
    )
    second = svc.create_initiative(
        sb_client, actor=actor, title="Toy Drive", date="2026-07-20", time="12:00",
        idempotency_key=key,
    )
    assert first["id"] == second["id"]

    cursor.execute("SELECT count(*) AS n FROM initiatives WHERE id = %s", (first["id"],))
    assert cursor.fetchone()["n"] == 1


# ── 3. create tenant guard ───────────────────────────────────────────────────


def test_create_rejects_chair_from_other_chapter(sb_client, chapter_id, cursor, user_factory):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('in-other', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO members (chapter_id, name, email, role, status) "
        "VALUES (%s, 'Foreign Member', %s, 'member', 'active') RETURNING id",
        (other_chapter, f"{uuid.uuid4()}@test.local"),
    )
    foreign_member = str(cursor.fetchone()["id"])

    actor = user_factory()
    with pytest.raises(Exception, match="member_not_in_chapter"):
        svc.create_initiative(
            sb_client,
            actor=actor,
            title="Cross-Chapter Mixer",
            date="2026-07-21",
            time="18:00",
            chair_member_ids=[foreign_member],
        )


# ── 4. update ─────────────────────────────────────────────────────────────────


def test_update_by_non_chair_is_not_permitted(sb_client, chapter_id, user_factory, create_initiative):
    actor = user_factory()
    ini = create_initiative(actor)
    outsider = user_factory()

    with pytest.raises(svc.NotPermitted):
        svc.update_initiative(
            sb_client, actor=outsider, initiative_id=ini["id"], updates={"title": "Hijacked"}
        )


def test_update_by_chair_changes_fields_and_bumps_updated_at_and_audits(
    sb_client, cursor, chapter_id, user_factory, create_initiative
):
    actor = user_factory()
    ini = create_initiative(actor, title="Original Title")

    cursor.execute("SELECT updated_at FROM initiatives WHERE id = %s", (ini["id"],))
    before = cursor.fetchone()["updated_at"]

    updated = svc.update_initiative(
        sb_client, actor=actor, initiative_id=ini["id"], updates={"title": "Renamed"}
    )
    assert updated["title"] == "Renamed"

    cursor.execute("SELECT updated_at FROM initiatives WHERE id = %s", (ini["id"],))
    after = cursor.fetchone()["updated_at"]
    assert after > before

    assert "INITIATIVE_UPDATED" in _audit_actions(cursor, ini["id"])


# ── 5. add/remove chair ──────────────────────────────────────────────────────


def test_add_chair_writes_audit_row(sb_client, cursor, chapter_id, user_factory, member_factory, create_initiative):
    actor = user_factory()
    ini = create_initiative(actor)
    new_chair = member_factory()

    svc.add_chair(sb_client, actor=actor, initiative_id=ini["id"], member_id=new_chair)

    cursor.execute(
        "SELECT 1 FROM initiative_chairs WHERE initiative_id = %s AND member_id = %s",
        (ini["id"], new_chair),
    )
    assert cursor.fetchone() is not None
    assert "INITIATIVE_CHAIR_ADDED" in _audit_actions(cursor, ini["id"])


def test_add_chair_duplicate_is_a_no_op(sb_client, cursor, chapter_id, user_factory, member_factory, create_initiative):
    actor = user_factory()
    ini = create_initiative(actor)
    new_chair = member_factory()

    svc.add_chair(sb_client, actor=actor, initiative_id=ini["id"], member_id=new_chair)
    svc.add_chair(sb_client, actor=actor, initiative_id=ini["id"], member_id=new_chair)

    cursor.execute(
        "SELECT count(*) AS n FROM initiative_chairs WHERE initiative_id = %s AND member_id = %s",
        (ini["id"], new_chair),
    )
    assert cursor.fetchone()["n"] == 1


def test_remove_chair_writes_audit_row(sb_client, cursor, chapter_id, user_factory, member_factory, create_initiative):
    actor = user_factory()
    co_chair = member_factory()
    ini = create_initiative(actor, chair_member_ids=[co_chair])

    svc.remove_chair(sb_client, actor=actor, initiative_id=ini["id"], member_id=co_chair)

    cursor.execute(
        "SELECT 1 FROM initiative_chairs WHERE initiative_id = %s AND member_id = %s",
        (ini["id"], co_chair),
    )
    assert cursor.fetchone() is None
    assert "INITIATIVE_CHAIR_REMOVED" in _audit_actions(cursor, ini["id"])


def test_remove_last_chair_raises_chair_rule_violation(sb_client, chapter_id, user_factory, create_initiative):
    actor = user_factory()
    ini = create_initiative(actor)  # actor is the sole chair

    with pytest.raises(svc.ChairRuleViolation):
        svc.remove_chair(sb_client, actor=actor, initiative_id=ini["id"], member_id=actor["id"])


def test_manage_chairs_by_non_chair_is_not_permitted(
    sb_client, chapter_id, user_factory, member_factory, create_initiative
):
    actor = user_factory()
    ini = create_initiative(actor)
    outsider = user_factory()
    target = member_factory()

    with pytest.raises(svc.NotPermitted):
        svc.add_chair(sb_client, actor=outsider, initiative_id=ini["id"], member_id=target)

    with pytest.raises(svc.NotPermitted):
        svc.remove_chair(sb_client, actor=outsider, initiative_id=ini["id"], member_id=actor["id"])
