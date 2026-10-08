"""The pool queues for a free connection and keeps what it opened (#109)."""
from types import SimpleNamespace

import psycopg2
import pytest
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from psycopg2.pool import PoolError

from api.platform import postgres as m


class FakeConn:
    def __init__(self):
        self.closed = 0
        self.info = SimpleNamespace(transaction_status=TRANSACTION_STATUS_IDLE)

    def close(self):
        self.closed = 1


def test_waits_then_fails_and_keeps_connections_open(monkeypatch):
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: FakeConn())
    monkeypatch.setattr(m, "_POOL_WAIT_SECONDS", 0.05)
    pool = m._WaitingPool(1, 2, "dsn")

    first, second = pool.getconn(), pool.getconn()
    with pytest.raises(PoolError):
        pool.getconn()

    pool.putconn(first)
    assert pool.getconn() is first
    assert first.closed == 0 and second.closed == 0
