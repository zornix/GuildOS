"""Attendance → treasury/standing signal seam (§7).

Absence-driven FINES already flow through api/services/fine_processor.py →
FineToInvoice → tr_create_invoice; that path is authoritative and is NOT
duplicated here. This module exposes the read-side absence signal for standing
derivation (memberadmin) and announcements audiences.
"""

from __future__ import annotations


def list_unexcused_absences(sb, *, chapter_id: str, event_id: str) -> list[dict]:
    """Members of the chapter with neither a check-in nor an approved excuse.

    TODO(attendance): once standing derivation consumes this, consider a
    DB-side view to avoid the three-query fan-in (same shape as the roster
    endpoint and fine_processor use today).
    """
    members = (
        sb.table("members")
        .select("id, name")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data or []
    attendance = (
        sb.table("attendance")
        .select("member_id, checked_in")
        .eq("event_id", event_id)
        .execute()
    ).data or []
    excuses = (
        sb.table("excuses")
        .select("member_id, status")
        .eq("event_id", event_id)
        .execute()
    ).data or []

    checked_in = {a["member_id"] for a in attendance if a.get("checked_in")}
    excused = {e["member_id"] for e in excuses if e.get("status") == "approved"}

    return [
        {"member_id": m["id"], "name": m["name"], "event_id": event_id}
        for m in members
        if m["id"] not in checked_in and m["id"] not in excused
    ]
