"""rc_update_recruit_stage (migration 0151) — audit, tenant guard, idempotency.

Superuser connection (bypasses RLS): these are RPC/trigger tests, and every
assertion is scoped to a freshly-inserted chapter.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from tests.recruitment.conftest import audit_rows, update_recruit_stage


# ── the audit write the bare UPDATE never made ────────────────────────────────

def test_stage_change_updates_row_and_writes_audit_log(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")

    result = update_recruit_stage(cursor, chapter, recruit, "bid_extended", officer)

    assert result["old_stage"] == "lead"
    assert result["new_stage"] == "bid_extended"
    assert result["stage"] == "bid_extended"
    assert str(result["id"]) == recruit

    cursor.execute("SELECT stage FROM recruits WHERE id = %s", (recruit,))
    assert cursor.fetchone()["stage"] == "bid_extended"

    rows = audit_rows(cursor, chapter, recruit)
    assert len(rows) == 1
    assert rows[0]["action"] == "UPDATE_RECRUIT_STAGE"
    assert str(rows[0]["actor_id"]) == officer
    assert rows[0]["target_table"] == "recruits"
    assert rows[0]["metadata"]["old_stage"] == "lead"
    assert rows[0]["metadata"]["new_stage"] == "bid_extended"


def test_every_stage_change_appends_its_own_audit_row(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")

    update_recruit_stage(cursor, chapter, recruit, "contacted", officer)
    update_recruit_stage(cursor, chapter, recruit, "attended_event", officer)

    rows = audit_rows(cursor, chapter, recruit)
    assert [(r["metadata"]["old_stage"], r["metadata"]["new_stage"]) for r in rows] == [
        ("lead", "contacted"),
        ("contacted", "attended_event"),
    ]


# ── tenant guard ──────────────────────────────────────────────────────────────

def test_foreign_chapter_cannot_move_a_recruit(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter_a = chapter_factory()
    chapter_b = chapter_factory()
    recruit_a = recruit_factory(chapter_a, stage="lead")
    officer_b = chapter_member_factory(chapter_b)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        update_recruit_stage(cursor, chapter_b, recruit_a, "bid_extended", officer_b)
    assert "recruit" in str(exc.value) and "not found in chapter" in str(exc.value)

    cursor.execute("SELECT stage FROM recruits WHERE id = %s", (recruit_a,))
    assert cursor.fetchone()["stage"] == "lead"


def test_unknown_recruit_is_not_found(
    cursor, chapter_factory, chapter_member_factory
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        update_recruit_stage(cursor, chapter, str(uuid.uuid4()), "contacted", officer)
    assert "not found in chapter" in str(exc.value)


def test_actor_from_another_chapter_is_rejected(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter_a = chapter_factory()
    chapter_b = chapter_factory()
    recruit_a = recruit_factory(chapter_a)
    officer_b = chapter_member_factory(chapter_b)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        update_recruit_stage(cursor, chapter_a, recruit_a, "contacted", officer_b)
    assert "not an active member" in str(exc.value)


# ── stage validation ──────────────────────────────────────────────────────────

def test_invalid_stage_is_rejected_before_the_update(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        update_recruit_stage(cursor, chapter, recruit, "initiated", officer)
    assert "invalid recruit stage" in str(exc.value)

    cursor.execute("SELECT stage FROM recruits WHERE id = %s", (recruit,))
    assert cursor.fetchone()["stage"] == "lead"
    assert audit_rows(cursor, chapter, recruit) == []


@pytest.mark.parametrize(
    "stage",
    ["lead", "contacted", "attended_event", "bid_extended", "bid_accepted", "dropped"],
)
def test_every_catalog_stage_is_accepted(
    cursor, chapter_factory, chapter_member_factory, recruit_factory, stage
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")

    result = update_recruit_stage(cursor, chapter, recruit, stage, officer)
    assert result["stage"] == stage


# ── idempotency ───────────────────────────────────────────────────────────────

def test_idempotent_replay_returns_same_result_without_duplicate_audit(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")
    key = f"rc-{uuid.uuid4()}"

    first = update_recruit_stage(cursor, chapter, recruit, "contacted", officer, key=key)
    second = update_recruit_stage(cursor, chapter, recruit, "contacted", officer, key=key)

    assert second == first
    assert len(audit_rows(cursor, chapter, recruit)) == 1

    cursor.execute(
        "SELECT count(*) AS n FROM idempotency_keys WHERE chapter_id = %s AND key = %s",
        (chapter, key),
    )
    assert cursor.fetchone()["n"] == 1


def test_replay_does_not_re_apply_a_superseded_stage(
    cursor, chapter_factory, chapter_member_factory, recruit_factory
):
    """A replayed key must not roll the recruit back to the stage it recorded."""
    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)
    recruit = recruit_factory(chapter, stage="lead")
    key = f"rc-{uuid.uuid4()}"

    update_recruit_stage(cursor, chapter, recruit, "contacted", officer, key=key)
    update_recruit_stage(cursor, chapter, recruit, "bid_extended", officer)
    update_recruit_stage(cursor, chapter, recruit, "contacted", officer, key=key)

    cursor.execute("SELECT stage FROM recruits WHERE id = %s", (recruit,))
    assert cursor.fetchone()["stage"] == "bid_extended"


# ── create path: the phone CHECK from 0149 ────────────────────────────────────

def test_service_create_recruit_stores_e164(sb_client, chapter_factory, chapter_member_factory):
    """The service insert must satisfy recruits_phone_e164 (migration 0149)."""
    from api.recruitment.services.pipeline import create_recruit

    chapter = chapter_factory()
    officer = chapter_member_factory(chapter)

    row = create_recruit(
        sb_client,
        chapter_id=chapter,
        name="Raw Phone PNM",
        email=None,
        phone="(555) 123-4567",
        notes=None,
        actor_id=officer,
    )
    assert row["phone"] == "+15551234567"
