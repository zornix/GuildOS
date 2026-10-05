def test_select_returns_string_ids(sb_client, member_id, chapter_id):
    row = sb_client.table("members").select("id, chapter_id").eq("id", member_id).single().execute().data
    assert isinstance(row["id"], str) and row["id"] == member_id
    assert isinstance(row["chapter_id"], str) and row["chapter_id"] == chapter_id
