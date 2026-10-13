import pytest
import secrets
from unittest.mock import MagicMock


def _no_connect(monkeypatch, module):
    monkeypatch.setattr(module.psycopg2, 'connect', lambda *a, **kw: pytest.fail('connected'))


def test_guard_runs_before_connection(monkeypatch):
    from scripts import reset_demo
    monkeypatch.setenv('SEED_PASSWORD', secrets.token_hex(6))
    monkeypatch.setattr(reset_demo, '_database_url', lambda: 'postgresql://user:pass@unknown.invalid/db')
    _no_connect(monkeypatch, reset_demo)
    assert reset_demo.main(['--yes']) == 1


def test_wrong_confirmation_changes_nothing(monkeypatch):
    from scripts import reset_demo
    monkeypatch.setenv('SEED_PASSWORD', secrets.token_hex(6))
    monkeypatch.setattr(reset_demo, '_database_url',
                        lambda: 'postgresql://postgres.kikzdpfpprfkkbmcwnhm:pw@pooler.supabase.com:6543/postgres')
    monkeypatch.setattr('builtins.input', lambda prompt: 'yes')
    _no_connect(monkeypatch, reset_demo)
    assert reset_demo.main([]) == 1


@pytest.mark.parametrize('args', [[], ['--yes'], ['--dry-run']], ids=['prompt', 'yes', 'dry-run'])
def test_missing_seed_password_fails_before_confirmation_or_database(monkeypatch, args):
    from scripts import reset_demo
    monkeypatch.delenv('SEED_PASSWORD', raising=False)
    database_url = MagicMock(side_effect=AssertionError('database configuration accessed'))
    prompt = MagicMock(side_effect=AssertionError('confirmation prompted'))
    connect = MagicMock(side_effect=AssertionError('database connection attempted'))
    monkeypatch.setattr(reset_demo, '_database_url', database_url)
    monkeypatch.setattr('builtins.input', prompt)
    monkeypatch.setattr(reset_demo.psycopg2, 'connect', connect)

    with pytest.raises(SystemExit) as exc:
        reset_demo.main(args)

    assert exc.value.code != 0
    assert 'SEED_PASSWORD' in str(exc.value)
    database_url.assert_not_called()
    prompt.assert_not_called()
    connect.assert_not_called()


def test_help_exits_successfully_without_seed_password(monkeypatch, capsys):
    from scripts import reset_demo
    monkeypatch.delenv('SEED_PASSWORD', raising=False)
    database_url = MagicMock(side_effect=AssertionError('database configuration accessed'))
    prompt = MagicMock(side_effect=AssertionError('confirmation prompted'))
    connect = MagicMock(side_effect=AssertionError('database connection attempted'))
    monkeypatch.setattr(reset_demo, '_database_url', database_url)
    monkeypatch.setattr('builtins.input', prompt)
    monkeypatch.setattr(reset_demo.psycopg2, 'connect', connect)

    with pytest.raises(SystemExit) as exc:
        reset_demo.main(['--help'])

    assert exc.value.code == 0
    assert 'usage:' in capsys.readouterr().out
    database_url.assert_not_called()
    prompt.assert_not_called()
    connect.assert_not_called()


def test_seed_includes_max_test_as_admin():
    from scripts import seed
    assert seed.TEST_ADMIN['email'] == 'testaccstudio@gmail.com'
    assert seed.TEST_ADMIN['name'] == 'Max Test'
    assert 'admin' in seed.TEST_ADMIN_ROLE_KEYS
