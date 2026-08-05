"""The unauthenticated /c/{short_code} page must never echo data back raw.

No DB: `validate_checkin_link` is stubbed, so these exercise the template's
escaping directly. Event title/location are officer-supplied and the page is
served to anyone holding the link, so an injection here is a stored XSS aimed
at every member who checks in.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

XSS_TITLE = "<script>alert(1)</script>'"
XSS_LOCATION = '<img src=x onerror="alert(2)">'


@pytest.fixture
def page_client(monkeypatch):
    """TestClient whose link lookup returns hostile event text."""
    import api.attendance.api.checkin_page as page

    async def _fake_validate(short_code: str):
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "event_id": "22222222-2222-2222-2222-222222222222",
            "short_code": short_code,
            "attendance_session": None,
            "events": {
                "id": "22222222-2222-2222-2222-222222222222",
                "chapter_id": "33333333-3333-3333-3333-333333333333",
                "title": XSS_TITLE,
                "date": "2026-03-01",
                "location": XSS_LOCATION,
            },
        }

    monkeypatch.setattr(page, "validate_checkin_link", _fake_validate)

    from api.index import app

    return TestClient(app)


def _script_block(body: str) -> str:
    match = re.search(r"<script>(.*)</script>", body, re.DOTALL)
    assert match, "the page must still contain exactly one script block"
    return match.group(1)


def test_page_renders(page_client):
    resp = page_client.get("/c/A7x9Kp")
    assert resp.status_code == 200


def test_title_is_html_escaped(page_client):
    body = page_client.get("/c/A7x9Kp").text
    assert "<script>alert(1)" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_location_is_html_escaped(page_client):
    body = page_client.get("/c/A7x9Kp").text
    assert "<img src=x" not in body
    assert "&lt;img src=x" in body


def test_script_element_is_not_broken_out_of(page_client):
    """A `</script>` in the title must not close the page's own script block."""
    body = page_client.get("/c/A7x9Kp").text
    assert body.count("<script>") == 1
    assert body.count("</script>") == 1
    # The single closing tag is the page's own, after the last statement.
    assert body.index("phoneInput.focus();") < body.index("</script>")


def test_js_string_context_is_escaped_not_quoted(page_client):
    """The three JS literals carry their own quotes and escape HTML syntax."""
    js = _script_block(page_client.get("/c/A7x9Kp").text)
    assert 'const SHORT_CODE = "A7x9Kp";' in js
    assert re.search(r'const API_BASE = ".*";', js)
    # The hostile title reaches JS only as \u-escaped text.
    assert "\\u003cscript\\u003ealert(1)" in js
    assert "<script>" not in js
    assert "</script>" not in js


def test_apostrophe_in_title_cannot_terminate_the_js_string(page_client):
    """The old template used single quotes, so a `'` in a title broke the page."""
    js = _script_block(page_client.get("/c/A7x9Kp").text)
    line = next(l for l in js.splitlines() if "data.event_title" in l)
    # Value is a double-quoted JSON literal; the apostrophe rides along inertly.
    assert line.rstrip().endswith(';')
    assert "'" in line  # the apostrophe survived as content...
    assert line.count('"') % 2 == 0  # ...without unbalancing the literal


def test_short_code_is_escaped_into_js(monkeypatch):
    """The short_code is path-supplied and lands in a JS string too."""
    import api.attendance.api.checkin_page as page

    async def _fake_validate(short_code: str):
        return {
            "id": "1",
            "event_id": "2",
            "short_code": short_code,
            "attendance_session": None,
            "events": {"id": "2", "chapter_id": "3", "title": "Ok", "date": "2026-03-01", "location": "Hall"},
        }

    monkeypatch.setattr(page, "validate_checkin_link", _fake_validate)
    from api.index import app

    # No "//" in the probe: Starlette redirect-normalizes duplicate slashes in
    # the path, which would mask what is being asserted here.
    hostile = '";alert(1);x'
    body = TestClient(app).get(f"/c/{quote(hostile, safe='')}").text
    # The injected quote is backslash-escaped, so the string is never terminated
    # early and `alert(1)` stays inert data rather than becoming a statement.
    assert 'const SHORT_CODE = "\\";alert(1);x";' in body
    assert 'const SHORT_CODE = "";alert(1);x' not in body


def test_expired_link_page_is_still_returned(monkeypatch):
    import api.attendance.api.checkin_page as page

    async def _none(short_code: str):
        return None

    monkeypatch.setattr(page, "validate_checkin_link", _none)
    from api.index import app

    resp = TestClient(app).get("/c/dead")
    assert resp.status_code == 410
    assert "no longer valid" in resp.text


def test_ten_digit_entry_is_preserved(page_client):
    """UX contract: 10-digit US entry, matching api.phone.to_e164's rule."""
    body = page_client.get("/c/A7x9Kp").text
    assert "slice(0, 10)" in body
    assert "getDigits().length !== 10" in body
    assert "10-digit" in body
