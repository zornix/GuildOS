"""prior_security_shifts on GET /api/memberadmin/scores (B4FEND §5.5, D17).

A count of approved security jobs the member held — the picker's "prior shifts"
column (spec Screen 6). A decoration only: it never feeds the 0–100 score.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from api.memberadmin.services.scoring import compute_engagement_scores
from tests.treasury.test_v1_helpers import api, make_user  # noqa: F401


def _event(cursor, chapter_id) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=30)
    cursor.execute(
        """INSERT INTO events (chapter_id, title, description, date, time, location, required, fine_amount)
           VALUES (%s, 'Party', '', %s, %s, 'Hall', true, 0) RETURNING id""",
        (chapter_id, start.date(), start.time()),
    )
    return str(cursor.fetchone()["id"])


def _security_shift(cursor, chapter_id, event_id, member_id, *, task_status, commitment_status):
    cursor.execute(
        "INSERT INTO tasks (chapter_id, title, status, kind, event_id, people_needed) "
        "VALUES (%s, %s, %s, 'security', %s, 1) RETURNING id",
        (chapter_id, f"Security {uuid.uuid4().hex[:6]}", task_status, event_id),
    )
    task_id = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO task_commitments (chapter_id, task_id, member_id, status) "
        "VALUES (%s, %s, %s, %s)",
        (chapter_id, task_id, member_id, commitment_status),
    )
    return task_id


async def test_prior_security_shifts_counts_approved_jobs_only(
    api, sb_client, cursor, chapter_id, member_factory
):
    veteran, rookie = member_factory(), member_factory()
    event_id = _event(cursor, chapter_id)

    _security_shift(cursor, chapter_id, event_id, veteran,
                    task_status="approved", commitment_status="completed")
    _security_shift(cursor, chapter_id, event_id, veteran,
                    task_status="approved", commitment_status="active")
    # Still on the door tonight — not a prior shift yet.
    _security_shift(cursor, chapter_id, event_id, veteran,
                    task_status="in_progress", commitment_status="active")

    scores = await compute_engagement_scores(chapter_id)
    by_member = {s["member_id"]: s for s in scores}
    assert by_member[veteran]["prior_security_shifts"] == 2
    assert by_member[rookie]["prior_security_shifts"] == 0


async def test_prior_shifts_do_not_move_the_score(
    api, sb_client, cursor, chapter_id, member_factory
):
    """Same fixture as the fine-penalty test: one required unattended event and a
    $10 fine give a known 9.5. Security history must not shift it."""
    member = member_factory()
    event_id = _event(cursor, chapter_id)
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s, %s, 'fine', 1000, 'unpaid')""",
        (chapter_id, member),
    )
    for _ in range(3):
        _security_shift(cursor, chapter_id, event_id, member,
                        task_status="approved", commitment_status="completed")

    row = next(s for s in await compute_engagement_scores(chapter_id) if s["member_id"] == member)
    assert row["prior_security_shifts"] == 3
    assert row["score"] == 9.5
