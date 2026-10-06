"""Chapter creation and CSV roster import (#74).

The CSV contract, in one place:

    required headers: name,email,phone
    optional header:  role      (a key from the `roles` catalog, e.g. treasurer)
    optional header:  consent   (yes|y|true|1 = this member signed an SMS opt-in)
    extra columns are ignored

The `consent` column carries the signed SMS opt-in the chapter collected before
import (#57). A missing column, an empty cell, or any other value leaves
`sms_consent_at` NULL — silence is never consent, and the delivery paths refuse
to text a member without it.

Import is **all-or-nothing**: the whole file is validated before a single row is
written, and any bad row returns 422 with the offending row numbers (1-based on
the file, so the header is row 1 and the first data row is row 2) and inserts
nothing. An email that already belongs to this chapter is not an error — it is
skipped and reported, so re-uploading a corrected file is safe.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from api.auth.api.auth import _issue_setup_code
from api.phone import to_e164
from api.platform.rpc import call_rpc
from api.sms_consent import is_truthy

REQUIRED_HEADERS = ("name", "email", "phone")
OPTIONAL_HEADERS = ("role", "consent")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RosterFileError(Exception):
    """Row-level validation failures. `errors` is [{row, error}, ...]."""

    def __init__(self, errors: list[dict]):
        super().__init__("roster file rejected")
        self.errors = errors


def create_chapter(
    sb,
    *,
    name,
    organization,
    school,
    officer_name,
    officer_email,
    officer_phone,
    sms_consent: bool = False,
):
    """Create the chapter, its first officer, and the officer's setup code."""
    with sb.transaction() as tx:
        result = call_rpc(
            "ch_create_chapter",
            {
                "p_name": name,
                "p_organization": organization or "",
                "p_school": school or "",
                "p_officer_name": officer_name,
                "p_officer_email": officer_email,
                "p_officer_phone": officer_phone,
            },
            sb=tx,
        )
        created = result.data
        if sms_consent:
            # Not an RPC param: a seventh argument would create a second
            # ch_create_chapter overload rather than replace 0156's. Stamping one
            # flag on a row we just created stays in this transaction.
            tx.table("members").update({"sms_consent_at": _now_iso()}).eq(
                "id", created["officer_id"]
            ).execute()
        code, expires_at = _issue_setup_code(
            tx, chapter_id=created["chapter_id"], member_id=created["officer_id"]
        )
    return {**created, "setup_code": code, "setup_code_expires_at": expires_at}


def _role_keys(sb) -> set[str]:
    return {r["key"] for r in (sb.table("roles").select("key").execute().data or [])}


def parse_roster_csv(raw: bytes, *, valid_role_keys: set[str]) -> list[dict]:
    """Validate the whole file. Returns normalized rows or raises RosterFileError."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterFileError([{"row": 0, "error": "file is not UTF-8 text"}])

    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise RosterFileError(
            [{"row": 1, "error": f"missing required column(s): {', '.join(missing)}"}]
        )

    rows: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()

    for offset, raw_row in enumerate(reader):
        row_no = offset + 2  # header is row 1
        cell = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }

        name = cell.get("name", "")
        email = cell.get("email", "").lower()
        phone = to_e164(cell.get("phone", ""))
        role_key = cell.get("role", "").lower() or None

        if not name:
            errors.append({"row": row_no, "error": "name is required"})
        if not email or "@" not in email:
            errors.append({"row": row_no, "error": "a valid email is required"})
        elif email in seen:
            errors.append({"row": row_no, "error": f"duplicate email in file: {email}"})
        else:
            seen.add(email)
        if not phone:
            errors.append({"row": row_no, "error": "phone is not a usable number (E.164 or 10-digit US)"})
        if role_key in ("admin", "president"):
            errors.append({"row": row_no, "error": "admin and president cannot be set by import"})
        elif role_key and role_key not in valid_role_keys:
            errors.append({"row": row_no, "error": f"unknown role: {role_key}"})

        rows.append({
            "name": name,
            "email": email,
            "phone": phone,
            "role_key": role_key,
            "sms_consent": is_truthy(cell.get("consent")),
        })

    if errors:
        raise RosterFileError(errors)
    if not rows:
        raise RosterFileError([{"row": 1, "error": "file has no data rows"}])
    return rows


def import_roster(sb, *, chapter_id: str, raw: bytes) -> dict:
    """Validate then import. Raises RosterFileError before writing anything."""
    rows = parse_roster_csv(raw, valid_role_keys=_role_keys(sb))

    # members.email is globally unique: an address already in THIS chapter is a
    # skip, one belonging to another chapter can never be created and is an error.
    emails = [r["email"] for r in rows]
    existing = (
        sb.table("members").select("email, chapter_id").in_("email", emails).execute().data or []
    )
    owned = {m["email"] for m in existing if str(m["chapter_id"]) == str(chapter_id)}
    foreign = {m["email"] for m in existing if str(m["chapter_id"]) != str(chapter_id)}
    if foreign:
        by_email = {r["email"]: i for i, r in enumerate(rows)}
        raise RosterFileError(
            [
                {"row": by_email[e] + 2, "error": "Member cannot be invited"}
                for e in sorted(foreign)
            ]
        )

    to_insert = [r for r in rows if r["email"] not in owned]
    created = []
    if to_insert:
        with sb.transaction() as tx:
            result = call_rpc(
                "ch_import_roster", {"p_chapter_id": chapter_id, "p_rows": to_insert}, sb=tx
            )
            for member in result.data or []:
                code, _expires = _issue_setup_code(
                    tx, chapter_id=chapter_id, member_id=member["member_id"]
                )
                created.append({"email": member["email"], "setup_code": code})

    return {
        "created": created,
        "skipped": sorted(owned),
        "created_count": len(created),
        "skipped_count": len(owned),
    }
