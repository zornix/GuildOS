import psycopg2
import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", ["members", "message_outbox", "unpaid_invoices", "events"])
def test_api_roles_cannot_read_tables(db_url, role, table):
    conn = psycopg2.connect(db_url, connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if not cur.fetchone():
                pytest.skip(f"role {role} does not exist on this database")
            cur.execute(f"SET LOCAL ROLE {role}")
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
    finally:
        conn.rollback()
        conn.close()
