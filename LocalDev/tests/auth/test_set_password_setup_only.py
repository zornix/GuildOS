"""Only redeemed setup sessions may replace a password."""

import secrets

import jwt as pyjwt
import pytest

from api.config import settings


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _claims(token):
    return pyjwt.decode(
        token, settings.JWT_SECRET, algorithms=["HS256"],
        audience="guildos", issuer="guildos",
    )


def _redeem(client, member, member_email, issue_code):
    code = secrets.token_hex(4).upper()
    issue_code(member, code)
    response = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": member_email(member), "code": code},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.parametrize("has_password", [False, True], ids=["passwordless", "existing"])
def test_normal_session_cannot_set_password(
    as_member, member_factory, set_password_hash, cursor, token_version, has_password
):
    member = member_factory()
    current = secrets.token_hex(16)
    if has_password:
        set_password_hash(member, current)
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    before_hash = cursor.fetchone()["password_hash"]
    before_version = token_version(member)

    # Even knowledge of the current password cannot turn a normal session into
    # a setup session; logged-in password changes are a separate feature.
    response = as_member(member).post(
        "/api/auth/set-password",
        json={"password": secrets.token_hex(16), "current_password": current},
    )

    assert response.status_code == 403
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    assert cursor.fetchone()["password_hash"] == before_hash
    assert token_version(member) == before_version


def test_invited_member_sets_password_without_current(
    client, member_factory, member_email, issue_code, cursor
):
    member = member_factory(status="invited")
    token = _redeem(client, member, member_email, issue_code)
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    assert cursor.fetchone()["password_hash"] is None
    password = secrets.token_hex(16)

    response = client.post(
        "/api/auth/set-password", json={"password": password}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": member_email(member), "password": password}
    ).status_code == 200


def test_officer_reset_keeps_old_password_until_setup_completes(
    client, as_member, member_factory, member_email, set_password_hash, cursor, token_version
):
    officer = member_factory(role="officer")
    member = member_factory()
    old_password = secrets.token_hex(16)
    new_password = secrets.token_hex(16)
    set_password_hash(member, old_password)
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    before_hash = cursor.fetchone()["password_hash"]
    email = member_email(member)

    reset = as_member(officer).post(f"/api/auth/reset-code/{member}")
    assert reset.status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": email, "password": old_password}
    ).status_code == 200
    redeemed = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": email, "code": reset.json()["setup_code"]},
    )
    assert redeemed.status_code == 200
    token = redeemed.json()["access_token"]
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    assert cursor.fetchone()["password_hash"] == before_hash
    old_login = client.post(
        "/api/auth/login", json={"email": email, "password": old_password}
    )
    assert old_login.status_code == 200
    before_version = token_version(member)

    response = client.post(
        "/api/auth/set-password", json={"password": new_password}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert token_version(member) == before_version + 1
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 403
    assert client.get(
        "/api/auth/me", headers=_auth(old_login.json()["access_token"])
    ).status_code == 403
    assert client.post(
        "/api/auth/login", json={"email": email, "password": old_password}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": email, "password": new_password}
    ).status_code == 200


def test_redeemed_token_carries_setup_claim(
    client, member_factory, member_email, issue_code
):
    member = member_factory(status="invited")
    token = _redeem(client, member, member_email, issue_code)

    claims = _claims(token)
    assert claims["pwd_setup"] is True
    assert 0 < claims["exp"] - claims["iat"] <= 3600


def test_normal_login_token_keeps_seven_day_ttl(
    client, member_factory, member_email, set_password_hash
):
    member = member_factory()
    password = secrets.token_hex(16)
    set_password_hash(member, password)

    response = client.post(
        "/api/auth/login", json={"email": member_email(member), "password": password}
    )

    assert response.status_code == 200
    claims = _claims(response.json()["access_token"])
    assert "pwd_setup" not in claims
    assert claims["exp"] - claims["iat"] == 7 * 24 * 3600


@pytest.mark.parametrize("path", ["/api/members/", "/api/rbac/me/permissions", "/api/contribution/me"])
def test_setup_session_is_scoped_to_password_and_me(
    client, member_factory, member_email, issue_code, auth_sb, monkeypatch, path
):
    import api.members.api.members as members_api
    import api.contribution.api.records as records_api
    import api.rbac.services.permissions as permissions

    monkeypatch.setattr(members_api, "get_db", lambda: auth_sb)
    monkeypatch.setattr(records_api, "get_db", lambda: auth_sb)
    monkeypatch.setattr(permissions, "get_db", lambda: auth_sb)
    member = member_factory(status="invited")
    token = _redeem(client, member, member_email, issue_code)

    response = client.get(path, headers=_auth(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "PASSWORD_SETUP_REQUIRED"}
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


@pytest.mark.parametrize("multibyte", [False, True], ids=["ascii", "utf8"])
def test_password_over_byte_limit_is_validation_error(
    client, member_factory, member_email, issue_code, token_version, cursor, multibyte
):
    member = member_factory(status="invited")
    token = _redeem(client, member, member_email, issue_code)
    before_version = token_version(member)
    password = "é" * 37 if multibyte else secrets.token_hex(37)

    response = client.post(
        "/api/auth/set-password", json={"password": password}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert token_version(member) == before_version
    cursor.execute("SELECT password_hash FROM members WHERE id = %s", (member,))
    assert cursor.fetchone()["password_hash"] is None


def test_password_at_byte_limit_returns_normal_session(
    client, member_factory, member_email, issue_code, auth_sb, monkeypatch
):
    import api.members.api.members as members_api
    import api.contribution.api.records as records_api

    monkeypatch.setattr(members_api, "get_db", lambda: auth_sb)
    monkeypatch.setattr(records_api, "get_db", lambda: auth_sb)
    member = member_factory(status="invited")
    token = _redeem(client, member, member_email, issue_code)
    password = "é" * 36

    response = client.post(
        "/api/auth/set-password", json={"password": password}, headers=_auth(token)
    )

    assert response.status_code == 200
    normal_token = response.json()["access_token"]
    assert "pwd_setup" not in _claims(normal_token)
    assert client.get("/api/members/", headers=_auth(normal_token)).status_code == 200
    assert client.get("/api/contribution/me", headers=_auth(normal_token)).status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": member_email(member), "password": password}
    ).status_code == 200
