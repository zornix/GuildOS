"""End-to-end check-in over HTTP against the test DB.

Covers signed-in check-in, removal of public phone check-in, redirects,
code-read permissions, auditing, session windows, and chapter isolation.
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


# ── signed-in check-in ────────────────────────────────────────────────────────────

def test_checkin_stamps_the_chapter_on_the_attendance_row(
    as_member, cursor, chapter_id, event_id, member_with_phone, checkin_link_factory
):
    _, code = checkin_link_factory(event_id)
    as_member(member_with_phone).post(f"/api/attendance/checkin/{code}")

    row = _attendance_row(cursor, event_id, member_with_phone)
    assert str(row["chapter_id"]) == chapter_id


def test_member_of_another_chapter_cannot_check_in(
    as_member, cursor, chapter_factory, member_factory, event_id, checkin_link_factory
):
    """A foreign chapter member cannot write attendance or an audit row."""
    other_chapter = chapter_factory()
    outsider = member_factory(chapter=other_chapter)
    _set_phone(cursor, outsider, "+15552220002")
    _, code = checkin_link_factory(event_id)

    resp = as_member(outsider).post(f"/api/attendance/checkin/{code}")
    assert resp.status_code == 403
    assert _attendance_row(cursor, event_id, outsider) is None
    cursor.execute("SELECT id FROM audit_logs WHERE chapter_id = %s AND actor_id = %s", (other_chapter, outsider))
    assert cursor.fetchall() == []
    cursor.execute("SELECT chapter_id FROM events WHERE id = %s", (event_id,))
    event_chapter = str(cursor.fetchone()["chapter_id"])
    cursor.execute("SELECT id FROM audit_logs WHERE chapter_id = %s AND actor_id = %s", (event_chapter, outsider))
    assert cursor.fetchall() == []


def test_expired_link_is_gone(as_member, event_id, member_with_phone, checkin_link_factory):
    _, code = checkin_link_factory(event_id, minutes=-5)
    resp = as_member(member_with_phone).post(f"/api/attendance/checkin/{code}")
    assert resp.status_code == 410


# ── the closes_at gate ────────────────────────────────────────────────────────

def test_closed_session_blocks_signed_in_checkin(
    as_member, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    """closes_at used to be written and read by nothing."""
    link_id, code = checkin_link_factory(event_id)
    session_factory(chapter_id, event_id, checkin_link_id=link_id, closes_in_minutes=-5)

    resp = as_member(member_with_phone).post(f"/api/attendance/checkin/{code}")
    assert resp.status_code == 410


def test_open_session_still_allows_checkin(
    as_member, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    link_id, code = checkin_link_factory(event_id)
    session_factory(chapter_id, event_id, checkin_link_id=link_id, closes_in_minutes=30)

    resp = as_member(member_with_phone).post(f"/api/attendance/checkin/{code}")
    assert resp.status_code == 200, resp.text


def test_checkin_rpc_rejection_is_a_fixed_404_not_a_500(
    as_member, cursor, event_id, member_with_phone, checkin_link_factory
):
    """A member no longer active after sign-in gets the RPC's 'not found', mapped."""
    _, code = checkin_link_factory(event_id)
    client = as_member(member_with_phone)
    cursor.execute("UPDATE members SET status = 'invited' WHERE id = %s", (member_with_phone,))

    resp = client.post(f"/api/attendance/checkin/{code}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Member not found"


def test_a_closed_session_bound_to_another_link_does_not_block(
    as_member, chapter_id, event_id, member_with_phone, checkin_link_factory, session_factory
):
    """An officer reopening check-in must not be killed by the old window."""
    old_link_id, _ = checkin_link_factory(event_id, active=False)
    session_factory(chapter_id, event_id, checkin_link_id=old_link_id, closes_in_minutes=-30)
    _, fresh_code = checkin_link_factory(event_id)

    resp = as_member(member_with_phone).post(
        f"/api/attendance/checkin/{fresh_code}"
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

    assert validate_checkin_link(code) is not None, "the fresh link is dead on arrival"

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
    as_member, member_factory, event_id, member_with_phone, checkin_link_factory
):
    officer = member_factory(role="officer")
    _, code = checkin_link_factory(event_id)
    as_member(officer).delete(f"/api/events/{event_id}/checkin-link")

    resp = as_member(member_with_phone).post(f"/api/attendance/checkin/{code}")
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


def test_phone_checkin_route_is_gone(anon_client, cursor, event_id, member_with_phone, checkin_link_factory):
    _, code = checkin_link_factory(event_id)
    response = anon_client.post(f"/api/attendance/checkin/{code}/phone", json={"phone": "5551110001"})
    assert response.status_code in (404, 405)
    assert _attendance_row(cursor, event_id, member_with_phone) is None


def test_checkin_page_redirects_into_the_app(anon_client):
    from api.config import settings
    response = anon_client.get("/c/ABC123", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == settings.FRONTEND_URL.rstrip("/") + "/?checkin=ABC123"


@pytest.mark.parametrize("code", ["<script>", "A" * 40])
def test_checkin_page_rejects_a_malformed_code(anon_client, code):
    assert anon_client.get(f"/c/{code}", follow_redirects=False).status_code == 404


def test_member_sees_that_a_code_is_live_but_not_the_code(as_member, member_factory, event_id):
    officer = member_factory(role="officer")
    link = as_member(officer).post(f"/api/events/{event_id}/checkin-link").json()
    response = as_member(member_factory()).get(f"/api/events/{event_id}/checkin-link")
    assert response.status_code == 200
    assert response.json() == {"event_id": event_id, "active": True, "expires_at": link["expires_at"]}


def test_manager_still_gets_the_code(as_member, member_factory, event_id):
    client = as_member(member_factory(role="officer"))
    link = client.post(f"/api/events/{event_id}/checkin-link").json()
    assert client.get(f"/api/events/{event_id}/checkin-link").json()["short_code"] == link["short_code"]


def test_no_live_code_returns_empty_object(as_member, member_factory, event_id):
    assert as_member(member_factory()).get(f"/api/events/{event_id}/checkin-link").json() == {}


def _self_checkin_audits(cursor, chapter_id, member_id):
    cursor.execute("""SELECT * FROM audit_logs WHERE chapter_id = %s AND actor_id = %s
                      AND action = 'ATTENDANCE_OVERRIDDEN' AND target_table = 'attendance'
                      AND metadata->>'method' = 'link'""", (chapter_id, member_id))
    return cursor.fetchall()


def test_link_checkin_writes_an_audit_row(as_member, cursor, chapter_id, member_factory, event_id, checkin_link_factory):
    member = member_factory()
    _, code = checkin_link_factory(event_id)
    response = as_member(member).post(f"/api/attendance/checkin/{code}")
    assert response.status_code == 200
    audits = _self_checkin_audits(cursor, chapter_id, member)
    assert len(audits) == 1
    assert str(audits[0]["target_id"]) == str(_attendance_row(cursor, event_id, member)["id"])
    assert audits[0]["metadata"]["self_checkin"] is True


def test_second_checkin_is_409_and_adds_no_audit_row(as_member, cursor, chapter_id, member_factory, event_id, checkin_link_factory):
    member = member_factory()
    _, code = checkin_link_factory(event_id)
    client = as_member(member)
    first = client.post(f"/api/attendance/checkin/{code}")
    assert first.status_code == 200
    checked_in_at = _attendance_row(cursor, event_id, member)["checked_in_at"]
    assert client.post(f"/api/attendance/checkin/{code}").status_code == 409
    assert _attendance_row(cursor, event_id, member)["checked_in_at"] == checked_in_at
    assert len(_self_checkin_audits(cursor, chapter_id, member)) == 1
