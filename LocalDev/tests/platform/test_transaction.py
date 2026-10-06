import uuid
import pytest
from api.platform.rpc import call_rpc


def _name():
    return f"tx-test-{uuid.uuid4()}"


def _exists(sb, name):
    return bool(sb.table("chapters").select("id").eq("name", name).execute().data)


def test_commit_on_success(sb_client):
    a, b = _name(), _name()
    with sb_client.transaction() as tx:
        tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
        tx.table("chapters").insert({"name": b, "organization": "t", "school": "t"}).execute()
    assert _exists(sb_client, a) and _exists(sb_client, b)


def test_rollback_on_error(sb_client):
    a = _name()
    with pytest.raises(RuntimeError):
        with sb_client.transaction() as tx:
            tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
            raise RuntimeError("boom")
    assert not _exists(sb_client, a)


def test_uncommitted_rows_invisible_outside(sb_client):
    a = _name()
    with sb_client.transaction() as tx:
        tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
        assert _exists(tx, a)
        assert not _exists(sb_client, a)
    assert _exists(sb_client, a)


def test_rpc_joins_the_transaction(sb_client, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()
    with pytest.raises(RuntimeError):
        with sb_client.transaction() as tx:
            call_rpc("rbac_assign_role", {
                "p_chapter_id": chapter_id, "p_member_id": target,
                "p_role_key": "secretary", "p_actor_id": actor,
            }, sb=tx)
            raise RuntimeError("boom")
    rows = sb_client.table("member_roles").select("id").eq("member_id", target).execute().data
    assert rows == []


def test_swallowed_db_error_cannot_commit_silently(sb_client):
    """Postgres aborts the transaction on any failed statement. If the caller swallows that
    error, COMMIT would quietly become ROLLBACK and the caller would think it saved."""
    a = _name()
    with pytest.raises(RuntimeError, match="aborted"):
        with sb_client.transaction() as tx:
            tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
            try:
                tx.table("chapters").insert({"no_such_column": 1}).execute()
            except Exception:
                pass                                   # the swallow
    assert not _exists(sb_client, a)


def test_connection_is_clean_after_rollback(sb_client):
    with pytest.raises(RuntimeError):
        with sb_client.transaction():
            raise RuntimeError("boom")
    a = _name()
    # a plain call after a failed transaction still autocommits
    sb_client.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
    assert _exists(sb_client, a)


def test_nested_transaction_joins_the_outer_one(sb_client):
    """A helper that opens its own transaction, handed a tx client, must not commit
    the outer work early or switch the connection back to autocommit."""
    a, b = _name(), _name()
    with pytest.raises(RuntimeError):
        with sb_client.transaction() as tx:
            with tx.transaction() as inner:
                inner.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
            tx.table("chapters").insert({"name": b, "organization": "t", "school": "t"}).execute()
            raise RuntimeError("boom")
    assert not _exists(sb_client, a) and not _exists(sb_client, b)


def test_tx_client_is_dead_after_the_block(sb_client):
    """The connection is back in the pool; a leaked tx must not write into whoever has it next."""
    with sb_client.transaction() as tx:
        pending = tx.table("chapters").insert({"name": _name(), "organization": "t", "school": "t"})
    with pytest.raises(RuntimeError, match="after its block ended"):
        pending.execute()
    with pytest.raises(RuntimeError, match="after its block ended"):
        tx.table("chapters").select("id").limit(1).execute()
