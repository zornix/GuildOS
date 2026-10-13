"""#97: list insert() rejects mismatched row keys; not_in_ filter."""

import uuid

import pytest

from api.platform.outbox import _row


def _keys(n):
    prefix = f"test-bulk:{uuid.uuid4()}"
    return [f"{prefix}:{i}" for i in range(n)]


def _outbox_row(chapter_id, member_id, key):
    return _row(
        event_type="INVOICE_ISSUED", chapter_id=chapter_id, member_id=member_id,
        target_table="unpaid_invoices", target_id=str(uuid.uuid4()), dedup_key=key,
        payload=None, channel="email",
    )


def _dedup_keys(query):
    return sorted(r["dedup_key"] for r in query.execute().data)


@pytest.mark.parametrize("short_row", [0, 1], ids=["extra-key-in-row-2", "missing-key-in-row-2"])
def test_list_insert_with_mismatched_keys_raises_and_inserts_nothing(sb_client, chapter_id, member_id, short_row):
    keys = _keys(2)
    rows = [_outbox_row(chapter_id, member_id, k) for k in keys]
    del rows[short_row]["status"]

    with pytest.raises(ValueError, match="status"):
        sb_client.table("message_outbox").insert(rows).execute()
    assert not sb_client.table("message_outbox").select("id").in_("dedup_key", keys).execute().data


def test_not_in_excludes_values_and_empty_list_adds_no_condition(sb_client, chapter_id, member_id):
    keys = _keys(3)
    sb_client.table("message_outbox").insert([_outbox_row(chapter_id, member_id, k) for k in keys]).execute()
    base = lambda: sb_client.table("message_outbox").select("dedup_key").in_("dedup_key", keys)  # noqa: E731

    assert _dedup_keys(base().not_in_("dedup_key", [keys[1]])) == [keys[0], keys[2]]
    assert _dedup_keys(base().not_in_("dedup_key", [])) == keys
