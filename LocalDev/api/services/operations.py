from __future__ import annotations

from fastapi import HTTPException

from api.db import get_supabase


def _coerce_rows(data):
    if not data:
        return []
    if isinstance(data, list):
        return data
    return [data]


def list_event_templates(chapter_id: str) -> list[dict]:
    sb = get_supabase()
    templates_result = (
        sb.table("event_templates")
        .select("*")
        .order("created_at")
        .execute()
    )
    templates = [
        t for t in _coerce_rows(templates_result.data)
        if t.get("chapter_id") in (None, chapter_id)
    ]
    if not templates:
        return []

    template_ids = [t["id"] for t in templates]
    roles_result = (
        sb.table("event_template_roles")
        .select("*")
        .in_("template_id", template_ids)
        .order("created_at")
        .execute()
    )
    tasks_result = (
        sb.table("event_template_tasks")
        .select("*")
        .in_("template_id", template_ids)
        .order("sort_order")
        .execute()
    )

    roles_by_template: dict[str, list[dict]] = {}
    for role in _coerce_rows(roles_result.data):
        roles_by_template.setdefault(role["template_id"], []).append(role)

    tasks_by_template: dict[str, list[dict]] = {}
    for task in _coerce_rows(tasks_result.data):
        tasks_by_template.setdefault(task["template_id"], []).append(task)

    for template in templates:
        template["roles"] = roles_by_template.get(template["id"], [])
        template["tasks"] = tasks_by_template.get(template["id"], [])

    return templates


def apply_template_to_event(*, event_id: str, template_id: str, chapter_id: str) -> dict:
    sb = get_supabase()

    event = (
        sb.table("events")
        .select("id, chapter_id, required, fine_amount")
        .eq("id", event_id)
        .eq("chapter_id", chapter_id)
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    template = (
        sb.table("event_templates")
        .select("*")
        .eq("id", template_id)
        .single()
        .execute()
    )
    if not template.data:
        raise HTTPException(404, "Template not found")
    if template.data.get("chapter_id") not in (None, chapter_id):
        raise HTTPException(403, "Template does not belong to your chapter")

    template_roles = _coerce_rows(
        sb.table("event_template_roles")
        .select("*")
        .eq("template_id", template_id)
        .order("created_at")
        .execute()
        .data
    )
    template_tasks = _coerce_rows(
        sb.table("event_template_tasks")
        .select("*")
        .eq("template_id", template_id)
        .order("sort_order")
        .execute()
        .data
    )

    existing_event_roles = _coerce_rows(
        sb.table("event_roles")
        .select("*")
        .eq("event_id", event_id)
        .execute()
        .data
    )
    event_role_by_name = {r["name"]: r for r in existing_event_roles}

    created_role_count = 0
    for role in template_roles:
        if role["name"] in event_role_by_name:
            continue
        created = (
            sb.table("event_roles")
            .insert({
                "event_id": event_id,
                "name": role["name"],
                "description": role.get("description"),
                "status": "unassigned",
            })
            .execute()
        )
        created_row = _coerce_rows(created.data)[0]
        event_role_by_name[created_row["name"]] = created_row
        created_role_count += 1

    existing_event_tasks = _coerce_rows(
        sb.table("event_tasks")
        .select("title, role_id")
        .eq("event_id", event_id)
        .execute()
        .data
    )
    existing_task_keys = {f'{t.get("role_id")}::{t.get("title")}' for t in existing_event_tasks}

    created_task_count = 0
    for task in template_tasks:
        role_name = task.get("role_name")
        role = event_role_by_name.get(role_name) if role_name else None
        role_id = role["id"] if role else None
        task_key = f"{role_id}::{task['title']}"
        if task_key in existing_task_keys:
            continue

        sb.table("event_tasks").insert({
            "event_id": event_id,
            "role_id": role_id,
            "title": task["title"],
            "description": task.get("description"),
            "due_offset_hours": task.get("due_offset_hours", 0),
            "status": "not_started",
        }).execute()
        created_task_count += 1
        existing_task_keys.add(task_key)

    if event.data.get("required") is False and template.data.get("default_required") is True:
        sb.table("events").update({"required": True}).eq("id", event_id).execute()
    if (event.data.get("fine_amount") or 0) == 0 and (template.data.get("default_fine_amount") or 0) > 0:
        sb.table("events").update({"fine_amount": template.data["default_fine_amount"]}).eq("id", event_id).execute()

    return {
        "event_id": event_id,
        "template_id": template_id,
        "template_name": template.data["name"],
        "created_roles": created_role_count,
        "created_tasks": created_task_count,
    }


def get_event_readiness(event_id: str, chapter_id: str) -> dict:
    sb = get_supabase()
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", chapter_id)
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    all_tasks = _coerce_rows(
        sb.table("event_tasks")
        .select("id, status")
        .eq("event_id", event_id)
        .execute()
        .data
    )
    total = len(all_tasks)
    done = sum(1 for t in all_tasks if t.get("status") == "done")
    readiness = 0.0 if total == 0 else round((done / total) * 100, 1)

    return {
        "event_id": event_id,
        "total_tasks": total,
        "completed_tasks": done,
        "readiness_percent": readiness,
        "status": "ready" if total > 0 and done == total else "in_progress",
    }
