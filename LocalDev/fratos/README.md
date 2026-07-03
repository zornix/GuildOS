# fratos (frontend)

Next.js UI for FraternityOS. Run the full stack from `LocalDev/` — see [../CLAUDE.md](../CLAUDE.md) (`npm run dev` or `npm run dev:docker`).

For frontend-only dev (API must already be running on port 8001):

```bash
npm install
echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001' > .env.local
npm run dev
```

Production default uses same-origin `/api` calls and Next rewrites (`BACKEND_URL`) to avoid browser CORS issues.
If you intentionally want direct cross-origin browser calls, set `NEXT_PUBLIC_USE_CROSS_ORIGIN_API=true`
alongside `NEXT_PUBLIC_API_BASE`.

### Resilience

- **Read requests** (`GET` list/detail flows in `lib/api-client.ts`): up to **3 attempts** with exponential backoff on network failures and HTTP **408 / 429 / 5xx**. Mutations (`POST` / `PUT` / `DELETE`) are **not** auto-retried.
- **UI:** Dashboard, Events, and Members show explicit **loading**, **error**, and **empty** states with a **Retry** action when fetches fail (so empty lists are not mistaken for a dead database).

Unit tests: `npm run test:unit` (Vitest).

E2E: `npm run test:e2e` (install browsers once with `npx playwright install chromium`).
