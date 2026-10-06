"""Fines route (Chunk A + GreekOS V1).

The legacy `fines` table is frozen (§7.8). Fines are unpaid_invoices(kind=fine):
- listing/summary read fine-kind invoices,
- a waive routes through the V1 void service (Treasurer only, reason REQUIRED,
  logged — decision #5),
- V1 issuance is MANUAL: GET /missed/{event_id} surfaces who missed a required
  event; POST /issue creates flat $25 fine invoices ≥24h after the event start
  (spec §5 Fines — never automatic).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.attendance.services.signals import list_unexcused_absences
from api.events.core.timing import chapter_timezone, event_start_utc
from api.treasury.services import remaining as remaining_svc
from api.platform.db import get_db
from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.services.permissions import has_permission
from api.treasury.core.fines import FINE_ISSUE_DELAY_HOURS, FLAT_FINE_CENTS
from api.treasury.services import invoices as invoice_svc

router = APIRouter()


class WaiveBody(BaseModel):
    reason: str = Field(min_length=1)


class IssueFinesBody(BaseModel):
    event_id: str
    member_ids: list[str] = Field(min_length=1)


def _load_required_event(sb, chapter_id: str, event_id: str) -> dict:
    event = (
        sb.table("events")
        .select("*")
        .eq("id", event_id)
        .eq("chapter_id", chapter_id)
        .eq("cancelled", False)
        .maybe_single()
        .execute()
    ).data
    if not event:
        raise HTTPException(404, "Event not found")
    if not event["required"]:
        raise HTTPException(422, "Event is not required — fines do not apply")
    return event


def _already_fined_ids(sb, event_id: str) -> set[str]:
    rows = (
        sb.table("unpaid_invoices")
        .select("member_id")
        .eq("source_event_id", event_id)
        .eq("kind", "fine")
        .execute()
    ).data or []
    return {str(r["member_id"]) for r in rows}


def _present_fines(sb, rows: list[dict]) -> list[dict]:
    """Map raw unpaid_invoices fine rows to the client fine shape.

    Money stays integer cents (`amount_cents`, `remaining_cents`); `description`/`created_at` are
    renamed to `reason`/`issued_at`; member and event names are stitched in
    Python — the local shim has no `unpaid_invoices` FK registered, so a
    PostgREST-style embedded select would silently drop the join locally.
    """
    if not rows:
        return []

    member_ids = {str(r["member_id"]) for r in rows if r.get("member_id")}
    event_ids = {str(r["source_event_id"]) for r in rows if r.get("source_event_id")}

    names: dict[str, str] = {}
    if member_ids:
        members = (
            sb.table("members").select("id, name").in_("id", list(member_ids)).execute()
        ).data or []
        names = {str(m["id"]): m["name"] for m in members}

    events: dict[str, dict] = {}
    if event_ids:
        ev_rows = (
            sb.table("events").select("id, title, date").in_("id", list(event_ids)).execute()
        ).data or []
        events = {str(e["id"]): e for e in ev_rows}

    remaining = remaining_svc.remaining_by_invoice(sb, rows)

    presented = []
    for r in rows:
        ev = events.get(str(r["source_event_id"])) if r.get("source_event_id") else None
        presented.append(
            {
                "id": r["id"],
                "amount_cents": int(r["amount_cents"]),
                "remaining_cents": 0
                if r["status"] == "cancelled"
                else remaining[r["id"]],
                "status": r["status"],
                "reason": r.get("description") or "",
                "issued_at": r.get("created_at"),
                "member_id": r.get("member_id"),
                "member_name": names.get(str(r.get("member_id"))),
                "event_id": r.get("source_event_id"),
                "event_title": ev["title"] if ev else None,
                "event_date": ev["date"] if ev else None,
            }
        )
    return presented


@router.get("/")
async def list_fines(status: str = None, user=Depends(get_current_user)):
    """List fine invoices, presented for the client.

    `treasury:audit:view` holders see every fine in their chapter — the same key
    that gates the fine summary; everyone else sees only their own.
    """
    sb = get_db()

    query = sb.table("unpaid_invoices").select("*").eq("kind", "fine")
    if has_permission(user, "treasury:audit:view"):
        query = query.eq("chapter_id", user["chapter_id"])
    else:
        query = query.eq("member_id", user["id"])
    if status:
        query = query.eq("status", status)

    rows = query.order("created_at", desc=True).execute().data or []
    return _present_fines(sb, rows)


@router.get("/missed/{event_id}")
async def list_missed_members(
    event_id: str,
    user=Depends(require_permission("treasury:fines:issue")),
):
    """Surface who missed a required event (unexcused) and whether already fined.

    The system proposes; humans choose to invoice (spec §5 — never automatic).
    """
    sb = get_db()
    event = _load_required_event(sb, user["chapter_id"], event_id)
    missed = list_unexcused_absences(sb, chapter_id=user["chapter_id"], event_id=event_id)
    fined = _already_fined_ids(sb, event_id)
    start = event_start_utc(event, chapter_timezone(sb, user["chapter_id"]))
    finable_at = start + timedelta(hours=FINE_ISSUE_DELAY_HOURS)
    return {
        "event_id": event_id,
        "event_start": start.isoformat(),
        "finable_at": finable_at.isoformat(),
        "finable_now": datetime.now(timezone.utc) >= finable_at,
        "flat_fine_cents": FLAT_FINE_CENTS,
        "missed": [
            {**m, "member_id": str(m["member_id"]), "already_fined": str(m["member_id"]) in fined}
            for m in missed
        ],
    }


@router.post("/issue")
async def issue_fines(
    body: IssueFinesBody,
    user=Depends(require_permission("treasury:fines:issue")),
):
    """Issue flat $25 fine invoices to selected unexcused members (≥24h gate)."""
    sb = get_db()
    event = _load_required_event(sb, user["chapter_id"], body.event_id)

    start = event_start_utc(event, chapter_timezone(sb, user["chapter_id"]))
    gate = start + timedelta(hours=FINE_ISSUE_DELAY_HOURS)
    now = datetime.now(timezone.utc)
    if now < gate:
        raise HTTPException(
            422,
            f"Fines may only be issued 24 hours after the event start "
            f"(event started {start.isoformat()}; finable from {gate.isoformat()}).",
        )

    unexcused = {
        str(m["member_id"])
        for m in list_unexcused_absences(sb, chapter_id=user["chapter_id"], event_id=body.event_id)
    }
    eligible, skipped = [], []
    for member_id in dict.fromkeys(body.member_ids):
        if member_id not in unexcused:
            skipped.append(member_id)
        else:
            eligible.append(member_id)
    result = invoice_svc.issue_event_fines(
        sb, chapter_id=user["chapter_id"], event_id=body.event_id,
        member_ids=eligible, amount_cents=FLAT_FINE_CENTS,
        description=f"Missed {event['title']} (unexcused)", actor_id=user["id"],
    )
    issued = result["issued"]
    skipped.extend(result["skipped_member_ids"])

    return {
        "event_id": body.event_id,
        "flat_fine_cents": FLAT_FINE_CENTS,
        "issued_member_ids": [str(i["member_id"]) for i in issued],
        "skipped_member_ids": skipped,
        "invoices": [invoice_svc.present_invoice_v1(i) for i in issued],
    }


@router.post("/{invoice_id}/waive")
async def waive_fine(
    invoice_id: str,
    body: WaiveBody,
    user=Depends(require_permission("treasury:invoice:void")),
):
    """Waive a fine — voids the underlying invoice (Treasurer only, reason
    required, logged; decision #5). Was officer-gated pre-V1; the permission
    change is intentional per spec."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to waive a fine")
    sb = get_db()
    try:
        return invoice_svc.void_invoice(
            sb,
            chapter_id=user["chapter_id"],
            invoice_id=invoice_id,
            actor_id=user["id"],
            reason=body.reason.strip(),
        )
    except Exception as exc:  # invoice not found / not waivable
        raise HTTPException(404, f"Fine not found or not waivable: {exc}")


@router.get("/summary")
async def fine_summary(officer=Depends(require_permission("treasury:audit:view"))):
    """Aggregate fine stats for the chapter, in cents."""
    sb = get_db()
    invoices = (
        sb.table("unpaid_invoices")
        .select("id, amount_cents, status")
        .eq("chapter_id", officer["chapter_id"])
        .eq("kind", "fine")
        .execute()
    ).data

    remaining = remaining_svc.remaining_by_invoice(
        sb, [inv for inv in invoices if inv["status"] in ("unpaid", "partially_paid")]
    )
    summary = {"total_unpaid_cents": 0, "total_paid_cents": 0, "total_cancelled_cents": 0, "count_unpaid": 0}
    for inv in invoices:
        amt = inv["amount_cents"]
        if inv["status"] in ("unpaid", "partially_paid"):
            owed = remaining[inv["id"]]
            summary["total_unpaid_cents"] += owed
            summary["count_unpaid"] += int(owed > 0)
        elif inv["status"] == "paid":
            summary["total_paid_cents"] += amt
        elif inv["status"] == "cancelled":
            summary["total_cancelled_cents"] += amt

    return summary
