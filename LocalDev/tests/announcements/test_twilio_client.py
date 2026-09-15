"""twilio_client sender form field: MessagingServiceSid vs From (issue #54).

Pure unit tests — httpx.post is mocked, no DB and no network.
"""

from __future__ import annotations

import pytest

from api.config import settings
from api.announcements.services import twilio_client


@pytest.fixture
def captured(monkeypatch):
    """Capture the form data twilio_client posts; return an OK response."""
    calls: list[dict] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"sid": "SM123"}

    def _post(url, data=None, auth=None, timeout=None):
        calls.append(data)
        return _Resp()

    monkeypatch.setattr("httpx.post", _post)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret-token")
    return calls


def test_messaging_service_sid_is_sent_instead_of_from(captured, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_MESSAGING_SERVICE_SID", "MG123")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15551234567")

    assert twilio_client.send_sms("+15559998888", "hello") == "SM123"

    assert captured == [
        {"To": "+15559998888", "Body": "hello", "MessagingServiceSid": "MG123"}
    ]


def test_from_number_is_used_when_no_messaging_service(captured, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_MESSAGING_SERVICE_SID", "")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15551234567")

    twilio_client.send_sms("+15559998888", "hello")

    assert captured == [{"To": "+15559998888", "Body": "hello", "From": "+15551234567"}]


def test_no_sender_configured_names_both_settings(captured, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_MESSAGING_SERVICE_SID", "")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "")

    with pytest.raises(RuntimeError, match="TWILIO_MESSAGING_SERVICE_SID"):
        twilio_client.send_sms("+15559998888", "hello")
    assert captured == []
