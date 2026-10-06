"""Changed record-payment requests return a safe HTTP conflict."""

from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


def test_record_idempotency_changed_amount_is_409(api, cursor, chapter_id, member_id, member_factory):
    officer = member_factory()
    assign_role(cursor, chapter_id, officer, "treasurer")
    client = api(make_user(officer, chapter_id))
    body = {"member_id": member_id, "amount_cents": 3000, "method": "cash"}
    headers = {"Authorization": "Bearer x", "Idempotency-Key": "record-conflict"}
    assert client.post("/api/treasury/payments/record", json=body, headers=headers).status_code == 200
    response = client.post("/api/treasury/payments/record", json={**body, "amount_cents": 4000}, headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Idempotency key was already used with a different request"}
    cursor.execute("SELECT amount_cents FROM verified_payments WHERE chapter_id=%s AND member_id=%s",
                   (chapter_id, member_id))
    assert [r["amount_cents"] for r in cursor.fetchall()] == [3000]
