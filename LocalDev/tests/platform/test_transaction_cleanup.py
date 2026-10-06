"""Transaction setup failures preserve the error and return the pool slot."""
from types import SimpleNamespace

import pytest

from api.platform.postgres import PostgresClient


def test_autocommit_setup_failure_returns_connection():
    class Connection:
        closed = False
        autocommit = property(lambda self: True)

        @autocommit.setter
        def autocommit(self, value):
            if value is False:
                raise RuntimeError("boom")

    conn = Connection()
    returned = []
    client = PostgresClient.__new__(PostgresClient)
    client._pool = SimpleNamespace(getconn=lambda: conn, putconn=returned.append)
    client.auth = None
    try:
        with pytest.raises(RuntimeError, match="^boom$"):
            with client.transaction():
                pytest.fail("setup failure must prevent entry")
    finally:
        assert returned == [conn]
