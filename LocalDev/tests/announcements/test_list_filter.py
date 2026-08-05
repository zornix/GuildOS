"""GET /api/announcements/ — the feed is filtered, not a draft leak.

A plain member sees only announcements that were actually sent AND whose
audience includes them. Holders of `announcements:create` keep the management
view (drafts + the `status` filter).
"""

from __future__ import annotations


def _list(client, status: str | None = None):
    url = "/api/announcements/"
    if status:
        url += f"?status={status}"
    return client.get(url)


def _ids(resp) -> set[str]:
    return {row["id"] for row in resp.json()}


def test_member_sees_sent_announcements_only(member_factory, as_member, announcement_factory):
    sent = announcement_factory(status="sent", title="Sent to all")
    draft = announcement_factory(status="draft", title="Unannounced draft")

    resp = _list(as_member(member_factory()))
    assert resp.status_code == 200, resp.text
    ids = _ids(resp)
    assert sent in ids
    assert draft not in ids
    assert all(row["status"] == "sent" for row in resp.json())


def test_member_cannot_request_drafts_via_status_param(
    member_factory, as_member, announcement_factory
):
    draft = announcement_factory(status="draft")

    resp = _list(as_member(member_factory()), status="draft")
    assert resp.status_code == 200, resp.text  # filtered, never a 403
    assert draft not in _ids(resp)
    assert resp.json() == []


def test_member_does_not_see_officers_only_announcement(
    member_factory, as_member, announcement_factory
):
    officers_only = announcement_factory(status="sent", audience="officers")
    chapter_wide = announcement_factory(status="sent", audience="chapter")

    ids = _ids(_list(as_member(member_factory())))
    assert chapter_wide in ids
    assert officers_only not in ids


def test_officer_sees_officers_only_announcement(
    member_factory, give_role, as_member, announcement_factory
):
    officers_only = announcement_factory(status="sent", audience="officers")
    officer = member_factory()
    give_role(officer, "social_chair")  # a role above plain member = officer audience

    assert officers_only in _ids(_list(as_member(officer)))


def test_member_without_balance_skips_balance_audience(
    member_factory, as_member, announcement_factory
):
    dunning = announcement_factory(status="sent", audience="members_with_balance")

    assert dunning not in _ids(_list(as_member(member_factory())))


def test_member_with_balance_sees_balance_audience(
    member_factory, as_member, announcement_factory, cursor, chapter_id
):
    dunning = announcement_factory(status="sent", audience="members_with_balance")
    debtor = member_factory()
    cursor.execute(
        """
        INSERT INTO member_finance_accounts (chapter_id, member_id, outstanding_balance_cents)
        VALUES (%s, %s, 2500)
        ON CONFLICT (member_id) DO UPDATE SET outstanding_balance_cents = 2500
        """,
        (chapter_id, debtor),
    )

    assert dunning in _ids(_list(as_member(debtor)))


def test_creator_sees_drafts(president, as_member, announcement_factory):
    """President holds announcements:create — the management view keeps drafts."""
    draft = announcement_factory(status="draft", title="Officer draft")
    sent = announcement_factory(status="sent")

    resp = _list(as_member(president))
    assert resp.status_code == 200, resp.text
    ids = _ids(resp)
    assert draft in ids
    assert sent in ids


def test_creator_status_filter_still_works(president, as_member, announcement_factory):
    draft = announcement_factory(status="draft")
    sent = announcement_factory(status="sent")

    ids = _ids(_list(as_member(president), status="draft"))
    assert draft in ids
    assert sent not in ids
