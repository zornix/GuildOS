# Architecture — FraternityOS Attendance MVP

Last updated: 2026-04-05

---

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Vercel                             │
│                                                         │
│  ┌─────────────────┐       ┌──────────────────────┐    │
│  │  Next.js (React) │       │  FastAPI (Python)     │    │
│  │  fratos/         │──────▶│  api/                 │    │
│  │  Port 3000       │ fetch │  Port 8001            │    │
│  └─────────────────┘       └──────────┬─────────────┘    │
│                                       │                  │
└───────────────────────────────────────┼──────────────────┘
                                        │ supabase-py / psycopg2
                                        ▼
                              ┌──────────────────┐
                              │   PostgreSQL      │
                              │   (Supabase or    │
                              │    local Docker)  │
                              └──────────────────┘
```

### Layer responsibilities

| Layer | Tech | Role |
|-------|------|------|
| Frontend | Next.js 16, React 19 | UI shell, pages, forms |
| Backend API | FastAPI (Python) | Business logic, auth, CRUD, check-in validation, fine processing, cron |
| Database | PostgreSQL (Supabase or local) | Persistence |
| Hosting | Vercel | Serverless functions (FastAPI), Next.js, Cron |

---

## Backend Structure

```
api/
  index.py              # App factory, CORS, router registration
  config.py             # Settings via pydantic-settings (.env)
  db.py                 # DB client: Supabase or local PostgresClient
  dependencies.py       # Auth: get_current_user, require_officer
  postgres_client.py    # Supabase-compatible query builder for local Postgres
  models/schemas.py     # Pydantic request/response models
  routes/
    auth.py             # /api/auth/* — login, me, invite
    events.py           # /api/events/* — CRUD + check-in links
    attendance.py       # /api/attendance/* — check-in, roster, manual
    excuses.py          # /api/excuses/* — submit, list, review
    fines.py            # /api/fines/* — list, pay, waive, process, summary
    members.py          # /api/members/* — roster, role change
    checkin_page.py     # /c/{code} — HTML phone check-in page
    cron.py             # /api/cron/* — auto-fine processing
    standing.py         # /api/standing/* — member standings
  services/
    checkin_links.py    # Short link generation + validation
    fine_processor.py   # Auto-fine generation after events
```

### Dual DB mode

`db.py` supports two modes:
- **Supabase mode**: when `DATABASE_URL` is unset, uses `supabase-py` client
- **Local Postgres mode**: when `DATABASE_URL` is set, uses `postgres_client.py` — a Supabase-compatible query builder backed by psycopg2

This allows local development against Docker Postgres without Supabase.

---

## Frontend Structure

```
fratos/
  app/                          # Next.js App Router
    layout.tsx, page.tsx
  fraternity-os-frontend.tsx    # App shell: sidebar nav + page routing
  lib/
    api-client.ts               # Typed ApiClient class (centralized API layer)
    types.ts                    # TypeScript interfaces for all entities
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

### Officer login (JWT)

1. Officer enters email → `POST /api/auth/login`
2. Backend verifies email exists in `members` with `role=officer`
3. Returns JWT (HS256, 30-day expiry) with `sub=member.id`
4. Frontend stores token in localStorage, attaches to all requests

### Phone check-in (no auth)

1. Officer opens check-in → generates 6-char short code with TTL
2. Member opens `/c/{code}` on phone → FastAPI serves HTML page
3. Member enters 9-digit phone → `POST /api/attendance/checkin/{code}/phone`
4. Backend validates link + looks up member by phone + chapter → records attendance

---

## Database Schema

7 tables. See `migrations/0001_initial_schema.sql` for full DDL.

| Table | Key columns | Notes |
|-------|-------------|-------|
| chapters | id, name, organization, school | Multi-tenancy root |
| members | id, auth_id, chapter_id, email, phone, role, status | phone used for check-in |
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

`vercel.json` routes:
- `/api/*` and `/c/*` → FastAPI serverless function (`api/index.py`)
- Everything else → Next.js frontend (`fratos/`)

Cron: `GET /api/cron/process-fines` every 15 minutes (Vercel Cron, production only).

See [deploy/README.md](../deploy/README.md) for full deployment guide.
