"""Outstanding codes and sessions are revoked at credential transitions."""

from api.auth.api.auth import _generate_setup_code
from tests.auth.test_tokens import PASSWORD, NEW_PASSWORD, _auth, _login


def test_setting_a_password_burns_unused_codes(
    client, as_member, member_factory, member_email, issue_code
):
    member = member_factory()
    email = member_email(member)
    codes = [_generate_setup_code(), _generate_setup_code()]
    for code in codes:
        issue_code(member, code)
    response = as_member(member).post(
        "/api/auth/set-password", json={"password": NEW_PASSWORD}
    )
    assert response.status_code == 200
    for code in codes:
        response = client.post(
            "/api/auth/redeem-setup-code", json={"email": email, "code": code}
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}


def test_issuing_a_reset_burns_older_codes(
    client, as_member, member_factory, member_email, issue_code
):
    officer = member_factory(role="officer")
    member = member_factory()
    email = member_email(member)
    old_code = _generate_setup_code()
    issue_code(member, old_code)
    reset = as_member(officer).post(f"/api/auth/reset-code/{member}")
    assert reset.status_code == 200
    assert client.post(
        "/api/auth/redeem-setup-code", json={"email": email, "code": old_code}
    ).status_code == 401
    redeemed = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": email, "code": reset.json()["setup_code"]},
    )
    assert redeemed.status_code == 200
    assert client.get(
        "/api/auth/me", headers=_auth(redeemed.json()["access_token"])
    ).status_code == 200


def test_redeem_revokes_earlier_sessions(
    client, as_member, member_factory, member_email, set_password_hash, issue_code
):
    officer = member_factory(role="officer")
    member = member_factory()
    email = member_email(member)
    set_password_hash(member, PASSWORD)
    reset = as_member(officer).post(f"/api/auth/reset-code/{member}")
    assert reset.status_code == 200
    # Log in after issuance: the reset's own epoch bump must not mask redemption.
    old_token = _login(client, email, PASSWORD)["access_token"]
    sibling = _generate_setup_code()
    issue_code(member, sibling)
    redeemed = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": email, "code": reset.json()["setup_code"]},
    )
    assert redeemed.status_code == 200
    response = client.get("/api/auth/me", headers=_auth(old_token))
    assert response.status_code == 403
    assert response.json() == {"detail": "Session no longer valid, please log in again"}
    assert client.get(
        "/api/auth/me", headers=_auth(redeemed.json()["access_token"])
    ).status_code == 200
    assert client.post(
        "/api/auth/redeem-setup-code", json={"email": email, "code": sibling}
    ).status_code == 401
