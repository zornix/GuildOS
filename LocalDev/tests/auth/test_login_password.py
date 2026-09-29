"""Login is password-gated for everyone, and leaks nothing about who exists.

Pins imp-one-gate.md D2: the officer-only password rule is gone — a plain member
with a password_hash must supply it. Pins imp-fix-grace-login-takeover.md D1:
a passwordless active member gets NO token — email only → 403 PASSWORD_REQUIRED,
email + any password → generic 401, both byte-identical to the hashed-member
paths. Also pins the oracle closure: unknown email and wrong password are
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


def test_member_without_hash_gets_no_token_on_email_alone(
    client, member_factory, member_email, set_password_hash
):
    """Passwordless active member, email only → 403, byte-identical to the 403 a
    password-holding member gets, and no token. The takeover's door is shut."""
    passwordless = member_factory(role="member")
    hashed = member_factory(role="member")
    set_password_hash(hashed, PASSWORD)

    res = client.post("/api/auth/login", json={"email": member_email(passwordless)})
    hashed_res = client.post("/api/auth/login", json={"email": member_email(hashed)})

    assert res.status_code == 403
    assert res.content == hashed_res.content
    assert "access_token" not in res.json()


def test_member_without_hash_with_password_is_generic_401(
    client, member_factory, member_email
):
    """Passwordless active member + any password → 401, byte-identical to the
    unknown-email 401 (extends the enumeration oracle to the passwordless shape)."""
    passwordless = member_factory(role="member")

    supplied = client.post(
        "/api/auth/login",
        json={"email": member_email(passwordless), "password": "anything"},
    )
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody-at-all@example.com", "password": "anything"},
    )

    assert supplied.status_code == unknown.status_code == 401
    assert supplied.content == unknown.content
    assert "access_token" not in supplied.json()


def test_takeover_regression_attacker_cannot_set_password(
    client, member_factory, member_email, token_version
):
    """The attack's first step (email-only login → real token) is dead: no token
    is issued and the victim's token_version is untouched."""
    victim = member_factory(role="member")
    before = token_version(victim)

    res = client.post("/api/auth/login", json={"email": member_email(victim)})

    assert "access_token" not in res.json()
    assert token_version(victim) == before


def test_unknown_email_and_wrong_password_are_identical(
    client, member_factory, member_email, set_password_hash, unknown_email
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
        json={"email": unknown_email, "password": "not-the-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.content == unknown_email.content


def test_invited_member_cannot_login_by_email(
    client, member_factory, member_email, set_status, unknown_email
):
    """The invite-claim hole: an unredeemed invitee is not claimable by email."""
    member = member_factory(role="member")
    email = member_email(member)
    set_status(member, "invited")

    res = client.post("/api/auth/login", json={"email": email})
    unknown = client.post("/api/auth/login", json={"email": unknown_email})

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
    client, member_factory, member_email, set_password_hash, burn_attempts
):
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)
    burn_attempts(email, 9)

    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200


def test_failed_login_is_recorded(
    client, member_factory, member_email, set_password_hash, cursor
):
    member = member_factory(role="member")
    email = member_email(member)
    set_password_hash(member, PASSWORD)

    # Correct password → recorded success; wrong password → recorded failure.
    client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    client.post("/api/auth/login", json={"email": email, "password": "wrong"})

    cursor.execute(
        "SELECT success FROM login_attempts WHERE email = %s ORDER BY created_at", (email,)
    )
    assert [r["success"] for r in cursor.fetchall()] == [True, False]
