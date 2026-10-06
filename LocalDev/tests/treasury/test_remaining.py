from api.treasury.services.remaining import remaining_by_invoice


def test_remaining_with_partial_payment_and_reversal(
    sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    invoices = []
    for _ in range(3):
        cursor.execute(
            "INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents) VALUES (%s,%s,'fine',2500) RETURNING id, amount_cents",
            (chapter_id, member),
        )
        invoices.append({**cursor.fetchone()})
    invoices = [{**r, "id": str(r["id"])} for r in invoices]
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id,member_id,amount_cents) VALUES (%s,%s,2501) RETURNING id",
        (chapter_id, member),
    )
    payment = str(cursor.fetchone()["id"])
    for inv, amount in zip(invoices, (1, 2500)):
        cursor.execute(
            "INSERT INTO payment_allocations (chapter_id,verified_payment_id,invoice_id,amount_cents) VALUES (%s,%s,%s,%s) RETURNING id",
            (chapter_id, payment, inv["id"], amount),
        )
        allocation = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO payment_allocations (chapter_id,verified_payment_id,invoice_id,amount_cents,reverses_allocation_id) VALUES (%s,%s,%s,2500,%s)",
        (chapter_id, payment, invoices[1]["id"], allocation),
    )
    assert remaining_by_invoice(sb_client, invoices) == dict(
        zip([r["id"] for r in invoices], (2499, 2500, 2500))
    )


def test_empty_does_not_query():
    assert remaining_by_invoice(None, []) == {}
