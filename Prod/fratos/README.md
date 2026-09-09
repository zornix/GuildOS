# Fratos (hosted GreekOS clone)

Vite + React UI cloned from `LocalDev/greekos`. This is the frontend the
FraternityOS Vercel project serves from `Prod/fratos`. It talks to the
FastAPI app in `Prod/api` over same-origin `/api`.

**Temporary:** production `DATABASE_URL` still points at the demo Supabase
project, same database `LocalDev/greekos` uses.

Active development stays in `LocalDev/greekos`. Copy changes here when they
should ship.

## Checks

```bash
npm test              # node:test via tsx — src/**/*.test.ts
npm run lint          # tsc --noEmit
npm run build         # vite build
```
