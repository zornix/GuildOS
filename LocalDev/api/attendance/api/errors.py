"""Map attendance domain/RPC exceptions onto HTTP errors with safe messages."""
from __future__ import annotations

from fastapi import HTTPException

from api.platform.errors import public_message

# The RAISE EXCEPTION texts of at_set_attendance, at_review_excuse and
# at_checkin_self (ids are UUIDs, so \S+ stands in for them).
KNOWN_ATTENDANCE_ERRORS: dict[str, str] = {
    r"excuse reason is required when marking as excused": "Excuse reason is required when marking as excused",
    r"status must be approved or denied": "Status must be approved or denied",
    r"actor \S+ is not an active member of chapter": "Actor is not an active member of this chapter",
    r"event \S+ not found in chapter": "Event not found",
    r"member \S+ not found in chapter": "Member not found",
    r"excuse \S+ not found in chapter": "Excuse not found",
}


def _rpc_http_error(exc: Exception) -> HTTPException:
    """Map at_* RPC exceptions onto HTTP statuses (mirrors the ev_* handlers)."""
    msg = str(exc)
    if "not found" in msg:
        status_code = 404
    elif "not an active member" in msg or "not authorized" in msg:
        status_code = 403
    else:
        status_code = 400
    return HTTPException(
        status_code, public_message(exc, KNOWN_ATTENDANCE_ERRORS, "That change is not allowed")
    )
