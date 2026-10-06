"""GET /api/events/upcoming-details — one bulk read replaces 3 requests per event (F-044)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.events.core.timing import DEFAULT_TZ

URL = "/api/events/upcoming-details"


def _day(offset: int) -> str:
    # The test chapter has no timezone set, so it runs on the default.
    return (datetime.now(ZoneInfo(DEFAULT_TZ)).date() + timedelta(days=offset)).isoformat()


def _assign_security(client, event_id, member_id):
    resp = client.post(f"/api/events/{event_id}/security", json={"member_id": member_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["task_id"]


def _open_link(cursor, event_id):
    cursor.execute(
        "INSERT INTO checkin_links (event_id, short_code, expires_at) "
        "VALUES (%s, %s, now() + interval '1 hour')",
        (event_id, uuid.uuid4().hex[:6]),
    )


def _by_task(rows):
    return sorted(rows, key=lambda r: r["task_id"])


def test_returns_upcoming_events_matching_single_event_routes(
    as_member, create_event, user_factory, cursor, monkeypatch, sb_client
):
    import api.attendance.services.checkin_links as links_svc

    monkeypatch.setattr(links_svc, "get_db", lambda: sb_client)
    officer = user_factory(role="officer")
    plain = user_factory()
    soon = create_event(officer, title="Soon", date=_day(2))
    later = create_event(officer, title="Later", date=_day(9))
    past = create_event(officer, title="Past", date=_day(-3))
    hidden = create_event(officer, title="Officers only", date=_day(4), audience="officers")
    cursor.execute(
        "INSERT INTO events (chapter_id, title, date, time, location, cancelled) "
        "VALUES (%s, 'Cancelled', %s, '19:00', 'Hall', true) RETURNING id",
        (officer["chapter_id"], _day(3)),
    )
    cancelled_id = str(cursor.fetchone()["id"])

    officer_client = as_member(officer["id"])
    task_id = _assign_security(officer_client, soon["id"], plain["id"])
    holder_client = as_member(plain["id"])
    swap = holder_client.post(
        f"/api/events/{soon['id']}/security/{task_id}/swap-request",
        json={"target_member_id": officer["id"]},
    )
    assert swap.status_code == 200, swap.text
    _open_link(cursor, soon["id"])

    client = as_member(plain["id"])
    resp = client.get(URL)
    assert resp.status_code == 200, resp.text
    rows = resp.json()["events"]
    ids = {r["event_id"] for r in rows}
    assert ids == {soon["id"], later["id"]}
    assert past["id"] not in ids and hidden["id"] not in ids and cancelled_id not in ids

    for row in rows:
        eid = row["event_id"]
        assert row["detail"] == client.get(f"/api/events/{eid}").json()
        assert _by_task(row["security"]) == _by_task(client.get(f"/api/events/{eid}/security").json())
        assert row["checkin_link"] == client.get(f"/api/events/{eid}/checkin-link").json()

    by_id = {r["event_id"]: r for r in rows}
    assert by_id[soon["id"]]["security"][0]["pending_swap"]["status"] == "pending"
    link = by_id[soon["id"]]["checkin_link"]
    assert link["active"] is True and "short_code" not in link
    assert by_id[later["id"]]["checkin_link"] == {}

    # An officer sees the officers-only event and the full link object.
    officer_client = as_member(officer["id"])  # the override is app-wide: re-point it
    officer_rows = {r["event_id"]: r for r in officer_client.get(URL).json()["events"]}
    assert set(officer_rows) == {soon["id"], later["id"], hidden["id"]}
    assert officer_rows[soon["id"]]["checkin_link"] == officer_client.get(
        f"/api/events/{soon['id']}/checkin-link"
    ).json()
    assert "short_code" in officer_rows[soon["id"]]["checkin_link"]


def test_route_is_not_swallowed_by_event_id(as_member, user_factory):
    resp = as_member(user_factory()["id"]).get(URL)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"events": []}


class _Counting:
    def __init__(self, sb):
        self._sb, self.calls = sb, 0

    def table(self, name):
        self.calls += 1
        return self._sb.table(name)

    def rpc(self, *args, **kwargs):
        self.calls += 1
        return self._sb.rpc(*args, **kwargs)


def test_query_count_is_constant(
    sb_client, create_event, user_factory, as_member, cursor, monkeypatch
):
    import api.attendance.services.checkin_links as links_svc
    from api.events.services import events as svc

    monkeypatch.setattr(links_svc, "get_db", lambda: sb_client)
    officer = user_factory(role="officer")
    client = as_member(officer["id"])

    def _add_events(n):
        for i in range(n):
            ev = create_event(officer, title=f"E{i}", date=_day(i + 1))
            _assign_security(client, ev["id"], user_factory()["id"])
            _open_link(cursor, ev["id"])

    def _count():
        counting = _Counting(sb_client)
        result = svc.list_upcoming_details(counting, user=dict(officer))
        return counting.calls, len(result["events"])

    _add_events(2)
    two_calls, two = _count()
    _add_events(4)
    six_calls, six = _count()
    assert (two, six) == (2, 6)
    assert six_calls == two_calls
