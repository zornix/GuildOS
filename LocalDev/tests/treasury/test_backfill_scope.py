"""The legacy-coverage test helper must scope every data statement."""

from tests.treasury.test_single_coverage import _run_0165_data


def test_0165_backfill_is_chapter_scoped():
    class RecordingCursor:
        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params

    cursor = RecordingCursor()
    chapter_id = "00000000-0000-0000-0000-000000000001"
    _run_0165_data(cursor, chapter_id)
    # The affected-invoice scan, INSERT and UPDATE must each have their own
    # chapter predicate. A filter only on the scan still permits global writes.
    assert "WHERE invoice_id IS NOT NULL AND chapter_id =" in cursor.sql
    assert cursor.sql.count("WHERE vp.invoice_id IS NOT NULL AND vp.chapter_id =") == 2
    assert cursor.params == (chapter_id, chapter_id, chapter_id)
