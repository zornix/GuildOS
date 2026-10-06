"""POST /api/chapters — bootstrap + ops secret, and the rows it writes."""

from __future__ import annotations

import pytest


def _created(res, cleanup):
    body = res.json()
    cleanup["chapters"].append(body["chapter_id"])
    return body


def test_create_chapter_writes_chapter_officer_and_role(client, create_body, cleanup, cursor):
    body = create_body()

    res = client.post("/api/chapters", json=body)

    assert res.status_code == 201, res.text
    created = _created(res, cleanup)
    assert created["officer_email"] == body["officer_email"]
    assert len(created["setup_code"]) == 8

    cursor.execute(
        "SELECT name, email, phone, role, status, password_hash FROM members WHERE id = %s",
        (created["officer_id"],),
    )
    officer = cursor.fetchone()
    assert officer["email"] == body["officer_email"]
    assert officer["phone"] == "+15551110001"
    assert (officer["role"], officer["status"]) == ("officer", "invited")
    assert officer["password_hash"] is None

    cursor.execute(
        "SELECT role_key FROM member_roles WHERE member_id = %s ORDER BY role_key",
        (created["officer_id"],),
    )
    assert [r["role_key"] for r in cursor.fetchall()] == ["admin", "officer"]

    # The code is a redeemable invite, stored only as a hash.
    cursor.execute(
        "SELECT code_hash, used_at FROM member_setup_codes WHERE member_id = %s",
        (created["officer_id"],),
    )
    code_row = cursor.fetchone()
    assert code_row["used_at"] is None
    assert created["setup_code"] not in code_row["code_hash"]


def test_creator_becomes_admin(client, create_body, cleanup, cursor):
    body = create_body()

    res = client.post("/api/chapters", json=body)

    assert res.status_code == 201, res.text
    created = _created(res, cleanup)
    cursor.execute(
        "SELECT role_key FROM member_roles WHERE member_id = %s ORDER BY role_key",
        (created["officer_id"],),
    )
    assert [r["role_key"] for r in cursor.fetchall()] == ["admin", "officer"]


def test_officer_redeems_setup_code_and_becomes_active(client, create_body, cleanup, cursor):
    body = create_body()
    created = _created(client.post("/api/chapters", json=body), cleanup)

    res = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": body["officer_email"], "code": created["setup_code"]},
    )

    assert res.status_code == 200, res.text
    assert res.json()["password_setup_required"] is True
    cursor.execute("SELECT status FROM members WHERE id = %s", (created["officer_id"],))
    assert cursor.fetchone()["status"] == "active"


@pytest.mark.parametrize("phone", [None, "", "555", "not-a-phone"])
def test_missing_or_bad_phone_is_rejected(client, create_body, phone, cursor):
    body = create_body()
    if phone is None:
        body.pop("officer_phone")
    else:
        body["officer_phone"] = phone

    res = client.post("/api/chapters", json=body)

    assert res.status_code == 422, res.text
    cursor.execute("SELECT 1 FROM chapters WHERE name = %s", (body["name"],))
    assert cursor.fetchone() is None


def test_duplicate_chapter_name_is_409_and_writes_nothing(client, create_body, cleanup, cursor):
    body = create_body()
    _created(client.post("/api/chapters", json=body), cleanup)

    second = create_body(name=body["name"].upper())
    res = client.post("/api/chapters", json=second)

    assert res.status_code == 409, res.text
    cursor.execute("SELECT 1 FROM members WHERE email = %s", (second["officer_email"],))
    assert cursor.fetchone() is None


def test_duplicate_officer_email_is_409_and_writes_nothing(client, create_body, cleanup, cursor):
    body = create_body()
    _created(client.post("/api/chapters", json=body), cleanup)

    second = create_body(officer_email=body["officer_email"])
    res = client.post("/api/chapters", json=second)

    assert res.status_code == 409, res.text
    cursor.execute("SELECT 1 FROM chapters WHERE name = %s", (second["name"],))
    assert cursor.fetchone() is None


def test_platform_secret_authorizes_and_bypasses_the_bootstrap_limit(
    client, create_body, cleanup, monkeypatch
):
    from api.config import settings

    monkeypatch.setattr(settings, "PLATFORM_SECRET", "ops-secret-value")
    headers = {"Authorization": "Bearer ops-secret-value"}

    # One more than the per-IP bootstrap ceiling; the secret path never consults it.
    from api.chapters.auth import _MAX_PER_IP

    for _ in range(_MAX_PER_IP + 1):
        res = client.post("/api/chapters", json=create_body(), headers=headers)
        assert res.status_code == 201, res.text
        _created(res, cleanup)


def test_wrong_or_unconfigured_secret_is_401(client, create_body, monkeypatch, cursor):
    from api.config import settings

    monkeypatch.setattr(settings, "PLATFORM_SECRET", "ops-secret-value")
    body = create_body()
    wrong = client.post(
        "/api/chapters", json=body, headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 401

    # Fail closed: with no secret configured, presenting one is never a match.
    monkeypatch.setattr(settings, "PLATFORM_SECRET", "")
    unset = client.post(
        "/api/chapters", json=body, headers={"Authorization": "Bearer ops-secret-value"}
    )
    assert unset.status_code == 401

    cursor.execute("SELECT 1 FROM chapters WHERE name = %s", (body["name"],))
    assert cursor.fetchone() is None


def test_bootstrap_path_is_rate_limited(client, create_body, cleanup):
    from api.chapters.auth import _MAX_PER_IP

    for _ in range(_MAX_PER_IP):
        res = client.post("/api/chapters", json=create_body())
        assert res.status_code == 201, res.text
        _created(res, cleanup)

    assert client.post("/api/chapters", json=create_body()).status_code == 429
