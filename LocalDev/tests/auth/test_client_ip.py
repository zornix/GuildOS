"""Client-IP derivation reads the rightmost-trusted X-Forwarded-For entry.

Pins imp-fix-client-ip-xff.md: proxies append the peer at the RIGHT, so the
leftmost (client-controlled) entry is never trusted. Rotating a junk leftmost
value can no longer open a fresh per-IP rate-limit bucket.
"""

from __future__ import annotations

import uuid

import pytest

from api.auth.api.auth import _ip_from_forwarded, RATE_LIMIT_MAX_PER_IP


# ── Unit: pure derivation, no DB ──────────────────────────────────────────────


def test_single_entry_returned_as_is():
    assert _ip_from_forwarded("1.2.3.4", 1) == "1.2.3.4"


def test_spoofed_chain_one_hop_takes_rightmost():
    assert _ip_from_forwarded("6.6.6.6, 9.9.9.9", 1) == "9.9.9.9"


def test_two_hops_takes_second_from_right():
    assert _ip_from_forwarded("1.1.1.1, 2.2.2.2, 3.3.3.3", 2) == "2.2.2.2"


def test_hops_larger_than_chain_takes_leftmost_no_indexerror():
    assert _ip_from_forwarded("1.1.1.1, 2.2.2.2", 5) == "1.1.1.1"


def test_whitespace_and_empty_segments_yield_none():
    assert _ip_from_forwarded(" , ,", 1) is None


def test_over_long_entry_truncated_to_64_chars():
    entry = "a" * 200
    assert _ip_from_forwarded(entry, 1) == "a" * 64


# ── End-to-end: real app via client / burn_ip_attempts fixtures ───────────────


def test_spoofed_leftmost_cannot_open_fresh_ip_bucket(
    client, member_factory, member_email, burn_ip_attempts
):
    """The defect's regression test: burn the per-IP budget against a fixed IP,
    then send a request whose leftmost XFF entry is fresh junk. Under the old
    leftmost rule this opened a new bucket and returned 200/401; now the trusted
    rightmost entry keys the bucket and the request is throttled."""
    victim_ip = f"10.0.0.{uuid.uuid4().int % 250}"
    burn_ip_attempts(victim_ip, RATE_LIMIT_MAX_PER_IP)
    member = member_factory(role="member")

    res = client.post(
        "/api/auth/login",
        json={"email": member_email(member)},
        headers={"X-Forwarded-For": f"junk-{uuid.uuid4()}, {victim_ip}"},
    )

    assert res.status_code == 429
    assert res.json() == {"detail": "Too many attempts"}


def test_recorded_ip_is_the_trusted_entry(client, cursor):
    """A failed login records the rightmost-trusted entry, not the client junk."""
    real_ip = f"10.1.0.{uuid.uuid4().int % 250}"
    email = f"ip-record-{uuid.uuid4().hex}@example.com"

    client.post(
        "/api/auth/login",
        json={"email": email},
        headers={"X-Forwarded-For": f"junk-leftmost, {real_ip}"},
    )

    cursor.execute("SELECT ip FROM login_attempts WHERE email = %s", (email,))
    assert cursor.fetchone()["ip"] == real_ip


def test_rotating_leftmost_junk_cannot_reset_redeem_bucket(client, burn_ip_attempts):
    """Both _client_ip call sites are covered: /redeem-setup-code throttles on the
    same rightmost entry even when the leftmost junk changes every request."""
    victim_ip = f"10.2.0.{uuid.uuid4().int % 250}"
    burn_ip_attempts(victim_ip, RATE_LIMIT_MAX_PER_IP)

    res = client.post(
        "/api/auth/redeem-setup-code",
        json={"email": f"redeem-{uuid.uuid4().hex}@example.com", "code": "ANYCODE1"},
        headers={"X-Forwarded-For": f"junk-{uuid.uuid4()}, {victim_ip}"},
    )

    assert res.status_code == 429
    assert res.json() == {"detail": "Too many attempts"}


def test_absent_header_falls_back_to_client_host(
    app_on_test_db, member_factory, member_email, set_password_hash
):
    """No X-Forwarded-For → fall back to request.client.host (D3 step 2): login
    still works, no None-key crash and no 500."""
    from fastapi.testclient import TestClient

    member = member_factory(role="member")
    set_password_hash(member, "fallback-password")

    bare = TestClient(app_on_test_db)  # deliberately no XFF header
    res = bare.post(
        "/api/auth/login",
        json={"email": member_email(member), "password": "fallback-password"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["access_token"]
