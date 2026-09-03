# GreekOS V1 Wave 2 — Calendar + Instrumentation Prompt

Use with **Gemini 3.1 Pro** (orchestrator) and **Gemini 3.5 Flash** subagents.

---

## Main prompt (Gemini 3.1 Pro)

```
You are implementing GreekOS V1 Wave 2: the calendar aggregation VIEW and usage instrumentation. Work in /home/mshi/GuildOS/LocalDev. The prior session wrote tests and migration but never built the API — your job is to make all 24 tests in tests/calendar_view/ pass and wire routers into api/index.py.

MODEL STRATEGY
- You (Gemini 3.1 Pro): orchestrate, implement calendar service logic, review integration, fix failures.
- Delegate to Gemini 3.5 Flash subagents for bounded, parallel tasks:
  1. Subagent A — scaffold api/instrumentation/ (package layout, db/session, services/usage.py, api/usage.py, api/router.py, api/schemas.py)
  2. Subagent B — scaffold api/calendar/ package shell (auth.py, db/session.py, api/router.py, api/schemas.py, get_calendar_db hook)
  3. Subagent C — wire api/index.py mounts + run verification loop after main implementation lands
Keep subagent prompts tight: file list, patterns to copy, acceptance criteria. Merge their output yourself; do not let subagents edit unrelated domains.

VERIFICATION COMMAND (run after every meaningful change)
cd /home/mshi/GuildOS/LocalDev && TEST_DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos python3 -m pytest tests/calendar_view/ -q

Full suite when calendar_view is green:
TEST_DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos python3 -m pytest -q

Current baseline: 301 passed, 24 errors — all ModuleNotFoundError: No module named 'api.calendar'.

CONTEXT
- Spec: SPEC.md §2 (calendar is a VIEW, not an entity)
- Build plan: BUILD_PLAN.md Wave 2
- Migration 0140_usage_events.sql already applied (usage_events table, append-only)
- tests/calendar/ was renamed to tests/calendar_view/ to avoid stdlib calendar conflict — do NOT rename back
- Wave 1 domains (events, tasks, treasury, announcements) are done and passing — do not refactor them

ARCHITECTURE (mandatory — match existing domains)
Canonical shape per docs/services/README.md (copy api/announcements/ or api/events/):
  api/<domain>/
    __init__.py
    api/router.py, <resource>.py, schemas.py
    services/<logic>.py   # no FastAPI imports
    db/session.py         # get_<domain>_db() → get_supabase_admin()
    auth.py               # permission constants if needed

Calendar is READ-ONLY aggregation — no new calendar tables, no plpgsql RPCs for calendar itself.
Instrumentation writes usage_events (append-only); calendar view fires calendar:viewed via instrumentation service (fire-and-forget).

TEST HARNESS CONTRACT (tests/calendar_view/conftest.py)
The harness expects these import paths — implement exactly:
  import api.calendar.api.calendar as calendar_api      # must expose get_calendar_db
  from api.calendar.api.router import router as calendar_router
  import api.instrumentation.api.usage as usage_api       # must expose get_usage_db
  from api.instrumentation.api.router import router as usage_router

Mounts in harness (mirror in api/index.py):
  /api/calendar  → calendar_router
  /api/usage     → usage_router

WHAT TO BUILD

### 1. api/calendar/ — GET /api/calendar

Query params: start (date), end (date). Default range: 1st of current month → +60 days.
Return 422 if start > end.

Response shape:
{
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "items": [ ... sorted by "date" ascending ... ],
  "groups": { "<group_id>": ["<event_id>", ...] },
  "overdue_invoices": [ ... caller's OWN overdue open invoices only ... ]
}

Item kinds (each has "kind" + "date"):

**kind: "event"** — from events table, audience-filtered, date in [start, end]
Fields tests assert: id, title, date, required, finable, organizer_count, organizers_needed,
understaffed (= organizers_needed > 0), group_id, supervisor_member_id, event_type
Reuse visibility logic from api/events/services/events.py (_can_view / list_events patterns).
Reuse organizer math from api/events/core/rules.py (organizers_needed, ORGANIZER_SOFT_MIN=2).
Build groups map: for each event with group_id, groups[group_id] = list of event ids in that group.

**kind: "invoice_due"** — open invoices (status unpaid|partially_paid) with due_at in range
Fields: invoice_id, member_id, amount_cents, remaining_cents, source (map DB kind → dues|fine|manual),
overdue (due_at < now), date (due_at as YYYY-MM-DD), kind="invoice_due"
Visibility:
  - Default: caller sees only their own invoices
  - Also sees others' if: has_permission(treasury:payment:verify) OR treasury_grants capability treasury:read
  - For others' invoices include member_name
  - Paid invoices never appear
Reuse remaining_cents math from api/treasury/services/member_dashboard.py (_direct_paid_cents, _net_allocated_cents)

**kind: "task_due"** — tasks with due_at in range, any chapter member can see
Fields: task_id, title, status, event_id, date (due date), kind="task_due"
Tasks without due_at excluded.

**Decision #3 — overdue invoices:**
- overdue_invoices array: caller's OWN open overdue invoices ALWAYS included, even if due_at outside [start, end]
- If overdue invoice's due_at IS in range, also appear in items as invoice_due with overdue=true
- overdue_invoices entries need: invoice_id, overdue=true, days_overdue (int)
- Treasurers viewing others' invoices: inline invoice_due items OK, but overdue_invoices stays [] (own only)

**Instrumentation hook:** after building response, fire-and-forget track(chapter_id, member_id, "calendar:viewed").
If track() raises, swallow — must not break 200 response (see test_calendar_survives_tracking_failure).

### 2. api/instrumentation/

**POST /api/usage/track** — body: { event_name: str, metadata?: dict }
- Insert into usage_events (chapter_id, member_id, event_name, metadata)
- Clamp event_name to 120 chars; if metadata JSON too large, truncate and set metadata._truncated=true
- Return {"ok": true}
- 422 if event_name missing

**GET /api/usage/summary?days=30** — officer-gated
- Require calendar:officer:view (legacy role "officer" maps to this in tests)
- Return { days, counts: { event_name: count }, total }
- Count usage_events for chapter in last N days

services/usage.py: track(), summary(), get_usage_db in db/session.py

### 3. api/index.py
Add:
  from api.calendar.api.router import router as calendar_router
  from api.instrumentation.api.router import router as usage_router
  app.include_router(calendar_router, prefix="/api/calendar", tags=["Calendar"])
  app.include_router(usage_router, prefix="/api/usage", tags=["Usage"])

FILES TO READ FIRST (do not guess)
- tests/calendar_view/test_calendar_view.py       — full behavioral contract
- tests/calendar_view/test_usage_instrumentation.py
- tests/calendar_view/conftest.py
- api/events/services/events.py                   — visibility + organizer decoration
- api/events/core/rules.py
- api/treasury/services/member_dashboard.py       — invoice remaining/overdue
- api/announcements/                              — package layout template
- migrations/0140_usage_events.sql
- api/rbac/services/permissions.py                  — has_permission, get_member_permissions

IMPLEMENTATION NOTES
- calendar.api.calendar.get_calendar_db() and instrumentation.api.usage.get_usage_db() must exist for test monkeypatching
- Use api.rbac.services.permissions.has_permission for treasury:payment:verify
- Use treasury_grants table for treasury:read (see tests/calendar_view/conftest.py grant_treasury_read)
- Invoice source: DB column is `kind` (dues|fine|manual) — expose as `source` in calendar items
- event_type on calendar items: resolve from event_types join or legacy event_type text field
- Sort items by date string ascending
- Default start/end: first day of current month, end = start + 60 days; echo resolved start/end in response

DO NOT
- Create new DB tables (0140 is sufficient)
- Edit applied migrations
- Refactor events/tasks/treasury/announcements domains
- Rename tests/calendar_view back to tests/calendar
- Add frontend work
- Use float for money — integer cents only

DEFINITION OF DONE
1. pytest tests/calendar_view/ -q → 24 passed, 0 errors
2. Full pytest -q → 325 passed (or current total with 0 failures)
3. api/index.py mounts both routers
4. Minimal diff — only api/calendar/, api/instrumentation/, api/index.py changes unless a tiny shared helper extraction is unavoidable

Start by reading the test files, then launch Flash subagents for package scaffolding while you implement services/calendar.py aggregation logic.
```

---

## Flash subagent prompts

### Flash A — instrumentation scaffold

```
In /home/mshi/GuildOS/LocalDev, create api/instrumentation/ following api/announcements/ layout.
Implement POST /api/usage/track and GET /api/usage/summary per tests/calendar_view/test_usage_instrumentation.py.
Expose get_usage_db in api/instrumentation/api/usage.py for test monkeypatching.
Use usage_events table from migrations/0140_usage_events.sql. Officer gate: calendar:officer:view.
Return only the files you created.
```

### Flash B — calendar package shell

```
In /home/mshi/GuildOS/LocalDev, create api/calendar/ package shell matching api/announcements/:
__init__.py, auth.py, db/session.py (get_calendar_db), api/router.py, api/schemas.py, api/calendar.py stub.
api/calendar.py must export get_calendar_db and a GET "" route delegating to services/calendar.py (stub ok).
Do not implement aggregation logic — just the package structure tests can import.
```

### Flash C — verify loop

```
After calendar implementation lands in /home/mshi/GuildOS/LocalDev, run:
TEST_DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos python3 -m pytest tests/calendar_view/ -q
Report pass/fail counts and first failure traceback if any.
```

---

## Status at time of writing (2026-06-12)

| Component | Status |
|-----------|--------|
| `tests/calendar_view/` (24 tests) | Done — behavioral contract |
| `migrations/0140_usage_events.sql` | Done — applied |
| `api/calendar/` | **Missing** |
| `api/instrumentation/` | **Missing** |
| `api/index.py` mounts | **Missing** |
| Full suite | 301 passed, 24 errors (calendar_view only) |
