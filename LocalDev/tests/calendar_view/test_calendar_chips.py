"""Screen 1 calendar chips — event decorations + announcement items (B4FEND §5.1/§5.2).

Same harness as test_calendar_view.py (tests/calendar_view/conftest.py); kept in
its own file so the existing aggregation suite stays focused on aggregation.
"""

from __future__ import annotations

RANGE = {"start": "2026-06-01", "end": "2026-08-01"}


def _items(body, kind):
    return [i for i in body["items"] if i["kind"] == kind]


# ── event chip decorations ───────────────────────────────────────────────────


def _seed_jobs(cursor, chapter_id, event_id):
    """2 open standard jobs + 1 security job + 1 approved standard job."""
    for title, status, kind in (
        ("Setup", "open", "standard"),
        ("Cleanup", "open", "standard"),
        ("Door", "in_progress", "security"),
        ("Flyers", "approved", "standard"),
    ):
        cursor.execute(
            "INSERT INTO tasks (chapter_id, title, status, kind, event_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (chapter_id, title, status, kind, event_id),
        )


def test_event_item_carries_job_counts_time_and_completeness(
    harness, user_factory, create_event, cursor, chapter_id, sb_client
):
    """job_count excludes security, open_job_count is the claim lure, and
    completeness is exactly the dict GET /api/events/{id} returns."""
    from api.events.services import events as ev_svc

    officer = user_factory(role="officer")
    ev = create_event(officer, end_date="2026-07-01", end_time="22:00")
    _seed_jobs(cursor, chapter_id, ev["id"])

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    item = next(e for e in _items(body, "event") if e["id"] == ev["id"])

    assert item["job_count"] == 3          # security excluded
    assert item["open_job_count"] == 2     # approved and security excluded
    assert item["time"] == "19:00:00"
    assert item["end_date"] == "2026-07-01"
    assert item["end_time"] == "22:00:00"

    detail = ev_svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert item["completeness"] == detail["completeness"]
    assert detail["open_job_count"] == 2


# ── announcements on the calendar (D15) ──────────────────────────────────────


def _announcement(cursor, chapter_id, **kw):
    cursor.execute(
        """
        INSERT INTO announcements
            (chapter_id, title, body, audience, status, sent_at,
             calendar_date, calendar_time, hidden_from_calendar)
        VALUES (%s, %s, 'Body', %s, %s,
                CASE WHEN %s = 'sent' THEN now() END, %s, %s, %s)
        RETURNING id
        """,
        (
            chapter_id,
            kw.get("title", "Rush kickoff"),
            kw.get("audience", "chapter"),
            kw.get("status", "sent"),
            kw.get("status", "sent"),
            kw.get("calendar_date", "2026-07-05"),
            kw.get("calendar_time", "18:30"),
            kw.get("hidden", False),
        ),
    )
    return str(cursor.fetchone()["id"])


def test_sent_dated_announcement_appears(harness, user_factory, cursor, chapter_id):
    ann = _announcement(cursor, chapter_id)
    body = harness.login(user_factory()).get("/api/calendar", params=RANGE).json()
    item = next(a for a in _items(body, "announcement") if a["announcement_id"] == ann)
    assert item["title"] == "Rush kickoff"
    assert item["date"] == "2026-07-05"
    assert item["time"] == "18:30:00"
    assert item["audience"] == "chapter"


def test_announcements_excluded_from_calendar(harness, user_factory, cursor, chapter_id):
    """Drafts, undated sends, hidden rows, non-chapter audiences and
    out-of-range dates all stay off the chapter calendar."""
    draft = _announcement(cursor, chapter_id, status="draft")
    undated = _announcement(cursor, chapter_id, calendar_date=None, calendar_time=None)
    hidden = _announcement(cursor, chapter_id, hidden=True)
    officers_only = _announcement(cursor, chapter_id, audience="officers")
    out_of_range = _announcement(cursor, chapter_id, calendar_date="2027-01-05")

    officer = user_factory(role="officer")
    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    shown = {a["announcement_id"] for a in _items(body, "announcement")}

    assert draft not in shown
    assert undated not in shown
    assert hidden not in shown
    assert officers_only not in shown  # chapter calendar is chapter-audience only
    assert out_of_range not in shown
