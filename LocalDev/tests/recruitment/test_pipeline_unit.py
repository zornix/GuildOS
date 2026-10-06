"""Pure-logic tests for the recruitment pipeline service (no database).

The RPC itself is covered by test_stage_rpc.py; these pin the Python side:
phone normalization on the create path and the RPC-error → domain-error →
HTTP-status translation on the stage path.
"""

from __future__ import annotations

import pytest

from api.recruitment.services import pipeline as svc


# ── fakes: the two client shapes the service touches ──────────────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _Insert:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return _Result([dict(self.payload, id="00000000-0000-0000-0000-000000000001")])


class _Table:
    def __init__(self, recorder):
        self.recorder = recorder

    def insert(self, payload):
        self.recorder.append(payload)
        return _Insert(payload)


class FakeClient:
    """Records `.table(...).insert(...)` payloads; `.rpc(...)` raises or returns."""

    def __init__(self, *, rpc_error: Exception | None = None, rpc_data=None):
        self.inserts: list[dict] = []
        self.rpc_calls: list[tuple[str, dict]] = []
        self._rpc_error = rpc_error
        self._rpc_data = rpc_data

    def table(self, _name):
        return _Table(self.inserts)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        client = self

        class _Rpc:
            def execute(self):
                if client._rpc_error is not None:
                    raise client._rpc_error
                return _Result(client._rpc_data)

        return _Rpc()


def _create(client, phone):
    return svc.create_recruit(
        client,
        chapter_id="chap-1",
        name="Test PNM",
        email=None,
        phone=phone,
        notes=None,
        actor_id="member-1",
    )


# ── create_recruit: phone normalization (migration 0149's CHECK) ──────────────

def test_create_recruit_normalizes_us_ten_digit_phone():
    client = FakeClient()
    row = _create(client, "5551234567")
    assert row["phone"] == "+15551234567"
    assert client.inserts[0]["phone"] == "+15551234567"


@pytest.mark.parametrize(
    "raw", ["(555) 123-4567", "555-123-4567", " 555 123 4567 ", "+1 555 123 4567"]
)
def test_create_recruit_normalizes_common_spellings(raw):
    assert _create(FakeClient(), raw)["phone"] == "+15551234567"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_create_recruit_keeps_absent_phone_null(raw):
    client = FakeClient()
    assert _create(client, raw)["phone"] is None
    assert client.inserts[0]["phone"] is None


@pytest.mark.parametrize("raw", ["not a phone", "12345", "555111001", "5551234567 x22"])
def test_create_recruit_rejects_garbage_phone(raw):
    client = FakeClient()
    with pytest.raises(svc.InvalidPhone):
        _create(client, raw)
    assert client.inserts == []  # nothing reaches the table on a 422


def test_normalized_phone_matches_the_recruits_check_constraint():
    """0149: phone IS NULL OR phone ~ '^\\+[0-9]{8,15}$'."""
    import re

    normalized = _create(FakeClient(), "(555) 123-4567")["phone"]
    assert re.fullmatch(r"\+[0-9]{8,15}", normalized)


# ── update_stage: parameters and error translation ────────────────────────────

def test_update_stage_calls_the_rpc_with_the_documented_params():
    client = FakeClient(rpc_data=[{"id": "r1", "stage": "contacted", "old_stage": "lead"}])
    row = svc.update_stage(
        client,
        chapter_id="chap-1",
        recruit_id="r1",
        stage="contacted",
        actor_id="member-1",
        idempotency_key="key-1",
    )
    assert row["stage"] == "contacted"
    name, params = client.rpc_calls[0]
    assert name == "rc_update_recruit_stage"
    assert params == {
        "p_chapter_id": "chap-1",
        "p_recruit_id": "r1",
        "p_stage": "contacted",
        "p_actor_member_id": "member-1",
        "p_idempotency_key": "key-1",
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("recruit abc not found in chapter def", svc.RecruitNotFound),
        ("invalid recruit stage initiated", svc.InvalidStage),
        ("actor abc is not an active member of chapter def", svc.NotPermitted),
        ("deadlock detected", svc.RecruitmentError),
    ],
)
def test_rpc_failures_map_to_domain_errors(message, expected):
    client = FakeClient(rpc_error=Exception(message))
    with pytest.raises(expected):
        svc.update_stage(
            client, chapter_id="c", recruit_id="r", stage="contacted", actor_id="m"
        )


def test_domain_errors_map_to_http_statuses():
    from api.recruitment.api.pipeline import _http_error

    assert _http_error(svc.RecruitNotFound("x")).status_code == 404
    assert _http_error(svc.NotPermitted("x")).status_code == 403
    assert _http_error(svc.InvalidStage("x")).status_code == 422
    assert _http_error(svc.InvalidPhone("x")).status_code == 422
    assert _http_error(svc.RecruitmentError("x")).status_code == 400


def test_http_errors_never_echo_database_text():
    from api.recruitment.api.pipeline import _http_error

    raw = 'duplicate key value violates unique constraint "recruits_pkey"'
    err = _http_error(svc.RecruitmentError(raw))
    assert err.status_code == 400
    assert err.detail == "That change could not be saved"

    forbidden = _http_error(svc.NotPermitted("actor abc is not an active member of chapter def"))
    assert forbidden.detail == "You are not an active member of this chapter"
    bad_stage = _http_error(svc.InvalidStage("invalid recruit stage initiated"))
    assert bad_stage.detail == "That is not a valid recruitment stage"
    # Our own validation text is already safe and stays as written.
    assert _http_error(svc.InvalidPhone("Enter a valid phone number")).detail == "Enter a valid phone number"


def test_service_stage_list_matches_the_request_schema():
    """STAGES, the RPC's list, and the RecruitStageUpdate pattern are one set."""
    from api.recruitment.api.schemas import RecruitStageUpdate

    pattern = RecruitStageUpdate.model_fields["stage"].metadata[0].pattern
    assert set(pattern.strip("^$()").split("|")) == set(svc.STAGES)
