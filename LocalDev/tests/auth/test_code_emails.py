"""Setup and reset codes are emailed as well as returned (ADR-0005).

`_issue_setup_code` is the single place a code is minted, so every producer —
invite, chapter creation, roster import, officer reset — queues the email from
the same line. These assert the row each path produces.
"""

from __future__ import annotations

import uuid

import pytest

from api.auth.api.auth import _issue_setup_code


@pytest.fixture
def code_rows(cursor, chapter_id):
    def _read(member_id: str) -> list[dict]:
        cursor.execute(
            """
            SELECT event_type, channel, payload, member_id
              FROM message_outbox
             WHERE chapter_id = %s AND member_id = %s
               AND event_type IN ('SETUP_CODE', 'RESET_CODE')
             ORDER BY created_at
            """,
            (chapter_id, member_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    return _read


def test_issuing_a_setup_code_queues_an_email_carrying_it(
    sb_client, chapter_id, member_factory, code_rows
):
    member = member_factory()
    code, expires_at = _issue_setup_code(
        sb_client, chapter_id=chapter_id, member_id=member
    )

    rows = code_rows(member)
    assert [r["event_type"] for r in rows] == ["SETUP_CODE"]
    assert rows[0]["channel"] == "email"
    assert rows[0]["payload"]["code"] == code
    assert rows[0]["payload"]["expires_at"] == expires_at
    assert rows[0]["payload"]["frontend_url"]


def test_a_reset_code_is_its_own_event_type(
    sb_client, chapter_id, member_factory, code_rows
):
    from api.auth.notifications import RESET_CODE

    member = member_factory()
    _issue_setup_code(
        sb_client, chapter_id=chapter_id, member_id=member, event_type=RESET_CODE
    )

    assert [r["event_type"] for r in code_rows(member)] == ["RESET_CODE"]


def test_re_issuing_queues_a_second_email(
    sb_client, chapter_id, member_factory, code_rows
):
    """The dedup key is per issuance: a re-invite must actually reach the member."""
    member = member_factory()
    _issue_setup_code(sb_client, chapter_id=chapter_id, member_id=member)
    _issue_setup_code(sb_client, chapter_id=chapter_id, member_id=member)

    assert len(code_rows(member)) == 2


def test_the_officer_outbox_never_prints_a_code(sb_client, chapter_id, member_factory):
    """A live credential must not be readable from the outbox surface."""
    from api.announcements.services.outbox import list_outbox

    member = member_factory()
    code, _ = _issue_setup_code(sb_client, chapter_id=chapter_id, member_id=member)

    rows = list_outbox(sb_client, chapter_id=chapter_id)
    setup = [r for r in rows if r["event_type"] == "SETUP_CODE"]
    assert setup, "the row should still be visible"
    assert all(code not in r["body"] for r in setup)


def test_roster_import_emails_every_created_member(sb_client, chapter_id, cursor):
    """The import path mints one code per member, so one email per member."""
    from api.chapters.services.onboarding import import_roster

    tag = uuid.uuid4().hex[:8]
    csv = "name,email,phone\n" + "".join(
        f"Member {tag}{i},roster-{tag}-{i}@example.test,555123{i:04d}\n" for i in range(3)
    )
    result = import_roster(sb_client, chapter_id=chapter_id, raw=csv.encode())
    assert result["created_count"] == 3

    cursor.execute(
        """
        SELECT count(*) AS n FROM message_outbox
         WHERE chapter_id = %s AND event_type = 'SETUP_CODE' AND channel = 'email'
        """,
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 3
