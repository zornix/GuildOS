# Deployment Guide — FraternityOS Attendance MVP

## Architecture

The app is deployed as **two separate Vercel projects** from the same repo:

| Layer    | Tech                | Vercel Project / Config       |
|----------|---------------------|-------------------------------|
| Frontend | Next.js 16 (React 19) | Vercel project with Root Directory = `fratos/` |
| Backend  | FastAPI (Python)    | Vercel project with Root Directory = repo root, config in `api/vercel.json` (copy to repo root) |
| Database | PostgreSQL          | Supabase (integrated via Vercel Marketplace) |
| Cron     | Vercel Cron         | `*/15 * * * *` → `/api/cron/process-fines` (backend project only) |

Backend routing (`api/vercel.json`):
- `/api/*` and `/c/*` → FastAPI serverless function (`api/index.py`)

The frontend calls the backend via `NEXT_PUBLIC_API_BASE` (the backend project's URL).

---

## Secrets & Environment Variables

### What Supabase ↔ Vercel Integration Auto-Provisions

When Supabase is connected through the Vercel Marketplace, these env vars are
**automatically injected** into your Vercel project (all environments):

| Auto-Provisioned Var              | Value |
|-----------------------------------|-------|
| `POSTGRES_URL`                    | Pooled connection string |
| `POSTGRES_URL_NON_POOLING`        | Direct connection string |
| `POSTGRES_USER`                   | `postgres` |
| `POSTGRES_HOST`                   | `db.<ref>.supabase.co` |
| `POSTGRES_PASSWORD`               | DB password |
| `POSTGRES_DATABASE`               | `postgres` |
| `SUPABASE_URL`                    | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY`       | Service role key (admin) |
| `SUPABASE_PUBLISHABLE_KEY`        | Public anon key |
| `SUPABASE_JWT_SECRET`             | Project JWT secret |
| `NEXT_PUBLIC_SUPABASE_URL`        | Same as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Same as publishable key |

### What You Must Add Manually in Vercel

The FastAPI backend config (`api/config.py`) uses slightly different names
than what the integration provisions. You must add these manually in
**Vercel → Project → Settings → Environment Variables**:

| Env Var              | Value / Source                                   | Required |
|----------------------|--------------------------------------------------|----------|
| `DATABASE_URL`       | Copy from auto-provisioned `POSTGRES_URL` or `POSTGRES_URL_NON_POOLING` | Yes |
| `SUPABASE_ANON_KEY`  | Copy from auto-provisioned `SUPABASE_PUBLISHABLE_KEY` | Yes |
| `JWT_SECRET`         | Generate a unique secret (`openssl rand -hex 32`) | **Yes — critical** |
| `FRONTEND_URL`       | Frontend project URL, e.g. `https://fratos.vercel.app` — used for CORS | Yes |
| `BASE_URL`           | **Backend** project URL, e.g. `https://fratos-api.vercel.app` — used for check-in links and the `/c/*` page's API calls | Yes |
| `CHECKIN_LINK_TTL_MINUTES` | `10` (default) or your preference            | No (defaults to 10) |

> **Security note:** `JWT_SECRET` must be a strong random string in production.
> Never reuse `local-dev-secret-key-change-in-prod`.

### Frontend Env Vars (fratos)

| Env Var                                        | Vercel (two-project deploy)          | Local Dev |
|------------------------------------------------|--------------------------------------|-----------|
| `NEXT_PUBLIC_API_BASE`                         | Backend project URL, e.g. `https://fratos-api.vercel.app` (required — frontend and backend are on different origins) | `http://127.0.0.1:8001` |
| `NEXT_PUBLIC_SUPABASE_URL`                     | Auto-provisioned | Set in `fratos/.env.local` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY` | Auto-provisioned as `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Set in `fratos/.env.local` |

---

## Local Development

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+
- `pip` and `npm`

### Quick Start

```bash
# From repo root:
bash deploy/local-dev.sh
```

This script:
1. Starts PostgreSQL via Docker Compose (port 5434)
2. Waits for DB readiness
3. Runs migrations
4. Installs Python and Node dependencies (if missing)
5. Starts the FastAPI backend on `:8001`
6. Starts the Next.js frontend on `:3000`

### Manual Steps (if you prefer)

```bash
# 1. Database
docker compose up -d
sleep 3
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos \
  python scripts/migrate_db.py

# 2. Backend
pip install -r requirements.txt
cp .env.example .env   # edit if needed
uvicorn api.index:app --reload --host 0.0.0.0 --port 8001

# 3. Frontend (separate terminal)
cd fratos
npm install
echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001' > .env.local
npm run dev
```

---

## Pre-Deployment Checklist

Run the preflight script before every deployment:

```bash
bash deploy/preflight.sh
```

It validates:

| Check | What it does |
|-------|-------------|
| Python imports | Verifies `api/index.py` loads without import errors |
| Frontend build | Runs `next build` to catch compile/type errors |
| Frontend lint | Runs ESLint |
| Env var validation | Checks all required vars are set (via `deploy/check-env.py`) |
| Health endpoint | Curls `/api/health` if backend is running locally |
| Migration state | Confirms migration files exist and are valid SQL |
| `vercel.json` | Validates JSON syntax |

---

## Cloud Deployment (Vercel)

### First-Time Setup

1. Install Vercel CLI: `npm i -g vercel`
2. Create **two** Vercel projects from the same repo:
   - **Backend:** Root Directory = repo root. Copy `api/vercel.json` to repo root (or use `vercel.json` already there minus the `@vercel/next` build).
   - **Frontend:** Root Directory = `fratos/`.
3. Connect Supabase via Vercel Marketplace on the backend project (Dashboard → Integrations → Supabase).
4. Add manual env vars on each project (see tables above). In particular:
   - Backend: set `BASE_URL` to the backend project's production URL.
   - Backend: set `FRONTEND_URL` to the frontend project's production URL.
   - Frontend: set `NEXT_PUBLIC_API_BASE` to the backend project's production URL.
5. Run migrations against Supabase:
   ```bash
   DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres" \
     python scripts/migrate_db.py
   ```

### Deploy

Deploy each project independently via the Vercel Dashboard (push-to-deploy) or CLI:

```bash
# Backend (from repo root):
vercel --prod

# Frontend (from fratos/):
cd fratos && vercel --prod
```

### Post-Deploy Verification

1. Hit `https://<backend-project>.vercel.app/api/health` — expect `{"status":"ok"}`
2. Open `https://<frontend-project>.vercel.app` — login page should load
3. Test the phone check-in flow: create event → open check-in → visit `https://<backend-project>.vercel.app/c/<code>`

---

## Smoke Test Checklist

After each deployment, verify:

- [ ] `GET /api/health` returns `{"status":"ok","version":"0.1.0"}`
- [ ] Officer can log in
- [ ] Members roster loads
- [ ] Create a new event
- [ ] Open check-in link on event
- [ ] Visit check-in link on phone, enter phone number, confirm attendance recorded
- [ ] Close check-in link
- [ ] Submit an excuse for an event
- [ ] Officer approves/denies excuse
- [ ] Fines list loads (or trigger via `/api/cron/process-fines`)
- [ ] Member standing page loads

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `500` on any `/api/*` route | Missing env var — check `DATABASE_URL` and `SUPABASE_*` in Vercel |
| Frontend shows "API returned non-JSON" | Backend not reachable — check `NEXT_PUBLIC_API_BASE` locally or Vercel routing |
| Check-in link 404 | `/c/*` route not hitting FastAPI — verify `vercel.json` routes |
| "JWT decode error" | `JWT_SECRET` mismatch between token issuance and validation |
| Migrations fail on Supabase | Password has special chars — URL-encode them in `DATABASE_URL` |
| Cron not firing | Vercel Cron only runs on production deployments, not previews |
