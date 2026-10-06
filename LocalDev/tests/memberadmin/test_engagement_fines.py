"""Standing/engagement reads unpaid *fine* invoices in integer cents.

Pins the fix in `imp-standing-fines.md`: the engagement loader now sums
`unpaid_invoices.amount_cents` where `kind='fine'` (D1), carries the total as
integer cents (D2), and the scoring/standing thresholds convert ×100 with
identical semantics (D3).

Pattern follows `tests/treasury/test_v1_fines.py`: real FastAPI app + real
Postgres, fines created through the `/api/fines/issue` RPC path. The DB
fixtures come from `tests/memberadmin/conftest.py` (re-exported treasury
harness); `api`/`assign_role`/`make_user` come from the treasury helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api.memberadmin.core.engagement import load_member_engagement
from api.memberadmin.services.scoring import compute_engagement_scores
from api.memberadmin.core.standing_rules import (
    HIGH_UNPAID_BALANCE,
    UNPAID_FINES,
)
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


def _make_required_event(cursor, chapter_id, *, hours_ago: float = 30) -> str:
    """A required event in the past so the loader's fine query path runs."""
    start = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).astimezone(ZoneInfo("America/Los_Angeles"))
    cursor.execute(
        """INSERT INTO events (chapter_id, title, description, date, time, location, required, fine_amount)
           VALUES (%s, 'Chapter Meeting', '', %s, %s, 'Hall', true, 0) RETURNING id""",
        (chapter_id, start.date(), start.time()),
    )
    return str(cursor.fetchone()["id"])


def _insert_invoice(cursor, chapter_id, member_id, kind, amount_cents) -> None:
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s, %s, %s, %s, 'unpaid')""",
        (chapter_id, member_id, kind, amount_cents),
    )


def _row_for(engagements, member_id):
    return next(r for r in engagements if r.member_id == member_id)


async def test_engagement_reads_unpaid_fine_from_invoices_in_cents(
    api, sb_client, cursor, chapter_id, member_factory
):
    """A fine issued through the RPC path shows up as unpaid_amount_cents=2500."""
    finance = member_factory()
    assign_role(cursor, chapter_id, finance, "finance_board")
    fined = member_factory()
    event_id = _make_required_event(cursor, chapter_id)

    client = api(make_user(finance, chapter_id))
    issue = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [fined]},
        headers={"Authorization": "Bearer x"},
    )
    assert issue.status_code == 200, issue.text

    engagements = await load_member_engagement(chapter_id)
    row = _row_for(engagements, fined)
    assert row.unpaid_amount_cents == 2500  # flat $25 fine, integer cents
    assert row.unpaid_fines == 1
    assert isinstance(row.unpaid_amount_cents, int)


async def test_dues_invoice_never_affects_standing(
    api, sb_client, cursor, chapter_id, member_factory
):
    """D1: only kind='fine' counts. A member with only a dues invoice owes $0
    toward standing and earns no fine-related reason codes."""
    duespayer = member_factory()
    _make_required_event(cursor, chapter_id)  # so the fine query path runs
    _insert_invoice(cursor, chapter_id, duespayer, "dues", 5000)  # $50 dues, not a fine

    engagements = await load_member_engagement(chapter_id)
    row = _row_for(engagements, duespayer)
    assert row.unpaid_amount_cents == 0
    assert row.unpaid_fines == 0

    # No fine-related reason codes are derivable from a dues-only member.
    from api.memberadmin.core.standing_rules import derive_standing

    _, reasons = derive_standing(
        unpaid_count=row.unpaid_fines,
        unpaid_total_cents=row.unpaid_amount_cents,
        unexcused=0,
    )
    assert UNPAID_FINES not in reasons
    assert HIGH_UNPAID_BALANCE not in reasons


async def test_scoring_penalty_uses_x100_cents_conversion(
    api, sb_client, cursor, chapter_id, member_factory
):
    """D3: the fine penalty is amount_cents/20000 (was dollars/200). A $10 fine
    (1000 cents) → penalty 0.05, uncapped. If the ×100 conversion were missed
    (amount_cents/200), the penalty would cap at 0.10 and the score would be
    0.9 instead — this pins the divisor.

    With one required, unattended event: attendance_pct=0, excuse_pct=0, so
    score == round((1 - penalty) * 10, 1). Correct: (1-0.05)*10 = 9.5.
    Buggy (capped 0.10): (1-0.10)*10 = 9.0.
    """
    fined = member_factory()
    _make_required_event(cursor, chapter_id)
    _insert_invoice(cursor, chapter_id, fined, "fine", 1000)  # $10 fine, below cap

    engagements = await load_member_engagement(chapter_id)
    assert _row_for(engagements, fined).unpaid_amount_cents == 1000

    scores = await compute_engagement_scores(chapter_id)
    row = next(s for s in scores if s["member_id"] == fined)
    assert row["unpaid_amount_cents"] == 1000
    assert row["score"] == 9.5  # correct /20000; the buggy /200 would give 9.0
