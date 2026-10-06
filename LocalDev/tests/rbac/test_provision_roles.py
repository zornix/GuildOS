from scripts.provision_chapter import _grant_officer_role


def test_provisioned_officer_has_officer_and_admin_roles(db_conn, chapter_id, member_factory):
    officer = member_factory()
    with db_conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM roles WHERE key = 'admin'")
        assert cursor.fetchone() is not None

        assert _grant_officer_role(cursor, chapter_id=chapter_id, member_id=officer) is True

        cursor.execute(
            "SELECT role_key FROM member_roles WHERE chapter_id = %s AND member_id = %s",
            (chapter_id, officer),
        )
        assert {row[0] for row in cursor.fetchall()} == {"officer", "admin"}

        # Retrying the helper keeps exactly the same two grants.
        assert _grant_officer_role(cursor, chapter_id=chapter_id, member_id=officer) is True
        cursor.execute(
            "SELECT role_key FROM member_roles WHERE chapter_id = %s AND member_id = %s",
            (chapter_id, officer),
        )
        assert sorted(row[0] for row in cursor.fetchall()) == ["admin", "officer"]
