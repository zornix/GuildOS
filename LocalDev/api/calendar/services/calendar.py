from __future__ import annotations

from datetime import datetime, timezone, timedelta

from api.events.services.events import list_events
from api.treasury.services.remaining import remaining_by_invoice
from api.rbac.services.permissions import get_member_permissions

def get_calendar(
    sb, 
    chapter_id: str, 
    member_id: str, 
    start: str | None = None, 
    end: str | None = None
) -> dict:
    now = datetime.now(timezone.utc)
    
    if start is None:
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = start_dt.strftime("%Y-%m-%d")
    if end is None:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=60)
        end = end_dt.strftime("%Y-%m-%d")
        
    items = []
    groups = {}
    overdue_invoices = []
    
    # --- 1. Events ---
    user = {"id": member_id, "chapter_id": chapter_id}
    events = list_events(sb, user=user)
    
    for ev in events:
        date_obj = ev.get("date")
        if not date_obj:
            continue
        date_str = str(date_obj)
        if start <= date_str <= end:
            items.append({
                "kind": "event",
                "id": ev["id"],
                "title": ev.get("title"),
                "date": date_str,
                "required": ev.get("required", False),
                "finable": ev.get("finable", False),
                "organizer_count": ev.get("organizer_count", 0),
                "organizers_needed": ev.get("organizers_needed", 0),
                "understaffed": ev.get("organizers_needed", 0) > 0,
                "group_id": ev.get("group_id"),
                "supervisor_member_id": ev.get("supervisor_member_id"),
                "event_type": ev.get("event_type"),
                # Screen 1 chips: the time/end pair renders the T-36h countdown,
                # open_job_count is the claim lure, completeness the Incomplete
                # badge. list_events already computed all of it.
                "time": str(ev["time"]) if ev.get("time") else None,
                "end_date": str(ev["end_date"]) if ev.get("end_date") else None,
                "end_time": str(ev["end_time"]) if ev.get("end_time") else None,
                "job_count": ev.get("job_count", 0),
                "open_job_count": ev.get("open_job_count", 0),
                "completeness": ev.get("completeness"),
            })
            if ev.get("group_id"):
                groups.setdefault(ev["group_id"], []).append(ev["id"])

    # --- 1b. Initiatives ---
    initiatives = (
        sb.table("initiatives")
        .select("*")
        .eq("chapter_id", chapter_id)
        .execute()
    ).data or []

    if initiatives:
        initiative_ids = [i["id"] for i in initiatives]
        chair_rows = (
            sb.table("initiative_chairs")
            .select("initiative_id, member_id")
            .in_("initiative_id", initiative_ids)
            .execute()
        ).data or []
        chairs_by_initiative: dict = {}
        for r in chair_rows:
            chairs_by_initiative.setdefault(r["initiative_id"], []).append(r["member_id"])

        for ini in initiatives:
            date_obj = ini.get("date")
            if not date_obj:
                continue
            date_str = str(date_obj)
            if start <= date_str <= end:
                items.append({
                    "kind": "initiative",
                    "initiative_id": ini["id"],
                    "title": ini.get("title"),
                    "date": date_str,
                    "time": str(ini["time"]) if ini.get("time") else None,
                    "end_date": str(ini["end_date"]) if ini.get("end_date") else None,
                    "end_time": str(ini["end_time"]) if ini.get("end_time") else None,
                    "chair_member_ids": chairs_by_initiative.get(ini["id"], []),
                })

    # --- 1c. Announcements (D15: a dated announcement is calendar presence) ---
    # Only sent, dated, unhidden, chapter-audience rows: drafts are not news,
    # the chapter calendar is not the officers-only / balance-targeted feed, and
    # a hidden row is one someone retired from the calendar via DELETE.
    announcements = (
        sb.table("announcements")
        .select("id, title, calendar_date, calendar_time, audience")
        .eq("chapter_id", chapter_id)
        .eq("status", "sent")
        .eq("audience", "chapter")
        .eq("hidden_from_calendar", False)
        .gte("calendar_date", start)
        .lte("calendar_date", end)
        .execute()
    ).data or []

    for an in announcements:
        if not an.get("calendar_date"):
            continue
        items.append({
            "kind": "announcement",
            "announcement_id": an["id"],
            "title": an.get("title"),
            "date": str(an["calendar_date"]),
            "time": str(an["calendar_time"]) if an.get("calendar_time") else None,
            "audience": an.get("audience"),
        })

    # --- 2. Invoices ---
    granted = get_member_permissions(user, sb=sb)
    # Seeing OTHER members' invoices is row-level treasury access
    # (treasury:audit:view since 0147 folded treasury_grants into the catalog),
    # or Finance Board review access.
    can_view_all_invoices = (
        "treasury:payment:verify" in granted or "treasury:audit:view" in granted
    )


    inv_query = sb.table("unpaid_invoices").select("*").eq("chapter_id", chapter_id).in_("status", ["unpaid", "partially_paid"])
    if not can_view_all_invoices:
        inv_query = inv_query.eq("member_id", member_id)
        
    invoices = inv_query.execute().data or []
    
    member_names = {}
    if can_view_all_invoices and invoices:
        member_ids = list(set(inv["member_id"] for inv in invoices if inv["member_id"] != member_id))
        if member_ids:
            members_resp = sb.table("members").select("id, name").in_("id", member_ids).execute()
            member_names = {m["id"]: m["name"] for m in (members_resp.data or [])}

    remaining = remaining_by_invoice(sb, invoices)
    for inv in invoices:
        due_at = inv.get("due_at")
        if not due_at:
            continue
            
        due_dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
            
        due_date_str = due_dt.strftime("%Y-%m-%d")
        is_overdue = due_dt < now
        
        rem = remaining[inv["id"]]
        
        if is_overdue and inv["member_id"] == member_id:
            days_overdue = (now - due_dt).days
            overdue_invoices.append({
                "invoice_id": inv["id"],
                "overdue": True,
                "days_overdue": days_overdue
            })
            
        if start <= due_date_str <= end:
            item = {
                "kind": "invoice_due",
                "invoice_id": inv["id"],
                "member_id": inv["member_id"],
                "amount_cents": int(inv["amount_cents"]),
                "remaining_cents": max(0, rem),
                "source": inv.get("kind"),
                "overdue": is_overdue,
                "date": due_date_str
            }
            if can_view_all_invoices and inv["member_id"] != member_id:
                item["member_name"] = member_names.get(inv["member_id"], "")
                
            items.append(item)
            
    # --- 3. Tasks ---
    tasks = (
        sb.table("tasks")
        .select("*")
        .eq("chapter_id", chapter_id)
        .execute()
    ).data or []
    
    for t in tasks:
        due_at = t.get("due_at")
        if not due_at:
            continue
        due_dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        due_date_str = due_dt.strftime("%Y-%m-%d")
        
        if start <= due_date_str <= end:
            items.append({
                "kind": "task_due",
                "task_id": t["id"],
                "title": t["title"],
                "status": t["status"],
                "event_id": t.get("event_id"),
                "date": due_date_str
            })
            
    items.sort(key=lambda x: x["date"])
    
    return {
        "start": start,
        "end": end,
        "items": items,
        "groups": groups,
        "overdue_invoices": overdue_invoices
    }
