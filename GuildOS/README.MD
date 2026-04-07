# FraternityOS — Chapter Attendance MVP

Attendance tracking, excuses, and fines for fraternity chapters.

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI (Python) |
| Frontend | Next.js 16 (React 19) |
| Database | PostgreSQL (Supabase or local Docker) |
| Hosting | Vercel (FastAPI serverless + Next.js) |

## Project Structure

```
ChapterAttendance/
  api/                  # FastAPI backend
    index.py            # App entrypoint
    config.py           # Settings (pydantic-settings)
    db.py               # DB client (Supabase or local Postgres)
    dependencies.py     # Auth: get_current_user, require_officer
    models/schemas.py   # Pydantic request/response models
    routes/             # Route handlers
    services/           # Business logic (checkin_links, fine_processor)
  fratos/               # Next.js frontend
    app/                # App Router (layout, page)
    lib/                # api-client, types, theme
    hooks/              # use-auth, use-api
    components/         # UI components, forms
    views/              # Page views (dashboard, events, fines, members, standing)
    e2e/                # Playwright E2E tests
  migrations/           # SQL migration files
  scripts/              # migrate_db.py, seed.py
  deploy/               # local-dev.sh, preflight.sh, vercel-deploy.sh
  deferred/             # Deferred features (delinquency, mocks, etc.)
```

## MVP Features

1. **Officer auth** — email login, JWT-based sessions
2. **Members roster** — list members, promote/demote roles
3. **Events CRUD** — create, list, detail, update, delete
4. **Check-in links** — officer opens/closes time-limited check-in
5. **Phone check-in** — member enters phone number on mobile, no login needed
6. **Attendance roster** — per-event attendance view with manual check-in
7. **Excuses** — submit, approve/deny, auto-removes fine on approval
8. **Fines** — auto-generated via cron or manual trigger, pay/waive
9. **Member standing** — good_standing / warning / delinquent

## API Endpoints

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/invite` |
| Events | `GET/POST /api/events`, `GET/PUT/DELETE /api/events/{id}`, `POST/DELETE /api/events/{id}/checkin-link` |
| Attendance | `POST /api/attendance/checkin/{code}`, `POST /api/attendance/checkin/{code}/phone`, `GET /api/attendance/event/{id}`, `POST /api/attendance/event/{id}/manual/{mid}` |
| Excuses | `POST /api/excuses/event/{id}`, `GET /api/excuses`, `PUT /api/excuses/{id}/review` |
| Fines | `GET /api/fines`, `POST /api/fines/{id}/pay`, `POST /api/fines/{id}/waive`, `POST /api/fines/process-event/{id}`, `GET /api/fines/summary` |
| Members | `GET /api/members`, `PUT /api/members/{id}/role` |
| Standing | `GET /api/standing` |
| Cron | `GET /api/cron/process-fines` |
| Check-in page | `GET /c/{code}` (HTML) |

## Quick Start (Local)

```bash
# One-command startup:
bash deploy/local-dev.sh

# Or manually:
docker compose up -d
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos python scripts/migrate_db.py
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos python -m scripts.seed
uvicorn api.index:app --reload --port 8001  # terminal 1
cd fratos && npm install && npm run dev     # terminal 2
```

Open http://localhost:3000. Log in as `jake@tke.org` (officer).

## Vercel Deployment

See [deploy/README.md](deploy/README.md) for full instructions.

```bash
bash deploy/vercel-deploy.sh          # preview
bash deploy/vercel-deploy.sh --prod   # production
```

## Environment Variables

See [.env.example](.env.example) for all variables. Key ones:

| Variable | Local | Production |
|----------|-------|------------|
| `DATABASE_URL` | `postgresql://fraternityos:localdev@localhost:5434/fraternityos` | Supabase connection string |
| `JWT_SECRET` | `local-dev-secret-key-change-in-prod` | Strong random secret |
| `FRONTEND_URL` | `http://localhost:3000` | Your Vercel domain |
| `BASE_URL` | `http://localhost:8001` | Your Vercel domain |
