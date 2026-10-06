"""Cancelling an event resolves outstanding swaps and releases job holders."""
import pytest


@pytest.mark.parametrize("check", ["swap", "claim"])
def test_event_cancel_cleans_pending_work(check, cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role="officer")
    holder = user_factory()
    target = user_factory()
    cursor.execute("INSERT INTO events(chapter_id,title,date,time,location) VALUES (%s,'Cancel cleanup','2026-07-01','19:00','Hall') RETURNING id", (chapter_id,))
    event_id = str(cursor.fetchone()["id"])
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title,kind,status) VALUES (%s,%s,'Security','security','in_progress') RETURNING id", (chapter_id, event_id))
    security_id = str(cursor.fetchone()["id"])
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title,status) VALUES (%s,%s,'Claimed job','in_progress') RETURNING id", (chapter_id, event_id))
    job_id = str(cursor.fetchone()["id"])
    for task_id in (security_id, job_id):
        cursor.execute("INSERT INTO task_commitments(chapter_id,task_id,member_id,status) VALUES (%s,%s,%s,'active')", (chapter_id, task_id, holder["id"]))
    cursor.execute("INSERT INTO security_swap_requests(chapter_id,event_id,task_id,requester_member_id,target_member_id) VALUES (%s,%s,%s,%s,%s) RETURNING id", (chapter_id, event_id, security_id, holder["id"], target["id"]))
    swap_id = str(cursor.fetchone()["id"])
    client = as_member(actor["id"])
    response = client.delete(f"/api/events/{event_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": False, "cancelled": True}
    if check == "swap":
        cursor.execute("SELECT status,resolved_at,resolved_by FROM security_swap_requests WHERE chapter_id=%s AND id=%s", (chapter_id, swap_id))
        swap = cursor.fetchone()
        assert swap["status"] == "cancelled"
        assert swap["resolved_at"] is not None
        assert str(swap["resolved_by"]) == actor["id"]
    else:
        cursor.execute("SELECT status,uncommitted_at FROM task_commitments WHERE chapter_id=%s AND task_id IN (%s,%s)", (chapter_id, security_id, job_id))
        claims = cursor.fetchall()
        assert len(claims) == 2
        assert all(c["status"] == "uncommitted" and c["uncommitted_at"] is not None for c in claims)
        cursor.execute("SELECT task_id,reason FROM task_commitment_log WHERE chapter_id=%s AND event_id=%s AND action='uncommit'", (chapter_id, event_id))
        assert {(str(r["task_id"]), r["reason"]) for r in cursor.fetchall()} == {(security_id, "event_cancelled"), (job_id, "event_cancelled")}
        assert client.delete(f"/api/events/{event_id}").status_code == 200
        cursor.execute("SELECT count(*) AS n FROM task_commitment_log WHERE chapter_id=%s AND event_id=%s AND action='uncommit'", (chapter_id, event_id))
        assert cursor.fetchone()["n"] == 2
