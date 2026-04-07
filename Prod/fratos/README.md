# fratos (frontend)

Next.js UI for FraternityOS. Run the full stack from the **repository root** — see [../README.md](../README.md) (`bash deploy/local-dev.sh`).

For frontend-only dev (API must already be running on port 8001):

```bash
npm install
echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001' > .env.local
npm run dev
```

E2E: `npm run test:e2e` (install browsers once with `npx playwright install chromium`).
