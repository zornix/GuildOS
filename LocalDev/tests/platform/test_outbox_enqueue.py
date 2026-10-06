"""F-021: enqueue dedups with ON CONFLICT and stops reporting real failures as duplicates."""

import logging
import uuid

import psycopg2
import pytest

from api.platform.outbox import _row, enqueue, enqueue_many


def _key():
    return f"test-outbox:{uuid.uuid4()}"


def _kw(chapter_id, member_id, key):
    return dict(
        event_type="INVOICE_ISSUED", chapter_id=chapter_id, member_id=member_id,
        target_table="unpaid_invoices", target_id=str(uuid.uuid4()), dedup_key=key,
    )


def _outbox_row(chapter_id, member_id, key):
    return _row(**_kw(chapter_id, member_id, key), payload=None, channel="email")


def _queued(sb, key):
    return sb.table("message_outbox").select("id").eq("dedup_key", key).execute().data


def test_insert_ignore_conflict_returns_only_new_rows(sb_client, chapter_id, member_id):
    k, k2 = _key(), _key()
    assert enqueue(sb_client, **_kw(chapter_id, member_id, k))
    data = (
        sb_client.table("message_outbox")
        .insert([_outbox_row(chapter_id, member_id, k), _outbox_row(chapter_id, member_id, k2)],
                ignore_conflict="dedup_key")
        .execute()
        .data
    )
    assert [r["dedup_key"] for r in data] == [k2]


def test_enqueue_duplicate_returns_none_without_error(sb_client, chapter_id, member_id, caplog):
    k = _key()
    assert enqueue(sb_client, **_kw(chapter_id, member_id, k))
    with caplog.at_level(logging.ERROR, logger="api.platform.outbox"):
        assert enqueue(sb_client, **_kw(chapter_id, member_id, k)) is None
    assert not caplog.records
    assert len(_queued(sb_client, k)) == 1


def test_enqueue_real_failure_is_not_reported_as_duplicate(sb_client, member_id, caplog):
    missing_chapter = str(uuid.uuid4())  # FK violation, not a duplicate

    with caplog.at_level(logging.ERROR, logger="api.platform.outbox"):
        assert enqueue(sb_client, **_kw(missing_chapter, member_id, _key())) is None
    assert any(r.levelno == logging.ERROR and r.name == "api.platform.outbox" for r in caplog.records)

    with pytest.raises(psycopg2.Error):
        with sb_client.transaction() as tx:
            enqueue(tx, **_kw(missing_chapter, member_id, _key()))


def test_enqueue_duplicate_inside_transaction_does_not_abort_it(sb_client, chapter_id, member_id):
    k, name = _key(), f"tx-outbox-{uuid.uuid4()}"
    with sb_client.transaction() as tx:
        assert enqueue(tx, **_kw(chapter_id, member_id, k))
        assert enqueue(tx, **_kw(chapter_id, member_id, k)) is None
        tx.table("chapters").insert({"name": name, "organization": "t", "school": "t"}).execute()
    assert sb_client.table("chapters").select("id").eq("name", name).execute().data
    assert len(_queued(sb_client, k)) == 1


def test_enqueue_many_counts_only_new_rows(sb_client, chapter_id, member_factory):
    members = [member_factory() for _ in range(3)]
    prefix = _key()
    key_for = lambda m: f"{prefix}:{m}"  # noqa: E731
    assert enqueue(sb_client, **_kw(chapter_id, members[0], key_for(members[0])))

    n = enqueue_many(
        sb_client, event_type="INVOICE_ISSUED", chapter_id=chapter_id,
        target_table="unpaid_invoices", target_id=str(uuid.uuid4()),
        member_ids=members, dedup_key_for=key_for,
    )
    assert n == 2
    assert all(len(_queued(sb_client, key_for(m))) == 1 for m in members)


def test_enqueue_many_real_failure_is_logged(sb_client, member_id, caplog):
    prefix = _key()
    with caplog.at_level(logging.ERROR, logger="api.platform.outbox"):
        n = enqueue_many(
            sb_client, event_type="INVOICE_ISSUED", chapter_id=str(uuid.uuid4()),
            target_table="unpaid_invoices", target_id=str(uuid.uuid4()),
            member_ids=[member_id], dedup_key_for=lambda m: f"{prefix}:{m}",
        )
    assert n == 0
    assert any(r.levelno == logging.ERROR and r.name == "api.platform.outbox" for r in caplog.records)


def test_enqueue_failure_log_does_not_echo_the_payload(sb_client, chapter_id, member_id, caplog):
    """Postgres' DETAIL line quotes the failing row, and auth payloads carry live codes."""
    code = f"{uuid.uuid4().int % 10**6:06d}"
    kw = _kw(chapter_id, member_id, _key()) | {"event_type": "NOT_A_REAL_EVENT"}  # CHECK violation
    with caplog.at_level(logging.ERROR, logger="api.platform.outbox"):
        assert enqueue(sb_client, **kw, payload={"code": code}) is None
    assert any(r.levelno == logging.ERROR and r.name == "api.platform.outbox" for r in caplog.records)
    assert code not in caplog.text
