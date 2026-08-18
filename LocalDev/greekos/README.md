# GreekOS prototype

A single-page React/Vite prototype of the GuildOS member-facing shell. It runs
against the **real** FastAPI backend in `LocalDev/api` — Vite proxies `/api` to
`http://localhost:8001` (see `vite.config.ts`), and `src/api.ts` is the only
place that talks to it.

## Prerequisites

- Node.js and Python (the same toolchain the rest of `LocalDev/` uses).
- The backend running on **:8001** against the **seeded demo database**
  (`DATABASE_URL` in `LocalDev/.env`). Swagger: <http://localhost:8001/api/docs>.
- **`DEV_AUTH_BYPASS=1` in `LocalDev/.env`** — the prototype has no login
  screen; it calls `POST /api/auth/dev-login`, which 404s unless the bypass is
  on. (The repo default is `0`.)

## Run

Two terminals:

```bash
cd LocalDev && npm run dev        # migrations + FastAPI on :8001 (also starts fratos on :3000)
cd LocalDev/greekos && npm run dev # this prototype on :3000
```

`LocalDev/npm run dev` also starts the `fratos` Next.js app on :3000, so either
stop that one or start the prototype with a free port (`npm run dev -- --port
3002`). Only the backend is required.

## Demo login

There is no login UI. On first load `src/api.ts` dev-logs-in as the seeded
officer **Jake Martinez — `jake@tke.org`** and caches the token in
`localStorage` under `g_token`. Everything you do in the app is written to the
demo database as Jake. Clear that key to force a fresh token.

## Checks

```bash
npm run lint          # tsc --noEmit
npm run build         # vite build
npx tsx src/selfcheck.ts   # adapter/contract self-check
```

## Demo-gated tabs

Three tabs are marked `DEMO` in the sidebar because no backend surface exists
for them yet — they run on client-local mock data and never write anything:

- **Bylaws & Conduct** (`rules`) — no bylaws Q&A backend.
- **Command Console** (`command`) — command *parsing* is frontend-local; the
  announcement branch is the one action that reaches the real API.
- **SMS / Push Outbox** (`outbox`) — the backend outbox has no read surface.

Every other tab reads and writes the live backend.
