"""The officers audience honours legacy officers again (issue #30).

Both audience resolvers had been narrowed to `member_roles` alone, on the premise
that 0147 backfilled every legacy officer into it. That premise held for exactly
as long as the migration took to run: an officer promoted afterwards is
authorized everywhere else in the app but was silently dropped from every
officers-audience SMS blast and never saw officers-only announcements in the
feed. Both now go through `rbac.services.permissions.is_officer` — the same union
`get_member_permissions` authorizes from.
"""

from __future__ import annotations

from api.announcements.services.announcements import (
    AUDIENCE_OFFICERS,
    audiences_for_viewer,
)
from api.announcements.services.sms import resolve_recipients


def _officers(sb_client, chapter_id) -> set[str]:
    return set(
        resolve_recipients(sb_client, chapter_id=chapter_id, audience="officers")[
            "recipient_member_ids"
        ]
    )


def test_legacy_officer_is_on_the_officers_blast(
    sb_client, chapter_id, member_factory, set_phone
):
    """The column alone grants nothing (F-022); the member_roles row does."""
    legacy = member_factory(role="officer")
    set_phone(legacy, "+15550000101")

    assert legacy in _officers(sb_client, chapter_id)


def test_legacy_officer_sees_officers_only_announcements(sb_client, chapter_id, member_factory):
    legacy = member_factory(role="officer")

    audiences = audiences_for_viewer(
        sb_client, chapter_id=chapter_id, viewer={"id": legacy, "role": "officer"}
    )
    assert AUDIENCE_OFFICERS in audiences


def test_granular_officer_without_the_legacy_column_still_counts(
    sb_client, chapter_id, member_factory, give_role, set_phone
):
    """The other half of the union: role catalog grant, legacy column says 'member'."""
    granular = member_factory()
    give_role(granular, "social_chair")
    set_phone(granular, "+15550000102")

    assert granular in _officers(sb_client, chapter_id)
    assert AUDIENCE_OFFICERS in audiences_for_viewer(
        sb_client, chapter_id=chapter_id, viewer={"id": granular, "role": "member"}
    )


def test_plain_member_is_on_neither(
    sb_client, chapter_id, member_factory, set_phone
):
    plain = member_factory()
    set_phone(plain, "+15550000103")

    assert plain not in _officers(sb_client, chapter_id)
    assert AUDIENCE_OFFICERS not in audiences_for_viewer(
        sb_client, chapter_id=chapter_id, viewer={"id": plain, "role": "member"}
    )


def test_demoted_officer_drops_off_the_blast(
    sb_client, chapter_id, member_factory, give_role, set_phone, cursor
):
    """Both sides cleared (what 0154 now does) means both resolvers agree."""
    demoted = member_factory(role="officer")
    give_role(demoted, "officer")
    set_phone(demoted, "+15550000104")
    assert demoted in _officers(sb_client, chapter_id)

    cursor.execute(
        "SELECT mem_set_legacy_role(%s, %s, 'member', NULL)", (chapter_id, demoted)
    )

    assert demoted not in _officers(sb_client, chapter_id)
    assert AUDIENCE_OFFICERS not in audiences_for_viewer(
        sb_client, chapter_id=chapter_id, viewer={"id": demoted, "role": "member"}
    )
