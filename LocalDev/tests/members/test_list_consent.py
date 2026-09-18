"""GET /api/members/ carries `sms_consent` per member (issue #57).

The roster UI shows officers who is textable, and the member's own toggle reads
its current state off the same row — without this field both would have to guess.
The handler is awaited directly: `get_db` is its only boundary.

DB-backed (skips without TEST_DATABASE_URL, like the rest of the suite).
"""

from __future__ import annotations

import pytest

from api.members.api.members import list_members


@pytest.fixture
def roster(sb_client, monkeypatch, chapter_id):
    import api.members.api.members as members_api

    monkeypatch.setattr(members_api, "get_db", lambda: sb_client)

    async def _list(member_id: str, *, role: str | None = None) -> dict[str, dict]:
        rows = await list_members(
            user={"id": member_id, "chapter_id": chapter_id, "role": role}
        )
        return {r["id"]: r for r in rows}

    return _list


async def test_consent_is_false_until_the_member_opts_in(roster, member_factory):
    plain = member_factory()

    assert (await roster(plain))[plain]["sms_consent"] is False


async def test_consent_is_true_once_recorded(roster, member_factory, cursor):
    m = member_factory()
    cursor.execute("UPDATE members SET sms_consent_at = now() WHERE id = %s", (m,))

    assert (await roster(m))[m]["sms_consent"] is True


async def test_a_plain_member_sees_no_one_elses_consent(roster, member_factory, cursor):
    """Consent is officer-or-yourself data (#88) — a teammate's row omits it."""
    me = member_factory()
    other = member_factory()
    cursor.execute("UPDATE members SET sms_consent_at = now() WHERE id = %s", (other,))

    rows = await roster(me)

    assert rows[me]["sms_consent"] is False
    assert "sms_consent" not in rows[other]


async def test_an_officer_who_can_invite_sees_every_consent(
    roster, member_factory, cursor
):
    officer = member_factory(role="officer")
    other = member_factory()
    cursor.execute("UPDATE members SET sms_consent_at = now() WHERE id = %s", (other,))

    rows = await roster(officer, role="officer")

    assert rows[other]["sms_consent"] is True


async def test_an_opt_out_overrides_an_earlier_consent(roster, member_factory, cursor):
    m = member_factory()
    cursor.execute(
        "UPDATE members SET sms_consent_at = now(), sms_opted_out_at = now() WHERE id = %s",
        (m,),
    )

    assert (await roster(m))[m]["sms_consent"] is False
