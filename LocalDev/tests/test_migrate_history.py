import argparse

import pytest

from scripts import migrate_db as m


def test_unknown_applied_names():
    assert m.unknown_applied({"0001_a.sql", "0002_old.sql"}, ["0001_a.sql", "0003_c.sql"]) == ["0002_old.sql"]
    assert m.unknown_applied({"0001_a.sql"}, ["0001_a.sql", "0003_c.sql"]) == []


def test_edited_after_apply():
    applied = {"0001_a.sql": "aaa", "0002_b.sql": None, "0003_c.sql": "ccc"}
    files = {"0001_a.sql": "aaa", "0002_b.sql": "anything", "0003_c.sql": "CHANGED"}
    assert m.edited_after_apply(applied, files) == ["0003_c.sql"]


class HistoryConnection:
    def __init__(self, history, checksum_column=True, table_exists=True):
        self.history = history
        self.checksum_column = checksum_column
        self.table_exists = table_exists
        self.statements = []
        self.commits = 0
        self.closed = False
        self.result = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params=None):
        self.statements.append(sql.strip())
        if 'to_regclass' in sql:
            self.result = [('schema_migrations' if self.table_exists else None,)]
        elif 'information_schema.columns' in sql:
            self.result = [(self.checksum_column,)]
        elif sql.startswith('SELECT name, checksum'):
            self.result = list(self.history.items())
        elif sql.startswith('SELECT name'):
            self.result = [(name, None) for name in self.history]

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True

    @property
    def writes(self):
        return [sql for sql in self.statements if not sql.startswith('SELECT')]


@pytest.fixture
def main_harness(tmp_path, monkeypatch):
    (tmp_path / '0001_a.sql').write_text('SELECT 1;')
    (tmp_path / '0002_b.sql').write_text('SELECT 2;')
    monkeypatch.setattr(m, 'MIGRATIONS_DIR', tmp_path)
    monkeypatch.setattr(m, '_parse_args', lambda: argparse.Namespace(prod=True, yes=False))
    monkeypatch.setattr(m, '_env_value', lambda key: 'synthetic-database')
    monkeypatch.setattr(m, 'require_prod', lambda url: None)
    monkeypatch.setattr(m, 'redact', lambda url: 'mock target')
    monkeypatch.setattr(m, 'confirmation_matches', lambda typed, url: typed == 'confirm')

    def connect(history, **kwargs):
        conn = HistoryConnection(history, **kwargs)
        monkeypatch.setattr(m.psycopg2, 'connect', lambda url: conn)
        return conn

    return connect


def test_prod_refusal_performs_no_writes(main_harness, monkeypatch, capsys):
    conn = main_harness({'0001_a.sql': None})
    monkeypatch.setattr('builtins.input', lambda prompt: 'refuse')
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert 'confirmation mismatch' in capsys.readouterr().err
    assert conn.closed
    assert conn.writes == []
    assert conn.commits == 0


@pytest.mark.parametrize('history,message', [
    ({'0001_a.sql': 'changed'}, 'changed after they were applied'),
    ({'missing.sql': None}, 'unknown history'),
])
def test_prod_history_refusals_perform_no_writes(main_harness, monkeypatch, capsys,
                                                history, message):
    conn = main_harness(history)
    def unexpected_prompt(prompt):
        pytest.fail('History must be checked before confirmation')
    monkeypatch.setattr('builtins.input', unexpected_prompt)
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert message in capsys.readouterr().err
    assert conn.closed
    assert conn.writes == []
    assert conn.commits == 0


@pytest.mark.parametrize('table_exists,checksum_column', [(True, True), (True, False), (False, False)])
def test_prod_confirmation_precedes_all_writes(main_harness, monkeypatch,
                                              table_exists, checksum_column):
    conn = main_harness({'0001_a.sql': None} if table_exists else {},
                        table_exists=table_exists, checksum_column=checksum_column)
    def confirm(prompt):
        assert conn.writes == []
        assert conn.commits == 0
        return 'confirm'
    monkeypatch.setattr('builtins.input', confirm)
    m.main()
    assert any(sql.startswith('ALTER TABLE') for sql in conn.writes)
    assert any(sql.startswith('INSERT INTO') for sql in conn.writes)
    if table_exists:
        assert any(sql.startswith('UPDATE') for sql in conn.writes)
    assert conn.closed


def test_prod_up_to_date_still_confirms_before_legacy_backfill(main_harness, monkeypatch):
    conn = main_harness({'0001_a.sql': None, '0002_b.sql': None}, checksum_column=False)
    monkeypatch.setattr('builtins.input', lambda prompt: 'refuse')
    with pytest.raises(SystemExit):
        m.main()
    assert conn.writes == []


def test_prod_eof_performs_no_writes(main_harness, monkeypatch, capsys):
    conn = main_harness({})
    def eof(prompt):
        raise EOFError
    monkeypatch.setattr('builtins.input', eof)
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert 'no confirmation input' in capsys.readouterr().err
    assert conn.writes == []


def test_prod_yes_skips_prompt_after_history_check(main_harness, monkeypatch):
    conn = main_harness({})
    monkeypatch.setattr(m, '_parse_args', lambda: argparse.Namespace(prod=True, yes=True))
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('Unexpected prompt'))
    m.main()
    assert any(sql.startswith('INSERT INTO') for sql in conn.writes)


def test_demo_path_keeps_legacy_backfill_without_prompt(main_harness, monkeypatch):
    conn = main_harness({'0001_a.sql': None, '0002_b.sql': None})
    monkeypatch.setattr(m, '_parse_args', lambda: argparse.Namespace(prod=False, yes=False))
    monkeypatch.setattr(m, '_database_url', lambda: 'synthetic-database')
    monkeypatch.setattr(m, 'require_demo', lambda url, context: None)
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('Unexpected prompt'))
    m.main()
    assert conn.statements[0].startswith('CREATE TABLE')
    assert any(sql.startswith('UPDATE') for sql in conn.writes)
    assert not any(sql.startswith('INSERT INTO') for sql in conn.writes)
