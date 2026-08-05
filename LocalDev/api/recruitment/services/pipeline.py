"""Recruitment pipeline service.

Reads and the single-row recruit insert stay on the table builder; the stage
change is a trust-boundary mutation and goes through the `rc_update_recruit_stage`
RPC (migration 0151), which owns the tenant guard, the stage validation, the
idempotency replay, and the UPDATE_RECRUIT_STAGE audit write.

Phone numbers are normalized to E.164 through the one sanctioned converter
(`api.phone.to_e164`) before they reach the database — `recruits.phone` carries
a CHECK for that shape since migration 0149, so a raw user-typed number would
otherwise fail as a 500 at insert time instead of a 422 at the boundary.

No FastAPI imports here — routes translate the domain exceptions below into
HTTP status codes.
"""

from __future__ import annotations

from api.phone import to_e164
from api.recruitment.db.rpc import call_rpc
from api.recruitment.db.session import get_recruitment_db  # noqa: F401  (re-export)

STAGES = (
    "lead",
    "contacted",
    "attended_event",
    "bid_extended",
    "bid_accepted",
    "dropped",
)


class RecruitmentError(Exception):
    """Base class for recruitment domain failures."""


class RecruitNotFound(RecruitmentError):
    """The recruit does not exist in the caller's chapter (HTTP 404)."""


class InvalidStage(RecruitmentError):
    """The requested stage is not one of STAGES (HTTP 422)."""


class InvalidPhone(RecruitmentError):
    """A non-empty phone number that is not a usable number (HTTP 422)."""


class NotPermitted(RecruitmentError):
    """The actor is not an active member of the chapter (HTTP 403)."""


def _row(result) -> dict:
    data = result.data
    return data[0] if isinstance(data, list) else data


def _normalize_phone(raw: str | None) -> str | None:
    """E.164 or None. A non-empty value that cannot be normalized is a 422."""
    if raw is None or not str(raw).strip():
        return None
    normalized = to_e164(raw)
    if normalized is None:
        raise InvalidPhone("Enter a valid phone number")
    return normalized


def create_recruit(
    sb,
    *,
    chapter_id: str,
    name: str,
    email: str | None,
    phone: str | None,
    notes: str | None,
    actor_id: str,
) -> dict:
    return _row(
        sb.table("recruits")
        .insert(
            {
                "chapter_id": chapter_id,
                "name": name,
                "email": email,
                "phone": _normalize_phone(phone),
                "notes": notes,
                "stage": "lead",
                "created_by": actor_id,
            }
        )
        .execute()
    )


def update_stage(
    sb,
    *,
    chapter_id: str,
    recruit_id: str,
    stage: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Advance a recruit's stage through the RPC. Returns the updated recruit row.

    The row is returned with the extra `old_stage` / `new_stage` keys the RPC
    reports, so existing callers that read recruit fields keep working.
    """
    try:
        result = call_rpc(
            "rc_update_recruit_stage",
            {
                "p_chapter_id": chapter_id,
                "p_recruit_id": recruit_id,
                "p_stage": stage,
                "p_actor_member_id": actor_id,
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except RecruitmentError:
        raise
    except Exception as exc:  # RPC-side guards (the trust boundary)
        raise _rpc_error(exc) from exc

    return _row(result)


def _rpc_error(exc: Exception) -> RecruitmentError:
    """Map rc_* RPC exceptions onto domain errors (mirrors the at_* handlers)."""
    msg = str(exc)
    if "not found in chapter" in msg:
        return RecruitNotFound(msg)
    if "invalid recruit stage" in msg:
        return InvalidStage(msg)
    if "not an active member" in msg:
        return NotPermitted(msg)
    return RecruitmentError(msg)


def list_recruits(sb, *, chapter_id: str, stage: str | None = None) -> list[dict]:
    query = sb.table("recruits").select("*").eq("chapter_id", chapter_id)
    if stage:
        query = query.eq("stage", stage)
    return query.order("created_at", desc=True).execute().data or []
