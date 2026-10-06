"""POST /api/chapters/{id}/roster — all-or-nothing CSV import."""

from __future__ import annotations

import pytest


@pytest.fixture
def officer(member_factory):
    return member_factory(role="officer")


@pytest.fixture
def upload(as_member, chapter_id, officer):
    def _post(raw: bytes, *, chapter: str | None = None, member: str | None = None):
        return as_member(member or officer).post(
            f"/api/chapters/{chapter or chapter_id}/roster",
            files={"file": ("roster.csv", raw, "text/csv")},
        )

    return _post


def _row(unique, phone="5551110001", role=""):
    email = f"rost-{unique()}@example.com"
    return f"Ann Smith,{email},{phone},{role}".rstrip(","), email


def test_all_good_rows_are_imported_as_invited_members(
    upload, csv_bytes, unique, cleanup, cursor, chapter_id
):
    line_a, email_a = _row(unique)
    line_b, email_b = _row(unique, phone="+447700900123")
    cleanup["emails"] += [email_a, email_b]

    res = upload(csv_bytes([line_a, line_b]))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created_count"] == 2
    assert body["skipped"] == []
    assert sorted(c["email"] for c in body["created"]) == sorted([email_a, email_b])
    assert all(len(c["setup_code"]) == 8 for c in body["created"])

    cursor.execute(
        "SELECT email, phone, role, status FROM members WHERE email = ANY(%s) ORDER BY email",
        ([email_a, email_b],),
    )
    rows = cursor.fetchall()
    assert {r["status"] for r in rows} == {"invited"}
    assert {r["role"] for r in rows} == {"member"}
    assert {r["phone"] for r in rows} == {"+15551110001", "+447700900123"}

    # Every imported member has a redeemable setup code, like an invitee.
    cursor.execute(
        "SELECT count(*) AS n FROM member_setup_codes c JOIN members m ON m.id = c.member_id "
        "WHERE m.email = ANY(%s)",
        ([email_a, email_b],),
    )
    assert cursor.fetchone()["n"] == 2


def test_optional_role_column_grants_the_catalog_role(
    upload, csv_bytes, unique, cleanup, cursor
):
    line, email = _row(unique, role="treasurer")
    cleanup["emails"].append(email)

    res = upload(csv_bytes([line], header="name,email,phone,role"))

    assert res.status_code == 200, res.text
    cursor.execute(
        "SELECT r.role_key FROM member_roles r JOIN members m ON m.id = r.member_id "
        "WHERE m.email = %s",
        (email,),
    )
    assert [r["role_key"] for r in cursor.fetchall()] == ["treasurer"]


def test_non_officer_role_keeps_legacy_column_member(
    upload, csv_bytes, unique, cleanup, cursor, sb_client
):
    from api.rbac.services.permissions import get_member_permissions

    line_tv, email_tv = _row(unique, role="treasury_viewer")
    line_sc, email_sc = _row(unique, role="social_chair")
    cleanup["emails"] += [email_tv, email_sc]

    res = upload(csv_bytes([line_tv, line_sc], header="name,email,phone,role"))

    assert res.status_code == 200, res.text
    for email, key in ((email_tv, "treasury_viewer"), (email_sc, "social_chair")):
        cursor.execute("SELECT id, role FROM members WHERE email = %s", (email,))
        row = cursor.fetchone()
        assert row["role"] == "member"
        cursor.execute(
            "SELECT role_key FROM member_roles WHERE member_id = %s", (row["id"],)
        )
        assert [r["role_key"] for r in cursor.fetchall()] == [key]
    member = (
        sb_client.table("members").select("*").eq("email", email_tv).single().execute().data
    )
    assert "roles:assign" not in get_member_permissions(member, sb=sb_client)


def test_officer_csv_role_marks_the_legacy_column(
    upload, csv_bytes, unique, cleanup, cursor
):
    line, email = _row(unique, role="officer")
    cleanup["emails"].append(email)

    res = upload(csv_bytes([line], header="name,email,phone,role"))

    assert res.status_code == 200, res.text
    cursor.execute("SELECT id, role FROM members WHERE email = %s", (email,))
    row = cursor.fetchone()
    assert row["role"] == "officer"
    cursor.execute("SELECT role_key FROM member_roles WHERE member_id = %s", (row["id"],))
    assert [r["role_key"] for r in cursor.fetchall()] == ["officer"]


def test_import_rejects_top_roles(upload, csv_bytes, unique, cursor):
    line, email = _row(unique, role="admin")

    res = upload(csv_bytes([line], header="name,email,phone,role"))

    assert res.status_code == 422, res.text
    assert res.json()["detail"]["errors"][0]["error"] == "admin and president cannot be set by import"
    cursor.execute("SELECT 1 FROM members WHERE email = %s", (email,))
    assert cursor.fetchone() is None


@pytest.mark.parametrize("cell", ["yes", "Y", "TRUE", "1"])
def test_a_truthy_consent_column_records_sms_consent(
    upload, csv_bytes, unique, cleanup, cursor, cell
):
    line, email = _row(unique)
    cleanup["emails"].append(email)

    res = upload(csv_bytes([f"{line},{cell}"], header="name,email,phone,consent"))

    assert res.status_code == 200, res.text
    cursor.execute(
        "SELECT sms_consent_at, sms_opted_out_at FROM members WHERE email = %s", (email,)
    )
    row = cursor.fetchone()
    assert row["sms_consent_at"] is not None
    assert row["sms_opted_out_at"] is None


@pytest.mark.parametrize("header,suffix", [("name,email,phone,consent", ",no"), ("name,email,phone", "")])
def test_a_falsy_or_missing_consent_column_leaves_consent_unset(
    upload, csv_bytes, unique, cleanup, cursor, header, suffix
):
    """Silence is never consent (#57)."""
    line, email = _row(unique)
    cleanup["emails"].append(email)

    res = upload(csv_bytes([f"{line}{suffix}"], header=header))

    assert res.status_code == 200, res.text
    cursor.execute("SELECT sms_consent_at FROM members WHERE email = %s", (email,))
    assert cursor.fetchone()["sms_consent_at"] is None


def test_one_bad_row_rejects_the_whole_file_and_inserts_nothing(
    upload, csv_bytes, unique, cursor
):
    good_line, good_email = _row(unique)
    bad_line, bad_email = _row(unique, phone="123")

    res = upload(csv_bytes([good_line, bad_line]))

    assert res.status_code == 422, res.text
    errors = res.json()["detail"]["errors"]
    assert [e["row"] for e in errors] == [3]
    assert "phone" in errors[0]["error"]

    cursor.execute("SELECT 1 FROM members WHERE email = ANY(%s)", ([good_email, bad_email],))
    assert cursor.fetchall() == []


def test_unknown_role_is_a_row_error(upload, csv_bytes, unique, cursor):
    line, email = _row(unique, role="grand-poobah")

    res = upload(csv_bytes([line], header="name,email,phone,role"))

    assert res.status_code == 422, res.text
    assert res.json()["detail"]["errors"][0]["row"] == 2
    cursor.execute("SELECT 1 FROM members WHERE email = %s", (email,))
    assert cursor.fetchone() is None


def test_missing_required_column_is_rejected(upload, csv_bytes, unique):
    line, _ = _row(unique)

    res = upload(csv_bytes([line.rsplit(",", 1)[0]], header="name,email"))

    assert res.status_code == 422, res.text
    assert "phone" in res.json()["detail"]["errors"][0]["error"]


def test_existing_email_in_chapter_is_skipped_and_reported(
    upload, csv_bytes, unique, cleanup, cursor, member_factory, member_email
):
    existing = member_email(member_factory())
    new_line, new_email = _row(unique)
    cleanup["emails"].append(new_email)

    res = upload(csv_bytes([f"Already Here,{existing},5551110002", new_line]))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skipped"] == [existing]
    assert [c["email"] for c in body["created"]] == [new_email]

    cursor.execute("SELECT count(*) AS n FROM members WHERE email = %s", (existing,))
    assert cursor.fetchone()["n"] == 1


def test_another_chapters_roster_is_not_reachable(upload, csv_bytes, unique, chapter_id):
    line, _ = _row(unique)

    res = upload(csv_bytes([line]), chapter="00000000-0000-0000-0000-000000000000")

    assert res.status_code == 404


def test_an_oversized_file_is_rejected(upload):
    """413 before the whole upload is buffered (the read is bounded)."""
    from api.chapters.api.chapters import MAX_ROSTER_BYTES

    res = upload(b"x" * (MAX_ROSTER_BYTES + 1))

    assert res.status_code == 413, res.text


def test_plain_member_cannot_import(upload, csv_bytes, unique, member_factory):
    line, _ = _row(unique)

    res = upload(csv_bytes([line]), member=member_factory(role="member"))

    assert res.status_code == 403


def test_roster_import_rolls_back_when_a_code_cannot_be_issued(
    auth_sb, chapter_id, csv_bytes, unique, cleanup, cursor, monkeypatch
):
    from api.chapters.services import onboarding

    lines, emails = zip(*[_row(unique) for _ in range(5)])
    cleanup["emails"] += list(emails)
    real_issue = onboarding._issue_setup_code
    calls = 0

    def fail_third(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("code issuance unavailable")
        return real_issue(*args, **kwargs)

    monkeypatch.setattr(onboarding, "_issue_setup_code", fail_third)
    with pytest.raises(RuntimeError, match="code issuance unavailable"):
        onboarding.import_roster(auth_sb, chapter_id=chapter_id, raw=csv_bytes(lines))
    cursor.execute(
        "SELECT id FROM members WHERE chapter_id = %s AND email = ANY(%s)",
        (chapter_id, list(emails)),
    )
    assert cursor.fetchall() == []
    cursor.execute(
        "SELECT id FROM message_outbox WHERE chapter_id = %s AND event_type = 'SETUP_CODE'",
        (chapter_id,),
    )
    assert cursor.fetchall() == []



def test_foreign_chapter_email_rejection_is_generic(monkeypatch):
    from types import SimpleNamespace
    from api.chapters.services import onboarding
    monkeypatch.setattr(onboarding, "_role_keys", lambda sb: set())
    class MembersQuery:
        def select(self, *args):
            return self
        def in_(self, *args):
            return self
        def execute(self):
            return SimpleNamespace(data=[{"email": "foreign@example.com", "chapter_id": "other"}])
    sb = SimpleNamespace(table=lambda name: MembersQuery())
    raw = b"name,email,phone\nMember,foreign@example.com,5551110001\n"
    with pytest.raises(onboarding.RosterFileError) as caught:
        onboarding.import_roster(sb, chapter_id="chapter", raw=raw)
    assert caught.value.errors == [{"row": 2, "error": "Member cannot be invited"}]
