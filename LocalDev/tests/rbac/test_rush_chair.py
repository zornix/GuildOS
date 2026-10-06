"""Migration 0218: rush_chair replaces recruitment_chair; recruitment is gone."""

from api.rbac.db.repositories.member_roles import list_role_catalog
from api.rbac.services.permissions import has_permission


def test_role_catalog_after_0218(sb_client):
    keys = {r["key"] for r in list_role_catalog(sb_client)}
    assert "rush_chair" in keys
    assert "recruitment_chair" not in keys
    assert "new_member_educator" not in keys


def test_rush_chair_grants_only_initiatives(cursor):
    cursor.execute("SELECT permission_key FROM role_permissions WHERE role_key = 'rush_chair' ORDER BY 1")
    assert [r["permission_key"] for r in cursor.fetchall()] == [
        "calendar:initiative:create",
        "calendar:initiative:update",
    ]


def test_rush_chair_can_create_initiatives_not_events(sb_client, cursor, chapter_id, member_factory):
    member_id = member_factory()
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'rush_chair')",
        (chapter_id, member_id),
    )
    member = sb_client.table("members").select("*").eq("id", member_id).single().execute().data
    assert has_permission(member, "calendar:initiative:create", sb=sb_client)
    assert not has_permission(member, "calendar:event:create", sb=sb_client)


def test_recruitment_objects_gone(cursor):
    cursor.execute("SELECT to_regclass('public.recruits') AS t")
    assert cursor.fetchone()["t"] is None
    cursor.execute("SELECT count(*) AS n FROM pg_proc WHERE proname = 'rc_update_recruit_stage'")
    assert cursor.fetchone()["n"] == 0
    cursor.execute("SELECT count(*) AS n FROM permissions WHERE key LIKE 'recruitment:%'")
    assert cursor.fetchone()["n"] == 0
