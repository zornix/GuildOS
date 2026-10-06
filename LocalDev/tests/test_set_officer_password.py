"""Break-glass script guards and SQL; never connects to a database."""
import sys
from unittest.mock import MagicMock

import pytest

from scripts import set_officer_password as script


@pytest.fixture
def run_script(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("member-id", "Member Name")
    monkeypatch.setattr(script.psycopg2, "connect", lambda url: connection)
    monkeypatch.setattr(script.getpass, "getpass", lambda prompt: "test-password-value")
    monkeypatch.setattr(sys, "argv", ["set_officer_password.py", "member@example.com"])
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/demo")

    def run():
        script.main()
        return [call.args[0] for call in cursor.execute.call_args_list]

    return run


def test_refuses_a_non_demo_url_without_prod_flag(run_script, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres.unrecognised@remote.example/db")
    with pytest.raises(SystemExit):
        run_script()


def test_update_statement_bumps_token_version_and_burns_codes(run_script):
    statements = run_script()
    assert any("token_version = token_version + 1" in sql for sql in statements)
    assert any("UPDATE member_setup_codes" in sql and "used_at IS NULL" in sql for sql in statements)


def test_matches_by_email_only(run_script):
    statements = run_script()
    update = next(sql for sql in statements if "UPDATE members" in sql)
    assert "role = 'officer'" not in update


@pytest.mark.parametrize("typed", ["wrong-project", None])
def test_prod_requires_matching_typed_confirmation(monkeypatch, typed):
    monkeypatch.setattr(script, "require_prod", lambda url: None)
    monkeypatch.setattr(script, "confirmation_matches", lambda value, url: value == "expected-project")

    def confirm(prompt):
        if typed is None:
            raise EOFError
        return typed

    monkeypatch.setattr("builtins.input", confirm)
    with pytest.raises(SystemExit):
        script.guard_database("unused-url", prod=True)


def test_prod_guard_runs_before_confirmation(monkeypatch):
    def refuse(url):
        raise script.ProdGuardError("unrecognised project")

    def unexpected(prompt):
        pytest.fail("confirmation must not run before the production guard")

    monkeypatch.setattr(script, "require_prod", refuse)
    monkeypatch.setattr("builtins.input", unexpected)
    with pytest.raises(SystemExit):
        script.guard_database("unused-url", prod=True)


def test_code_burn_failure_rolls_back_password_and_session_update(run_script, monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("member-id", "Member Name")
    cursor.execute.side_effect = [None, RuntimeError("code burn failed")]
    monkeypatch.setattr(script.psycopg2, "connect", lambda url: connection)
    with pytest.raises(RuntimeError, match="code burn failed"):
        run_script()
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
