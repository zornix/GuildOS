import pytest


def test_name_filter_matches_fixture_names_only():
    from scripts.purge_test_chapters import is_test_chapter
    for name in ('tr-test-abc', 'rc-test-abc', 'at-test-abc', 'ob-test-abc',
                 'tx-test-abc', 'tx-outbox-abc', 'foreign-abc', 'other-abc',
                 'rbac-other-abc', 'contrib-other-abc', 'Chapter abc123def456',
                 'other', 'other2', 'ev-other', 'in-other', 'other-get',
                 'other-jobs', 'Other delete chapter'):
        assert is_test_chapter(name), name
    for name in ('Delta Mu', 'Alpha Beta', 'other real chapter', 'Chapter Delta',
                 'Treasury', '', 'TR-TEST-abc'):
        assert not is_test_chapter(name), name


def test_guard_runs_before_connection(monkeypatch):
    from scripts import purge_test_chapters as purge
    from scripts.db_guard import ProdGuardError
    monkeypatch.setattr(purge, '_database_url', lambda: 'postgresql://user:pass@unknown.invalid/db')
    monkeypatch.setattr(purge.psycopg2, 'connect', lambda *a, **kw: pytest.fail('connected before guard'))
    with pytest.raises(ProdGuardError):
        purge.main([])


@pytest.mark.parametrize('failure', [None, 'DELETE FROM', 'ENABLE REPLICA'])
def test_apply_restores_trigger_states_on_success_and_error(monkeypatch, failure):
    from scripts import purge_test_chapters as purge

    # Simulate PostgreSQL's transactional DDL, including its aborted state.
    monkeypatch.setattr(purge.sql, 'Identifier', lambda name: purge.sql.SQL(name))

    class Cursor:
        def __init__(self):
            self.states = {'ledger_guard': 'O', 'receipt_guard': 'R', 'audit_guard': 'A'}
            self.initial = self.states.copy()
            self.deleted = False
            self.aborted = False
            self.commands = []

        def execute(self, query, params=None):
            query = query if isinstance(query, str) else query.as_string(None)
            self.commands.append(query)
            if query.startswith('ROLLBACK TO'):
                self.states = self.initial.copy()
                self.deleted = False
                self.aborted = False
                return
            assert not self.aborted, 'query attempted in aborted transaction'
            if failure and failure in query:
                self.aborted = True
                raise RuntimeError('injected database failure')
            if 'DISABLE TRIGGER' in query:
                self.states[query.split()[-1]] = 'D'
            elif 'ENABLE' in query:
                self.states[query.split()[-1]] = (
                    'R' if 'REPLICA' in query else 'A' if 'ALWAYS' in query else 'O')
            elif query.startswith('DELETE FROM'):
                self.deleted = True

        def fetchall(self):
            return [('big_ledger', 'ledger_guard', 'O'),
                    ('receipts', 'receipt_guard', 'R'),
                    ('audit_logs', 'audit_guard', 'A')]

    cursor = Cursor()
    if failure:
        with pytest.raises(RuntimeError, match='injected database failure'):
            purge.apply_purge(cursor, ['00000000-0000-0000-0000-000000000001'])
        assert not cursor.deleted
    else:
        purge.apply_purge(cursor, ['00000000-0000-0000-0000-000000000001'])
        assert cursor.deleted
    assert cursor.states == cursor.initial
    assert cursor.commands[-1] == 'RELEASE SAVEPOINT purge_test_chapters'


def test_every_delete_blocking_table_is_unguarded_during_the_purge():
    """A table whose trigger blocks DELETE and is missing here makes --apply roll back."""
    import re
    from pathlib import Path
    from scripts.purge_test_chapters import DELETE_GUARD_TABLES
    pattern = re.compile(r"BEFORE\s+[A-Z\s]*DELETE[A-Z\s]*\s+ON\s+(?:public\.)?(\w+)", re.I)
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    blocked = {m.group(1) for f in migrations.glob("*.sql") for m in pattern.finditer(f.read_text())}
    assert blocked - set(DELETE_GUARD_TABLES) == set()
