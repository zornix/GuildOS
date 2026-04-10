# GuildOS / FraternityOS — Prod

## Purpose

**FraternityOS** is a chapter operations tool for Greek-letter organizations: events, attendance (including phone check-in via short links), excuses, fines, member roster, and simple standing rules. This folder is the production-shaped **FastAPI backend** plus the **Next.js (`fratos`)** web app that talks to it.

## High-level architecture

```
┌─────────────────────┐     HTTPS (CORS: FRONTEND_URL)     ┌─────────────────────┐
│  Next.js (`fratos`) │ ──────────────────────────────────▶│  FastAPI (`api/`)   │
│  Browser / Vercel   │   Authorization: Bearer <JWT>      │  Vercel / uvicorn   │
└─────────────────────┘                                     └──────────┬──────────┘
                                                                       │
                                                                       │ psycopg2
                                                                       ▼
                                                            ┌─────────────────────┐
                                                            │  PostgreSQL         │
                                                            │  (hosted / Docker)  │
                                                            └─────────────────────┘
```

- **Frontend** (`fratos/`): App Router UI, auth context, typed API client (`NEXT_PUBLIC_API_BASE` → backend).
- **Backend** (`api/`): REST API, JWT issuance on login (`/api/auth/login`), JWT validation on protected routes (`get_current_user`), business logic and cron hooks.
- **Data layer**: `PostgresClient` in `postgres_client.py` — a Supabase-py–shaped query builder over raw PostgreSQL (no Supabase JS SDK in the server path).

### Authentication

1. `POST /api/auth/login` loads the member by email (and `password_hash` only in that route for officer password checks).
2. Success returns an HS256 JWT with `sub` = member UUID; `get_current_user` decodes via `_LocalAuth` and loads the member row **without** selecting `password_hash`.
3. Officers can `POST /api/auth/set-password`; updates run by `user["id"]` from the dependency (no hash needed in the loaded profile).

### Required configuration

| Variable | Role |
|----------|------|
| `POSTGRES_URL_NON_POOLING` | PostgreSQL connection string for the API. |
| `SUPABASE_JWT_SECRET` | **Required, non-empty.** Used to sign login JWTs and to validate them in `PostgresClient` auth. Must match the JWT secret your project uses (e.g. Supabase **Project Settings → API → JWT Secret**). **Local dev:** set this in `.env` in the directory from which you run uvicorn (or export it); the process exits at import time if it is missing or whitespace-only. |
| `FRONTEND_URL` | CORS allow-origin for the Next app. |
| `BASE_URL` | Public API base for absolute check-in links in emails/pages. |
| `CRON_SECRET` | Optional bearer for `/api/cron/*` if used. |

---

## Directory map

### `api/` — FastAPI application

| File | Description |
|------|-------------|
| `index.py` | App factory: CORS, router mounts, `/api/health`. |
| `config.py` | `pydantic-settings` load from env/`.env`; **fails fast** if `SUPABASE_JWT_SECRET` is empty. |
| `db.py` | Singleton `get_supabase()` → `PostgresClient` (name kept for compatibility). |
| `dependencies.py` | `get_current_user` (Bearer JWT + active member lookup), `require_officer`. |
| `postgres_client.py` | psycopg2 pool, query builder, nested joins, `_LocalAuth.get_user` (JWT decode). |
| `models/schemas.py` | Pydantic request/response models. |
| `routes/auth.py` | Login (selects `password_hash` only here), `/me`, `/set-password`, `/invite`. |
| `routes/events.py` | Chapter events CRUD and check-in link metadata. |
| `routes/attendance.py` | Check-in flows (authenticated + short-code phone check-in). |
| `routes/excuses.py` | Excuse submit and officer review. |
| `routes/fines.py` | Fines list, pay, waive, processing triggers. |
| `routes/members.py` | Member listing for the chapter. |
| `routes/checkin_links.py` | API for creating/managing ephemeral check-in links. |
| `routes/checkin_page.py` | Serves `/c/{code}` HTML for phone check-in. |
| `routes/cron.py` | Secured cron endpoints (e.g. fine processing). |
| `routes/standing.py` | Member standing summaries. |
| `services/checkin_links.py` | Short code generation, TTL, URL building. |
| `services/fine_processor.py` | Automated fine generation after events. |

### `fratos/` — Next.js frontend

| Area | Description |
|------|-------------|
| `app/` | App Router entry: `layout.tsx`, `page.tsx`, global styles. |
| `fraternity-os-frontend.tsx` | Main shell: navigation and view switching. |
| `lib/api-client.ts` | Typed HTTP client to the FastAPI base URL. |
| `lib/types.ts`, `lib/theme.ts`, `lib/event-time.ts` | Types, tokens, time helpers. |
| `hooks/use-auth.tsx` | Auth state, login/logout, token storage. |
| `hooks/use-api.ts` | Data-fetching helper. |
| `components/` | UI primitives (`ui/`), forms, countdown for check-in windows. |
| `views/` | Feature screens: dashboard, events, fines, members, standing, active check-ins. |

### Other

| Path | Description |
|------|-------------|
| `migrations/` | SQL migrations (e.g. schema, `password_hash` on `members`). |
| `scripts/` | Operational scripts (`migrate_db.py`, `set_officer_password.py`, etc.). |
| `docs/` | Additional notes (`ARCHITECTURE.md`, `FEATURES.md`, `PHONE_LOGIN.md`). |
| `requirements.txt` | Python dependencies for the API. |

---

## Local API run

From the `Prod` directory (with `.env` containing at least `POSTGRES_URL_NON_POOLING` and `SUPABASE_JWT_SECRET`):

```bash
uvicorn api.index:app --reload --port 8001
```

See `fratos/README.md` for the frontend dev server and `docs/ARCHITECTURE.md` for a deeper walkthrough.
