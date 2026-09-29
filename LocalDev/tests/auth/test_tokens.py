"""Token hardening: audience/issuer/subject verification and the session epoch.

Setting a password bumps members.token_version, which must kill every token
minted before the bump while the fresh token handed back keeps the caller
logged in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

PASSWORD = "an-initial-password"
NEW_PASSWORD = "a-brand-new-password"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email: str, password: str | None = None) -> dict:
    payload = {"email": email}
    if password is not None:
        payload["password"] = password
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_set_password_bumps_epoch_and_returns_working_token(
    client, member_factory, member_email, set_password_hash, token_version
):
    """role='member' sets their own password — no officer check any more."""
    member = member_factory(role="member")
    set_password_hash(member, PASSWORD)
    old_token = _login(client, member_email(member), PASSWORD)["access_token"]
    assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 200

    before = token_version(member)
    res = client.post(
        "/api/auth/set-password", json={"password": NEW_PASSWORD}, headers=_auth(old_token)
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["message"] == "Password set successfully"
    assert token_version(member) == before + 1

    # The old session is dead, the returned one works.
    assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 403
    assert client.get("/api/auth/me", headers=_auth(body["access_token"])).status_code == 200


def test_password_is_enforced_after_being_set(
    client, member_factory, member_email, set_password_hash
):
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)
    token = _login(client, email, PASSWORD)["access_token"]
    client.post("/api/auth/set-password", json={"password": NEW_PASSWORD}, headers=_auth(token))

    assert client.post("/api/auth/login", json={"email": email}).status_code == 403
    assert _login(client, email, NEW_PASSWORD)["access_token"]


def test_login_token_carries_hardened_claims(
    client, member_factory, member_email, set_password_hash
):
    from api.config import settings

    member = member_factory(role="member")
    set_password_hash(member, PASSWORD)
    token = _login(client, member_email(member), PASSWORD)["access_token"]

    claims = pyjwt.decode(
        token, settings.JWT_SECRET, algorithms=["HS256"],
        audience="guildos", issuer="guildos",
    )
    assert claims["sub"] == member
    assert claims["ver"] == 0
    assert claims["iat"]
    # 7-day TTL, not the old 30 days.
    ttl = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=6) < ttl <= timedelta(days=7)


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"sub": "x", "iss": "guildos"}, id="missing-aud"),
        pytest.param({"sub": "x", "aud": "guildos"}, id="missing-iss"),
        pytest.param({"aud": "guildos", "iss": "guildos"}, id="missing-sub"),
        pytest.param({"sub": "x", "aud": "elsewhere", "iss": "guildos"}, id="wrong-aud"),
        pytest.param({"sub": "x", "aud": "guildos", "iss": "elsewhere"}, id="wrong-iss"),
    ],
)
def test_malformed_tokens_are_rejected(client, claims):
    """Pre-hardening tokens (no aud/iss) and forged audiences both fail decode.

    'missing-sub' previously raised a bare KeyError inside the auth shim.
    """
    from api.config import settings

    payload = dict(claims)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=1)
    token = pyjwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401


def test_stale_epoch_token_is_rejected(
    client, member_factory, member_email, set_password_hash, cursor
):
    """A token whose ver predates a token_version bump is dead on arrival."""
    member = member_factory(role="member")
    set_password_hash(member, PASSWORD)
    token = _login(client, member_email(member), PASSWORD)["access_token"]
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200

    cursor.execute("UPDATE members SET token_version = token_version + 1 WHERE id = %s", (member,))

    res = client.get("/api/auth/me", headers=_auth(token))
    assert res.status_code == 403
    assert res.json() == {"detail": "Session no longer valid, please log in again"}
