"""Evidence is identified by its bytes and limited to pending submissions."""

import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from api.treasury.services import payments as pay_svc
from tests.treasury.test_v1_helpers import api, make_user  # noqa: F401

PNG = b"\x89PNG\r\n\x1a\nproof"
JPEG = b"\xff\xd8\xffproof"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


@pytest.fixture
def submission(sb_client, chapter_id, member_id):
    return pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=1000, method="venmo",
    )


def _upload(client, submission, data, content_type="image/jpeg"):
    return client.post(
        f"/api/treasury/payments/submissions/{submission['id']}/evidence",
        json={"content_type": content_type, "data_base64": base64.b64encode(data).decode()},
        headers={"Authorization": "Bearer x"},
    )


def _evidence_rows(cursor, chapter_id, submission):
    cursor.execute(
        "SELECT content_type, data, size_bytes FROM payment_evidence "
        "WHERE chapter_id = %s AND submission_id = %s ORDER BY created_at",
        (chapter_id, submission["id"]),
    )
    return cursor.fetchall()


@pytest.mark.parametrize("content_type", ["text/plain", "image/png"])
def test_unknown_image_bytes_are_unsupported(
    api, chapter_id, member_id, submission, cursor, content_type
):
    response = _upload(api(make_user(member_id, chapter_id)), submission, b"memo", content_type)

    assert response.status_code == 415
    assert _evidence_rows(cursor, chapter_id, submission) == []


def test_png_bytes_override_client_type(api, chapter_id, member_id, submission, cursor):
    response = _upload(api(make_user(member_id, chapter_id)), submission, PNG, "image/jpeg")

    assert response.status_code == 200
    assert response.json()["content_type"] == "image/png"
    row = _evidence_rows(cursor, chapter_id, submission)[0]
    assert row["content_type"] == "image/png"
    assert bytes(row["data"]) == PNG
    assert row["size_bytes"] == len(PNG)


def test_heic_bytes_are_accepted(api, chapter_id, member_id, submission, cursor):
    response = _upload(api(make_user(member_id, chapter_id)), submission, HEIC, "text/plain")

    assert response.status_code == 200
    assert response.json()["content_type"] == "image/heic"
    row = _evidence_rows(cursor, chapter_id, submission)[0]
    assert row["content_type"] == "image/heic"
    assert bytes(row["data"]) == HEIC


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_non_pending_submission_refuses_evidence(
    api, cursor, chapter_id, member_id, submission, status
):
    cursor.execute(
        "UPDATE payment_submissions SET status = %s WHERE chapter_id = %s AND id = %s",
        (status, chapter_id, submission["id"]),
    )

    response = _upload(api(make_user(member_id, chapter_id)), submission, PNG)

    assert response.status_code == 409
    assert _evidence_rows(cursor, chapter_id, submission) == []


def test_fourth_file_is_refused(api, cursor, chapter_id, member_id, submission):
    client = api(make_user(member_id, chapter_id))
    for _ in range(3):
        assert _upload(client, submission, PNG).status_code == 200

    response = _upload(client, submission, JPEG)

    assert response.status_code == 409
    rows = _evidence_rows(cursor, chapter_id, submission)
    assert len(rows) == 3
    assert all(bytes(row["data"]) == PNG for row in rows)


def test_concurrent_uploads_cannot_exceed_three_files(sb_client, cursor, chapter_id, submission):
    def add():
        return pay_svc.add_evidence(
            sb_client, chapter_id=chapter_id, submission_id=submission["id"],
            data=PNG,
        )

    for _ in range(2):
        add()
    start = Barrier(4)

    def upload(_):
        start.wait(timeout=10)
        try:
            add()
        except ValueError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=4) as workers:
        accepted = list(workers.map(upload, range(4)))

    assert accepted.count(True) == 1
    assert len(_evidence_rows(cursor, chapter_id, submission)) == 3


def test_evidence_over_size_cap_remains_413(api, cursor, chapter_id, member_id, submission):
    oversized = PNG + b"x" * (pay_svc.MAX_EVIDENCE_BYTES + 1 - len(PNG))

    response = _upload(api(make_user(member_id, chapter_id)), submission, oversized)

    assert response.status_code == 413
    assert _evidence_rows(cursor, chapter_id, submission) == []


def test_evidence_at_size_cap_is_accepted(api, cursor, chapter_id, member_id, submission):
    data = PNG + b"x" * (pay_svc.MAX_EVIDENCE_BYTES - len(PNG))

    response = _upload(api(make_user(member_id, chapter_id)), submission, data)

    assert response.status_code == 200
    assert response.json()["size_bytes"] == pay_svc.MAX_EVIDENCE_BYTES
    assert bytes(_evidence_rows(cursor, chapter_id, submission)[0]["data"]) == data


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(PNG, "image/png", id="png"),
        pytest.param(JPEG, "image/jpeg", id="jpeg"),
        *[
            pytest.param(b"\x00\x00\x00\x18ftyp" + brand, "image/heic", id=brand.decode())
            for brand in (b"heic", b"heix", b"hevc", b"hevx")
        ],
        *[
            pytest.param(b"\x00\x00\x00\x18ftyp" + brand, "image/heif", id=brand.decode())
            for brand in (b"mif1", b"msf1")
        ],
        pytest.param(b"", None, id="empty"),
        pytest.param(b"\x89PNG", None, id="truncated-png"),
        pytest.param(b"\xff\xd8", None, id="truncated-jpeg"),
        pytest.param(b"\x00\x00\x00\x18ftyphei", None, id="truncated-brand"),
        pytest.param(b"ftypheic", None, id="wrong-offset"),
        pytest.param(b"\x00\x00\x00\x18ftypavif", None, id="unknown-brand"),
        pytest.param(b"memo", None, id="text"),
    ],
)
def test_sniff_image_type(data, expected):
    from api.treasury.core.image_sniff import sniff_image_type

    assert sniff_image_type(data) == expected
