import pytest


def _no_connect(monkeypatch, module):
    monkeypatch.setattr(module.psycopg2, 'connect', lambda *a, **kw: pytest.fail('connected'))


def test_guard_runs_before_connection(monkeypatch):
    from scripts import reset_demo
    monkeypatch.setattr(reset_demo, '_database_url', lambda: 'postgresql://user:pass@unknown.invalid/db')
    _no_connect(monkeypatch, reset_demo)
    assert reset_demo.main(['--yes']) == 1


def test_wrong_confirmation_changes_nothing(monkeypatch):
    from scripts import reset_demo
    monkeypatch.setattr(reset_demo, '_database_url',
                        lambda: 'postgresql://postgres.kikzdpfpprfkkbmcwnhm:pw@pooler.supabase.com:6543/postgres')
    monkeypatch.setattr('builtins.input', lambda prompt: 'yes')
    _no_connect(monkeypatch, reset_demo)
    assert reset_demo.main([]) == 1


def test_seed_includes_max_test_as_admin():
    from scripts import seed
    assert seed.TEST_ADMIN['email'] == 'testaccstudio@gmail.com'
    assert seed.TEST_ADMIN['name'] == 'Max Test'
    assert 'admin' in seed.TEST_ADMIN_ROLE_KEYS
