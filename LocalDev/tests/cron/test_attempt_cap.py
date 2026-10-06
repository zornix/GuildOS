"""Repeated abandoned claims must consume the bounded retry allowance."""


def test_repeated_crashed_claims_reach_attempt_cap(cursor, chapter_id, outbox_row, read_outbox):
    row = outbox_row()
    handed_out = 0
    for _ in range(6):
        cursor.execute("SELECT outbox_claim_batch(1, %s::uuid) AS rows", (chapter_id,))
        handed_out += len(cursor.fetchone()["rows"])
        cursor.execute(
            "UPDATE message_outbox SET claimed_at=now()-interval '20 minutes' "
            "WHERE id=%s AND chapter_id=%s AND status='sending'",
            (row["id"], chapter_id),
        )
        cursor.execute("SELECT outbox_claim_batch(0, %s::uuid)", (chapter_id,))
    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert after["attempts"] == 5
    assert handed_out == 5
    assert "attempt cap" in after["last_error"]
