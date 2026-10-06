import psycopg2
import pytest

from api.rbac.services.permissions import get_member_permissions
from api.platform.rpc import call_rpc


def _member(sb, member_id):
    return sb.table("members").select("*").eq("id", member_id).single().execute().data


def _assign(sb, chapter_id, member_id, role_key, actor_id):
    return call_rpc("rbac_assign_role", {
        "p_chapter_id": chapter_id, "p_member_id": member_id,
        "p_role_key": role_key, "p_actor_id": actor_id}, sb=sb)


def _revoke(sb, chapter_id, member_id, role_key, actor_id):
    return call_rpc("rbac_revoke_role", {
        "p_chapter_id": chapter_id, "p_member_id": member_id,
        "p_role_key": role_key, "p_actor_id": actor_id}, sb=sb)


def test_revoking_officer_removes_officer_permissions(sb_client, chapter_id, member_factory):
    boss = member_factory(role="officer")
    target = member_factory(role="officer")          # legacy column says officer
    _assign(sb_client, chapter_id, boss, "officer", boss)
    _assign(sb_client, chapter_id, target, "officer", boss)
    assert "roles:assign" in get_member_permissions(_member(sb_client, target), sb=sb_client)

    _revoke(sb_client, chapter_id, target, "officer", boss)

    m = _member(sb_client, target)
    assert "roles:assign" not in get_member_permissions(m, sb=sb_client)
    assert m["role"] == "member"


def test_legacy_column_alone_grants_nothing(sb_client, cursor, chapter_id, member_factory):
    target = member_factory()
    cursor.execute("UPDATE members SET role = 'officer' WHERE id = %s", (target,))   # column only
    perms = get_member_permissions(_member(sb_client, target), sb=sb_client)
    assert "roles:assign" not in perms


def test_member_with_no_rows_keeps_member_baseline(sb_client, chapter_id, member_factory):
    target = member_factory()
    perms = get_member_permissions(_member(sb_client, target), sb=sb_client)
    expected = {r["permission_key"] for r in
                sb_client.table("role_permissions").select("permission_key").eq("role_key", "member").execute().data}
    assert perms == expected


def _make_admin(cursor, chapter_id, member_id):
    """Test bootstrap only: a fresh test chapter has no admin to do the granting."""
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'admin')",
        (chapter_id, member_id))


def _roles(sb, member_id):
    return {r["role_key"] for r in sb.table("member_roles").select("role_key").eq("member_id", member_id).execute().data}


def test_officer_cannot_grant_admin_or_president(sb_client, chapter_id, member_factory):
    officer = member_factory(role="officer")
    _assign(sb_client, chapter_id, officer, "officer", officer)
    for role in ("admin", "president"):
        with pytest.raises(psycopg2.Error, match="rbac_ceiling"):
            _assign(sb_client, chapter_id, officer, role, officer)


def test_admin_can_hand_off_and_step_down(sb_client, cursor, chapter_id, member_factory):
    founder, heir = member_factory(role="officer"), member_factory()
    _make_admin(cursor, chapter_id, founder)
    _assign(sb_client, chapter_id, heir, "admin", founder)          # hand off
    assert _revoke(sb_client, chapter_id, founder, "admin", founder).data["revoked"] is True   # step down
    assert "admin" in _roles(sb_client, heir) and "admin" not in _roles(sb_client, founder)


def test_two_admins_may_coexist(sb_client, cursor, chapter_id, member_factory):
    a, b = member_factory(), member_factory()
    _make_admin(cursor, chapter_id, a)
    _assign(sb_client, chapter_id, b, "admin", a)
    assert "admin" in _roles(sb_client, a) and "admin" in _roles(sb_client, b)


def test_non_admin_cannot_revoke_admin(sb_client, cursor, chapter_id, member_factory):
    admin, officer = member_factory(), member_factory(role="officer")
    _make_admin(cursor, chapter_id, admin)
    _assign(sb_client, chapter_id, officer, "officer", admin)
    with pytest.raises(psycopg2.Error, match="rbac_ceiling"):
        _revoke(sb_client, chapter_id, admin, "admin", officer)


def test_officer_can_still_grant_ordinary_roles(sb_client, chapter_id, member_factory):
    officer, target = member_factory(role="officer"), member_factory()
    _assign(sb_client, chapter_id, officer, "officer", officer)
    assert _assign(sb_client, chapter_id, target, "treasurer", officer).data["role_key"] == "treasurer"


def test_last_admin_cannot_step_down(sb_client, cursor, chapter_id, member_factory):
    only = member_factory()
    _make_admin(cursor, chapter_id, only)
    with pytest.raises(psycopg2.Error, match="rbac_last_admin"):
        _revoke(sb_client, chapter_id, only, "admin", only)
    assert "admin" in _roles(sb_client, only)


def test_revoking_a_role_not_held_is_still_a_noop(sb_client, cursor, chapter_id, member_factory):
    only = member_factory()
    _make_admin(cursor, chapter_id, only)
    assert _revoke(sb_client, chapter_id, only, "secretary", only).data["revoked"] is False


def test_an_inactive_admin_does_not_count_as_the_remaining_admin(sb_client, cursor, chapter_id, member_factory):
    a, b = member_factory(), member_factory()
    _make_admin(cursor, chapter_id, a)
    _make_admin(cursor, chapter_id, b)
    cursor.execute("UPDATE members SET status = 'inactive' WHERE id = %s", (b,))
    with pytest.raises(psycopg2.Error, match="rbac_last_admin"):
        _revoke(sb_client, chapter_id, a, "admin", a)


def test_officer_grant_of_admin_is_403(sb_client, chapter_id, member_factory, monkeypatch):
    import api.rbac.api.roles as roles_api
    import api.rbac.services.permissions as perm
    from fastapi.testclient import TestClient

    from api.dependencies import get_current_user
    from api.index import app

    monkeypatch.setattr(roles_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(perm, "get_db", lambda: sb_client)

    officer = member_factory(role="officer")
    _assign(sb_client, chapter_id, officer, "officer", officer)

    async def _user():
        return _member(sb_client, officer)

    app.dependency_overrides[get_current_user] = _user
    try:
        res = TestClient(app).post(
            f"/api/rbac/members/{officer}/roles", json={"role_key": "admin"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert res.status_code == 403
    assert res.json()["detail"] == "Only an admin can grant or revoke that role"


def test_admin_revoke_takes_the_chapter_lock(db_url, cursor, chapter_id, member_factory):
    """Two concurrent step-downs must serialize, or both could pass the last-admin check."""
    a, b = member_factory(), member_factory()
    _make_admin(cursor, chapter_id, a)
    _make_admin(cursor, chapter_id, b)

    hold = psycopg2.connect(db_url)
    hold.autocommit = False
    try:
        with hold.cursor() as hcur:
            # NO KEY UPDATE: conflicts with the function's FOR UPDATE but not with
            # the audit insert's FK check, so the test fails if the lock is removed.
            hcur.execute("SELECT 1 FROM chapters WHERE id = %s FOR NO KEY UPDATE", (chapter_id,))
        probe = psycopg2.connect(db_url)
        try:
            probe.autocommit = False
            with probe.cursor() as pcur:
                pcur.execute("SET LOCAL lock_timeout = '500ms'")
                with pytest.raises(psycopg2.errors.LockNotAvailable):
                    pcur.execute("SELECT rbac_revoke_role(%s, %s, 'admin', %s, NULL)", (chapter_id, a, a))
        finally:
            probe.rollback()
            probe.close()
    finally:
        hold.rollback()
        hold.close()
