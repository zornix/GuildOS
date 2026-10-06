"""Case-insensitive insert races must leave the event transaction usable."""
from api.events.services import events as svc


def test_resolve_conflicting_type_commits(sb_client, cursor, chapter_id, monkeypatch):
    cursor.execute("INSERT INTO event_types(chapter_id,name) VALUES (%s,'Social') RETURNING id", (chapter_id,))
    existing_id = str(cursor.fetchone()["id"])
    original = svc.list_event_types
    missed = False

    def miss_first_read(sb, *, chapter_id):
        nonlocal missed
        rows = original(sb, chapter_id=chapter_id)
        if not missed:
            missed = True
            return []
        return rows

    monkeypatch.setattr(svc, "list_event_types", miss_first_read)
    with sb_client.transaction() as tx:
        assert svc.resolve_event_type_id(tx, chapter_id=chapter_id, name="social") == existing_id
        tx.table("events").insert({"chapter_id": chapter_id, "title": "Committed race", "date": "2026-07-01", "time": "19:00", "location": "Hall"}).execute()
    assert sb_client.table("events").select("id").eq("chapter_id", chapter_id).execute().data


def test_concurrent_default_seeding_commits(sb_client, cursor, chapter_id, monkeypatch):
    # Another connection seeds after the initial empty read but before insertion.
    from api.platform.postgres import QueryBuilder
    execute = QueryBuilder.execute
    seeded = False

    def seed_after_read(query):
        nonlocal seeded
        result = execute(query)
        if query._table == "event_types" and not seeded:
            seeded = True
            for name in svc.DEFAULT_EVENT_TYPES:
                cursor.execute("INSERT INTO event_types(chapter_id,name) VALUES (%s,%s)", (chapter_id, name))
        return result

    monkeypatch.setattr(QueryBuilder, "execute", seed_after_read)
    with sb_client.transaction() as tx:
        svc.ensure_default_event_types(tx, chapter_id=chapter_id)
        assert len(tx.table("event_types").select("id").eq("chapter_id", chapter_id).execute().data) == len(svc.DEFAULT_EVENT_TYPES)
