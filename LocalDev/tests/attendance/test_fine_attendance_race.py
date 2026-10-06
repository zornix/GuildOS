"""A stale Python absence list must not override current attendance."""
import json

import pytest

from tests.attendance.conftest import review_excuse, set_attendance


@pytest.mark.parametrize("handled", ["present", "excused", "approved"])
def test_stale_absence_list_skips_handled_member(
    cursor, chapter_id, event_factory, member_factory, excuse_factory, handled
):
    event = event_factory(chapter_id, required=True)
    actor, member = member_factory(role="officer"), member_factory()
    stale_absences = json.dumps([member])
    if handled == "approved":
        excuse = excuse_factory(chapter_id, event, member)
        review_excuse(cursor, chapter_id, excuse, "approved", actor)
    else:
        set_attendance(cursor, chapter_id, event, member, handled, actor, reason="sick")
    cursor.execute(
        "SELECT tr_issue_event_fines(%s,%s,%s::jsonb,2500,'Missed',%s) AS r",
        (chapter_id, event, stale_absences, actor),
    )
    result = cursor.fetchone()["r"]
    assert result["issued"] == []
    assert result["skipped_member_ids"] == [member]
    cursor.execute(
        "SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s AND source_event_id=%s",
        (chapter_id, event),
    )
    assert cursor.fetchone()["n"] == 0
