from scripts import migration_checksums as mc


def test_no_recorded_migration_has_changed():
    listed = mc.read_manifest()
    assert listed, "migrations/CHECKSUMS is missing or empty"
    assert mc.changed(listed, mc.current()) == []


def test_changed_detects_an_edit_and_a_delete():
    listed = {"0001_a.sql": "aaa", "0002_b.sql": "bbb"}
    assert mc.changed(listed, {"0001_a.sql": "aaa", "0002_b.sql": "XXX"}) == ["0002_b.sql"]
    assert mc.changed(listed, {"0001_a.sql": "aaa"}) == ["0002_b.sql"]


def test_unlisted_reports_new_files_only():
    assert mc.unlisted({"0001_a.sql": "aaa"}, {"0001_a.sql": "zzz", "0003_c.sql": "ccc"}) == ["0003_c.sql"]
