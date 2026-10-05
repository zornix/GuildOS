import pytest


def test_unknown_nested_relation_raises(sb_client):
    with pytest.raises(ValueError, match="unpaid_invoices.*members"):
        sb_client.table("unpaid_invoices").select("*, members(name)")


def test_known_nested_relation_still_works(sb_client, member_id):
    row = sb_client.table("members").select("id, chapters(name)").eq("id", member_id).single().execute().data
    assert row["chapters"]["name"]
