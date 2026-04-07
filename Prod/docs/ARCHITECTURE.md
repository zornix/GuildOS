# Architecture — FraternityOS Attendance MVP

Last updated: 2026-04-06

---

## System Overview

**Local demo**

```
┌──────────────────┐      HTTP (NEXT_PUBLIC_API_BASE)      ┌──────────────────┐
│  Next.js (fratos)│ ─────────────────────────────────────▶│  FastAPI (api/)  │
│  Port 3000       │                                      │  Port 8001       │
└──────────────────┘                                      └────────┬─────────┘
                                                                   │ psycopg2
                                                                   ▼
                                                        ┌──────────────────┐
                                                        │  PostgreSQL       │
                                                        │  (Docker / hosted)│
                                                        └──────────────────┘
```

### Layer responsibilities

| Layer | Tech | Role |
|-------|------|------|
| Frontend | Next.js 16, React 19 | UI shell, pages, forms |
| Backend API | FastAPI (Python) | Business logic, auth, CRUD, check-in validation, fine processing, cron endpoint |
| Database | PostgreSQL | Persistence via `DATABASE_URL` |

---

## Backend Structure

```
api/
  index.py              # App factory, CORS, router registration
  config.py             # Settings via pydantic-settings (.env)
  db.py                 # PostgresClient singleton (legacy `get_supabase` naming)
  dependencies.py       # Auth: get_current_user, require_officer
  postgres_client.py    # psycopg2-backed data access
  models/schemas.py     # Pydantic request/response models
  routes/
    auth.py             # /api/auth/* — login, me
    events.py           # /api/events/* — CRUD + check-in links
    attendance.py       # /api/attendance/* — check-in, roster, manual
    excuses.py          # /api/excuses/* — submit, list, review
    fines.py            # /api/fines/* — list, pay, waive, process, summary
    members.py          # /api/members/* — roster, role change
    checkin_page.py     # /c/{code} — HTML phone check-in page
    cron.py             # /api/cron/* — fine processing trigger
    standing.py         # /api/standing/* — member standings
  services/
    checkin_links.py    # Short link generation + validation
    fine_processor.py   # Auto-fine generation after events
```

### Data access

The app uses **`PostgresClient`** (`postgres_client.py`) with **psycopg2** and **`DATABASE_URL`**. There is no Supabase client SDK in the current dependency set; local and production both use a standard Postgres connection string.

---

## Frontend Structure

```
fratos/
  app/                          # Next.js App Router
    layout.tsx, page.tsx
  fraternity-os-frontend.tsx    # App shell: sidebar nav + page routing
  lib/
    api-client.ts               # Typed API client
    types.ts                    # TypeScript interfaces for entities
    theme.ts                    # Design tokens
  hooks/
    use-auth.tsx                # AuthProvider context, login/logout
    use-api.ts                  # Generic data-fetching hook
  components/
    ui/                         # Primitives: btn, card, badge, input, avatar, modal, toast, icon
    forms/                      # create-event, check-in, excuse
    countdown.tsx               # Check-in link timer
  views/
    dashboard.tsx, events.tsx, fines.tsx, members.tsx, standing.tsx
```

---

## Auth Flow

### Officer / member login (JWT)

1. User enters email → `POST /api/auth/login`
2. Backend verifies email exists in `members` (officer-only routes require `role=officer`)
3. Returns JWT (HS256) with `sub=member.id`
4. Frontend stores token in localStorage, attaches to API requests

### Phone check-in (no auth)

1. Officer opens check-in → generates 6-char short code with TTL
2. Member opens `/c/{code}` on phone → FastAPI serves HTML page
3. Member enters 10-digit phone → `POST /api/attendance/checkin/{code}/phone`
4. Backend validates link + looks up member by phone + chapter → records attendance

---

## Database Schema

7 tables. See `migrations/0001_initial_schema.sql` for full DDL.

| Table | Key columns | Notes |
|-------|-------------|-------|
| chapters | id, name, organization, school | Multi-tenancy root |
| members | id, chapter_id, email, phone, role, status | phone used for check-in |
| events | id, chapter_id, title, date, time, location, required, fine_amount | required events trigger fines |
| attendance | id, event_id, member_id, checked_in, method | unique(event_id, member_id) |
| excuses | id, event_id, member_id, reason, status | unique(event_id, member_id) |
| fines | id, event_id, member_id, chapter_id, amount, status | unpaid/paid/waived |
| checkin_links | id, event_id, short_code, expires_at, active | TTL-based expiry |

---

## Member Standing Rules

Simple explicit rules (in `routes/standing.py`):

- **good_standing**: no issues
- **warning**: 1 unpaid fine OR 1+ unexcused absence
- **delinquent**: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences

---

## Deployment

Run the FastAPI app and Next.js app behind your host’s process manager or serverless platform. Set **`DATABASE_URL`**, **`JWT_SECRET`**, **`FRONTEND_URL`** (CORS), and **`BASE_URL`** (absolute check-in URLs). A scheduled job or cron can call `GET /api/cron/process-fines` on your chosen interval.

**Local demo:** see [README.md](../README.md) and `deploy/local-dev.sh`.
