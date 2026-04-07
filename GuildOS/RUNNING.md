# Running FraternityOS Locally

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+

## Automated Start

```bash
bash deploy/local-dev.sh
```

This starts PostgreSQL (Docker), runs migrations, installs dependencies, and launches both backend (:8001) and frontend (:3000).

## Manual Start

### 1. Database

```bash
docker compose up -d
# Wait for Postgres to be ready, then:
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos \
  python scripts/migrate_db.py
```

### 2. Seed test data (optional)

```bash
DATABASE_URL=postgresql://fraternityos:localdev@localhost:5434/fraternityos \
  python -m scripts.seed
```

This creates a chapter, 8 members, 5 events, attendance records, excuses, and fines. The officer login is `jake@tke.org`.

### 3. Backend (terminal 1)

```bash
pip install -r requirements.txt
cp .env.example .env  # edit if needed
uvicorn api.index:app --reload --host 0.0.0.0 --port 8001
```

API docs: http://localhost:8001/api/docs

### 4. Frontend (terminal 2)

```bash
cd fratos
npm install
# fratos/.env.local should contain:
#   NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001
npm run dev
```

App: http://localhost:3000

## E2E Tests

```bash
cd fratos
npx playwright install chromium
npm run test:e2e
```

## Smoke Test Checklist

- [ ] Log in as `jake@tke.org` (officer)
- [ ] Members page loads with roster
- [ ] Create a new event (required, with fine)
- [ ] Open check-in link on event
- [ ] Visit `/c/<code>` on phone, enter phone `555111002` (Ryan)
- [ ] Verify attendance recorded on event detail
- [ ] Close check-in link
- [ ] Submit an excuse for an event (log in as member)
- [ ] Officer approves/denies excuse
- [ ] Process fines (button on past required event detail, or `/api/cron/process-fines`)
- [ ] Fines page shows fines, pay/waive works
- [ ] Standing page shows member standings
