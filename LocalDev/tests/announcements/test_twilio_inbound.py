"""POST /api/twilio/inbound — signature check and STOP/START/HELP (#57).

DB-backed (needs TEST_DATABASE_URL / SUPABASE_DB_URL): the point of the webhook
is the row it writes, so the opt-out is asserted on `members`, not on a mock.
"""

from __future__ import annotations

import uuid

import pytest

from api.announcements.api.twilio_inbound import expected_signature
from api.config import settings

AUTH_TOKEN = "test-twilio-auth-token"
BASE_URL = "https://guildos.example.com"
PATH = "/api/twilio/inbound"


@pytest.fixture
def inbound_client(sb_client, monkeypatch):
    """TestClient on the real app with the webhook's DB + Twilio settings bound."""
    from fastapi.testclient import TestClient

    import api.announcements.api.twilio_inbound as webhook

    monkeypatch.setattr(webhook, "get_db", lambda: sb_client)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setattr(settings, "BASE_URL", BASE_URL)

    from api.index import app

    return TestClient(app)


@pytest.fixture
def post(inbound_client):
    def _post(params: dict, *, signature: str | None = None):
        sig = (
            signature
            if signature is not None
            else expected_signature(BASE_URL + PATH, params, AUTH_TOKEN)
        )
        return inbound_client.post(
            PATH, data=params, headers={"X-Twilio-Signature": sig}
        )

    return _post


@pytest.fixture
def texting_member(member_factory, cursor):
    """A consenting member holding a phone number unique to this test."""
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    member = member_factory()
    cursor.execute(
        "UPDATE members SET phone = %s, sms_consent_at = now() WHERE id = %s",
        (phone, member),
    )
    return {"id": member, "phone": phone}


@pytest.fixture
def consent_state(cursor):
    def _read(member_id: str) -> dict:
        cursor.execute(
            "SELECT sms_consent_at, sms_opted_out_at FROM members WHERE id = %s",
            (member_id,),
        )
        return dict(cursor.fetchone())

    return _read


# ── Signature ────────────────────────────────────────────────────────────────


def test_a_wrong_signature_is_rejected_and_changes_nothing(post, texting_member, consent_state):
    res = post({"From": texting_member["phone"], "Body": "STOP"}, signature="nope")

    assert res.status_code == 403
    assert consent_state(texting_member["id"])["sms_opted_out_at"] is None


def test_a_missing_auth_token_fails_closed(post, texting_member, monkeypatch, consent_state):
    """Unconfigured must never mean "anyone may opt the roster out"."""
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")

    assert post({"From": texting_member["phone"], "Body": "STOP"}).status_code == 403
    assert consent_state(texting_member["id"])["sms_opted_out_at"] is None


def test_a_valid_signature_is_accepted(post, texting_member):
    res = post({"From": texting_member["phone"], "Body": "hello there"})

    assert res.status_code == 200
    assert res.text.endswith("<Response/>")


# ── Keywords ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("word", ["STOP", "stop", "  StopAll ", "UNSUBSCRIBE", "cancel", "END", "quit"])
def test_stop_words_opt_the_number_out(post, texting_member, consent_state, word):
    assert post({"From": texting_member["phone"], "Body": word}).status_code == 200
    assert consent_state(texting_member["id"])["sms_opted_out_at"] is not None


@pytest.mark.parametrize("word", ["START", "yes", "UnStop"])
def test_start_words_clear_the_opt_out_and_record_consent(
    post, texting_member, consent_state, cursor, word
):
    cursor.execute(
        "UPDATE members SET sms_opted_out_at = now(), sms_consent_at = NULL WHERE id = %s",
        (texting_member["id"],),
    )

    assert post({"From": texting_member["phone"], "Body": word}).status_code == 200

    state = consent_state(texting_member["id"])
    assert state["sms_opted_out_at"] is None
    assert state["sms_consent_at"] is not None


def test_help_replies_with_one_line_of_twiml(post, texting_member, consent_state):
    res = post({"From": texting_member["phone"], "Body": "HELP"})

    assert res.status_code == 200
    assert "<Message>" in res.text
    assert "Reply STOP to opt out." in res.text
    assert consent_state(texting_member["id"])["sms_opted_out_at"] is None


def test_an_unrecognized_reply_is_an_empty_twiml_response(post, texting_member, consent_state):
    res = post({"From": texting_member["phone"], "Body": "who is this"})

    assert res.status_code == 200
    assert "<Message>" not in res.text
    assert consent_state(texting_member["id"])["sms_opted_out_at"] is None


def test_an_unknown_number_is_accepted_without_writing_anything(post):
    assert post({"From": "+15550000000", "Body": "STOP"}).status_code == 200
