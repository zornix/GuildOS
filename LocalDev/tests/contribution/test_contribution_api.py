"""GET /api/contribution/me and /{member_id} (issue #40)."""

from __future__ import annotations

import uuid


def test_me_returns_the_members_own_derived_record(
    as_member, member_factory, create_event, add_organizer, add_supervisor,
    check_in, create_initiative, create_job,
):
    me = member_factory()
    other = member_factory()

    organized = create_event(title="Formal")
    add_organizer(organized, me)
    check_in(organized, me)
    check_in(organized, other)

    supervised = create_event(title="Rush Night")
    add_supervisor(supervised, me)

    create_initiative(me)
    create_job(me, event_id=organized)
    create_job(me, status="open")  # not approved → not counted

    body = as_member(me).get("/api/contribution/me").json()

    assert body["member_id"] == me
    assert [e["title"] for e in body["events_organized"]] == ["Formal"]
    assert body["events_organized"][0]["attendee_count"] == 2
    assert body["events_organized"][0]["event_id"] == organized
    assert body["events_organized"][0]["date"] == "2026-03-01"
    assert [e["title"] for e in body["events_supervised"]] == ["Rush Night"]
    assert body["events_supervised"][0]["attendee_count"] == 0
    assert len(body["initiatives_chaired"]) == 1
    assert body["initiatives_chaired"][0]["date_range"] == {
        "start": "2026-04-01",
        "end": "2026-04-05",
    }
    assert len(body["jobs_done"]) == 1
    assert body["jobs_done"][0]["attached_to"] == "event"
    assert body["events_attended_count"] == 1


def test_uncommitted_jobs_and_other_members_rows_never_count(
    as_member, member_factory, create_event, add_organizer, create_job
):
    me = member_factory()
    other = member_factory()

    add_organizer(create_event(), other)  # someone else's event
    create_job(me, commitment_status="uncommitted")

    body = as_member(me).get("/api/contribution/me").json()

    assert body["events_organized"] == []
    assert body["jobs_done"] == []


def test_member_record_is_officer_gated(as_member, member_factory, assign_role):
    subject = member_factory()
    plain = member_factory()
    officer = member_factory()
    assign_role(officer, "officer")  # holds standing:view_all

    assert as_member(plain).get(f"/api/contribution/{subject}").status_code == 403
    assert as_member(officer).get(f"/api/contribution/{subject}").status_code == 200


def test_non_uuid_member_id_is_rejected_before_the_query(
    as_member, member_factory, assign_role
):
    officer = member_factory()
    assign_role(officer, "officer")

    assert as_member(officer).get("/api/contribution/not-a-uuid").status_code == 422


def test_officer_cannot_read_a_member_of_another_chapter(
    as_member, member_factory, assign_role, cursor
):
    officer = member_factory()
    assign_role(officer, "officer")

    cursor.execute(
        "INSERT INTO chapters (name, organization, school) "
        "VALUES (%s, 'Other Org', 'Other U') RETURNING id",
        (f"contrib-other-{uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])

    try:
        outsider = member_factory(chapter=other_chapter)

        assert as_member(officer).get(f"/api/contribution/{outsider}").status_code == 404
    finally:
        # The autouse cleanup only knows this test's own chapter; its members
        # go with it by ON DELETE CASCADE.
        cursor.execute("DELETE FROM chapters WHERE id = %s", (other_chapter,))
