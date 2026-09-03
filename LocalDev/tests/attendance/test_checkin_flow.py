"""End-to-end check-in over HTTP against the test DB.

Covers the shipped phone check-in bug (page sent 10 digits, schema demanded 9,
so every attempt 422'd), the chapter stamp on the attendance row, the closes_at
gate, and the cross-chapter link kill.
"""

from __future__ import annotations

import pytest


def _set_phone(cursor, member_id: str, phone: str | None) -> None:
    cursor.execute("UPDATE members SET phone = %s WHERE id = %s", (phone, member_id))


def _attendance_row(cursor, event_id: str, member_id: str) -> dict | None:
    cursor.execute(
        "SELECT * FROM attendance WHERE event_id = %s AND member_id = %s",
        (event_id, member_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def _link_is_active(cursor, link_id: str) -> bool:
    cursor.execute("SELECT active FROM checkin_links WHERE id = %s", (link_id,))
    return cursor.fetchone()["active"]


@pytest.fixture
def event_id(event_factory, chapter_id):
    return event_factory(chapter_id)


@pytest.fixture
def member_with_phone(member_factory, cursor):
    member = member_factory()
    _set_phone(cursor, member, "+15551110001")
    return member


# ── phone check-in ────────────────────────────────────────────────────────────

def test_ten_digit_phone_checks_in(
    anon_client, cursor, chapter_id, event_id, member_with_phone, checkin_link_factory
):
    """The bug this whole package exists for: 10 digits in, check-in out."""
    _, code = checkin_link_factory(event_id)

    resp = anon_client.post(
        f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "checked_in"

    row = _attendance_row(cursor, event_id, member_with_phone)
    assert row is not None
    assert row["checked_in"] is True
    assert row["method"] == "link"


def test_checkin_stamps_the_chapter_on_the_attendance_row(
    anon_client, cursor, chapter_id, event_id, member_with_phone, checkin_link_factory
):
    _, code = checkin_link_factory(event_id)
    anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})

    row = _attendance_row(cursor, event_id, member_with_phone)
    assert str(row["chapter_id"]) == chapter_id


@pytest.mark.parametrize(
    "entered",
    ["5551110001", "555-111-0001", "(555) 111-0001", "+15551110001", "15551110001"],
)
def test_every_spelling_of_the_same_number_matches(
    anon_client, cursor, event_factory, chapter_id, member_with_phone,
    checkin_link_factory, entered,
):
    """E.164 normalization means the member can type it however they like."""
    event = event_factory(chapter_id)
    _, code = checkin_link_factory(event)

    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": entered})
    assert resp.status_code == 200, resp.text


def test_nine_digit_phone_is_rejected_by_the_schema(
    anon_client, event_id, member_with_phone, checkin_link_factory
):
    _, code = checkin_link_factory(event_id)
    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "555111000"})
    assert resp.status_code == 422


def test_unknown_phone_is_not_found(anon_client, event_id, member_with_phone, checkin_link_factory):
    _, code = checkin_link_factory(event_id)
    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5559999999"})
    assert resp.status_code == 404


def test_checkin_twice_reports_already_checked_in(
    anon_client, event_id, member_with_phone, checkin_link_factory
):
    _, code = checkin_link_factory(event_id)
    anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert resp.status_code == 409


def test_member_of_another_chapter_cannot_check_in(
    anon_client, cursor, chapter_factory, member_factory, event_id, checkin_link_factory
):
    """Same phone digits, different chapter — the lookup is chapter-scoped."""
    other_chapter = chapter_factory()
    outsider = member_factory(chapter=other_chapter)
    _set_phone(cursor, outsider, "+15552220002")
    _, code = checkin_link_factory(event_id)

    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5552220002"})
    assert resp.status_code == 404


def test_expired_link_is_gone(anon_client, event_id, member_with_phone, checkin_link_factory):
    _, code = checkin_link_factory(event_id, minutes=-5)
    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert resp.status_code == 410


# ── the closes_at gate ────────────────────────────────────────────────────────

def test_closed_session_blocks_phone_checkin(
    anon_client, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    """closes_at used to be written and read by nothing."""
    link_id, code = checkin_link_factory(event_id)
    session_factory(chapter_id, event_id, checkin_link_id=link_id, closes_in_minutes=-5)

    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert resp.status_code == 410


def test_closed_session_blocks_the_page(
    anon_client, chapter_id, event_id, checkin_link_factory, session_factory
):
    link_id, code = checkin_link_factory(event_id)
    session_factory(chapter_id, event_id, checkin_link_id=link_id, closes_in_minutes=-5)

    resp = anon_client.get(f"/c/{code}")
    assert resp.status_code == 410


def test_open_session_still_allows_checkin(
    anon_client, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    link_id, code = checkin_link_factory(event_id)
    session_factory(chapter_id, event_id, checkin_link_id=link_id, closes_in_minutes=30)

    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert resp.status_code == 200, resp.text


def test_a_closed_session_bound_to_another_link_does_not_block(
    anon_client, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    """An officer reopening check-in must not be killed by the old window."""
    old_link_id, _ = checkin_link_factory(event_id, active=False)
    session_factory(chapter_id, event_id, checkin_link_id=old_link_id, closes_in_minutes=-30)
    _, fresh_code = checkin_link_factory(event_id)

    resp = anon_client.post(
        f"/api/attendance/checkin/{fresh_code}/phone", json={"phone": "5551110001"}
    )
    assert resp.status_code == 200, resp.text


async def test_a_fresh_link_survives_a_closed_manual_session(
    as_member, cursor, chapter_id, event_id, member_factory, member_with_phone,
    session_factory,
):
    """#34: a closed manual session used to kill every link generated after it.

    Manual sessions carry no checkin_link_id, so _session_for_link's unbound
    fallback adopted the stale closed window and 410'd the brand-new link on the
    first scan — unfixable from the officer's side, regenerating made another
    dead link. create_checkin_link now binds the event's open sessions instead
    of leaving the governing window to be guessed.
    """
    from api.attendance.services.checkin_links import validate_checkin_link

    officer = member_factory(role="officer")
    stale = session_factory(chapter_id, event_id, mode="manual", closes_in_minutes=-5)

    resp = as_member(officer).post(f"/api/events/{event_id}/checkin-link")
    assert resp.status_code == 200, resp.text
    code = resp.json()["short_code"]

    assert await validate_checkin_link(code) is not None, "the fresh link is dead on arrival"

    cursor.execute("SELECT checkin_link_id FROM attendance_sessions WHERE id = %s", (stale,))
    assert cursor.fetchone()["checkin_link_id"] is None, "a closed session must not be bound"


async def test_a_new_link_adopts_the_open_manual_session(
    as_member, cursor, chapter_id, event_id, member_factory, session_factory
):
    """The other half of the bind: an OPEN window still governs the new link."""
    officer = member_factory(role="officer")
    session = session_factory(chapter_id, event_id, mode="manual", closes_in_minutes=30)

    resp = as_member(officer).post(f"/api/events/{event_id}/checkin-link")
    assert resp.status_code == 200, resp.text

    cursor.execute("SELECT checkin_link_id FROM attendance_sessions WHERE id = %s", (session,))
    link_id = cursor.fetchone()["checkin_link_id"]
    cursor.execute("SELECT short_code FROM checkin_links WHERE id = %s", (link_id,))
    assert cursor.fetchone()["short_code"] == resp.json()["short_code"]


# ── killing a link is chapter-scoped ──────────────────────────────────────────

def test_officer_kills_their_own_chapters_link(
    as_member, cursor, member_factory, event_id, checkin_link_factory
):
    officer = member_factory(role="officer")
    link_id, _ = checkin_link_factory(event_id)

    resp = as_member(officer).delete(f"/api/events/{event_id}/checkin-link")

    assert resp.status_code == 200
    assert _link_is_active(cursor, link_id) is False


def test_foreign_officer_cannot_kill_a_link(
    as_member, cursor, chapter_factory, member_factory, event_id, checkin_link_factory
):
    """Cross-tenant kill: the old handler took event_id on trust."""
    other_chapter = chapter_factory()
    outsider = member_factory(role="officer", chapter=other_chapter)
    link_id, _ = checkin_link_factory(event_id)

    resp = as_member(outsider).delete(f"/api/events/{event_id}/checkin-link")

    assert resp.status_code == 404
    assert _link_is_active(cursor, link_id) is True, "the link must survive a foreign kill"


def test_killed_link_stops_checkins(
    anon_client, as_member, member_factory, event_id, member_with_phone, checkin_link_factory
):
    officer = member_factory(role="officer")
    _, code = checkin_link_factory(event_id)
    as_member(officer).delete(f"/api/events/{event_id}/checkin-link")

    resp = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert resp.status_code == 410


# ── listing active links ──────────────────────────────────────────────────────

def test_active_link_listing_is_chapter_scoped(
    as_member, chapter_factory, member_factory, event_factory, chapter_id,
    event_id, checkin_link_factory,
):
    officer = member_factory(role="officer")
    _, mine = checkin_link_factory(event_id)

    other_chapter = chapter_factory()
    foreign_event = event_factory(other_chapter)
    _, theirs = checkin_link_factory(foreign_event)

    rows = as_member(officer).get("/api/checkin-links/active").json()
    codes = {r["short_code"] for r in rows}

    assert mine in codes
    assert theirs not in codes
