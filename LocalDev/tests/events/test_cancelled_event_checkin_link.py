"""Regression for RV-11-4a: a cancelled event refuses new check-in links."""


def test_cancelled_event_refuses_new_link(cursor, chapter_id, user_factory, as_member, sb_client, monkeypatch):
    import api.attendance.services.checkin_links as links
    monkeypatch.setattr(links, "get_db", lambda: sb_client)
    actor = user_factory(role="officer")
    cursor.execute("INSERT INTO events(chapter_id,title,date,time,location) VALUES (%s,'Cancelled link','2026-07-01','19:00','Hall') RETURNING id", (chapter_id,))
    event_id = str(cursor.fetchone()["id"])
    cursor.execute("INSERT INTO attendance(event_id,member_id) VALUES (%s,%s)", (event_id, actor["id"]))
    client = as_member(actor["id"])
    cancelled = client.delete(f"/api/events/{event_id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"]
    response = client.post(f"/api/events/{event_id}/checkin-link")
    assert response.status_code == 409
