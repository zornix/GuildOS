# GreekOS

The product UI for GuildOS. Vite + React, talking to the FastAPI backend in
`LocalDev/api`. Vercel serves this app at `/` and the API at `/api`.

## Local

```bash
cd LocalDev && npm run dev
```

That migrates the **demo** Supabase database, starts FastAPI on `:8001`, and
this app on `:3000` (Vite proxies `/api` to the backend).

Sign in with a seeded officer (`jake@tke.org` / `demo-officer-pw`). In a local
Vite session you can also use **Local only: sign in as seeded officer** if
`DEV_AUTH_BYPASS=1` is set in `LocalDev/.env`. That bypass is 404 on Vercel.

## Checks

```bash
npm test              # node:test via tsx — src/**/*.test.ts
npm run lint          # tsc --noEmit
npm run build         # vite build
```

## What is not here

Bylaws Q&A, the NL-controller product tab, and a local mock-data fallback were
removed. Command console stays, gated on `nl_controller:execute`. There is no
self-serve chapter signup — see the chapter-creation API issue.
