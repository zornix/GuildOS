"""Event types — default seeding, case-insensitive uniqueness, get-or-create."""

from __future__ import annotations

import pytest

from api.events.services import events as svc

DEFAULTS = {"Chapter Meeting", "Philanthropy", "Brotherhood", "Social", "Recruitment"}


def test_defaults_seeded_on_first_list(sb_client, chapter_id):
    types = svc.list_event_types(sb_client, chapter_id=chapter_id)
    assert {t["name"] for t in types} == DEFAULTS

    # Idempotent: listing again does not duplicate the seed.
    again = svc.list_event_types(sb_client, chapter_id=chapter_id)
    assert len(again) == len(DEFAULTS)


def test_case_insensitive_unique_per_chapter(cursor, chapter_id):
    cursor.execute(
        "INSERT INTO event_types (chapter_id, name) VALUES (%s, 'Formal')",
        (chapter_id,),
    )
    with pytest.raises(Exception, match="duplicate key|uq_event_types"):
        cursor.execute(
            "INSERT INTO event_types (chapter_id, name) VALUES (%s, 'fORMAL')",
            (chapter_id,),
        )


def test_same_name_allowed_in_other_chapter(cursor, chapter_id):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('ev-other', 'o', 's') RETURNING id"
    )
    other = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO event_types (chapter_id, name) VALUES (%s, 'Retreat')", (chapter_id,)
    )
    cursor.execute(
        "INSERT INTO event_types (chapter_id, name) VALUES (%s, 'retreat')", (other,)
    )  # no raise


def test_resolve_matches_existing_case_insensitively(sb_client, chapter_id):
    types = svc.list_event_types(sb_client, chapter_id=chapter_id)
    social = next(t for t in types if t["name"] == "Social")

    resolved = svc.resolve_event_type_id(sb_client, chapter_id=chapter_id, name="sOcIaL")
    assert resolved == social["id"]
    # No new row appeared.
    assert len(svc.list_event_types(sb_client, chapter_id=chapter_id)) == len(types)


def test_resolve_creates_new_type(sb_client, chapter_id, member_factory):
    creator = member_factory(role="officer")
    new_id = svc.resolve_event_type_id(
        sb_client, chapter_id=chapter_id, name="Alumni Mixer", actor_id=creator
    )
    types = svc.list_event_types(sb_client, chapter_id=chapter_id)
    created = next(t for t in types if t["id"] == new_id)
    assert created["name"] == "Alumni Mixer"


def test_create_event_with_new_and_existing_type(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")

    ev1 = create_event(officer, event_type_name="philanthropy")
    types = svc.list_event_types(sb_client, chapter_id=chapter_id)
    phil = next(t for t in types if t["name"] == "Philanthropy")
    assert ev1["event_type_id"] == phil["id"]

    ev2 = create_event(officer, event_type_name="Senior Send-off")
    assert ev2["event_type_id"] is not None
    names = {t["name"] for t in svc.list_event_types(sb_client, chapter_id=chapter_id)}
    assert "Senior Send-off" in names
