"""The seed entrypoint refuses unsafe passwords before any database access."""

import secrets
from unittest.mock import MagicMock

import pytest

from scripts import seed as script


@pytest.mark.parametrize("value", [None, "", "x" * 11], ids=["missing", "empty", "short"])
def test_seed_requires_password_before_database_access(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SEED_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SEED_PASSWORD", value)
    guard = MagicMock()
    connect = MagicMock(side_effect=RuntimeError("database access attempted"))
    monkeypatch.setattr(script, "require_demo", guard)
    monkeypatch.setattr(script.psycopg2, "connect", connect)

    with pytest.raises(SystemExit) as exc:
        script.seed()

    assert exc.value.code != 0
    assert "SEED_PASSWORD" in str(exc.value)
    guard.assert_not_called()
    connect.assert_not_called()


def test_seed_rows_requires_explicit_password_before_clearing_rows(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", secrets.token_hex(6))
    clear = MagicMock(side_effect=RuntimeError("database mutation attempted"))
    monkeypatch.setattr(script, "_clear_demo_seed", clear)
    cursor = MagicMock()

    with pytest.raises(TypeError, match="seed_password"):
        script.seed_rows(cursor)

    clear.assert_not_called()
    cursor.execute.assert_not_called()


def test_seed_rows_hashes_supplied_password(monkeypatch):
    value = secrets.token_hex(6)
    monkeypatch.setattr(script, "_clear_demo_seed", lambda cur: None)
    hash_password = MagicMock(return_value=b"hashed")
    monkeypatch.setattr(script.bcrypt, "hashpw", hash_password)

    script.seed_rows(MagicMock(), seed_password=value)

    assert hash_password.call_count == len(script.MEMBERS_DATA) + 1
    assert all(call.args[0] == value.encode("utf-8") for call in hash_password.call_args_list)


def test_seed_entrypoint_validates_password_once(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", secrets.token_hex(6))
    password = MagicMock(wraps=script._seed_password)
    monkeypatch.setattr(script, "_seed_password", password)
    monkeypatch.setattr(script, "require_demo", lambda *a, **kw: None)
    monkeypatch.setattr(script.psycopg2, "connect", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(script, "_clear_demo_seed", lambda cur: None)
    monkeypatch.setattr(script.bcrypt, "hashpw", MagicMock(return_value=b"hashed"))
    monkeypatch.setattr(script, "_print_summary", lambda: None)

    script.seed()

    password.assert_called_once_with()
