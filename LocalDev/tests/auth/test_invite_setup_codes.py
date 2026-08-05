"""Invites land as 'invited' and are claimed with a single-use setup code.

Covers the invite-claim hole (an unredeemed invitee has no email-only login),
the redemption flow end to end, and the officer-assisted reset path.
"""

from __future__ import annotations

import uuid

import pytest


def _emails(n: int = 1) -> list[str]:
    return [f"invitee-{uuid.uuid4().hex[:10]}@example.com" for _ in range(n)]


def test_invite_creates_invited_members_with_codes(as_member, member_factory, cursor):
    officer = member_factory(role="officer")
    emails = _emails(2)

    res = as_member(officer).post("/api/auth/invite", json={"emails": emails})

    assert res.status_code == 200, res.text
    body = res.json()
    assert sorted(body["invited"]) == sorted(emails)
    assert body["failed"] == []

    # invited[] stays a plain string list (fratos InviteResult); codes ride alongside.
    assert sorted(c["email"] for c in body["setup_codes"]) == sorted(emails)
    assert all(len(c["setup_code"]) == 8 for c in body["setup_codes"])

    cursor.execute("SELECT status FROM members WHERE email = ANY(%s)", (emails,))
    assert {r["status"] for r in cursor.fetchall()} == {"invited"}


def test_invite_stores_only_the_hash(as_member, member_factory, cursor):
    officer = member_factory(role="officer")
    email = _emails()[0]

    res = as_member(officer).post("/api/auth/invite", json={"emails": [email]})
    code = res.json()["setup_codes"][0]["setup_code"]

    cursor.execute(
        """
        SELECT c.code_hash FROM member_setup_codes c
        JOIN members m ON m.id = c.member_id WHERE m.email = %s
        """,
        (email,),
    )
    stored = cursor.fetchone()["code_hash"]
    assert code not in stored
    assert stored.startswith("$2")


def test_invited_member_cannot_login_but_can_redeem(
    as_member, client, member_factory, cursor
):
    officer = member_factory(role="officer")
    email = _emails()[0]
    code = (
        as_member(officer)
        .post("/api/auth/invite", json={"emails": [email]})
        .json()["setup_codes"][0]["setup_code"]
    )

    assert client.post("/api/auth/login", json={"email": email}).status_code == 401

    res = client.post("/api/auth/redeem-setup-code", json={"email": email, "code": code})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["password_setup_required"] is True

    cursor.execute("SELECT status FROM members WHERE email = %s", (email,))
    assert cursor.fetchone()["status"] == "active"

    # And now the ordinary email login works.
    assert client.post("/api/auth/login", json={"email": email}).status_code == 200


def test_redeemed_token_authenticates(as_member, client, member_factory):
    officer = member_factory(role="officer")
    email = _emails()[0]
    code = (
        as_member(officer)
        .post("/api/auth/invite", json={"emails": [email]})
        .json()["setup_codes"][0]["setup_code"]
    )
    token = client.post(
        "/api/auth/redeem-setup-code", json={"email": email, "code": code}
    ).json()["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.json()["email"] == email


def test_code_is_single_use(as_member, client, member_factory):
    officer = member_factory(role="officer")
    email = _emails()[0]
    code = (
        as_member(officer)
        .post("/api/auth/invite", json={"emails": [email]})
        .json()["setup_codes"][0]["setup_code"]
    )

    first = client.post("/api/auth/redeem-setup-code", json={"email": email, "code": code})
    second = client.post("/api/auth/redeem-setup-code", json={"email": email, "code": code})

    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json() == {"detail": "Invalid credentials"}


@pytest.mark.parametrize(
    "scenario", ["wrong-code", "expired", "already-used", "unknown-email"]
)
def test_redeem_failures_are_all_the_same_401(
    client, member_factory, member_email, set_status, issue_code, scenario
):
    member = member_factory(role="member")
    email = member_email(member)
    set_status(member, "invited")

    if scenario == "wrong-code":
        issue_code(member, "RIGHTCOD")
        payload = {"email": email, "code": "WRONGCOD"}
    elif scenario == "expired":
        issue_code(member, "EXPIRED1", expires_in_days=-1)
        payload = {"email": email, "code": "EXPIRED1"}
    elif scenario == "already-used":
        issue_code(member, "USEDCODE", used=True)
        payload = {"email": email, "code": "USEDCODE"}
    else:
        payload = {"email": "nobody-at-all@example.com", "code": "ANYCODE1"}

    res = client.post("/api/auth/redeem-setup-code", json=payload)

    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid credentials"}


def test_redeem_is_rate_limited(client, member_factory, member_email, burn_attempts):
    member = member_factory(role="member")
    email = member_email(member)
    burn_attempts(email, 10)

    res = client.post("/api/auth/redeem-setup-code", json={"email": email, "code": "ANYCODE1"})

    assert res.status_code == 429
    assert res.json() == {"detail": "Too many attempts"}


def test_reset_code_issues_code_and_revokes_sessions(
    as_member, client, member_factory, member_email, token_version
):
    officer = member_factory(role="officer")
    member = member_factory(role="member")
    email = member_email(member)
    old_token = client.post("/api/auth/login", json={"email": email}).json()["access_token"]
    before = token_version(member)

    res = as_member(officer).post(f"/api/auth/reset-code/{member}")

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["setup_code"]) == 8
    assert body["expires_at"]
    assert token_version(member) == before + 1

    # The reset kills the member's existing session...
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 403
    # ...and the fresh code works.
    redeemed = client.post(
        "/api/auth/redeem-setup-code", json={"email": email, "code": body["setup_code"]}
    )
    assert redeemed.status_code == 200
    assert redeemed.json()["password_setup_required"] is True


def test_reset_code_refuses_other_chapters(as_member, member_factory, cursor):
    officer = member_factory(role="officer")
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s, 'Other Org', 'Other U') RETURNING id",
        (f"other-{uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])
    outsider = member_factory(role="member", chapter=other_chapter)

    res = as_member(officer).post(f"/api/auth/reset-code/{outsider}")

    assert res.status_code == 404
    assert res.json() == {"detail": "Member not found"}


def test_reset_code_requires_officer(as_member, member_factory):
    plain = member_factory(role="member")
    target = member_factory(role="member")

    res = as_member(plain).post(f"/api/auth/reset-code/{target}")

    assert res.status_code == 403
