import pytest

BAD = 'id"; DROP TABLE members; --'


@pytest.mark.parametrize("build", [
    lambda sb: sb.table("members").select("*").eq(BAD, 1).execute(),
    lambda sb: sb.table("members").select("*").in_(BAD, [1]).execute(),
    lambda sb: sb.table("members").select("*").order(BAD).execute(),
    lambda sb: sb.table("members").select(f"id, {BAD}").execute(),
    lambda sb: sb.table("members").insert({BAD: 1}).execute(),
    lambda sb: sb.table("members").update({BAD: 1}).eq("id", "x").execute(),
    lambda sb: sb.table("members").upsert({"id": "x"}, on_conflict=BAD).execute(),
    lambda sb: sb.table(BAD).select("*").execute(),
])
def test_bad_identifier_rejected(sb_client, build):
    with pytest.raises(ValueError, match="identifier"):
        build(sb_client)


def test_dotted_join_filter_allowed(sb_client, chapter_id):
    sb_client.table("attendance").select("id, events(title)").eq("events.chapter_id", chapter_id).execute()
