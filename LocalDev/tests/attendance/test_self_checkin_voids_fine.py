"""Door-code check-in must clear an outstanding event fine."""
import json


def test_self_checkin_voids_open_fine(
    as_member, cursor, chapter_id, event_factory, member_factory, checkin_link_factory
):
    event = event_factory(chapter_id, required=True)
    actor, member = member_factory(role="officer"), member_factory()
    cursor.execute(
        "SELECT tr_issue_event_fines(%s,%s,%s::jsonb,2500,'Missed',%s) AS r",
        (chapter_id, event, json.dumps([member]), actor),
    )
    invoice = cursor.fetchone()["r"]["issued"][0]
    _, code = checkin_link_factory(event)
    response = as_member(member).post(f"/api/attendance/checkin/{code}")
    assert response.status_code == 200, response.text
    cursor.execute("SELECT status FROM unpaid_invoices WHERE chapter_id=%s AND id=%s", (chapter_id, invoice["id"]))
    assert cursor.fetchone()["status"] == "cancelled"
