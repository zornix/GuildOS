"""Login is password-gated for everyone, and leaks nothing about who exists.

Pins imp-one-gate.md D2: the officer-only password rule is gone — a plain member
with a password_hash must supply it, and a plain member without one gets the
grace token. Also pins the oracle closure: unknown email and wrong password are
indistinguishable.
"""

from __future__ import annotations

PASSWORD = "correct-horse-battery"


def test_member_with_hash_must_supply_password(
    client, member_factory, member_email, set_password_hash
):
    """role='member' — the D2 point. Was: only officers were challenged."""
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)

    res = client.post("/api/auth/login", json={"email": email})

    assert res.status_code == 403
    # Shape is load-bearing: fratos/hooks/use-auth.tsx greps for the literal.
    assert res.json()["detail"]["code"] == "PASSWORD_REQUIRED"


def test_member_with_hash_rejects_wrong_password(
    client, member_factory, member_email, set_password_hash
):
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)

    res = client.post("/api/auth/login", json={"email": email, "password": "wrong"})

    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid credentials"}


def test_member_with_hash_accepts_correct_password(
    client, member_factory, member_email, set_password_hash
):
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)

    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert "password_setup_required" not in body


def test_member_without_hash_gets_grace_token(client, member_factory, member_email):
    """No hash → token plus the setup flag, for any role."""
    member = member_factory(role="member")

    res = client.post("/api/auth/login", json={"email": member_email(member)})

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["password_setup_required"] is True


def test_unknown_email_and_wrong_password_are_identical(
    client, member_factory, member_email, set_password_hash
):
    """The enumeration oracle: both responses must be byte-identical."""
    member = member_factory(role="member")
    set_password_hash(member, PASSWORD)

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": member_email(member), "password": "not-the-password"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "nobody-at-all@example.com", "password": "not-the-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.content == unknown_email.content


def test_invited_member_cannot_login_by_email(
    client, member_factory, member_email, set_status
):
    """The invite-claim hole: an unredeemed invitee is not claimable by email."""
    member = member_factory(role="member")
    email = member_email(member)
    set_status(member, "invited")

    res = client.post("/api/auth/login", json={"email": email})
    unknown = client.post("/api/auth/login", json={"email": "nobody-at-all@example.com"})

    assert res.status_code == 401
    assert res.json() == unknown.json()


def test_rate_limit_blocks_after_ten_failures(
    client, member_factory, member_email, burn_attempts
):
    member = member_factory(role="member")
    email = member_email(member)
    burn_attempts(email, 10)

    res = client.post("/api/auth/login", json={"email": email})

    assert res.status_code == 429
    assert res.json() == {"detail": "Too many attempts"}


def test_rate_limit_allows_below_threshold(
    client, member_factory, member_email, burn_attempts
):
    member = member_factory(role="member")
    email = member_email(member)
    burn_attempts(email, 9)

    res = client.post("/api/auth/login", json={"email": email})

    assert res.status_code == 200


def test_failed_login_is_recorded(client, member_factory, member_email, cursor):
    member = member_factory(role="member")
    email = member_email(member)

    client.post("/api/auth/login", json={"email": email})  # success, no hash
    client.post("/api/auth/login", json={"email": "nobody-at-all-2@example.com"})

    cursor.execute(
        "SELECT success FROM login_attempts WHERE email = %s ORDER BY created_at", (email,)
    )
    assert [r["success"] for r in cursor.fetchall()] == [True]
