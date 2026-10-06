from scripts import migrate_db as m


def test_unknown_applied_names():
    assert m.unknown_applied({"0001_a.sql", "0002_old.sql"}, ["0001_a.sql", "0003_c.sql"]) == ["0002_old.sql"]
    assert m.unknown_applied({"0001_a.sql"}, ["0001_a.sql", "0003_c.sql"]) == []


def test_edited_after_apply():
    applied = {"0001_a.sql": "aaa", "0002_b.sql": None, "0003_c.sql": "ccc"}
    files = {"0001_a.sql": "aaa", "0002_b.sql": "anything", "0003_c.sql": "CHANGED"}
    assert m.edited_after_apply(applied, files) == ["0003_c.sql"]
