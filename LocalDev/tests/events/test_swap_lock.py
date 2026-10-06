"""Security swap acceptance must serialize with event-wide assignments."""

import psycopg2
import pytest

from tests.events.test_security import _assign, _request


def test_accept_security_swap_takes_the_event_lock(
    db_url, sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    event = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task = _assign(sb_client, chapter_id, event["id"], holder["id"], officer["id"])
    swap = _request(sb_client, chapter_id, task["task"]["id"], target["id"], holder["id"])

    hold = psycopg2.connect(db_url, connect_timeout=15)
    accept = psycopg2.connect(db_url, connect_timeout=15)
    try:
        with hold.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext('ev_security:' || %s))",
                (event["id"],),
            )
        with accept.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '500ms'")
            with pytest.raises(psycopg2.errors.LockNotAvailable, match="lock timeout"):
                cur.execute(
                    "SELECT ev_accept_security_swap(%s, %s, %s, NULL)",
                    (chapter_id, swap["id"], target["id"]),
                )
    finally:
        accept.rollback()
        accept.close()
        hold.rollback()
        hold.close()
