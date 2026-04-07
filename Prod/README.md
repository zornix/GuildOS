# FraternityOS — Local demo

This repository is a **self-contained local demo** of FraternityOS: a small web app for a fraternity chapter to run **events, attendance, excuses, and fines** in one place. Officers manage the roster, create events, open check-in, review excuses, and see who is in good standing. Members sign in (or check in by phone at the door) and can submit excuses for required events.

The demo uses **Docker for PostgreSQL**, a **FastAPI** backend, and a **Next.js** frontend. Everything runs on your machine; no cloud account is required.

## Try these flows

**1. Officer runs a meeting check-in**

1. Start the stack (see below) and open [http://localhost:3000](http://localhost:3000).
2. Log in as **Jake** (`jake@tke.org`) — demo login is email only, no password.
3. Open **Events**, pick an event, and create or open a **check-in link** (time-limited URL/QR).
4. In another browser (or incognito), visit the check-in URL (`/c/<code>`), enter a member’s **10-digit phone** from the demo roster (e.g. Ryan: `5551110002`).
5. Back as Jake, confirm that member appears on the event **attendance** view.

**2. Member excuse and fines (officer + member)**

1. Log in as a **member** (e.g. `ryan@tke.org`) and submit an **excuse** for a required event.
2. Log in as **Jake**, find the excuse, and **approve or deny** it.
3. For past required events, use **process fines** (UI on the event or `GET /api/cron/process-fines` via API docs) so missed attendance becomes fines where rules apply.
4. On **Fines**, see balances; members can mark their own fines paid; officers can **waive**. On **Standing** (officers), see chapter standing summaries.

## Run it on your machine

**Prerequisites:** Docker (with Compose), Python 3.11+, Node.js 20+

**One command** (starts Postgres, migrates, seeds on first run, then API + UI):

```bash
bash deploy/local-dev.sh
```

Then:

- **App:** [http://localhost:3000](http://localhost:3000)
- **API docs:** [http://localhost:8001/api/docs](http://localhost:8001/api/docs)
- **Postgres:** `localhost:5434` (user `fraternityos`, password `localdev`, database `fraternityos`)

Stop everything with **Ctrl+C** in that terminal (the script tears down the dev servers it started; Postgres keeps running in Docker until you `docker compose down`).

### Manual setup (optional)

If you prefer separate terminals:

```bash
docker compose up -d
cp .env.example .env
python scripts/migrate_db.py
python -m scripts.seed
pip install -r requirements.txt
uvicorn api.index:app --reload --host 0.0.0.0 --port 8001
```

```bash
cd fratos
npm install
echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001' > .env.local
npm run dev
```

### Demo logins

| Name | Email | Role | Phone (check-in demo) |
|------|-------|------|------------------------|
| Jake Martinez | jake@tke.org | Officer | 5551110001 |
| Ryan Chen | ryan@tke.org | Member | 5551110002 |
| Tyler Brooks | tyler@tke.org | Member | 5551110003 |

Additional seeded members: `marcus@tke.org` … `noah@tke.org` (phones `5551110004`–`5551110008`). Use any member email to explore the member experience.

### E2E tests (optional)

```bash
cd fratos
npx playwright install chromium
npm run test:e2e
```

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI (Python) |
| Frontend | Next.js 16, React 19 |
| Database | PostgreSQL (Docker locally; same app code can use any Postgres URL in production) |

The backend talks to Postgres with **`DATABASE_URL`** (see [`.env.example`](.env.example)). Other useful settings: **`JWT_SECRET`**, **`FRONTEND_URL`** (CORS), **`BASE_URL`** (check-in links), **`CHECKIN_LINK_TTL_MINUTES`**.

## Architecture

### System overview (local demo)

```
┌──────────────────┐      HTTP (NEXT_PUBLIC_API_BASE)      ┌──────────────────┐
│  Next.js (fratos)│ ─────────────────────────────────────▶│  FastAPI (api/)  │
│  Port 3000       │                                      │  Port 8001       │
└──────────────────┘                                      └────────┬─────────┘
                                                                   │ psycopg2
                                                                   ▼
                                                        ┌──────────────────┐
                                                        │  PostgreSQL       │
                                                        │  (Docker :5434)   │
                                                        └──────────────────┘
```

| Layer | Role |
|-------|------|
| **Frontend** | UI shell, pages, forms; calls the API with JWT from `localStorage`. |
| **Backend API** | Auth, CRUD, check-in validation, fine processing, cron-style fine processing endpoint, HTML phone check-in page at `/c/{code}`. |
| **Database** | Chapters, members, events, attendance, excuses, fines, check-in links. |

### Backend layout

```
api/
  index.py              # App factory, CORS, router registration
  config.py             # Settings via pydantic-settings (.env)
  db.py                 # PostgresClient singleton (get_supabase naming is legacy)
  dependencies.py       # Auth: get_current_user, require_officer
  postgres_client.py    # Query helpers over psycopg2
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
    checkin_links.py    # Short code generation + validation
    fine_processor.py   # Auto-fine generation after events
```

### Frontend layout

```
fratos/
  app/                          # Next.js App Router (layout, page)
  fraternity-os-frontend.tsx    # App shell: sidebar nav + page routing
  lib/
    api-client.ts               # Typed API client
    types.ts                    # TypeScript entity shapes
    theme.ts                    # Design tokens
  hooks/
    use-auth.tsx                # AuthProvider, login/logout
    use-api.ts                  # Data-fetching hook
  components/
    ui/                         # Primitives (btn, card, input, …)
    forms/                      # create-event, check-in, excuse
  views/                        # dashboard, events, fines, members, standing
  e2e/                          # Playwright tests
```

### Auth

**Officer/member login (JWT)**

1. User enters email → `POST /api/auth/login`.
2. Backend checks the member exists (officers must have `role=officer` for full officer UI).
3. Response includes a JWT (HS256); frontend stores it and sends `Authorization: Bearer` on API calls.

**Phone check-in (no app login)**

1. Officer activates a check-in link → short code with TTL in `checkin_links`.
2. Member opens `/c/{code}` (HTML from FastAPI).
3. Member submits 10-digit phone → `POST /api/attendance/checkin/{code}/phone`.
4. Backend validates the link, resolves member by phone + chapter, records attendance.

### Database (summary)

Full DDL: [`migrations/0001_initial_schema.sql`](migrations/0001_initial_schema.sql).

| Table | Purpose |
|-------|---------|
| `chapters` | Tenant root |
| `members` | Roster, email, phone (check-in), `role`, `status` |
| `events` | Required flag and `fine_amount` drive fines |
| `attendance` | Per event/member, method, `checked_in` |
| `excuses` | Submit / pending / approved / denied |
| `fines` | Amount, `unpaid` / `paid` / `waived` |
| `checkin_links` | `short_code`, `expires_at`, `active` |

### Member standing (officers)

Rules live in `api/routes/standing.py`: **good_standing**, **warning** (e.g. one unpaid fine or unexcused absence patterns), **delinquent** (e.g. multiple unpaid fines or higher balances/absences).

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/FEATURES.md`](docs/FEATURES.md).

## Project layout

```
FraternityOS/
  api/                  # FastAPI app
  fratos/               # Next.js frontend
  migrations/           # SQL schema
  scripts/              # migrate_db.py, seed.py
  deploy/               # local-dev.sh
  docs/                 # Architecture, features, phone login
```

